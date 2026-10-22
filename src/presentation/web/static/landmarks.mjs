/** Guia visual local; landmarks não são enviados, persistidos ou usados na decisão do servidor. */

const VISION_PACKAGE_URL = "/assets/vendor/mediapipe/vision_bundle.mjs";
const VISION_WASM_URL = "/assets/vendor/mediapipe/wasm";
const MODEL_URL = "/assets/models/face_landmarker.task";

export function desenharLandmarks(canvas, faces = []) {
  const contexto = canvas?.getContext?.("2d");
  if (!contexto) return 0;
  contexto.clearRect(0, 0, canvas.width, canvas.height);
  contexto.fillStyle = "#b9f8f0";
  for (const face of faces) for (const ponto of face) {
    if (!Number.isFinite(ponto?.x) || !Number.isFinite(ponto?.y)) continue;
    contexto.beginPath();
    contexto.arc(ponto.x * canvas.width, ponto.y * canvas.height, 1.6, 0, Math.PI * 2);
    contexto.fill();
  }
  return faces.length;
}

async function carregarVision() {
  return import(VISION_PACKAGE_URL);
}

export function criarVisualizadorLandmarks({ carregar = carregarVision } = {}) {
  let detector = null;
  let frame = null;
  let ativo = false;
  let ultimoProcessamento = 0;
  const limpar = (canvas) => canvas?.getContext?.("2d")?.clearRect(0, 0, canvas.width, canvas.height);
  const encerrar = (canvas) => {
    ativo = false;
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    detector?.close?.();
    detector = null;
    limpar(canvas);
  };

  async function iniciar(video, canvas, informar = () => {}) {
    if (!video || !canvas) return false;
    encerrar(canvas);
    informar("Preparando o guia facial local…");
    try {
      const { FaceLandmarker, FilesetResolver } = await carregar();
      const vision = await FilesetResolver.forVisionTasks(VISION_WASM_URL);
      detector = await FaceLandmarker.createFromOptions(vision, {
        baseOptions: { modelAssetPath: MODEL_URL, delegate: "CPU" }, runningMode: "VIDEO", numFaces: 2,
        minFaceDetectionConfidence: 0.5, minFacePresenceConfidence: 0.5, minTrackingConfidence: 0.5,
      });
      ativo = true;
      const atualizar = (agora) => {
        if (!ativo || !video.isConnected) return;
        frame = requestAnimationFrame(atualizar);
        if (video.readyState < 2 || agora - ultimoProcessamento < 100) return;
        ultimoProcessamento = agora;
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        try {
          const resultado = detector.detectForVideo(video, agora);
          const quantidade = desenharLandmarks(canvas, resultado.faceLandmarks || []);
          if (quantidade === 1) informar("Guia facial: um rosto detectado localmente.", "success");
          else if (quantidade > 1) informar("Guia facial: mantenha apenas um rosto na câmera.", "error");
          else informar("Guia facial: posicione um rosto dentro do enquadramento.");
        } catch {
          limpar(canvas);
          informar("Guia facial temporariamente indisponível. A validação final continua no servidor.", "error");
        }
      };
      frame = requestAnimationFrame(atualizar);
      return true;
    } catch {
      encerrar(canvas);
      informar("Guia facial indisponível neste navegador. A validação final continua no servidor.");
      return false;
    }
  }
  return Object.freeze({ iniciar, encerrar });
}
