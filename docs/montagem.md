# Montagem do Hardware Físico (Hands-On)

Guia passo a passo para montar a estação de treino com um **ESP32 real**. Siga a
ordem sugerida: montar em blocos (alimentação → LEDs → buzzer → RFID → LCD) evita
50% dos erros de fiação.

> 💡 **Antes de ligar o USB:** confira duas vezes os fios de alimentação
> (3V3 e GND). Um curto entre 3V3 e GND pode queimar o ESP32.

---

## 1. Lista de materiais

| Qtd | Componente | Observação |
|---|---|---|
| 1 | **ESP32 DevKit** (30 ou 38 pinos) | Qualquer ESP32 com Wi-Fi 2,4 GHz |
| 1 | Módulo RFID **MFRC522** (RC522) | Vem com 1 cartão branco + 1 chaveiro azul |
| 1 | LED **verde** 5 mm | Indica máquina **LIVRE** |
| 1 | LED **vermelho** 5 mm | Indica máquina **OCUPADA** |
| 2 | Resistor **220 Ω** (vermelho-vermelho-marrom) | Limitador de corrente dos LEDs |
| 1 | **Buzzer passivo** | Ativo também funciona (tom único) |
| 1 | Display **LCD 16x2 I2C** (opcional) | Mostra o estado da máquina em texto |
| 1 | **Protoboard** 400 ou 830 pontos | |
| ~15 | Jumpers macho-macho e macho-fêmea | |
| 1 | Cabo USB de **dados** (micro-USB ou USB-C) | ⚠️ cabo só de carga **não** grava o ESP32 |

---

## 2. Entendendo a protoboard

```
     ╔═══════════════════════════════════════════╗
     ║  +  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   ║ ← trilho de alimentação (+)
     ║  −  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   ║ ← trilho de GND (−)
     ║                                           ║
     ║  a b c d e   f g h i j                    ║
     ║  │ │ │ │ │   │ │ │ │ │                    ║ ← colunas conectadas
     ║  │ │ │ │ │   │ │ │ │ │                    ║   verticalmente de a-e
     ║                                           ║   e de f-j (separadas
     ║  −  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   ║   pelo canal central)
     ║  +  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   ║
     ╚═══════════════════════════════════════════╝
```

- **Linhas horizontais superiores/inferiores** (+ e −): são **barramentos**.
  Tudo que estiver na mesma linha + está conectado; o mesmo para a linha −.
- **Colunas a–e** e **f–j**: cada coluna de 5 furos é um ponto elétrico único.
  Separar entre `a–e` e `f–j` é intencional (o canal central permite encaixar CIs).
- Encaixe o **ESP32 no meio da protoboard**, de forma que cada pino caia em uma
  coluna diferente (uma perna de cada lado do canal central).

---

## 3. Alimentação (sempre primeiro)

Puxe **duas pontes** da própria placa para os trilhos da protoboard:

| Fio | De (ESP32) | Para (protoboard) | Cor sugerida |
|---|---|---|---|
| 1 | pino **3V3** | trilho **+** | 🔴 vermelho |
| 2 | pino **GND** | trilho **−** | ⚫ preto |

> ⚠️ **Não use o pino 5V/VIN** para alimentar o MFRC522 — ele é 3,3 V e
> queima com 5 V. O LCD I2C, sim, pode ir no 5V/VIN.

Teste: ligue o USB. O LED on-board do ESP32 deve acender. Se cheirar queimado
ou esquentar na hora, **desconecte** — provavelmente há um curto entre + e −.

---

## 4. LEDs (verde e vermelho)

Cada LED tem uma **perna longa (ânodo, +)** e uma **perna curta (cátodo, −)**.
A corrente entra pelo ânodo. O resistor de 220 Ω vai em série com qualquer uma
das pernas (convenção: no ânodo).

### LED verde — máquina LIVRE

```
   GPIO 26 ──────┬── 220Ω ──┬── ânodo (perna longa) ──[LED verde]── cátodo ── GND
                 │          │
             (jumper)   (resistor na protoboard)
```

| Ponto | Vai para |
|---|---|
| **GPIO 26** do ESP32 | uma ponta do resistor 220 Ω |
| **Outra ponta** do resistor | perna longa do LED verde |
| **Perna curta** do LED verde | trilho **GND (−)** |

### LED vermelho — máquina OCUPADA

Mesma lógica, trocando o pino do ESP32:

| Ponto | Vai para |
|---|---|
| **GPIO 27** do ESP32 | resistor 220 Ω → ânodo do LED vermelho |
| Cátodo do LED vermelho | trilho **GND (−)** |

**Teste rápido:** grave o firmware com `SIMULAR_RFID 1` e aperte o botão
verde no Wokwi — o LED verde do protótipo real deve acender também (se o
firmware já estiver no ESP32 e conectado ao broker).

---

## 5. Buzzer

| Perna | Ligação |
|---|---|
| **(+)** do buzzer (geralmente marcada com `+` ou perna maior) | **GPIO 25** do ESP32 |
| **(−)** do buzzer | trilho **GND (−)** |

Buzzer **passivo** permite tons diferentes (bip curto para OK, bip longo para
negado). O **ativo** emite um único tom — funciona, mas sem variação.

---

## 6. Módulo RFID MFRC522 (SPI)

É o passo mais sensível: são **7 fios**. Use cores diferentes e cheque **duas
vezes** antes de energizar.

### Diagrama de ligação

```
         MFRC522                              ESP32 DevKit
    ┌──────────────┐                      ┌──────────────────┐
    │ 3.3V ────────┼──── 🔴 vermelho ─────┤ 3V3              │
    │ RST  ────────┼──── 🟠 laranja  ─────┤ GPIO 4           │
    │ GND  ────────┼──── ⚫ preto    ─────┤ GND              │
    │ IRQ  ────────┼──── (não usar)       │                  │
    │ MISO ────────┼──── 🟡 amarelo  ─────┤ GPIO 19          │
    │ MOSI ────────┼──── 🟢 verde    ─────┤ GPIO 23          │
    │ SCK  ────────┼──── 🔵 azul     ─────┤ GPIO 18          │
    │ SDA/SS ──────┼──── 🟣 roxo     ─────┤ GPIO 5           │
    └──────────────┘                      └──────────────────┘
```

### Tabela de pinos

| Pino do MFRC522 | Pino do ESP32 | Função | Constante no firmware |
|---|---|---|---|
| **3.3V** | **3V3** | Alimentação — ⚠️ **nunca no 5V** | — |
| **GND** | **GND** | Terra comum | — |
| **RST** | **GPIO 4** | Reset do módulo | `PINO_RFID_RST` |
| **SDA (SS)** | **GPIO 5** | Chip-Select (escolhe o módulo no barramento SPI) | `PINO_RFID_SS` |
| **SCK** | **GPIO 18** | Clock do SPI | SPI padrão |
| **MOSI** | **GPIO 23** | Dados do ESP32 → módulo | SPI padrão |
| **MISO** | **GPIO 19** | Dados do módulo → ESP32 | SPI padrão |
| **IRQ** | — | Interrupção (não usada) | — |

### Dicas práticas

- **Sem solda, não funciona bem.** A maioria dos módulos vem com os pinos
  **soltos** no saquinho. Solde todos antes de montar, caso contrário o
  contato intermitente faz o leitor "sumir".
- Encoste o cartão **a menos de 2 cm** do módulo (face plana).
- Se usar jumpers longos (>20 cm), a leitura pode falhar — prefira curtos.

---

## 7. Display LCD 16x2 I2C *(opcional)*

Só 4 fios, muito mais tolerante que o SPI. Pode pular se não tiver — no
`config.h`, defina `USAR_LCD 0`.

| Pino do LCD I2C | Pino do ESP32 |
|---|---|
| **GND** | **GND** |
| **VCC** | **VIN** (ou **5V**) — este sim aceita 5 V |
| **SDA** | **GPIO 21** |
| **SCL** | **GPIO 22** |

> ⚙️ **Ajuste o contraste** no potenciômetro azul atrás do módulo. É muito
> comum ligar o LCD, ver só a luz de fundo acesa e achar que está quebrado —
> gire o potenciômetro até os caracteres aparecerem.
>
> Se continuar em branco, o endereço I2C pode ser `0x3F` em vez de `0x27`.
> Troque `LCD_ENDERECO` no `config.h`.

---

## 8. Mapa completo de pinos do ESP32

Resumo de tudo o que foi usado — útil para conferir no final:

```
                   ┌───────────────────────┐
                   │        ESP32          │
                   │                       │
   LED verde   ───▶│ GPIO 26        GPIO 23│◀── MOSI  (RC522)
   LED vermelho ──▶│ GPIO 27        GPIO 22│◀── SCL   (LCD)
   Buzzer      ───▶│ GPIO 25        GPIO 21│◀── SDA   (LCD)
   RC522 SDA/SS ──▶│ GPIO  5        GPIO 19│◀── MISO  (RC522)
   RC522 RST   ───▶│ GPIO  4        GPIO 18│◀── SCK   (RC522)
                   │                       │
   RC522 3.3V  ───▶│ 3V3            VIN/5V │◀── LCD VCC
   TUDO que é GND ▶│ GND            GND    │
                   └───────────────────────┘
```

**Trilhos da protoboard:**
- **Trilho +** (3V3): só o MFRC522 (e o próprio ESP32).
- **Trilho −** (GND): **comum a tudo** — LEDs, buzzer, MFRC522, LCD.
- **5V/VIN**: só o LCD (se usar). Nunca o MFRC522.

---

## 9. Preparar o Arduino IDE

1. Instale o [Arduino IDE 2](https://www.arduino.cc/en/software).
2. Em **Arquivo → Preferências → URLs adicionais de Gerenciadores de Placas**, cole:
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
3. Em **Ferramentas → Placa → Gerenciador de placas**, pesquise `esp32` e
   instale **esp32 by Espressif Systems**.
4. Em **Ferramentas → Gerenciar bibliotecas**, instale (uma por vez):
   - **PubSubClient** (Nick O'Leary)
   - **ArduinoJson** (Benoit Blanchon) — **versão 7.x**
   - **MFRC522** (GithubCommunity / miguelbalboa)
   - **LiquidCrystal I2C** (Frank de Brabander)
5. Abra o arquivo `firmware/estacao_esp32/estacao_esp32.ino`.

---

## 10. Configurar o firmware (`config.h`)

```cpp
#define SIMULAR_RFID 0                    // 0 = MFRC522 real, 1 = botões (Wokwi)
#define USAR_LCD     1                    // 0 se não tiver o display

#define WIFI_SSID     "NOME_DA_SUA_REDE"  // ⚠️ rede 2,4 GHz
#define WIFI_PASSWORD "SENHA_DA_SUA_REDE"

#define TOPICO_BASE "fiap/cp5/SEU_GRUPO/estacao01"
```

> ⚠️ O ESP32 **só conecta em redes 2,4 GHz** e **não suporta** redes
> corporativas com login (WPA2-Enterprise ou portal cativo).
> Em sala, use o **hotspot do celular** em 2,4 GHz — é o mais garantido.

---

## 11. Gravar e cadastrar os cartões

1. **Ferramentas → Placa → ESP32 Dev Module** e selecione a **porta COM** certa.
2. Clique no botão **Carregar** (seta →).
   - Se travar em `Connecting....`, **segure o botão BOOT** do ESP32 até começar a gravar.
3. Abra o **Serial Monitor** em **115200 baud**. Deve aparecer:
   ```
   [RFID] MFRC522 iniciado. Firmware Version: 0x92 = v2.0
   [WiFi] Conectado! IP: 192.168.x.x
   [MQTT] Conectado!
   ```
4. Encoste cada cartão/chaveiro no leitor. Como ainda não estão cadastrados:
   ```
   [RFID] UID lido: 3A7F9C21 (nao cadastrado)
   ```
5. Copie o UID lido para a tabela `ALUNOS_CADASTRADOS` em `config.h`:
   ```cpp
   static const Aluno ALUNOS_CADASTRADOS[] = {
     { "3A7F9C21", "Ana Souza"  },
     { "B4120A7E", "Bruno Lima" },
   };
   ```
6. **Grave de novo**. Agora, ao aproximar o cartão: bip duplo, LED vermelho acende,
   dashboard muda para **OCUPADA** com o nome do aluno.

---

## 12. Checklist final (antes da apresentação)

- [ ] LED **verde** aceso quando a máquina está livre
- [ ] Cartão cadastrado → bip duplo + LED **vermelho** + dashboard **OCUPADA** com o nome
- [ ] Cartão desconhecido → bip longo + LED vermelho pisca + evento **NEGADO** no dashboard
- [ ] Contador (`visao/`) exibe **LIBERADA: nome** e conta repetições corretamente
- [ ] Após 8 s parado, a série aparece no histórico do dashboard (e no LCD, se houver)
- [ ] Mesmo cartão de novo → **check-out**, LED verde, dashboard **LIVRE**
- [ ] Tirar o ESP32 da tomada → em até ~30 s o dashboard mostra **OFFLINE**
      *(LWT: keepalive de 15 s × 1,5)*

---

## 13. Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `Firmware Version: 0x0` ou `0xFF` | Fiação SPI invertida ou alimentação errada | Reconfira SDA=5, SCK=18, MOSI=23, MISO=19, RST=4 e **3V3** |
| Cartão não é lido | Distância ou pinos mal soldados | Encoste na antena; ressolde os pinos do módulo |
| LCD acende mas não mostra texto | Contraste no mínimo | Gire o potenciômetro azul atrás do módulo |
| LCD totalmente em branco | Endereço I2C diferente | Troque `LCD_ENDERECO` para `0x3F` |
| LED acende invertido (vermelho quando era pra ser verde) | GPIOs trocados | Reconfira: verde = GPIO 26, vermelho = GPIO 27 |
| ESP32 reinicia sozinho | Corrente insuficiente (USB fraco) | Troque o cabo e/ou use porta USB traseira do PC |
| Fica em `Conectando WiFi....` | Rede 5 GHz, senha errada ou rede com portal | Hotspot 2,4 GHz do celular |
| `[MQTT] Falhou (rc=-2)` | Porta 1883 bloqueada pelo roteador | Hotspot do celular |
| Dashboard não recebe nada | `TOPICO_BASE` diferente entre firmware/visão/dashboard | Tem que ser **idêntico** nos 3 arquivos |
| `Connecting....` eterno ao gravar | Timing do bootloader | Segure **BOOT**, clique Carregar, solte **BOOT** quando aparecer `Writing at 0x…` |
