import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { acompanharOperacao, criarClienteApi, criarPollerSerial, esperar } from "../../../src/presentation/web/static/api.mjs";
import { CameraError, criarControladorCamera } from "../../../src/presentation/web/static/camera.mjs";
import {
  criarVisualizadorLandmarks,
  desenharLandmarks,
} from "../../../src/presentation/web/static/landmarks.mjs";
import { iniciarCursorMagnetico } from "../../../src/presentation/web/static/magnetic_cursor.mjs";
import { iniciarRevelacaoScroll } from "../../../src/presentation/web/static/scroll_reveal.mjs";
import {
  caminhoParaNovoAcessoPublico,
  limparSolicitacaoPublica,
  registrarTokenCompartilhado,
} from "../../../src/presentation/web/static/public_link_session.mjs";
import {
  periodoSessao,
  resumoTentativas,
  situacaoSessao,
} from "../../../src/presentation/web/static/sessoes.mjs";

test("sessões resumem tentativas em linguagem comum, sem JSON", () => {
  assert.equal(resumoTentativas({ concluida: 1 }), "Tentativas: 1 confirmada");
  assert.equal(
    resumoTentativas({ iniciada: 1, processando: 2, concluida: 3, rejeitada: 1, expirada: 0 }),
    "Tentativas: 3 em andamento · 3 confirmadas · 1 recusada",
  );
  assert.equal(resumoTentativas({}), "Nenhuma tentativa de verificação ainda.");
  assert.equal(resumoTentativas(undefined), "Nenhuma tentativa de verificação ainda.");
});

test("sessões informam situação e período legíveis", () => {
  const agora = new Date(2026, 9, 22, 12, 0);
  const sessao = (inicio, fim, revogada = false) => ({
    inicio_em: inicio.toISOString(), fim_em: fim.toISOString(), revogada,
  });
  const manha = new Date(2026, 9, 22, 8, 20);
  const noite = new Date(2026, 9, 22, 20, 25);

  assert.equal(situacaoSessao(sessao(manha, noite), agora), "Aberta agora");
  assert.equal(situacaoSessao(sessao(manha, noite, true), agora), "Revogada");
  assert.equal(situacaoSessao(sessao(manha, new Date(2026, 9, 22, 9, 0)), agora), "Encerrada");
  assert.equal(situacaoSessao(sessao(noite, new Date(2026, 9, 22, 22, 0)), agora), "Agendada");
  assert.equal(periodoSessao(manha.toISOString(), noite.toISOString()), "22/10/2026 · 08:20 – 20:25");
  assert.equal(
    periodoSessao(manha.toISOString(), new Date(2026, 9, 23, 10, 0).toISOString()),
    "22/10/2026 08:20 – 23/10/2026 10:00",
  );
});

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

test("novo cadastro preserva o link compartilhado e descarta a solicitacao anterior", () => {
  const estadoInicial = {
    "cadastro.token_link": "convite-da-turma",
    "cadastro.credencial": "credencial-da-aluna-anterior",
    "cadastro.id": 41,
    "cadastro.desafio": { nonce: "desafio-anterior" },
    "cadastro.idempotency": "idempotencia-anterior",
    "presenca.credencial": "nao-deve-ser-alterada",
  };

  const comLink = registrarTokenCompartilhado(estadoInicial, "cadastro", "convite-da-turma");
  const proximo = limparSolicitacaoPublica(comLink, "cadastro");

  assert.deepEqual(proximo, {
    "cadastro.token_link": "convite-da-turma",
    "presenca.credencial": "nao-deve-ser-alterada",
  });
  assert.equal(caminhoParaNovoAcessoPublico(proximo, "cadastro"), "/cadastro/convite-da-turma");
});

test("guia de landmarks desenha apenas os pontos locais detectados", () => {
  const operacoes = [];
  const contexto = {
    clearRect: (...args) => operacoes.push(["clearRect", ...args]),
    beginPath: () => operacoes.push(["beginPath"]),
    arc: (...args) => operacoes.push(["arc", ...args]),
    fill: () => operacoes.push(["fill"]),
  };
  const canvas = { width: 200, height: 100, getContext: () => contexto };

  const quantidade = desenharLandmarks(canvas, [[{ x: 0.25, y: 0.5 }, { x: 0.75, y: 0.5 }]]);

  assert.equal(quantidade, 1);
  assert.deepEqual(operacoes.filter(([nome]) => nome === "arc"), [
    ["arc", 50, 50, 1.6, 0, Math.PI * 2],
    ["arc", 150, 50, 1.6, 0, Math.PI * 2],
  ]);
});

test("guia de landmarks usa CPU para funcionar sem aceleração gráfica", async () => {
  let opcoes;
  const visualizador = criarVisualizadorLandmarks({
    carregar: async () => ({
      FilesetResolver: { forVisionTasks: async () => ({}) },
      FaceLandmarker: {
        createFromOptions: async (_vision, options) => {
          opcoes = options;
          return { close() {} };
        },
      },
    }),
  });
  const canvas = { width: 0, height: 0, getContext: () => ({ clearRect() {} }) };

  await visualizador.iniciar({ isConnected: false }, canvas);

  assert.equal(opcoes.baseOptions.delegate, "CPU");
});

test("cliente API mostra mensagem e código estáveis enviados pelo servidor", async () => {
  const api = criarClienteApi({
    fetchImpl: async () => new Response(JSON.stringify({
      codigo: "credenciais_invalidas",
      mensagem: "Usuário ou senha inválidos.",
      request_id: "request-sintetico",
    }), {
      status: 401,
      headers: { "content-type": "application/json" },
    }),
  });

  await assert.rejects(api.post("/api/v1/auth/login", {}), (error) => {
    assert.equal(error.status, 401);
    assert.equal(error.code, "credenciais_invalidas");
    assert.equal(error.message, "Usuário ou senha inválidos.");
    return true;
  });
});

test("cliente API usa fallback de autenticação, não mensagem de link", async () => {
  const api = criarClienteApi({
    fetchImpl: async () => new Response(null, { status: 401 }),
  });

  await assert.rejects(api.post("/api/v1/auth/login", {}), (error) => {
    assert.equal(error.message, "Não foi possível autenticar. Confira os dados e tente novamente.");
    assert.equal(error.code, "autenticacao_necessaria");
    return true;
  });
});

test("cliente API usa códigos estáveis nos fallbacks HTTP", async () => {
  const codigosEsperados = new Map([
    [400, "requisicao_invalida"],
    [401, "autenticacao_necessaria"],
    [403, "operacao_nao_autorizada"],
    [404, "recurso_nao_encontrado"],
    [405, "metodo_nao_permitido"],
    [409, "conflito_estado"],
    [410, "acesso_expirado"],
    [413, "conteudo_excedeu_limite"],
    [415, "tipo_midia_nao_suportado"],
    [422, "requisicao_invalida"],
    [429, "limite_requisicoes"],
    [500, "erro_interno"],
    [502, "servico_indisponivel"],
    [503, "servico_indisponivel"],
    [504, "servico_indisponivel"],
  ]);

  for (const [status, codigo] of codigosEsperados) {
    const api = criarClienteApi({
      fetchImpl: async () => new Response(null, { status }),
    });
    await assert.rejects(api.get("/api/v1/recurso"), (error) => {
      assert.equal(error.status, status);
      assert.equal(error.code, codigo);
      assert.ok(error.message.length > 0);
      return true;
    });
  }
});

test("poller usa intervalo de 15 segundos e não sobrepõe leituras", async () => {
  const primeira = deferred();
  let chamadas = 0;
  let callback;
  const atualizadas = [];
  const poller = criarPollerSerial(() => {
    chamadas += 1;
    return primeira.promise;
  }, {
    setIntervalFn(fn, ms) { callback = fn; assert.equal(ms, 15000); return 1; },
    clearIntervalFn() {},
    aoAtualizar: (valor) => atualizadas.push(valor),
  });

  poller.iniciar();
  await Promise.resolve();
  callback();
  assert.equal(chamadas, 1);
  primeira.resolve({ atualizado_em: "2026-10-20T12:00:00Z" });
  await poller.atualizar();
  assert.equal(atualizadas.length, 1);
  assert.equal(atualizadas[0].atualizado_em, "2026-10-20T12:00:00Z");
  poller.parar();
});

test("acompanhamento de operação usa backoff e para no estado terminal", async () => {
  const esperas = [];
  let chamadas = 0;
  const estado = await acompanharOperacao(async () => {
    chamadas += 1;
    return { estado: chamadas === 3 ? "concluida" : "processando" };
  }, {
    concluida: (valor) => valor.estado === "concluida",
    intervaloInicialMs: 250,
    intervaloMaximoMs: 1000,
    aguardar: async (ms) => esperas.push(ms),
  });

  assert.equal(estado.estado, "concluida");
  assert.deepEqual(esperas, [250, 500]);
});

test("cancelar o acompanhamento limpa a espera e impede novas consultas", async () => {
  const controller = new AbortController();
  let chamadas = 0;
  const consulta = acompanharOperacao(async () => {
    chamadas += 1;
    return { estado: "processando" };
  }, { concluida: () => false, intervaloInicialMs: 60000, signal: controller.signal });
  await Promise.resolve();
  await Promise.resolve();
  controller.abort(new DOMException("cancelada", "AbortError"));
  await assert.rejects(consulta, { name: "AbortError" });
  assert.ok(chamadas <= 1);

  const esperaController = new AbortController();
  const espera = esperar(60000, esperaController.signal);
  esperaController.abort(new DOMException("cancelada", "AbortError"));
  await assert.rejects(espera, { name: "AbortError" });
});

test("câmera limita a imagem enviada e encerra todas as tracks", async () => {
  const tracks = [{ stopped: false, stop() { this.stopped = true; } }];
  const stream = { getTracks: () => tracks };
  const constraints = [];
  const mediaDevices = {
    async getUserMedia(value) { constraints.push(value.video); return stream; },
    async enumerateDevices() { return [{ kind: "videoinput", deviceId: "camera-1" }]; },
  };
  const camera = criarControladorCamera({ mediaDevices });
  const video = {
    readyState: 2,
    videoWidth: 1920,
    videoHeight: 1080,
    srcObject: null,
    async play() {},
  };
  let desenhada;
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => ({ drawImage: (...args) => { desenhada = args; } }),
    toDataURL: () => "data:image/jpeg;base64,c3ludGhldGljYQ==",
  };

  await camera.iniciar(video);
  assert.equal(constraints[0].facingMode, "user");
  const captura = camera.capturar(video, canvas);
  assert.deepEqual([captura.largura, captura.altura], [960, 540]);
  assert.equal(captura.base64, "c3ludGhldGljYQ==");
  assert.equal(desenhada[0], video);
  assert.deepEqual(await camera.enumerar(), [{ kind: "videoinput", deviceId: "camera-1" }]);
  await camera.iniciar(video, "camera-1");
  assert.deepEqual(constraints[1].deviceId, { exact: "camera-1" });
  assert.equal("facingMode" in constraints[1], false);
  camera.encerrar(video);
  assert.equal(tracks[0].stopped, true);
  assert.equal(video.srcObject, null);
});

test("câmera traduz indisponibilidade sem ocultar o controle acessível", async () => {
  const camera = criarControladorCamera({ mediaDevices: {
    async getUserMedia() { throw Object.assign(new Error(), { name: "NotAllowedError" }); },
  } });
  await assert.rejects(camera.iniciar({ srcObject: null }), (error) => {
    assert.ok(error instanceof CameraError);
    assert.equal(error.code, "negada");
    return true;
  });
});

test("revelações de scroll aparecem ao entrar na viewport e limpam o observer", () => {
  const primeiro = criarAlvo();
  const segundo = criarAlvo();
  const classesContainer = new Set();
  const container = {
    defaultView: { matchMedia: () => ({ matches: false }) },
    classList: {
      add: (classe) => classesContainer.add(classe),
      remove: (classe) => classesContainer.delete(classe),
      contains: (classe) => classesContainer.has(classe),
    },
    querySelectorAll: () => [primeiro, segundo],
  };
  let callback;
  let observados = [];
  let desconectado = false;
  class ObserverFake {
    constructor(onChange) { callback = onChange; }
    observe(alvo) { observados.push(alvo); }
    unobserve(alvo) { observados = observados.filter((item) => item !== alvo); }
    disconnect() { desconectado = true; observados = []; }
  }
  container.defaultView.IntersectionObserver = ObserverFake;

  const parar = iniciarRevelacaoScroll(container);
  assert.equal(container.classList.contains("scroll-reveal-ready"), true);
  assert.deepEqual(observados, [primeiro, segundo]);
  callback([{ target: primeiro, isIntersecting: true }]);
  assert.equal(primeiro.classList.contains("is-visible"), true);
  assert.deepEqual(observados, [segundo]);
  parar();
  assert.equal(desconectado, true);
  assert.equal(container.classList.contains("scroll-reveal-ready"), false);
  assert.equal(primeiro.classList.contains("is-visible"), false);
});

test("revelações incluem os contêineres que animam a passagem entre seções", () => {
  const fluxo = criarAlvo();
  const perguntas = criarAlvo();
  let seletorUsado = "";
  const container = {
    defaultView: { matchMedia: () => ({ matches: false }) },
    classList: { add() {}, remove() {} },
    querySelectorAll(seletor) {
      seletorUsado = seletor;
      return [fluxo, perguntas];
    },
  };
  let callback;
  class ObserverFake {
    constructor(onChange) { callback = onChange; }
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  container.defaultView.IntersectionObserver = ObserverFake;

  iniciarRevelacaoScroll(container);

  assert.match(seletorUsado, /#como-funciona \.steps/);
  assert.match(seletorUsado, /#duvidas \.faq-list/);
  callback([{ target: fluxo, isIntersecting: true }, { target: perguntas, isIntersecting: true }]);
  assert.equal(fluxo.classList.contains("is-visible"), true);
  assert.equal(perguntas.classList.contains("is-visible"), true);
});

test("revelações permanecem visíveis quando movimento reduzido está ativo", () => {
  const classesContainer = new Set();
  const container = {
    defaultView: { matchMedia: () => ({ matches: true }) },
    classList: {
      add: (classe) => classesContainer.add(classe),
      remove: (classe) => classesContainer.delete(classe),
      contains: (classe) => classesContainer.has(classe),
    },
    querySelectorAll: () => [criarAlvo()],
  };

  const parar = iniciarRevelacaoScroll(container);
  assert.equal(container.classList.contains("scroll-reveal-ready"), false);
  parar();
});

test("ornamento do fluxo não ultrapassa horizontalmente a seção", () => {
  const css = readFileSync(new URL("../../../src/presentation/web/static/app.css", import.meta.url), "utf8");
  const ornamento = css.match(/#como-funciona::before \{([\s\S]*?)\n\}/)?.[1] || "";

  assert.doesNotMatch(ornamento, /right:\s*-/);
});

test("cursor magnetico acompanha o mouse, reage aos alvos e limpa recursos", () => {
  const ambiente = criarAmbienteCursor();
  const parar = iniciarCursorMagnetico(ambiente.documento);

  assert.equal(ambiente.cursor.atributos["aria-hidden"], "true");
  assert.equal(ambiente.documento.body.children.includes(ambiente.cursor), true);
  ambiente.documento.disparar("pointermove", {
    pointerType: "touch", clientX: 12, clientY: 18,
  });
  assert.equal(ambiente.cursor.animacoes.length, 0);
  ambiente.alvo.disparar("pointerenter", { pointerType: "touch" });
  assert.equal(ambiente.cursor.classList.contains("is-attracted"), false);

  ambiente.documento.disparar("pointermove", {
    pointerType: "mouse", clientX: 84, clientY: 36,
  });
  ambiente.executarFrame();
  assert.equal(ambiente.cursor.classList.contains("is-visible"), true);
  assert.match(
    ambiente.cursor.animacoes[0].keyframes.at(-1).transform,
    /84px.*36px/,
  );
  const xSemAtracao = extrairCoordenadaX(ambiente.cursor.animacoes.at(-1));

  ambiente.alvo.disparar("pointerenter", { pointerType: "mouse" });
  assert.equal(ambiente.cursor.classList.contains("is-attracted"), true);
  ambiente.documento.disparar("pointermove", {
    pointerType: "mouse", clientX: 84, clientY: 36,
  });
  ambiente.executarFrame();
  const xComAtracao = extrairCoordenadaX(ambiente.cursor.animacoes.at(-1));
  assert.ok(xComAtracao > xSemAtracao);
  assert.ok(xComAtracao < 100);
  assert.equal(ambiente.cursor.animacoes.length, 1);
  ambiente.alvo.disparar("pointerleave", { pointerType: "mouse" });
  assert.equal(ambiente.cursor.classList.contains("is-attracted"), false);

  parar();
  assert.equal(ambiente.documento.body.children.includes(ambiente.cursor), false);
  assert.equal(ambiente.cursor.animacoes[0].cancelada, true);
});

test("cursor magnetico fica desativado em toque ou movimento reduzido", () => {
  for (const preferencias of [{ coarse: true }, { reduzido: true }]) {
    const ambiente = criarAmbienteCursor(preferencias);
    const parar = iniciarCursorMagnetico(ambiente.documento);
    assert.equal(ambiente.criouCursor, false);
    parar();
  }
});

function criarAmbienteCursor({ coarse = false, reduzido = false } = {}) {
  const criarClasses = () => {
    const valores = new Set();
    return {
      add: (valor) => valores.add(valor),
      remove: (valor) => valores.delete(valor),
      contains: (valor) => valores.has(valor),
    };
  };
  const criarEventos = () => {
    const listeners = new Map();
    return {
      addEventListener(tipo, callback) {
        listeners.set(tipo, [...(listeners.get(tipo) || []), callback]);
      },
      disparar(tipo, evento = {}) {
        for (const callback of listeners.get(tipo) || []) callback(evento);
      },
    };
  };
  const cursor = {
    atributos: {},
    animacoes: [],
    classList: criarClasses(),
    setAttribute(chave, valor) { this.atributos[chave] = valor; },
    animate(keyframes, options) {
      const animacao = {
        cancelada: false,
        currentTime: 0,
        keyframes,
        options,
        effect: { setKeyframes(proximos) { animacao.keyframes = proximos; } },
        cancel() { this.cancelada = true; },
      };
      this.animacoes.push(animacao);
      return animacao;
    },
    remove() {
      this.removido = true;
      const indice = this.parentNode?.children.indexOf(this) ?? -1;
      if (indice >= 0) this.parentNode.children.splice(indice, 1);
    },
  };
  const alvo = {
    ...criarEventos(),
    getBoundingClientRect() { return { left: 80, top: 20, width: 40, height: 40 }; },
  };
  let frame;
  let criouCursor = false;
  const documento = {
    ...criarEventos(),
    body: {
      children: [],
      appendChild(elemento) { elemento.parentNode = this; this.children.push(elemento); },
    },
    createElement() { criouCursor = true; return cursor; },
    querySelectorAll() { return [alvo]; },
    defaultView: {
      ...criarEventos(),
      matchMedia(query) {
        return { matches: query.includes("prefers-reduced-motion") ? reduzido : !coarse };
      },
      requestAnimationFrame(callback) { frame = callback; return 1; },
      cancelAnimationFrame() { frame = null; },
    },
  };
  return {
    documento,
    cursor,
    alvo,
    get criouCursor() { return criouCursor; },
    executarFrame() { frame?.(); },
  };
}

function extrairCoordenadaX(animacao) {
  const transform = animacao.keyframes.at(-1).transform;
  return Number(/translate3d\(([-\d.]+)px/.exec(transform)?.[1]);
}

function criarAlvo() {
  const classes = new Set();
  return {
    classList: {
      add: (...nomes) => nomes.forEach((nome) => classes.add(nome)),
      remove: (...nomes) => nomes.forEach((nome) => classes.delete(nome)),
      contains: (classe) => classes.has(classe),
    },
  };
}

test("shell da interface monta landing e login em um navegador sintético", async () => {
  const anteriores = Object.fromEntries(["document", "window", "location", "sessionStorage", "fetch"].map((chave) => [chave, globalThis[chave]]));
  const raiz = { innerHTML: "", setAttribute() {}, querySelector() { return null; } };
  const armazenamento = new Map();
  const fakeDocument = {
    hidden: false,
    defaultView: { matchMedia: () => ({ matches: false }) },
    querySelector(seletor) { return seletor === "#app" ? raiz : null; },
    querySelectorAll() { return []; },
    addEventListener() {},
  };
  globalThis.document = fakeDocument;
  globalThis.window = { scrollTo() {}, addEventListener() {} };
  globalThis.location = { pathname: "/", search: "", origin: "http://localhost", href: "http://localhost/", replace() {}, assign() {} };
  globalThis.sessionStorage = {
    getItem(chave) { return armazenamento.get(chave) ?? null; },
    setItem(chave, valor) { armazenamento.set(chave, valor); },
  };
  globalThis.fetch = async (url) => {
    if (["/trocar-senha", "/professor", "/professor/turmas/1"].includes(globalThis.location.pathname) && String(url).endsWith("/api/v1/me")) {
      return new Response(JSON.stringify({ id: 2, usuario: "professor.teste", papel: "professor", troca_senha_obrigatoria: false }), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    }
    if (["/trocar-senha", "/professor", "/professor/turmas/1"].includes(globalThis.location.pathname) && String(url).endsWith("/api/v1/auth/csrf")) {
      return new Response(JSON.stringify({ csrf_token: "teste" }), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    }
    if (globalThis.location.pathname === "/professor" && String(url).endsWith("/api/v1/turmas")) {
      const turmas = ["?view=presencas", "?view=turmas"].includes(globalThis.location.search)
        ? [{ id: 1, materia: "IA Aplicada", periodo: "noturno", responsavel_professor_id: 2 }]
        : [];
      return new Response(JSON.stringify(turmas), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    }
    if (globalThis.location.pathname === "/professor/turmas/1" && String(url).endsWith("/api/v1/turmas")) {
      return new Response(JSON.stringify([{
        id: 1, materia: "IA Aplicada", periodo: "noturno", responsavel_professor_id: 2,
      }]), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (globalThis.location.pathname === "/professor/turmas/1" && String(url).endsWith("/api/v1/turmas/1/alunos")) {
      return new Response(JSON.stringify([]), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify({ mensagem: "Sessão ausente" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const modulo = new URL("../../../src/presentation/web/static/app.mjs", import.meta.url).href;
    await import(`${modulo}?landing-smoke=${Date.now()}`);
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(raiz.innerHTML, /Presença, no seu tempo de aula/);
    assert.match(raiz.innerHTML, /id="duvidas"/);
    assert.match(raiz.innerHTML, /assets\/img\/hero-section-img\.jpg/);
    assert.match(raiz.innerHTML, /assets\/img\/logo\.png/);
    assert.doesNotMatch(raiz.innerHTML, /wordmark__symbol/);
    assert.doesNotMatch(raiz.innerHTML, /id="hero-particles"/);
    assert.match(raiz.innerHTML, /class="mobile-nav__icon"/);
    assert.doesNotMatch(raiz.innerHTML, /<span aria-hidden="true">Menu<\/span>/);

    globalThis.location.pathname = "/login";
    globalThis.location.href = "http://localhost/login";
    await import(`${modulo}?login-smoke=${Date.now()}`);
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(raiz.innerHTML, /data-form="login"/);
    assert.match(raiz.innerHTML, /autocomplete="username"/);
    assert.match(raiz.innerHTML, /class="login-layout login-layout--animated"/);
    assert.match(raiz.innerHTML, /wordmark wordmark--inverse/);
    assert.match(raiz.innerHTML, /assets\/img\/logo-white\.png/);
    assert.match(raiz.innerHTML, /data-magnetic/);

    globalThis.location.pathname = "/trocar-senha";
    globalThis.location.href = "http://localhost/trocar-senha";
    await import(`${modulo}?password-smoke=${Date.now()}`);
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(raiz.innerHTML, /data-form="trocar-senha"/);
    assert.doesNotMatch(raiz.innerHTML, /data-magnetic/);

    globalThis.location.pathname = "/professor";
    globalThis.location.search = "?view=painel";
    globalThis.location.href = "http://localhost/professor?view=painel";
    await import(`${modulo}?professor-smoke=${Date.now()}`);
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(raiz.innerHTML, /page-shell--animated/);
    assert.match(raiz.innerHTML, /assets\/img\/logo\.png/);
    assert.match(
      raiz.innerHTML,
      /class="app-header__user" aria-label="Usuário conectado">professor\.teste<\/span><a class="button button--quiet" href="\/"/,
    );
    assert.match(raiz.innerHTML, /data-reveal/);
    assert.doesNotMatch(raiz.innerHTML, /data-magnetic/);

    globalThis.location.pathname = "/professor";
    globalThis.location.search = "?view=presencas";
    globalThis.location.href = "http://localhost/professor?view=presencas";
    await import(`${modulo}?presencas-smoke=${Date.now()}`);
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(raiz.innerHTML, /data-action="session-new"[^>]*aria-expanded="false"/);
    assert.match(raiz.innerHTML, /<form class="form-grid" data-form="criar-sessao" id="form-nova-sessao" hidden>/);
    assert.match(raiz.innerHTML, /data-session-scheduler/);
    assert.match(raiz.innerHTML, /data-scheduler-calendar/);
    assert.match(raiz.innerHTML, /name="inicio_em"/);
    assert.match(raiz.innerHTML, /name="fim_em"/);
    assert.doesNotMatch(raiz.innerHTML, /type="datetime-local"/);

    globalThis.location.pathname = "/professor";
    globalThis.location.search = "?view=turmas";
    globalThis.location.href = "http://localhost/professor?view=turmas";
    await import(`${modulo}?turmas-smoke=${Date.now()}`);
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(raiz.innerHTML, /data-action="open-delete-class:1"/);
    assert.match(raiz.innerHTML, /<dialog class="confirmation-dialog" data-delete-class-dialog data-id="1"/);
    assert.match(raiz.innerHTML, /data-form="excluir-turma" data-id="1"/);
    assert.match(raiz.innerHTML, /Cancelar/);
    assert.doesNotMatch(raiz.innerHTML, /<details><summary class="button button--quiet">Excluir/);

    globalThis.location.pathname = "/professor/turmas/1";
    globalThis.location.search = "";
    globalThis.location.href = "http://localhost/professor/turmas/1";
    await import(`${modulo}?turma-smoke=${Date.now()}`);
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(raiz.innerHTML, /Vínculos de alunos/);
    assert.match(raiz.innerHTML, /Link de cadastro/);
    assert.doesNotMatch(raiz.innerHTML, /Criar turma/);
  } finally {
    for (const chave of Object.keys(anteriores)) {
      if (anteriores[chave] === undefined) delete globalThis[chave];
      else globalThis[chave] = anteriores[chave];
    }
  }
});
