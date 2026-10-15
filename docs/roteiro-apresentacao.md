# Roteiro da Apresentação (Hands-On)

Duração sugerida: **5 a 7 minutos** de demonstração + perguntas.

## Antes da aula (checklist)

- [ ] Celular com hotspot 2,4 GHz ligado (ESP32 e notebook na mesma rede não é obrigatório, mas evita bloqueio da porta 1883)
- [ ] ESP32 ligado, Serial Monitor aberto mostrando `[MQTT] Conectado!`
- [ ] Contador rodando: `python visao/cp5_contador_mqtt.py`
- [ ] Dashboard aberto em tela cheia (de preferência também no celular, via GitHub Pages)
- [ ] Terminal extra com `python tools/simulador.py monitor` para mostrar o tráfego MQTT
- [ ] **Plano B** pronto: se a câmera falhar, `python tools/simulador.py contador`; se o hardware falhar, o mesmo firmware rodando no Wokwi

## Demonstração passo a passo

| # | Ação | O que mostrar / falar |
|---|---|---|
| 1 | Mostrar o dashboard **VERDE** e as pílulas *ESP32 online / Contador online* | "Os três clientes estão conectados ao broker. O status chegou na hora porque é uma mensagem **retida**." |
| 2 | Passar um cartão **não cadastrado** | Bip longo + LED pisca. No dashboard aparece **NEGADO** com o UID. "Validação de acesso acontece no ESP32, e o evento é publicado em `/acesso`." |
| 3 | Passar o cartão **cadastrado** | LED vermelho, dashboard fica **VERMELHO** com o nome. No HUD do contador aparece **LIBERADA: nome**. |
| 4 | Fazer roscas com o "equipamento" (celular) na mão | O número no dashboard sobe a cada repetição (tópico `/reps`), e o LCD do ESP32 também mostra — prova de que o ESP32 também **assina** tópicos. |
| 5 | Mostrar que **sem RFID não conta**: fazer check-out, tentar treinar | Contador ignora o movimento. "A contagem só é habilitada pelo status vindo do RFID." |
| 6 | Liberar de novo, fazer uma série e **parar 8 segundos** | A série aparece no histórico com **nome + repetições** (tópico `/serie`, QoS 1). |
| 7 | Passar o mesmo cartão (check-out) | Dashboard volta para **VERDE**. Se havia série aberta, ela é fechada com motivo *check-out*. |
| 8 | (Opcional) Desligar o ESP32 da tomada | Em ~30 s o card fica **OFFLINE**: é o **LWT** publicado pelo próprio broker. |

## Explicação técnica (pontos-chave)

1. **Publish/Subscribe**: ninguém fala diretamente com ninguém. ESP32, contador e
   dashboard só conhecem o broker e os tópicos → dá para adicionar novos consumidores
   (ex.: um app, um banco de dados) sem mexer no ESP32.
2. **Divisão de responsabilidades**: ESP32 = acesso e estado da máquina; Python = visão
   computacional (pesado demais para o ESP32); navegador = visualização.
3. **Tópicos hierárquicos** `fiap/cp5/grupo/estacao01/...` → o dashboard assina
   `estacao01/#` (curinga) e recebe tudo de uma estação; com `+` daria para monitorar
   várias estações.
4. **Sessão**: cada check-in gera um ID de sessão. Mensagens de repetição de uma sessão
   antiga são descartadas pelo ESP32 e pelo dashboard.
5. **Dashboard sem back-end**: o navegador conecta direto no broker via **WebSocket
   seguro (WSS, porta 8884)**, porque navegadores não abrem conexões TCP puras (1883).

## Perguntas prováveis e respostas

**Por que MQTT e não HTTP?**
MQTT mantém uma conexão aberta e o broker *empurra* a mensagem na hora (sem polling),
o cabeçalho é mínimo (2 bytes) e tem recursos pensados para IoT: QoS, mensagens retidas,
LWT e reconexão. HTTP exigiria que o dashboard ficasse perguntando o estado a cada segundo.

**Qual a diferença entre QoS 0, 1 e 2?**
0 = no máximo uma vez (sem confirmação); 1 = pelo menos uma vez (com PUBACK, pode
duplicar); 2 = exatamente uma vez (handshake de 4 etapas). Usamos QoS 0 para a contagem
ao vivo (se perder uma, a próxima corrige) e QoS 1 para a série (dado importante). O
dashboard trata duplicatas pela chave `sessao + serie`.

**O que é mensagem retida?**
O broker guarda a última mensagem do tópico e entrega para quem se inscrever depois.
Por isso o dashboard já abre mostrando se a máquina está livre ou ocupada.

**O que é LWT?**
*Last Will and Testament*: na conexão o cliente deixa uma mensagem com o broker. Se ele
cair sem se despedir (queda de energia, Wi-Fi), o broker publica essa mensagem
(`offline`) em nome dele.

**E se o Wi-Fi cair no meio da sessão?**
O ESP32 continua controlando o acesso localmente (LEDs/buzzer) e tenta reconectar a
cada 3 s; ao voltar, republica o status atual (retido). O contador também reconecta
sozinho (paho `reconnect_delay_set`).

**E se o aluno esquecer de fazer check-out?**
Depois de 3 min sem repetições (`SESSAO_TIMEOUT_MS`) o ESP32 libera a máquina e publica
o evento `timeout`.

**O sistema é seguro?**
Para a demonstração usamos um broker público sem autenticação, então qualquer pessoa que
souber o tópico pode ler ou publicar. Mitigações já feitas: tópico com prefixo do grupo e
o dashboard nunca injeta HTML vindo do broker (usa `textContent`). Em produção:
broker próprio com **usuário/senha, TLS (porta 8883) e ACL por tópico**, e o UID do cartão
não deveria trafegar em texto aberto.

**Por que o celular representa o equipamento?**
O YOLO pré-treinado no COCO não tem a classe "halter", mas tem "cell phone" (classe 67).
Mantivemos a regra do CP4: só conta se o equipamento estiver no frame.
