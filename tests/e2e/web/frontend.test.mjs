import assert from "node:assert/strict";
import test from "node:test";

import { acompanharOperacao, criarPollerSerial, esperar } from "../../../src/presentation/web/static/api.mjs";
import { CameraError, criarControladorCamera } from "../../../src/presentation/web/static/camera.mjs";
import { iniciarRevelacaoScroll } from "../../../src/presentation/web/static/scroll_reveal.mjs";

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

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
  const raiz = { innerHTML: "", setAttribute() {} };
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
  globalThis.fetch = async () => new Response(JSON.stringify({ mensagem: "Sessão ausente" }), {
    status: 401,
    headers: { "Content-Type": "application/json" },
  });

  try {
    const modulo = new URL("../../../src/presentation/web/static/app.mjs", import.meta.url).href;
    await import(`${modulo}?landing-smoke=${Date.now()}`);
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(raiz.innerHTML, /Presença, no seu tempo de aula/);
    assert.match(raiz.innerHTML, /id="duvidas"/);

    globalThis.location.pathname = "/login";
    globalThis.location.href = "http://localhost/login";
    await import(`${modulo}?login-smoke=${Date.now()}`);
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(raiz.innerHTML, /data-form="login"/);
    assert.match(raiz.innerHTML, /autocomplete="username"/);
  } finally {
    for (const chave of Object.keys(anteriores)) {
      if (anteriores[chave] === undefined) delete globalThis[chave];
      else globalThis[chave] = anteriores[chave];
    }
  }
});
