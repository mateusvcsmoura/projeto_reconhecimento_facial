/** Acrescenta um cursor fluido com contraste invertido à landing e ao login. */
export function iniciarCursorMagnetico(documento = globalThis.document) {
  const janela = documento?.defaultView;
  const noop = () => {};
  if (
    !documento?.body
    || !documento.createElement
    || !documento.querySelectorAll
    || !janela?.requestAnimationFrame
    || !janela.cancelAnimationFrame
  ) return noop;
  const podeHover = janela.matchMedia?.("(hover: hover) and (pointer: fine)")?.matches;
  const movimentoReduzido = janela.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  if (!podeHover || movimentoReduzido) return noop;

  const alvos = [...documento.querySelectorAll("[data-magnetic]")];
  if (!alvos.length) return noop;

  const cursor = documento.createElement("span");
  cursor.className = "magnetic-cursor";
  cursor.setAttribute("aria-hidden", "true");
  documento.body.appendChild(cursor);

  const abort = new AbortController();
  let frame = 0;
  let animation = null;
  let ponteiro = null;
  let posicao = null;
  let velocidade = { x: 0, y: 0 };
  let alvoAtivo = null;

  function ocultar() {
    if (frame) janela.cancelAnimationFrame(frame);
    frame = 0;
    ponteiro = null;
    posicao = null;
    velocidade = { x: 0, y: 0 };
    alvoAtivo = null;
    animation?.cancel();
    animation = null;
    cursor.classList.remove("is-visible");
    cursor.classList.remove("is-attracted");
  }

  function destino() {
    if (!alvoAtivo?.getBoundingClientRect) return ponteiro;
    const caixa = alvoAtivo.getBoundingClientRect();
    const centroX = caixa.left + caixa.width / 2;
    const centroY = caixa.top + caixa.height / 2;
    return {
      x: ponteiro.x + (centroX - ponteiro.x) * 0.55,
      y: ponteiro.y + (centroY - ponteiro.y) * 0.55,
    };
  }

  function agendar() {
    if (!frame) frame = janela.requestAnimationFrame(posicionar);
  }

  function posicionar() {
    frame = 0;
    if (!ponteiro) return;
    const proxima = destino();
    if (!posicao) posicao = { ...ponteiro };
    const dx = proxima.x - posicao.x;
    const dy = proxima.y - posicao.y;
    velocidade.x = (velocidade.x + dx * 0.2) * 0.72;
    velocidade.y = (velocidade.y + dy * 0.2) * 0.72;
    posicao.x += velocidade.x;
    posicao.y += velocidade.y;
    const transform = `translate3d(${posicao.x}px, ${posicao.y}px, 0) translate(-50%, -50%)`;
    if (!animation) {
      animation = cursor.animate([{ transform }], { duration: 1, fill: "forwards" });
    } else {
      animation.effect.setKeyframes([{ transform }]);
    }
    animation.currentTime = 1;
    cursor.classList.add("is-visible");
    if (
      Math.abs(dx) > 0.1
      || Math.abs(dy) > 0.1
      || Math.abs(velocidade.x) > 0.1
      || Math.abs(velocidade.y) > 0.1
    ) {
      agendar();
    }
  }

  documento.addEventListener("pointermove", (evento) => {
    if (evento.pointerType && evento.pointerType !== "mouse") return;
    ponteiro = { x: evento.clientX, y: evento.clientY };
    agendar();
  }, { passive: true, signal: abort.signal });
  documento.addEventListener("pointerout", (evento) => {
    if (!evento.relatedTarget) ocultar();
  }, { signal: abort.signal });
  documento.addEventListener("visibilitychange", () => {
    if (documento.hidden) ocultar();
  }, { signal: abort.signal });
  janela.addEventListener("blur", ocultar, { signal: abort.signal });

  for (const alvo of alvos) {
    alvo.addEventListener("pointerenter", (evento) => {
      if (!evento.pointerType || evento.pointerType === "mouse") {
        alvoAtivo = alvo;
        cursor.classList.add("is-attracted");
        agendar();
      }
    }, { signal: abort.signal });
    alvo.addEventListener("pointerleave", () => {
      if (alvoAtivo === alvo) alvoAtivo = null;
      cursor.classList.remove("is-attracted");
      agendar();
    }, { signal: abort.signal });
  }

  return () => {
    abort.abort();
    ocultar();
    cursor.remove();
  };
}
