/*
 * config.h — Configurações da Estação de Treino IoT (CP5)
 * ---------------------------------------------------------
 * Tudo que muda entre Wokwi e hardware físico fica aqui.
 */
#pragma once

// =========================================================
// MODO DE OPERAÇÃO
// =========================================================
// 1 = Wokwi: botões fazem o papel dos cartões RFID (o Wokwi não tem MFRC522)
// 0 = Hardware físico: usa o leitor MFRC522 real
#define SIMULAR_RFID 1

// 1 = usa display LCD 16x2 I2C (opcional no hardware físico)
#define USAR_LCD 1

// =========================================================
// WI-FI
// =========================================================
#if SIMULAR_RFID
  #define WIFI_SSID     "Wokwi-GUEST"   // rede virtual do Wokwi
  #define WIFI_PASSWORD ""
  #define WIFI_CANAL    6               // canal fixo acelera a conexão no Wokwi
#else
  #define WIFI_SSID     "NOME_DA_SUA_REDE"
  #define WIFI_PASSWORD "SENHA_DA_SUA_REDE"
  #define WIFI_CANAL    0               // 0 = procura em todos os canais
#endif

// =========================================================
// MQTT
// =========================================================
#define MQTT_BROKER "broker.hivemq.com"
#define MQTT_PORTA  1883

// o broker é público e outros grupos podem usar o mesmo nome.
// O MESMO valor deve estar em visao/config.py e dashboard/config.js.
#define TOPICO_BASE "fiap/cp5/ronaldos-fc/estacao01"
#define ESTACAO_ID  "estacao01"

// =========================================================
// REGRAS DE NEGÓCIO
// =========================================================
// Libera a máquina automaticamente se ninguém treinar por este tempo (ms)
#define SESSAO_TIMEOUT_MS (3UL * 60UL * 1000UL)   // 3 minutos

// =========================================================
// PINOS (ESP32 DevKit)
// =========================================================
// MFRC522 (SPI): SCK=18, MISO=19, MOSI=23 (pinos SPI padrão do ESP32)
#define PINO_RFID_SS   5
#define PINO_RFID_RST  4

// LCD I2C: SDA=21, SCL=22 (padrão do ESP32)
#define LCD_ENDERECO   0x27

#define PINO_LED_VERDE    26
#define PINO_LED_VERMELHO 27
#define PINO_BUZZER       25

// Botões que simulam cartões no Wokwi (INPUT_PULLUP, ligam ao GND)
#define PINO_BTN_CARTAO_1 32   // cartão da Ana
#define PINO_BTN_CARTAO_2 33   // cartão do Bruno
#define PINO_BTN_CARTAO_3 14   // cartão NÃO cadastrado

// =========================================================
// CARTÕES CADASTRADOS
// =========================================================
// No hardware físico: passe o cartão, copie o UID mostrado no Serial Monitor
// e cadastre aqui (letras maiúsculas, sem espaços).
struct Aluno {
  const char* uid;
  const char* nome;
};

static const Aluno ALUNOS_CADASTRADOS[] = {
  { "A1B2C3D4", "Ana Souza"  },
  { "B5C6D7E8", "Bruno Lima" },
  // { "UID_DO_SEU_CARTAO", "Seu Nome" },
};

// UIDs que os botões do Wokwi "leem"
#define UID_SIMULADO_1 "A1B2C3D4"
#define UID_SIMULADO_2 "B5C6D7E8"
#define UID_SIMULADO_3 "DEADBEEF"   // não cadastrado → acesso negado
