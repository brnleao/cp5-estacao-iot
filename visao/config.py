"""
Configurações do contador de repetições (CP4) integrado ao MQTT (CP5).
Todos os valores podem ser sobrescritos por argumentos de linha de comando
(veja `python cp5_contador_mqtt.py --help`).
"""

# =========================================================
# MQTT — deve bater com firmware/estacao_esp32/config.h e dashboard/config.js
# =========================================================
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORTA = 1883
TOPICO_BASE = "fiap/cp5/ronaldos-fc/estacao01"

# Série é encerrada automaticamente após este tempo sem nova repetição (s)
PAUSA_FIM_SERIE_S = 8.0

# =========================================================
# VISÃO COMPUTACIONAL (mesmos valores do CP4)
# =========================================================
CAM_INDEX = 0
PHONE_CLASS_ID = 67          # COCO: "cell phone" — representa o equipamento
YOLO_CONF = 0.35
PHONE_PERSISTENCE = 30       # ~1 s a 30 fps — tolera piscadas do YOLO
ANGLE_FLEXED_MAX = 55
ANGLE_EXTENDED_MIN = 155
DEFAULT_ARM = "right"

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task")
MODEL_PATH = "pose_landmarker_lite.task"
