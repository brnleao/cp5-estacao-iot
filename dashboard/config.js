// Configuração do dashboard.
// TOPICO_BASE deve ser IGUAL ao de firmware/estacao_esp32/config.h e visao/config.py.
// Também é possível sobrescrever pela URL: index.html?base=fiap/cp5/meugrupo/estacao01
// ou pelo painel "Configurações" no rodapé da página (fica salvo no navegador).
window.CONFIG = {
  // Navegadores só falam MQTT via WebSocket. HiveMQ público: WSS na porta 8884, caminho /mqtt
  BROKER_URL: "wss://broker.hivemq.com:8884/mqtt",
  TOPICO_BASE: "fiap/cp5/ronaldos-fc/estacao01",
};
