/*
 * Dashboard da Estação de Treino IoT (CP5)
 * -----------------------------------------
 * Cliente MQTT no navegador (MQTT.js sobre WebSocket seguro).
 * Assina {base}/# e atualiza a tela a cada mensagem — não há servidor próprio:
 * o broker entrega os dados direto para a página (Publish/Subscribe).
 *
 * Segurança: o broker é público, então todo texto recebido é inserido com
 * textContent (nunca innerHTML) para evitar injeção de HTML/JS.
 */
(function () {
  "use strict";

  // ---------------------------------------------------------------
  // Configuração (config.js < localStorage < parâmetros da URL)
  // ---------------------------------------------------------------
  const params = new URLSearchParams(location.search);
  const salvo = lerStorage("cp5-config", {});
  const cfg = {
    broker: params.get("broker") || salvo.broker || window.CONFIG.BROKER_URL,
    base: (params.get("base") || salvo.base || window.CONFIG.TOPICO_BASE).replace(/\/+$/, ""),
  };

  const MAX_ACESSOS = 15;
  const MAX_SERIES = 50;

  // ---------------------------------------------------------------
  // Estado
  // ---------------------------------------------------------------
  const estado = {
    maquina: null,          // payload do tópico status
    inicioSessao: null,     // Date.now() de quando vimos a máquina ficar ocupada
    esp32Online: null,
    contadorOnline: null,
    reps: null,             // último payload de reps
    series: lerStorage("cp5-series-" + cfg.base, []),
  };

  // ---------------------------------------------------------------
  // Elementos
  // ---------------------------------------------------------------
  const $ = (id) => document.getElementById(id);
  const el = {
    cardStatus: $("card-status"), statusEstado: $("status-estado"), statusAluno: $("status-aluno"),
    statusTempo: $("status-tempo"), statusSessao: $("status-sessao"),
    repsNumero: $("reps-numero"), repsSerie: $("reps-serie"),
    ultimaVazia: $("ultima-vazia"), ultimaConteudo: $("ultima-conteudo"),
    ultimaAluno: $("ultima-aluno"), ultimaReps: $("ultima-reps"),
    ultimaSerie: $("ultima-serie"), ultimaDuracao: $("ultima-duracao"),
    tabela: $("tabela-series"), tabelaVazia: $("tabela-vazia"), resumo: $("resumo-alunos"),
    acessos: $("lista-acessos"),
    pillBroker: $("pill-broker"), pillEsp32: $("pill-esp32"), pillContador: $("pill-contador"),
    rodapeTopico: $("rodape-topico"), nomeEstacao: $("nome-estacao"),
    cfgBroker: $("cfg-broker"), cfgBase: $("cfg-base"),
  };

  // ---------------------------------------------------------------
  // MQTT
  // ---------------------------------------------------------------
  let cliente = null;

  function conectar() {
    if (cliente) cliente.end(true);
    setPill(el.pillBroker, "espera", "conectando…");
    el.rodapeTopico.textContent = cfg.broker + "  ·  " + cfg.base + "/#";
    el.nomeEstacao.textContent = cfg.base.split("/").pop();

    cliente = mqtt.connect(cfg.broker, {
      clientId: "dashboard-" + Math.random().toString(16).slice(2, 10),
      clean: true,
      connectTimeout: 8000,
      reconnectPeriod: 2000,
    });

    cliente.on("connect", () => {
      setPill(el.pillBroker, "on", "conectado");
      cliente.subscribe(cfg.base + "/#", { qos: 1 });
    });
    cliente.on("reconnect", () => setPill(el.pillBroker, "espera", "reconectando…"));
    cliente.on("offline", () => setPill(el.pillBroker, "off", "offline"));
    cliente.on("error", (err) => {
      console.error("[MQTT]", err);
      setPill(el.pillBroker, "off", "erro");
    });
    cliente.on("message", aoReceber);
  }

  function aoReceber(topico, payloadBuf, pacote) {
    const sub = topico.slice(cfg.base.length + 1);
    const texto = payloadBuf.toString();

    if (sub === "esp32/online") { estado.esp32Online = texto === "online"; renderDispositivos(); renderStatus(); return; }
    if (sub === "contador/online") { estado.contadorOnline = texto === "online"; renderDispositivos(); return; }

    let dados;
    try { dados = JSON.parse(texto); } catch (e) {
      console.warn("Payload não-JSON em", topico, texto);
      return;
    }
    if (!dados || typeof dados !== "object") return;

    switch (sub) {
      case "status": tratarStatus(dados, pacote.retain); break;
      case "acesso": tratarAcesso(dados); break;
      case "reps":   tratarReps(dados); break;
      case "serie":  tratarSerie(dados); break;
    }
  }

  // ---------------------------------------------------------------
  // Tratamento de cada tópico
  // ---------------------------------------------------------------
  function tratarStatus(dados, retido) {
    const anterior = estado.maquina;
    const novaSessao = dados.estado === "ocupada" &&
      (!anterior || anterior.estado !== "ocupada" || anterior.sessao !== dados.sessao);

    if (novaSessao) {
      // Mensagem retida = a sessão começou antes de abrirmos a página: não sabemos o início
      estado.inicioSessao = retido ? null : Date.now();
      estado.reps = null;
    }
    if (dados.estado === "livre") {
      estado.inicioSessao = null;
      estado.reps = null;
    }
    estado.maquina = dados;
    renderStatus(anterior && anterior.estado !== dados.estado);
    renderReps(false);
  }

  function tratarAcesso(dados) {
    const vazio = el.acessos.querySelector(".vazio");
    if (vazio) vazio.remove();

    const textos = {
      liberado: "check-in — máquina liberada",
      encerrado: "check-out — máquina livre",
      negado: "cartão não cadastrado",
      ocupada: "tentou usar a máquina ocupada",
      timeout: "liberada por inatividade",
    };
    const resultado = String(dados.resultado || "?");

    const li = document.createElement("li");
    const hora = document.createElement("span");
    hora.className = "hora";
    hora.textContent = horaAgora();
    const selo = document.createElement("span");
    selo.className = "selo " + resultado.replace(/[^a-z]/g, "");
    selo.textContent = resultado;
    const desc = document.createElement("span");
    desc.className = "acesso-texto";
    desc.textContent = (dados.aluno ? dados.aluno : "UID " + (dados.uid || "?")) +
      " · " + (textos[resultado] || resultado);

    li.append(hora, selo, desc);
    el.acessos.prepend(li);
    while (el.acessos.children.length > MAX_ACESSOS) el.acessos.lastElementChild.remove();
  }

  function tratarReps(dados) {
    const m = estado.maquina;
    if (m && m.sessao && dados.sessao && m.sessao !== dados.sessao) return; // de outra sessão
    estado.reps = dados;
    renderReps(true);
  }

  function tratarSerie(dados) {
    // QoS 1 pode entregar em duplicidade: ignora série já registrada
    const chave = (dados.sessao || "") + "#" + dados.serie;
    if (estado.series.some((s) => s.chave === chave)) return;

    estado.series.unshift({
      chave,
      hora: horaAgora(),
      aluno: String(dados.aluno || "—"),
      serie: Number(dados.serie) || 0,
      reps: Number(dados.reps) || 0,
      duracao: Number(dados.duracao_s) || 0,
      motivo: String(dados.motivo || ""),
    });
    estado.series = estado.series.slice(0, MAX_SERIES);
    gravarStorage("cp5-series-" + cfg.base, estado.series);

    estado.reps = null;   // a série fechou: zera o contador ao vivo
    renderReps(false);
    renderSeries(true);
  }

  // ---------------------------------------------------------------
  // Renderização
  // ---------------------------------------------------------------
  function renderStatus(mudou) {
    const m = estado.maquina;
    const c = el.cardStatus;
    c.classList.remove("livre", "ocupada", "desconhecido", "offline");

    if (estado.esp32Online === false) {
      c.classList.add("offline");
      el.statusEstado.textContent = "OFFLINE";
      el.statusAluno.textContent = "A estação (ESP32) perdeu a conexão com o broker";
      el.statusSessao.textContent = "";
      el.statusTempo.textContent = m ? "Último estado conhecido: " + m.estado : "";
      return;
    }
    if (!m) {
      c.classList.add("desconhecido");
      el.statusEstado.textContent = "AGUARDANDO";
      el.statusAluno.textContent = "Sem dados da estação ainda";
      return;
    }

    if (m.estado === "ocupada") {
      c.classList.add("ocupada");
      el.statusEstado.textContent = "OCUPADA";
      el.statusAluno.textContent = m.aluno || "Aluno não identificado";
      el.statusSessao.textContent = m.sessao ? "sessão " + m.sessao : "";
    } else {
      c.classList.add("livre");
      el.statusEstado.textContent = "LIVRE";
      el.statusAluno.textContent = "Aproxime o cartão RFID para iniciar";
      el.statusSessao.textContent = "";
    }
    atualizarTempo();

    if (mudou) {
      c.classList.remove("pulso");
      void c.offsetWidth;   // reinicia a animação
      c.classList.add("pulso");
    }
  }

  function atualizarTempo() {
    const m = estado.maquina;
    if (!m || m.estado !== "ocupada" || estado.esp32Online === false) {
      if (m && m.estado === "livre") el.statusTempo.textContent = "";
      return;
    }
    if (estado.inicioSessao === null) {
      el.statusTempo.textContent = "Sessão em andamento";
      return;
    }
    const s = Math.floor((Date.now() - estado.inicioSessao) / 1000);
    el.statusTempo.textContent = "Em uso há " + String(Math.floor(s / 60)).padStart(2, "0") +
      ":" + String(s % 60).padStart(2, "0");
  }

  function renderReps(animar) {
    const r = estado.reps;
    const ocupada = estado.maquina && estado.maquina.estado === "ocupada";
    el.repsNumero.classList.toggle("inativo", !r);
    el.repsNumero.textContent = r ? r.reps : "0";
    if (r) {
      el.repsSerie.textContent = (r.aluno || "") + " · série " + r.serie + " em andamento";
    } else {
      el.repsSerie.textContent = ocupada ? "Aguardando a primeira repetição" : "Nenhuma série em andamento";
    }
    if (animar) {
      el.repsNumero.classList.remove("bump");
      void el.repsNumero.offsetWidth;
      el.repsNumero.classList.add("bump");
    }
  }

  function renderSeries(destacarPrimeira) {
    el.tabela.replaceChildren();
    el.tabelaVazia.hidden = estado.series.length > 0;
    const motivos = { pausa: "pausa", checkout: "check-out", manual: "manual" };

    estado.series.forEach((s, i) => {
      const tr = document.createElement("tr");
      if (destacarPrimeira && i === 0) tr.className = "nova";
      [s.hora, s.aluno, s.serie, s.reps, formatarDuracao(s.duracao), motivos[s.motivo] || s.motivo]
        .forEach((valor, col) => {
          const td = document.createElement("td");
          if (col === 2 || col === 3) td.className = "num";
          td.textContent = valor;
          tr.append(td);
        });
      el.tabela.append(tr);
    });

    // Última série
    const u = estado.series[0];
    el.ultimaVazia.hidden = !!u;
    el.ultimaConteudo.hidden = !u;
    if (u) {
      el.ultimaAluno.textContent = u.aluno;
      el.ultimaReps.textContent = u.reps;
      el.ultimaSerie.textContent = u.serie;
      el.ultimaDuracao.textContent = formatarDuracao(u.duracao);
    }

    // Resumo por aluno
    const porAluno = {};
    estado.series.forEach((s) => {
      porAluno[s.aluno] = porAluno[s.aluno] || { series: 0, reps: 0 };
      porAluno[s.aluno].series += 1;
      porAluno[s.aluno].reps += s.reps;
    });
    el.resumo.replaceChildren();
    Object.entries(porAluno).forEach(([nome, t]) => {
      const div = document.createElement("div");
      div.className = "resumo-item";
      const b = document.createElement("b");
      b.textContent = nome;
      const span = document.createElement("span");
      span.textContent = t.series + (t.series === 1 ? " série · " : " séries · ") + t.reps + " reps";
      div.append(b, span);
      el.resumo.append(div);
    });
  }

  function renderDispositivos() {
    const pill = (p, v) => setPill(p, v === null ? "" : v ? "on" : "off", v === null ? "?" : v ? "online" : "offline");
    pill(el.pillEsp32, estado.esp32Online);
    pill(el.pillContador, estado.contadorOnline);
  }

  function setPill(p, classe, texto) {
    p.classList.remove("on", "off", "espera");
    if (classe) p.classList.add(classe);
    p.querySelector("em").textContent = texto;
  }

  // ---------------------------------------------------------------
  // Utilidades
  // ---------------------------------------------------------------
  function horaAgora() {
    return new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
  function formatarDuracao(s) {
    return s >= 60 ? Math.floor(s / 60) + "m" + String(Math.round(s % 60)).padStart(2, "0") + "s" : s.toFixed(1) + "s";
  }
  function lerStorage(chave, padrao) {
    try { const v = localStorage.getItem(chave); return v ? JSON.parse(v) : padrao; } catch (e) { return padrao; }
  }
  function gravarStorage(chave, valor) {
    try { localStorage.setItem(chave, JSON.stringify(valor)); } catch (e) { /* sem storage: só memória */ }
  }

  // ---------------------------------------------------------------
  // Interações
  // ---------------------------------------------------------------
  $("btn-limpar").addEventListener("click", () => {
    estado.series = [];
    gravarStorage("cp5-series-" + cfg.base, []);
    renderSeries(false);
  });

  el.cfgBroker.value = cfg.broker;
  el.cfgBase.value = cfg.base;
  $("form-config").addEventListener("submit", (ev) => {
    ev.preventDefault();
    cfg.broker = el.cfgBroker.value.trim();
    cfg.base = el.cfgBase.value.trim().replace(/\/+$/, "");
    gravarStorage("cp5-config", cfg);
    estado.maquina = null; estado.reps = null; estado.esp32Online = null; estado.contadorOnline = null;
    estado.series = lerStorage("cp5-series-" + cfg.base, []);
    renderStatus(); renderReps(false); renderSeries(false); renderDispositivos();
    conectar();
  });

  // ---------------------------------------------------------------
  // Início
  // ---------------------------------------------------------------
  renderSeries(false);
  setInterval(atualizarTempo, 1000);
  if (typeof mqtt === "undefined") {
    setPill(el.pillBroker, "off", "MQTT.js não carregou (sem internet?)");
  } else {
    conectar();
  }
})();
