/** Cliente HTTP de mesma origem; conserva apenas o CSRF em memória. */

export class ApiError extends Error {
  constructor(message, { status = 0, code = "erro_rede", retryAfter = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

const ERROS_HTTP = {
  400: {
    code: "requisicao_invalida",
    message: "A solicitação contém dados inválidos. Revise e tente novamente.",
  },
  401: {
    code: "autenticacao_necessaria",
    message: "Não foi possível autenticar. Confira os dados e tente novamente.",
  },
  403: {
    code: "operacao_nao_autorizada",
    message: "Você não tem permissão para realizar esta ação.",
  },
  404: {
    code: "recurso_nao_encontrado",
    message: "O recurso solicitado não foi encontrado ou está indisponível.",
  },
  405: {
    code: "metodo_nao_permitido",
    message: "Esta ação não é permitida.",
  },
  409: {
    code: "conflito_estado",
    message: "A operação não pode ser concluída no estado atual.",
  },
  410: {
    code: "acesso_expirado",
    message: "Este acesso expirou. Solicite um novo link.",
  },
  413: {
    code: "conteudo_excedeu_limite",
    message: "O envio excede o limite permitido.",
  },
  415: {
    code: "tipo_midia_nao_suportado",
    message: "O formato enviado não é aceito.",
  },
  422: {
    code: "requisicao_invalida",
    message: "Revise os dados enviados e tente novamente.",
  },
  429: {
    code: "limite_requisicoes",
    message: "Muitas tentativas em pouco tempo. Aguarde e tente novamente.",
  },
  500: {
    code: "erro_interno",
    message: "Ocorreu um erro interno. Tente novamente em instantes.",
  },
  502: {
    code: "servico_indisponivel",
    message: "O serviço está temporariamente indisponível. Tente novamente em instantes.",
  },
  503: {
    code: "servico_indisponivel",
    message: "O serviço está temporariamente indisponível. Tente novamente em instantes.",
  },
  504: {
    code: "servico_indisponivel",
    message: "O serviço está temporariamente indisponível. Tente novamente em instantes.",
  },
};

function erroHttp(status) {
  return ERROS_HTTP[status] || {
    code: "requisicao_recusada",
    message: "A solicitação não foi concluída. Revise os dados e tente novamente.",
  };
}

function mensagemErro(payload, status) {
  if (payload && typeof payload.mensagem === "string" && payload.mensagem.trim()) {
    return payload.mensagem;
  }
  return erroHttp(status).message;
}

export function criarClienteApi({ fetchImpl = globalThis.fetch } = {}) {
  let csrfToken = null;

  async function request(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    const temCorpo = options.body !== undefined && options.body !== null;
    if (temCorpo && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (method !== "GET" && method !== "HEAD" && csrfToken && options.csrf !== false) {
      headers.set("X-CSRF-Token", csrfToken);
    }

    let response;
    try {
      response = await fetchImpl(path, {
        method,
        headers,
        body: temCorpo && typeof options.body !== "string" && !(options.body instanceof FormData)
          ? JSON.stringify(options.body)
          : options.body,
        credentials: "same-origin",
        cache: "no-store",
        signal: options.signal,
      });
    } catch (error) {
      if (error?.name === "AbortError") throw error;
      throw new ApiError("Sem conexão com o servidor. Verifique a rede e tente novamente.");
    }

    if (response.status === 204) return null;
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json().catch(() => null)
      : null;
    if (!response.ok) {
      const espera = Number.parseInt(response.headers.get("retry-after") || "", 10);
      throw new ApiError(mensagemErro(payload, response.status), {
        status: response.status,
        code: typeof payload?.codigo === "string"
          ? payload.codigo
          : erroHttp(response.status).code,
        retryAfter: Number.isFinite(espera) ? espera : null,
      });
    }
    return contentType.includes("application/json") ? payload : response;
  }

  return Object.freeze({
    request,
    get: (path, options) => request(path, { ...options, method: "GET" }),
    post: (path, body, options = {}) => request(path, { ...options, method: "POST", body }),
    patch: (path, body, options = {}) => request(path, { ...options, method: "PATCH", body }),
    delete: (path, body, options = {}) => request(path, { ...options, method: "DELETE", body }),
    setCsrfToken(token) { csrfToken = typeof token === "string" && token ? token : null; },
    clearCsrfToken() { csrfToken = null; },
  });
}

/** Poller serial: mantém uma única leitura simultânea e não muda o foco. */
export function criarPollerSerial(carregar, {
  intervaloMs = 15000,
  setIntervalFn = globalThis.setInterval,
  clearIntervalFn = globalThis.clearInterval,
  aoAtualizar = () => {},
  aoFalhar = () => {},
} = {}) {
  let timer = null;
  let inFlight = null;
  let ativo = true;

  function atualizar() {
    if (!ativo) return Promise.resolve(null);
    if (inFlight) return inFlight;
    inFlight = Promise.resolve()
      .then(carregar)
      .then((valor) => {
        if (ativo) aoAtualizar(valor);
        return valor;
      })
      .catch((erro) => {
        if (ativo) aoFalhar(erro);
        return null;
      })
      .finally(() => { inFlight = null; });
    return inFlight;
  }

  return Object.freeze({
    iniciar() {
      if (timer !== null) return;
      ativo = true;
      void atualizar();
      timer = setIntervalFn(() => { void atualizar(); }, intervaloMs);
    },
    atualizar,
    parar() {
      ativo = false;
      if (timer !== null) clearIntervalFn(timer);
      timer = null;
    },
  });
}

export function esperar(ms, signal, timeoutFn = globalThis.setTimeout) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason || new DOMException("Operação cancelada.", "AbortError"));
      return;
    }
    let id;
    const aoCancelar = () => {
      globalThis.clearTimeout(id);
      signal?.removeEventListener("abort", aoCancelar);
      reject(signal?.reason || new DOMException("Operação cancelada.", "AbortError"));
    };
    id = timeoutFn(() => {
      signal?.removeEventListener("abort", aoCancelar);
      resolve();
    }, ms);
    signal?.addEventListener("abort", aoCancelar, { once: true });
  });
}

/** Backoff limitado para acompanhar uma operação ou tentativa já emitida. */
export async function acompanharOperacao(carregar, {
  concluida,
  intervaloInicialMs = 1000,
  intervaloMaximoMs = 15000,
  signal,
  aoAtualizar = () => {},
  aguardar = esperar,
} = {}) {
  let intervalo = intervaloInicialMs;
  while (!signal?.aborted) {
    const estado = await carregar();
    aoAtualizar(estado);
    if (concluida(estado)) return estado;
    await aguardar(intervalo, signal);
    intervalo = Math.min(intervalo * 2, intervaloMaximoMs);
  }
  throw signal.reason || new DOMException("Operação cancelada.", "AbortError");
}
