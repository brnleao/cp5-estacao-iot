# Montagem do Hardware Físico (Hands-On)

Passo a passo para levar o protótipo do Wokwi para o ESP32 real. O circuito é o
mesmo; a diferença é que os botões que simulavam cartões são trocados pelo leitor
**MFRC522** de verdade.

## 1. Lista de materiais

| Qtd | Componente | Observação |
|---|---|---|
| 1 | ESP32 DevKit (30 ou 38 pinos) | Qualquer ESP32 com Wi-Fi |
| 1 | Módulo RFID **MFRC522** (RC522) + cartão/chaveiro | Normalmente vem 1 cartão e 1 tag |
| 1 | LED verde 5 mm | Máquina livre |
| 1 | LED vermelho 5 mm | Máquina ocupada |
| 2 | Resistor 220 Ω | Um por LED |
| 1 | Buzzer **passivo** | Ativo também funciona, mas com um tom só |
| 1 | Display LCD 16x2 com módulo I2C | *Opcional* — desligue com `USAR_LCD 0` |
| 1 | Protoboard + jumpers macho-macho/macho-fêmea | |
| 1 | Cabo USB de **dados** | Cabo só de carga não grava o ESP32 |

## 2. Ligações

### MFRC522 → ESP32 (SPI)

| MFRC522 | ESP32 | |
|---|---|---|
| SDA (SS) | GPIO **5** | `PINO_RFID_SS` |
| SCK | GPIO **18** | SPI padrão |
| MOSI | GPIO **23** | SPI padrão |
| MISO | GPIO **19** | SPI padrão |
| IRQ | — | não usado |
| GND | GND | |
| RST | GPIO **4** | `PINO_RFID_RST` |
| 3.3V | **3V3** | ⚠️ **Nunca ligue no 5V** — o MFRC522 é 3,3 V |

### LCD 16x2 I2C → ESP32 (opcional)

| LCD I2C | ESP32 |
|---|---|
| GND | GND |
| VCC | VIN / 5V |
| SDA | GPIO **21** |
| SCL | GPIO **22** |

### LEDs e buzzer

| Componente | Ligação |
|---|---|
| LED verde | GPIO **26** → resistor 220 Ω → perna longa (ânodo); perna curta (cátodo) → GND |
| LED vermelho | GPIO **27** → resistor 220 Ω → ânodo; cátodo → GND |
| Buzzer | (+) → GPIO **25**; (−) → GND |

```
              ESP32 DevKit
           ┌───────────────┐
  RC522 RST│ GPIO4   GPIO23│MOSI  RC522
  RC522 SDA│ GPIO5   GPIO22│SCL   LCD
  RC522 SCK│ GPIO18  GPIO21│SDA   LCD
  RC522 MISO GPIO19  GPIO25│(+)   Buzzer
           │         GPIO26│──220Ω──▶|── GND  LED verde
  RC522 3.3│ 3V3     GPIO27│──220Ω──▶|── GND  LED vermelho
  LCD VCC  │ VIN       GND │GND comum (RC522, LCD, LEDs, buzzer)
           └───────────────┘
```

> Dica: monte e teste **uma parte de cada vez** (LEDs → RFID → LCD). Fica muito mais
> fácil achar um fio errado.

## 3. Preparar o Arduino IDE

1. Instale o [Arduino IDE 2](https://www.arduino.cc/en/software).
2. Em **Arquivo → Preferências → URLs adicionais**, adicione:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. Em **Ferramentas → Placa → Gerenciador de placas**, instale **esp32 (Espressif Systems)**.
4. Em **Gerenciador de bibliotecas**, instale:
   - **PubSubClient** (Nick O'Leary)
   - **ArduinoJson** (Benoit Blanchon) — versão 7
   - **MFRC522** (GithubCommunity / miguelbalboa)
   - **LiquidCrystal I2C** (Frank de Brabander)
5. Abra a pasta `firmware/estacao_esp32/` (o arquivo `estacao_esp32.ino`).

## 4. Configurar o firmware (`config.h`)

```cpp
#define SIMULAR_RFID 0                    // usa o MFRC522 real
#define USAR_LCD     1                    // 0 se não tiver o display

#define WIFI_SSID     "NOME_DA_SUA_REDE"  // rede 2,4 GHz
#define WIFI_PASSWORD "SENHA_DA_SUA_REDE"

#define TOPICO_BASE "fiap/cp5/SEU_GRUPO/estacao01"
```

> ⚠️ O ESP32 **só conecta em redes 2,4 GHz** e não suporta redes corporativas com
> login (WPA2-Enterprise / portal cativo). Em sala, o mais garantido é usar o
> **roteador do celular** (hotspot 2,4 GHz).

## 5. Gravar e cadastrar os cartões

1. Selecione **Ferramentas → Placa → ESP32 Dev Module** e a porta COM correta.
2. Clique em **Carregar**. (Se travar em `Connecting...`, segure o botão **BOOT** do ESP32.)
3. Abra o **Serial Monitor** em **115200 baud**. Você deve ver:
   ```
   [RFID] MFRC522 iniciado. Firmware Version: 0x92 = v2.0
   [WiFi] Conectado! IP: 192.168.x.x
   [MQTT] Conectado!
   ```
4. Aproxime cada cartão do leitor. Como ainda não estão cadastrados, aparece:
   ```
   [RFID] UID lido: 3A7F9C21 (nao cadastrado)
   ```
5. Copie os UIDs para a tabela `ALUNOS_CADASTRADOS` em `config.h`:
   ```cpp
   static const Aluno ALUNOS_CADASTRADOS[] = {
     { "3A7F9C21", "Ana Souza"  },
     { "B4120A7E", "Bruno Lima" },
   };
   ```
6. Grave de novo. Agora o cartão libera a máquina (LED vermelho acende, dashboard fica vermelho).

## 6. Teste final antes da apresentação

- [ ] LED verde aceso com a máquina livre
- [ ] Cartão cadastrado → bip duplo, LED vermelho, dashboard **OCUPADA** com o nome
- [ ] Cartão desconhecido → bip longo, LED vermelho pisca, evento **NEGADO** no dashboard
- [ ] Contador (`visao/`) mostra **LIBERADA: nome** e conta as repetições
- [ ] Ao parar por 8 s a série aparece no histórico do dashboard e no LCD
- [ ] Mesmo cartão de novo → check-out, LED verde, dashboard **LIVRE**
- [ ] Tirar o ESP32 da tomada → em até ~30 s o dashboard mostra **OFFLINE** (LWT: keepalive de 15 s × 1,5)

## 7. Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `Firmware Version: 0x0` ou `0xFF` | Fiação do SPI ou alimentação | Confira SDA=5, RST=4 e se está no **3V3** |
| Cartão não é lido | Distância / módulo mal soldado | Encoste o cartão na antena; ressolde os pinos do módulo |
| LCD acende mas não mostra texto | Contraste | Gire o potenciômetro azul atrás do módulo I2C |
| LCD totalmente em branco | Endereço I2C diferente | Troque `LCD_ENDERECO` para `0x3F` |
| Fica em `Conectando WiFi....` | Rede 5 GHz, senha ou rede com login | Use hotspot 2,4 GHz do celular |
| `[MQTT] Falhou (rc=-2)` | Porta 1883 bloqueada na rede | Use hotspot do celular |
| Dashboard não recebe nada | Tópico base diferente | O `TOPICO_BASE` deve ser **idêntico** nos 3 lugares |
