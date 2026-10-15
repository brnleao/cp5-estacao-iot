"""
CP5 - Contador de Rosca Bíceps conectado via MQTT
==================================================
Evolução do CP4 (YOLO + MediaPipe Tasks API) para a estação IoT:

- YOLO (COCO) detecta o equipamento (classe 67 = "cell phone")
- MediaPipe Pose Landmarker rastreia ombro, cotovelo e punho
- NOVO: só conta repetições quando a máquina foi LIBERADA pelo RFID do ESP32
        (assina o tópico {base}/status)
- NOVO: publica a contagem ao vivo em {base}/reps
- NOVO: ao final da série publica nome do aluno + volume de repetições em {base}/serie
        A série termina por: pausa sem repetições | check-out no RFID | tecla 'f'

Uma repetição continua exigindo:
    (a) equipamento presente no frame
    (b) ciclo completo: extensão -> flexão -> extensão

Como rodar:
    pip install -r requirements.txt
    python cp5_contador_mqtt.py                 # usa os valores de config.py
    python cp5_contador_mqtt.py --base fiap/cp5/meugrupo/estacao01 --cam 1

Teclas:
    q -> sair            f -> finalizar série agora (publica)
    r -> zerar série     b -> alternar braço (direito/esquerdo)
"""

import argparse
import os
import time
import urllib.request
from collections import deque

import cv2
import numpy as np
from ultralytics import YOLO

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

import config as cfg
from mqtt_estacao import EstacaoMQTT

# Índices dos landmarks
NOSE, L_SHO, R_SHO = 0, 11, 12
L_ELB, R_ELB = 13, 14
L_WRI, R_WRI = 15, 16
L_HIP, R_HIP = 23, 24
L_KNE, R_KNE = 25, 26
L_ANK, R_ANK = 27, 28

POSE_CONNECTIONS = [
    (L_SHO, R_SHO), (L_SHO, L_ELB), (L_ELB, L_WRI),
    (R_SHO, R_ELB), (R_ELB, R_WRI),
    (L_SHO, L_HIP), (R_SHO, R_HIP), (L_HIP, R_HIP),
    (L_HIP, L_KNE), (L_KNE, L_ANK),
    (R_HIP, R_KNE), (R_KNE, R_ANK),
]

VERDE = (0, 220, 0)
VERMELHO = (0, 0, 230)
LARANJA = (0, 165, 255)
CINZA = (180, 180, 180)
BRANCO = (255, 255, 255)


# =========================================================
# UTILIDADES (iguais ao CP4)
# =========================================================
def ensure_model():
    if not os.path.exists(cfg.MODEL_PATH):
        print("Baixando modelo Pose Landmarker (~5 MB)...")
        urllib.request.urlretrieve(cfg.MODEL_URL, cfg.MODEL_PATH)
        print("Modelo baixado.")


def calc_angle(a, b, c):
    """Ângulo (graus) no ponto b, formado por a-b-c."""
    a, b, c = np.array(a), np.array(b), np.array(c)
    ba, bc = a - b, c - b
    cos = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


def draw_pose(frame, landmarks, w, h):
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    for a, b in POSE_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], BRANCO, 2)
    for (x, y) in pts:
        cv2.circle(frame, (x, y), 4, (0, 200, 255), -1)


def draw_panel(frame, est, stage, phone_present, arm):
    """HUD: equipamento + estado da estação (RFID/MQTT) + repetições."""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 145), (25, 25, 25), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    # Linha 1: estação (vem do RFID via MQTT)
    if not est["conectado"]:
        txt, cor = "MQTT desconectado", LARANJA
    elif est["liberada"]:
        txt, cor = f"LIBERADA: {est['aluno']}", VERMELHO   # vermelho = máquina ocupada
    else:
        txt, cor = "MAQUINA LIVRE - passe o cartao RFID", VERDE
    cv2.circle(frame, (25, 30), 10, cor, -1)
    cv2.putText(frame, txt, (45, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.7, cor, 2)

    # Linha 2: equipamento (YOLO)
    eq_txt = "Equipamento detectado" if phone_present else "Aguardando equipamento"
    eq_cor = VERDE if phone_present else LARANJA
    cv2.circle(frame, (25, 65), 7, eq_cor, -1)
    cv2.putText(frame, eq_txt, (45, 71), cv2.FONT_HERSHEY_SIMPLEX, 0.55, eq_cor, 2)

    # Linha 3: contagem
    cv2.putText(frame, f"REPS: {est['reps']}", (25, 125),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, BRANCO, 3)
    cv2.putText(frame, f"Serie: {est['serie']}", (240, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, CINZA, 2)
    stage_txt = stage.upper() if stage else "---"
    cv2.putText(frame, f"Estagio: {stage_txt}  Braco: {arm}", (240, 128),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, CINZA, 2)


def parse_args():
    p = argparse.ArgumentParser(description="Contador de rosca bíceps (CP4) conectado via MQTT (CP5)")
    p.add_argument("--broker", default=cfg.MQTT_BROKER)
    p.add_argument("--porta", type=int, default=cfg.MQTT_PORTA)
    p.add_argument("--base", default=cfg.TOPICO_BASE, help="prefixo dos tópicos MQTT")
    p.add_argument("--cam", type=int, default=cfg.CAM_INDEX, help="índice da webcam")
    p.add_argument("--pausa", type=float, default=cfg.PAUSA_FIM_SERIE_S,
                   help="segundos sem repetição para encerrar a série")
    return p.parse_args()


# =========================================================
# PROGRAMA PRINCIPAL
# =========================================================
def main():
    args = parse_args()

    estacao = EstacaoMQTT(args.broker, args.porta, args.base, pausa_fim_serie_s=args.pausa)
    estacao.conectar()

    ensure_model()
    print("Carregando YOLOv8n (download automático na 1ª execução)...")
    yolo = YOLO("yolov8n.pt")

    print("Carregando MediaPipe Pose Landmarker (Tasks API)...")
    options = mp_vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=cfg.MODEL_PATH),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = mp_vision.PoseLandmarker.create_from_options(options)

    cap = cv2.VideoCapture(args.cam)
    if not cap.isOpened():
        estacao.encerrar()
        raise RuntimeError("Não consegui abrir a webcam. Verifique --cam.")

    stage = "down"
    arm = cfg.DEFAULT_ARM
    phone_seen_buffer = deque(maxlen=cfg.PHONE_PERSISTENCE)
    t0 = time.time()

    print("Rodando. Teclas: [q]=sair  [f]=finalizar série  [r]=zerar  [b]=trocar braço")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]

            liberada = estacao.snapshot()["liberada"]
            if not liberada:
                stage = "down"   # sem RFID liberado a máquina de estados fica parada

            # ---------- YOLO: equipamento ----------
            yolo_res = yolo(frame, verbose=False, conf=cfg.YOLO_CONF)[0]
            phone_boxes = []
            for box in yolo_res.boxes:
                if int(box.cls[0]) == cfg.PHONE_CLASS_ID:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    phone_boxes.append((x1, y1, x2, y2, float(box.conf[0])))

            phone_seen_buffer.append(len(phone_boxes) > 0)
            phone_present = any(phone_seen_buffer)

            for (x1, y1, x2, y2, conf) in phone_boxes:
                cv2.rectangle(frame, (x1, y1), (x2, y2), VERDE, 2)
                cv2.putText(frame, f"equipamento {conf:.2f}", (x1, y1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, VERDE, 2)

            # ---------- MediaPipe: pose ----------
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts_ms = int((time.time() - t0) * 1000)
            result = landmarker.detect_for_video(mp_image, ts_ms)

            if result.pose_landmarks:
                lms = result.pose_landmarks[0]
                sh, el, wr = (R_SHO, R_ELB, R_WRI) if arm == "right" else (L_SHO, L_ELB, L_WRI)

                vis_ok = min(lms[sh].visibility, lms[el].visibility, lms[wr].visibility) > 0.5
                if vis_ok:
                    p_sh = (lms[sh].x * w, lms[sh].y * h)
                    p_el = (lms[el].x * w, lms[el].y * h)
                    p_wr = (lms[wr].x * w, lms[wr].y * h)
                    angle = calc_angle(p_sh, p_el, p_wr)

                    # Máquina de estados — só progride com RFID liberado E equipamento presente
                    if liberada and phone_present:
                        if angle > cfg.ANGLE_EXTENDED_MIN:
                            if stage == "up":
                                estacao.registrar_rep()   # conta + publica {base}/reps
                            stage = "down"
                        elif angle < cfg.ANGLE_FLEXED_MAX and stage == "down":
                            stage = "up"

                    cv2.putText(frame, f"{int(angle)}",
                                (int(p_el[0]) + 10, int(p_el[1]) - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                draw_pose(frame, lms, w, h)

            # Encerra a série se o aluno parou de treinar
            estacao.verificar_pausa()

            # ---------- HUD ----------
            draw_panel(frame, estacao.snapshot(), stage, phone_present, arm)
            cv2.imshow("CP5 - Estacao IoT (YOLO + MediaPipe + MQTT)", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("f"):
                estacao.finalizar_serie()
            elif key == ord("r"):
                estacao.zerar_serie()
                stage = "down"
            elif key == ord("b"):
                arm = "left" if arm == "right" else "right"
                estacao.zerar_serie()
                stage = "down"
    finally:
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()
        estacao.encerrar()


if __name__ == "__main__":
    main()
