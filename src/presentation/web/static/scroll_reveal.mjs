/** Revela blocos da landing ao alcançarem a viewport, sem controlar a rolagem. */
export function iniciarRevelacaoScroll(conteudo = globalThis.document) {
  const janela = conteudo?.defaultView || globalThis;
  const Observer = janela.IntersectionObserver;
  if (
    !conteudo?.querySelectorAll
    || !Observer
    || janela.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  ) return () => {};

  const alvos = [...conteudo.querySelectorAll(
    ".hero__copy, .hero__art, #como-funciona .section-heading, "
    + "#como-funciona .step, #duvidas .faq-intro, #duvidas .faq-item",
  )];
  if (!alvos.length) return () => {};

  conteudo.classList.add("scroll-reveal-ready");
  for (const alvo of alvos) alvo.classList.add("scroll-reveal");
  const observer = new Observer((entradas) => {
    for (const entrada of entradas) {
      if (!entrada.isIntersecting) continue;
      entrada.target.classList.add("is-visible");
      observer.unobserve(entrada.target);
    }
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });

  for (const alvo of alvos) observer.observe(alvo);

  return () => {
    observer.disconnect();
    conteudo.classList.remove("scroll-reveal-ready");
    for (const alvo of alvos) {
      alvo.classList.remove("scroll-reveal", "is-visible");
    }
  };
}
