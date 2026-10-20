/** Acrescenta um halo visual ao cursor nativo somente na landing. */
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

  function ocultar() {
    if (frame) janela.cancelAnimationFrame(frame);
    frame = 0;
    ponteiro = null;
    animation?.cancel();
    animation = null;
    cursor.classList.remove("is-visible");
    cursor.classList.remove("is-attracted");
  }

  function posicionar() {
    frame = 0;
    if (!ponteiro) return;
    animation?.cancel();
    const transform = `translate3d(${ponteiro.x}px, ${ponteiro.y}px, 0) translate(-50%, -50%)`;
    animation = cursor.animate(
      [{ transform }],
      { duration: 1, fill: "forwards" },
    );
    cursor.classList.add("is-visible");
  }

  documento.addEventListener("pointermove", (evento) => {
    if (evento.pointerType && evento.pointerType !== "mouse") return;
    ponteiro = { x: evento.clientX, y: evento.clientY };
    if (!frame) frame = janela.requestAnimationFrame(posicionar);
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
        cursor.classList.add("is-attracted");
      }
    }, { signal: abort.signal });
    alvo.addEventListener("pointerleave", () => {
      cursor.classList.remove("is-attracted");
    }, { signal: abort.signal });
  }

  return () => {
    abort.abort();
    ocultar();
    cursor.remove();
  };
}
