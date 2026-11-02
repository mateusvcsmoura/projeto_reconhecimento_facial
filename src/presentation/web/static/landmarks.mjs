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

// Mesma geometria do DesafioMovimentoAdapter (servidor: frente <= 0.08, virada
// 0.12–0.50), com folga: o guia só aprova dentro da faixa que o servidor aceita.
const OLHO_A = 33;
const OLHO_B = 263;
const NARIZ = 1;
const FRENTE_MAXIMO = 0.06;
const VIRADA_MINIMA = 0.16;
const VIRADA_MAXIMA = 0.4;
const POSE_CERTA = Object.freeze({ ok: true, dica: "Posição certa. Mantenha assim." });

export function avaliarPose(faces, esperada) {
  if (!["frente", "esquerda", "direita"].includes(esperada)) return null;
  if (faces.length !== 1) {
    return { ok: false, dica: faces.length ? "Mantenha apenas um rosto na câmera." : "Posicione o rosto dentro do enquadramento." };
  }
  const [a, b, nariz] = [faces[0][OLHO_A], faces[0][OLHO_B], faces[0][NARIZ]];
  const distancia = Math.abs(b?.x - a?.x);
  if (!(distancia >= 0.05) || !Number.isFinite(nariz?.x)) return { ok: false, dica: "Aproxime o rosto da câmera." };
  const deslocamento = (nariz.x - (a.x + b.x) / 2) / distancia;
  if (esperada === "frente") {
    return Math.abs(deslocamento) <= FRENTE_MAXIMO ? POSE_CERTA : { ok: false, dica: "Olhe de frente para a câmera, sem inclinar a cabeça." };
  }
  // Frame cru (sem espelho): a esquerda da pessoa leva o nariz para a direita da imagem.
  const giro = esperada === "esquerda" ? deslocamento : -deslocamento;
  if (giro < -FRENTE_MAXIMO) return { ok: false, dica: `Lado oposto: vire a cabeça para a sua ${esperada}.` };
  if (giro < VIRADA_MINIMA) return { ok: false, dica: `Vire a cabeça um pouco mais para a sua ${esperada}.` };
  if (giro > VIRADA_MAXIMA) return { ok: false, dica: "Vire um pouco menos, sem tirar o rosto da câmera." };
  return POSE_CERTA;
}

// Sem um rosto único, mede o centro do quadro, onde o rosto deveria estar.
const REGIAO_CENTRAL = Object.freeze({ x: 0.3, y: 0.2, largura: 0.4, altura: 0.6 });

/** Caixa do rosto (frações do quadro) para medir a luz onde o worker mede. */
export function regiaoMedicaoLuz(faces) {
  const pontos = faces.length === 1 ? faces[0].filter((p) => Number.isFinite(p?.x) && Number.isFinite(p?.y)) : [];
  if (!pontos.length) return REGIAO_CENTRAL;
  const limitar = (valor) => Math.min(1, Math.max(0, valor));
  const x = limitar(Math.min(...pontos.map((p) => p.x)));
  const y = limitar(Math.min(...pontos.map((p) => p.y)));
  const largura = limitar(Math.max(...pontos.map((p) => p.x))) - x;
  const altura = limitar(Math.max(...pontos.map((p) => p.y))) - y;
  return largura > 0 && altura > 0 ? { x, y, largura, altura } : REGIAO_CENTRAL;
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

  // aoDetectar(faces) devolve true quando já cuidou do aviso (guia de pose).
  async function iniciar(video, canvas, informar = () => {}, aoDetectar = () => false) {
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
          const faces = resultado.faceLandmarks || [];
          const quantidade = desenharLandmarks(canvas, faces);
          if (aoDetectar(faces)) return;
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
