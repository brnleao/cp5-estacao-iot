"""
mqtt_estacao.py — Cliente MQTT do contador de repetições
=========================================================
Faz a ponte entre o contador de visão (CP4) e a estação IoT (CP5):

  * ASSINA  {base}/status  -> sabe se a máquina foi liberada pelo RFID e para qual aluno
  * PUBLICA {base}/reps    -> contagem ao vivo a cada repetição
  * PUBLICA {base}/serie   -> resumo da série (aluno + volume de repetições) ao final
  * LWT     {base}/contador/online -> "offline" publicado pelo broker se o contador cair

Este módulo não depende de OpenCV/YOLO, então pode ser reutilizado e testado
sem câmera (veja tools/simulador.py).
"""

import json
import threading
import time
import uuid

import paho.mqtt.client as mqtt


class EstacaoMQTT:
    def __init__(self, broker, porta, topico_base, pausa_fim_serie_s=8.0, log=print):
        self.broker = broker
        self.porta = porta
        self.base = topico_base.rstrip("/")
        self.pausa_fim_serie_s = pausa_fim_serie_s
        self.log = log

        self.t_status = f"{self.base}/status"
        self.t_reps = f"{self.base}/reps"
        self.t_serie = f"{self.base}/serie"
        self.t_online = f"{self.base}/contador/online"

        # Estado compartilhado entre a thread de rede (callbacks) e o loop da câmera
        self._lock = threading.Lock()
        self.conectado = False
        self.liberada = False
        self.aluno = ""
        self.uid = ""
        self.sessao = ""
        self.serie_num = 1
        self.reps = 0
        self._inicio_serie = 0.0
        self._ultima_rep = 0.0

        client_id = f"contador-{uuid.uuid4().hex[:8]}"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.will_set(self.t_online, "offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)

    # -----------------------------------------------------------------
    # Conexão
    # -----------------------------------------------------------------
    def conectar(self):
        self.log(f"[MQTT] Conectando a {self.broker}:{self.porta} (base: {self.base})")
        self.client.connect_async(self.broker, self.porta, keepalive=30)
        self.client.loop_start()   # thread de rede em segundo plano

    def encerrar(self):
        with self._lock:
            self._fechar_serie_locked("manual")
        try:
            self.client.publish(self.t_online, "offline", qos=1, retain=True).wait_for_publish(2)
        except (RuntimeError, ValueError):
            pass   # já estava desconectado: o LWT cuida do "offline"
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self.log(f"[MQTT] Falha na conexão: {reason_code}")
            return
        self.conectado = True
        self.log("[MQTT] Conectado!")
        client.publish(self.t_online, "online", qos=1, retain=True)
        client.subscribe(self.t_status, qos=1)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.conectado = False
        self.log(f"[MQTT] Desconectado ({reason_code}). Reconectando...")

    # -----------------------------------------------------------------
    # Mensagens recebidas
    # -----------------------------------------------------------------
    def _on_message(self, client, userdata, msg):
        if msg.topic != self.t_status:
            return
        try:
            status = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.log(f"[MQTT] Payload inválido em {msg.topic}: {msg.payload!r}")
            return
        self._aplicar_status(status)

    def _aplicar_status(self, status):
        estado = status.get("estado")
        with self._lock:
            if estado == "ocupada":
                sessao = status.get("sessao", "")
                if self.liberada and sessao == self.sessao:
                    return   # mesma sessão (ex.: republicação após reconexão do ESP32)
                self._fechar_serie_locked("checkout")   # fecha série de uma sessão anterior
                self.liberada = True
                self.aluno = status.get("aluno", "")
                self.uid = status.get("uid", "")
                self.sessao = sessao
                self.serie_num = 1
                self.reps = 0
                self.log(f"[ESTACAO] Liberada para {self.aluno} (sessão {self.sessao})")
            elif estado == "livre":
                if self.liberada:
                    self._fechar_serie_locked("checkout")
                    self.log(f"[ESTACAO] Liberada pelo RFID — sessão de {self.aluno} encerrada")
                self.liberada = False
                self.aluno = self.uid = self.sessao = ""
                self.reps = 0

    # -----------------------------------------------------------------
    # API usada pelo contador
    # -----------------------------------------------------------------
    def registrar_rep(self):
        """Conta uma repetição. Retorna False se a máquina não está liberada."""
        with self._lock:
            if not self.liberada:
                return False
            agora = time.time()
            self.reps += 1
            if self.reps == 1:
                self._inicio_serie = agora
            self._ultima_rep = agora
            payload = {"sessao": self.sessao, "aluno": self.aluno,
                       "serie": self.serie_num, "reps": self.reps}
        self._publicar(self.t_reps, payload, qos=0)
        return True

    def verificar_pausa(self):
        """Fecha a série se o aluno ficou PAUSA_FIM_SERIE_S sem fazer repetições."""
        with self._lock:
            if self.reps > 0 and time.time() - self._ultima_rep >= self.pausa_fim_serie_s:
                self._fechar_serie_locked("pausa")

    def finalizar_serie(self):
        """Fecha a série manualmente (tecla 'f')."""
        with self._lock:
            self._fechar_serie_locked("manual")

    def zerar_serie(self):
        """Descarta a série atual sem publicar (tecla 'r')."""
        with self._lock:
            self.reps = 0

    def snapshot(self):
        with self._lock:
            return {"conectado": self.conectado, "liberada": self.liberada,
                    "aluno": self.aluno, "serie": self.serie_num, "reps": self.reps}

    # -----------------------------------------------------------------
    # Internos
    # -----------------------------------------------------------------
    def _fechar_serie_locked(self, motivo):
        if self.reps == 0:
            return
        payload = {
            "sessao": self.sessao,
            "aluno": self.aluno,
            "uid": self.uid,
            "serie": self.serie_num,
            "reps": self.reps,
            "duracao_s": round(self._ultima_rep - self._inicio_serie, 1),
            "motivo": motivo,
        }
        self._publicar(self.t_serie, payload, qos=1)   # dado de negócio: QoS 1
        self.log(f"[SERIE] {self.aluno} — série {self.serie_num}: {self.reps} reps ({motivo})")
        self.serie_num += 1
        self.reps = 0

    def _publicar(self, topico, payload, qos):
        texto = json.dumps(payload, ensure_ascii=False)
        info = self.client.publish(topico, texto, qos=qos)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            self.log(f"[MQTT] Falha ao publicar em {topico} (rc={info.rc})")
