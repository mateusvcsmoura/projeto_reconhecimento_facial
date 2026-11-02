/** Captura local transitória; não escreve frames em storage. */

export class CameraError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "CameraError";
    this.code = code;
  }
}

function traduzirErro(error) {
  if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
    return new CameraError("negada", "A câmera não foi autorizada. Libere a permissão no navegador para continuar.");
  }
  if (error?.name === "NotFoundError" || error?.name === "DevicesNotFoundError") {
    return new CameraError("ausente", "Nenhuma câmera disponível foi encontrada neste dispositivo.");
  }
  if (error?.name === "NotReadableError" || error?.name === "TrackStartError") {
    return new CameraError("ocupada", "A câmera está em uso por outro aplicativo. Feche-o e tente novamente.");
  }
  if (error?.name === "OverconstrainedError") {
    return new CameraError("dispositivo", "A câmera escolhida não está disponível. Selecione outra câmera.");
  }
  return new CameraError("indisponivel", "Não foi possível iniciar a câmera. Confira as permissões e tente novamente.");
}

/**
 * Flash frontal: tela branca ilumina o rosto enquanto `acao` captura o quadro.
 * ponytail: espera fixa para a exposição automática da câmera se ajustar;
 * medir o brilho do quadro até estabilizar se 1 s não bastar em algum aparelho.
 */
export async function comFlashFrontal(acao, {
  documento = globalThis.document,
  esperaMs = 1000,
  aguardar = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); }),
} = {}) {
  const tela = documento.createElement("div");
  tela.className = "flash-frontal";
  tela.setAttribute("aria-hidden", "true");
  documento.body.append(tela);
  try {
    await aguardar(esperaMs);
    return await acao();
  } finally {
    tela.remove();
  }
}

export function criarControladorCamera({ mediaDevices = globalThis.navigator?.mediaDevices } = {}) {
  let stream = null;

  async function iniciar(video, deviceId = null) {
    if (!mediaDevices || typeof mediaDevices.getUserMedia !== "function") {
      throw new CameraError("ambiente", "A câmera exige HTTPS ou localhost e um navegador compatível.");
    }
    encerrar(video);
    const videoConstraints = {
      width: { ideal: 960 },
      height: { ideal: 720 },
      ...(deviceId ? { deviceId: { exact: deviceId } } : { facingMode: "user" }),
    };
    try {
      stream = await mediaDevices.getUserMedia({ audio: false, video: videoConstraints });
      video.srcObject = stream;
      await video.play();
      return stream;
    } catch (error) {
      encerrar(video);
      throw traduzirErro(error);
    }
  }

  function capturar(video, canvas, { larguraMaxima = 960, alturaMaxima = 720, qualidade = 0.82 } = {}) {
    if (!stream || video.readyState < 2 || video.videoWidth < 1 || video.videoHeight < 1) {
      throw new CameraError("aguardando", "A imagem da câmera ainda não está pronta. Aguarde e tente novamente.");
    }
    const escala = Math.min(1, larguraMaxima / video.videoWidth, alturaMaxima / video.videoHeight);
    canvas.width = Math.max(1, Math.round(video.videoWidth * escala));
    canvas.height = Math.max(1, Math.round(video.videoHeight * escala));
    const contexto = canvas.getContext("2d", { alpha: false });
    if (!contexto) throw new CameraError("indisponivel", "Não foi possível preparar a captura.");
    contexto.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", qualidade);
    const separador = dataUrl.indexOf(",");
    if (separador < 0) throw new CameraError("indisponivel", "Não foi possível codificar a captura.");
    return {
      dataUrl,
      base64: dataUrl.slice(separador + 1),
      largura: canvas.width,
      altura: canvas.height,
    };
  }

  function enumerar() {
    return mediaDevices?.enumerateDevices
      ? mediaDevices.enumerateDevices().then((itens) => itens.filter((item) => item.kind === "videoinput"))
      : Promise.resolve([]);
  }

  function encerrar(video = null) {
    if (stream) {
      for (const track of stream.getTracks()) track.stop();
      stream = null;
    }
    if (video && video.srcObject) video.srcObject = null;
  }

  return Object.freeze({ iniciar, capturar, enumerar, encerrar, get stream() { return stream; } });
}
