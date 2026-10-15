"""
simulador.py — Ferramentas de teste da estação IoT (sem câmera e/ou sem hardware)
==================================================================================

  python tools/simulador.py monitor
      Assina {base}/# e imprime tudo que passa pelo broker. Ótimo para depurar
      e para mostrar o tráfego MQTT durante a apresentação.

  python tools/simulador.py contador
      Substitui o contador de visão: quando o ESP32 (Wokwi) libera a máquina,
      gera repetições automaticamente. Usa o MESMO módulo MQTT do contador real
      (visao/mqtt_estacao.py). Útil para testar Wokwi + dashboard sem webcam.

  python tools/simulador.py demo
      Simula TODO o sistema (ESP32 + contador) com um roteiro fixo.
      Útil para testar o dashboard sem nada ligado.

Requer: pip install paho-mqtt
"""

import argparse
import json
import os
import random
import sys
import time
import uuid

import paho.mqtt.client as mqtt

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "visao"))
import config as cfg                     # noqa: E402
from mqtt_estacao import EstacaoMQTT     # noqa: E402


def novo_cliente(prefixo):
    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                       client_id=f"{prefixo}-{uuid.uuid4().hex[:6]}")


# ---------------------------------------------------------------------------
# monitor
# ---------------------------------------------------------------------------
def cmd_monitor(args):
    cli = novo_cliente("monitor")

    def on_connect(c, u, f, rc, p):
        print(f"[monitor] conectado a {args.broker} — assinando {args.base}/#\n")
        c.subscribe(f"{args.base}/#", qos=1)

    def on_message(c, u, msg):
        topico = msg.topic[len(args.base) + 1:]
        retido = " (retido)" if msg.retain else ""
        print(f"{time.strftime('%H:%M:%S')}  {topico:<16} {msg.payload.decode(errors='replace')}{retido}")

    cli.on_connect = on_connect
    cli.on_message = on_message
    cli.connect(args.broker, args.porta, 30)
    try:
        cli.loop_forever()
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------------------
# contador (substitui a câmera)
# ---------------------------------------------------------------------------
def cmd_contador(args):
    est = EstacaoMQTT(args.broker, args.porta, args.base, pausa_fim_serie_s=args.pausa)
    est.conectar()
    print(f"[contador-sim] aguardando o RFID liberar a máquina... "
          f"(séries de {args.min_reps}-{args.max_reps} reps, Ctrl+C para sair)")
    serie_vista, alvo, proxima = None, 0, 0.0
    try:
        while True:
            s = est.snapshot()
            agora = time.time()
            if s["liberada"]:
                if s["serie"] != serie_vista:
                    # nova sessão ou a série anterior foi fechada pela pausa: sorteia a próxima
                    serie_vista = s["serie"]
                    alvo = random.randint(args.min_reps, args.max_reps)
                    proxima = agora + 2
                if s["reps"] < alvo and agora >= proxima:
                    est.registrar_rep()
                    print(f"  {s['aluno']} — série {s['serie']}: rep {s['reps'] + 1}/{alvo}")
                    proxima = agora + args.intervalo
            else:
                serie_vista = None
            est.verificar_pausa()
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        est.encerrar()


# ---------------------------------------------------------------------------
# demo (simula ESP32 + contador)
# ---------------------------------------------------------------------------
def cmd_demo(args):
    cli = novo_cliente("demo")
    cli.connect(args.broker, args.porta, 30)
    cli.loop_start()
    b = args.base
    rapido = args.rapido

    def pub(topico, payload, retain=False, qos=1):
        texto = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        cli.publish(f"{b}/{topico}", texto, qos=qos, retain=retain).wait_for_publish()
        print(f"  -> {topico:<14} {texto}")

    def espera(s):
        time.sleep(s * (0.15 if rapido else 1))

    def sessao(aluno, uid, series):
        sid = f"demo-{uuid.uuid4().hex[:4]}"
        pub("status", {"estado": "ocupada", "estacao": "estacao01",
                       "aluno": aluno, "uid": uid, "sessao": sid}, retain=True)
        pub("acesso", {"uid": uid, "aluno": aluno, "resultado": "liberado"})
        espera(2)
        for n, total in enumerate(series, start=1):
            for r in range(1, total + 1):
                pub("reps", {"sessao": sid, "aluno": aluno, "serie": n, "reps": r}, qos=0)
                espera(1)
            espera(3)
            pub("serie", {"sessao": sid, "aluno": aluno, "uid": uid, "serie": n,
                          "reps": total, "duracao_s": float(total - 1), "motivo": "pausa"})
            espera(3)
        pub("acesso", {"uid": uid, "aluno": aluno, "resultado": "encerrado"})
        pub("status", {"estado": "livre", "estacao": "estacao01"}, retain=True)
        espera(3)

    print("[demo] simulando ESP32 + contador. Abra o dashboard!\n")
    pub("esp32/online", "online", retain=True, qos=0)
    pub("contador/online", "online", retain=True)
    pub("status", {"estado": "livre", "estacao": "estacao01"}, retain=True)
    espera(3)
    pub("acesso", {"uid": "DEADBEEF", "aluno": "", "resultado": "negado"})
    espera(2)
    sessao("Ana Souza", "A1B2C3D4", [10, 8])
    sessao("Bruno Lima", "B5C6D7E8", [12])
    print("\n[demo] fim.")
    cli.loop_stop()
    cli.disconnect()


# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", default=cfg.MQTT_BROKER)
    p.add_argument("--porta", type=int, default=cfg.MQTT_PORTA)
    p.add_argument("--base", default=cfg.TOPICO_BASE)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("monitor", help="mostra todo o tráfego MQTT da estação")

    pc = sub.add_parser("contador", help="gera repetições quando o RFID libera a máquina")
    pc.add_argument("--intervalo", type=float, default=1.5, help="segundos entre repetições")
    pc.add_argument("--pausa", type=float, default=cfg.PAUSA_FIM_SERIE_S)
    pc.add_argument("--min-reps", type=int, default=6)
    pc.add_argument("--max-reps", type=int, default=12)

    pd = sub.add_parser("demo", help="simula ESP32 + contador com um roteiro fixo")
    pd.add_argument("--rapido", action="store_true", help="executa o roteiro ~7x mais rápido")

    args = p.parse_args()
    {"monitor": cmd_monitor, "contador": cmd_contador, "demo": cmd_demo}[args.cmd](args)


if __name__ == "__main__":
    main()
