/*
 * CP5 - Estação de Treino IoT (RFID + MQTT)
 * ==========================================
 * ESP32 que controla o acesso à estação de treino por RFID e publica
 * o status da máquina via MQTT (Publish/Subscribe).
 *
 *  - Cartão cadastrado com a máquina LIVRE   -> máquina OCUPADA (LED vermelho)
 *  - Mesmo cartão com a máquina OCUPADA      -> check-out, máquina LIVRE (LED verde)
 *  - Cartão desconhecido / outro aluno       -> acesso negado (bip longo)
 *  - Sem atividade por SESSAO_TIMEOUT_MS     -> libera automaticamente
 *
 * Publica:  {base}/status (retido), {base}/acesso, {base}/esp32/online (LWT)
 * Assina:   {base}/reps, {base}/serie  (vindos do contador de visão do CP4)
 *
 * Bibliotecas: PubSubClient, ArduinoJson (v7), LiquidCrystal I2C, MFRC522
 * Configurações: config.h
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "config.h"

#if !SIMULAR_RFID
  #include <SPI.h>
  #include <MFRC522.h>
  MFRC522 rfid(PINO_RFID_SS, PINO_RFID_RST);
#endif

#if USAR_LCD
  #include <Wire.h>
  #include <LiquidCrystal_I2C.h>
  LiquidCrystal_I2C lcd(LCD_ENDERECO, 16, 2);
#endif

// =========================================================
// TÓPICOS
// =========================================================
const String T_STATUS  = String(TOPICO_BASE) + "/status";
const String T_ACESSO  = String(TOPICO_BASE) + "/acesso";
const String T_REPS    = String(TOPICO_BASE) + "/reps";
const String T_SERIE   = String(TOPICO_BASE) + "/serie";
const String T_ONLINE  = String(TOPICO_BASE) + "/esp32/online";

// =========================================================
// ESTADO
// =========================================================
enum EstadoMaquina { LIVRE, OCUPADA };

EstadoMaquina estado = LIVRE;
String alunoAtual    = "";
String uidAtual      = "";
String sessaoAtual   = "";
unsigned long ultimaAtividade = 0;   // millis() da última leitura/repetição
uint16_t prefixoSessao = 0;
uint16_t contadorSessao = 0;

String ultimoUidLido = "";
unsigned long ultimaLeituraMs = 0;
const unsigned long BLOQUEIO_RELEITURA_MS = 2000;  // evita ler o mesmo cartão 2x seguidas

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
unsigned long ultimaTentativaMqtt = 0;

// =========================================================
// LCD
// =========================================================
void lcdMostrar(const String& linha1, const String& linha2) {
#if USAR_LCD
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(linha1.substring(0, 16));
  lcd.setCursor(0, 1);
  lcd.print(linha2.substring(0, 16));
#endif
}

void lcdTelaEstado() {
  if (estado == LIVRE) {
    lcdMostrar("MAQUINA LIVRE", "Aproxime cartao");
  } else {
    lcdMostrar(alunoAtual, "Treino liberado");
  }
}

// =========================================================
// ATUADORES (LEDs e buzzer)
// =========================================================
void aplicarLeds() {
  digitalWrite(PINO_LED_VERDE,    estado == LIVRE   ? HIGH : LOW);
  digitalWrite(PINO_LED_VERMELHO, estado == OCUPADA ? HIGH : LOW);
}

void bipOk() {
  tone(PINO_BUZZER, 1800, 80);
  delay(120);
  tone(PINO_BUZZER, 2400, 80);
}

void bipErro() {
  tone(PINO_BUZZER, 400, 500);
  for (int i = 0; i < 3; i++) {          // pisca o vermelho para sinalizar negado
    digitalWrite(PINO_LED_VERMELHO, HIGH);
    digitalWrite(PINO_LED_VERDE, LOW);
    delay(120);
    digitalWrite(PINO_LED_VERMELHO, LOW);
    delay(120);
  }
  aplicarLeds();
}

// =========================================================
// MQTT — PUBLICAÇÃO
// =========================================================
void publicarJson(const String& topico, JsonDocument& doc, bool retido) {
  char buffer[384];
  size_t n = serializeJson(doc, buffer, sizeof(buffer));
  bool ok = mqtt.connected() && mqtt.publish(topico.c_str(), (const uint8_t*)buffer, n, retido);
  Serial.printf("[MQTT] %s %s -> %s\n", ok ? "PUB" : "FALHOU", topico.c_str(), buffer);
}

void publicarStatus() {
  JsonDocument doc;
  doc["estado"]  = (estado == LIVRE) ? "livre" : "ocupada";
  doc["estacao"] = ESTACAO_ID;
  if (estado == OCUPADA) {
    doc["aluno"]  = alunoAtual;
    doc["uid"]    = uidAtual;
    doc["sessao"] = sessaoAtual;
  }
  publicarJson(T_STATUS, doc, true);   // retido: quem conectar depois recebe o estado atual
}

void publicarAcesso(const String& uid, const String& aluno, const char* resultado) {
  JsonDocument doc;
  doc["uid"]       = uid;
  doc["aluno"]     = aluno;
  doc["resultado"] = resultado;
  publicarJson(T_ACESSO, doc, false);
}

// =========================================================
// MQTT — ASSINATURA (mensagens do contador de visão)
// =========================================================
void aoReceberMensagem(char* topico, byte* payload, unsigned int tamanho) {
  String t = String(topico);
  JsonDocument doc;
  if (deserializeJson(doc, payload, tamanho)) {
    Serial.printf("[MQTT] JSON invalido em %s\n", topico);
    return;
  }

  // Ignora mensagens de sessões antigas ou com a máquina livre
  String sessao = doc["sessao"] | "";
  if (estado != OCUPADA || sessao != sessaoAtual) return;

  ultimaAtividade = millis();   // houve treino: reinicia o timeout da sessão

  int serie = doc["serie"] | 0;
  int reps  = doc["reps"]  | 0;

  if (t == T_REPS) {
    lcdMostrar(alunoAtual, "S" + String(serie) + "  Reps: " + String(reps));
  } else if (t == T_SERIE) {
    lcdMostrar(alunoAtual, "S" + String(serie) + " fim: " + String(reps) + " reps");
    tone(PINO_BUZZER, 2000, 150);
  }
}

// =========================================================
// CONECTIVIDADE
// =========================================================
void conectarWiFi() {   // usado só no boot (bloqueante)
  Serial.printf("[WiFi] Conectando a %s", WIFI_SSID);
  lcdMostrar("Conectando WiFi", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WIFI_CANAL);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print(".");
  }
  Serial.printf("\n[WiFi] Conectado! IP: %s\n", WiFi.localIP().toString().c_str());
}

// Reconexão NÃO bloqueante: o controle de acesso local (RFID, LEDs) continua
// funcionando mesmo sem rede.
unsigned long ultimaTentativaWifi = 0;
void manterWiFi() {
  if (WiFi.status() == WL_CONNECTED || millis() - ultimaTentativaWifi < 5000) return;
  ultimaTentativaWifi = millis();
  Serial.println("[WiFi] Conexao perdida. Tentando reconectar...");
  WiFi.reconnect();
}

void conectarMqtt() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (mqtt.connected() || millis() - ultimaTentativaMqtt < 3000) return;
  ultimaTentativaMqtt = millis();

  String clientId = String(ESTACAO_ID) + "-esp32-" + String((uint32_t)esp_random(), HEX);
  Serial.printf("[MQTT] Conectando a %s:%d como %s...\n", MQTT_BROKER, MQTT_PORTA, clientId.c_str());

  // LWT: se o ESP32 cair, o broker publica "offline" (retido) em nome dele
  bool ok = mqtt.connect(clientId.c_str(), nullptr, nullptr,
                         T_ONLINE.c_str(), 0, true, "offline");
  if (ok) {
    Serial.println("[MQTT] Conectado!");
    mqtt.publish(T_ONLINE.c_str(), "online", true);
    mqtt.subscribe(T_REPS.c_str());
    mqtt.subscribe(T_SERIE.c_str());
    publicarStatus();   // republica o estado atual (ex.: após reconexão)
    lcdTelaEstado();
  } else {
    Serial.printf("[MQTT] Falhou (rc=%d). Nova tentativa em 3 s.\n", mqtt.state());
    lcdMostrar("MQTT offline", "tentando...");
  }
}

// =========================================================
// CONTROLE DE ACESSO
// =========================================================
const Aluno* buscarAluno(const String& uid) {
  for (const Aluno& a : ALUNOS_CADASTRADOS) {
    if (uid.equalsIgnoreCase(a.uid)) return &a;
  }
  return nullptr;
}

String novaSessao() {
  char buf[12];
  snprintf(buf, sizeof(buf), "%04x-%04u", prefixoSessao, ++contadorSessao);
  return String(buf);
}

void liberarMaquina(const char* motivo) {
  estado      = LIVRE;
  alunoAtual  = "";
  uidAtual    = "";
  sessaoAtual = "";
  aplicarLeds();
  publicarStatus();
  lcdTelaEstado();
  Serial.printf("[ESTACAO] Maquina LIVRE (%s)\n", motivo);
}

void processarCartao(String uid) {
  uid.trim();
  uid.toUpperCase();
  if (uid.isEmpty()) return;

  // Antirrepique: o mesmo cartão parado no leitor gera várias leituras
  if (uid == ultimoUidLido && millis() - ultimaLeituraMs < BLOQUEIO_RELEITURA_MS) return;
  ultimoUidLido   = uid;
  ultimaLeituraMs = millis();

  const Aluno* aluno = buscarAluno(uid);
  Serial.printf("[RFID] UID lido: %s (%s)\n", uid.c_str(), aluno ? aluno->nome : "nao cadastrado");

  if (!aluno) {
    publicarAcesso(uid, "", "negado");
    lcdMostrar("ACESSO NEGADO", "Cartao: " + uid);
    bipErro();
    delay(1200);
    lcdTelaEstado();
    return;
  }

  if (estado == LIVRE) {
    // Check-in
    estado          = OCUPADA;
    alunoAtual      = aluno->nome;
    uidAtual        = uid;
    sessaoAtual     = novaSessao();
    ultimaAtividade = millis();
    aplicarLeds();
    publicarStatus();
    publicarAcesso(uid, alunoAtual, "liberado");
    lcdMostrar("Bom treino!", alunoAtual);
    bipOk();
    Serial.printf("[ESTACAO] Maquina OCUPADA por %s (sessao %s)\n", alunoAtual.c_str(), sessaoAtual.c_str());
  } else if (uid == uidAtual) {
    // Check-out pelo próprio aluno
    publicarAcesso(uid, alunoAtual, "encerrado");
    bipOk();
    liberarMaquina("check-out");
  } else {
    // Outro aluno tentando usar uma máquina ocupada
    publicarAcesso(uid, aluno->nome, "ocupada");
    lcdMostrar("EM USO POR", alunoAtual);
    bipErro();
    delay(1200);
    lcdTelaEstado();
  }
}

// =========================================================
// LEITURA DE CARTÕES
// =========================================================
#if SIMULAR_RFID
struct BotaoCartao { uint8_t pino; const char* uid; bool anterior; };
BotaoCartao botoes[] = {
  { PINO_BTN_CARTAO_1, UID_SIMULADO_1, HIGH },
  { PINO_BTN_CARTAO_2, UID_SIMULADO_2, HIGH },
  { PINO_BTN_CARTAO_3, UID_SIMULADO_3, HIGH },
};
#endif

void lerCartoes() {
#if SIMULAR_RFID
  // Cada botão "aproxima" um cartão (detecção de borda de descida)
  for (BotaoCartao& b : botoes) {
    bool atual = digitalRead(b.pino);
    if (b.anterior == HIGH && atual == LOW) {
      delay(30);   // debounce
      if (digitalRead(b.pino) == LOW) processarCartao(b.uid);
    }
    b.anterior = atual;
  }
#else
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    String uid = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
      if (rfid.uid.uidByte[i] < 0x10) uid += "0";
      uid += String(rfid.uid.uidByte[i], HEX);
    }
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    processarCartao(uid);
  }
#endif

  // Em qualquer modo: digitar um UID no Serial Monitor simula a leitura
  if (Serial.available()) {
    processarCartao(Serial.readStringUntil('\n'));
  }
}

// =========================================================
// SETUP / LOOP
// =========================================================
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(50);

  pinMode(PINO_LED_VERDE, OUTPUT);
  pinMode(PINO_LED_VERMELHO, OUTPUT);
  pinMode(PINO_BUZZER, OUTPUT);

#if SIMULAR_RFID
  for (BotaoCartao& b : botoes) pinMode(b.pino, INPUT_PULLUP);
  Serial.println("[RFID] Modo SIMULADO: use os botoes ou digite um UID no Serial Monitor");
#else
  SPI.begin();
  rfid.PCD_Init();
  Serial.print("[RFID] MFRC522 iniciado. ");
  rfid.PCD_DumpVersionToSerial();
#endif

#if USAR_LCD
  lcd.init();
  lcd.backlight();
#endif

  prefixoSessao = (uint16_t)(esp_random() & 0xFFFF);
  aplicarLeds();

  conectarWiFi();
  mqtt.setServer(MQTT_BROKER, MQTT_PORTA);
  mqtt.setBufferSize(512);
  mqtt.setCallback(aoReceberMensagem);
  conectarMqtt();
}

void loop() {
  manterWiFi();
  conectarMqtt();
  mqtt.loop();

  lerCartoes();

  // Libera a máquina se o aluno esquecer de fazer check-out
  if (estado == OCUPADA && millis() - ultimaAtividade > SESSAO_TIMEOUT_MS) {
    publicarAcesso(uidAtual, alunoAtual, "timeout");
    liberarMaquina("timeout por inatividade");
  }
}
