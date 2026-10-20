/** Efeitos opcionais e confinados à landing page. */

export function iniciarHero(canvas, root = globalThis.document) {
  const contexto = canvas?.getContext?.("2d", { alpha: true });
  if (!contexto) return () => {};
  const reduzido = root.defaultView?.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (reduzido) return () => {};

  let largura = 0;
  let altura = 0;
  let raf = 0;
  let ativo = false;
  let visivel = true;
  let pontos = [];
  let ponteiro = null;
  let observer = null;
  let resizeObserver = null;
  const abort = new AbortController();

  function dimensionar() {
    const caixa = canvas.getBoundingClientRect();
    largura = Math.max(1, caixa.width);
    altura = Math.max(1, caixa.height);
    const dpr = Math.min(root.defaultView?.devicePixelRatio || 1, 2);
    canvas.width = Math.round(largura * dpr);
    canvas.height = Math.round(altura * dpr);
    contexto.setTransform(dpr, 0, 0, dpr, 0, 0);
    const quantidade = largura < 640 ? 24 : 60;
    pontos = Array.from({ length: quantidade }, () => ({
      x: Math.random() * largura,
      y: Math.random() * altura,
      vx: (Math.random() - 0.5) * 0.12,
      vy: (Math.random() - 0.5) * 0.12,
      raio: 0.7 + Math.random() * 1.2,
    }));
  }

  function desenhar() {
    if (!ativo || !visivel || root.hidden) return;
    contexto.clearRect(0, 0, largura, altura);
    const distanciaMaxima = largura < 640 ? 88 : 118;
    for (let indice = 0; indice < pontos.length; indice += 1) {
      const ponto = pontos[indice];
      if (ponteiro) {
        const dx = ponto.x - ponteiro.x;
        const dy = ponto.y - ponteiro.y;
        const distancia = Math.hypot(dx, dy);
        if (distancia < 150) {
          const segura = Math.max(distancia, 0.001);
          ponto.vx += (dx / segura) * 0.012;
          ponto.vy += (dy / segura) * 0.012;
        }
      }
      ponto.x += ponto.vx;
      ponto.y += ponto.vy;
      ponto.vx *= 0.992;
      ponto.vy *= 0.992;
      if (ponto.x < 0 || ponto.x > largura) ponto.vx *= -1;
      if (ponto.y < 0 || ponto.y > altura) ponto.vy *= -1;
      ponto.x = Math.min(largura, Math.max(0, ponto.x));
      ponto.y = Math.min(altura, Math.max(0, ponto.y));

      for (let outroIndice = indice + 1; outroIndice < pontos.length; outroIndice += 1) {
        const outro = pontos[outroIndice];
        const distancia = Math.hypot(ponto.x - outro.x, ponto.y - outro.y);
        if (distancia < distanciaMaxima) {
          const opacidade = Math.min(0.24, Math.max(0, (1 - distancia / distanciaMaxima) * 0.22));
          contexto.strokeStyle = `rgba(255,255,255,${opacidade})`;
          contexto.lineWidth = 0.7;
          contexto.beginPath();
          contexto.moveTo(ponto.x, ponto.y);
          contexto.lineTo(outro.x, outro.y);
          contexto.stroke();
        }
      }
      contexto.fillStyle = "rgba(255,255,255,0.58)";
      contexto.beginPath();
      contexto.arc(ponto.x, ponto.y, ponto.raio, 0, Math.PI * 2);
      contexto.fill();
    }
    raf = root.defaultView.requestAnimationFrame(desenhar);
  }

  function iniciar() {
    if (ativo || !visivel || root.hidden) return;
    ativo = true;
    raf = root.defaultView.requestAnimationFrame(desenhar);
  }

  function pausar() {
    ativo = false;
    if (raf) root.defaultView.cancelAnimationFrame(raf);
    raf = 0;
  }

  dimensionar();
  if ("ResizeObserver" in root.defaultView) {
    resizeObserver = new root.defaultView.ResizeObserver(dimensionar);
    resizeObserver.observe(canvas);
  } else {
    root.defaultView.addEventListener("resize", dimensionar, { signal: abort.signal });
  }
  if ("IntersectionObserver" in root.defaultView) {
    observer = new root.defaultView.IntersectionObserver(([entrada]) => {
      visivel = entrada.isIntersecting;
      if (visivel) iniciar();
      else pausar();
    });
    observer.observe(canvas);
  }
  root.addEventListener("visibilitychange", () => {
    if (root.hidden) pausar();
    else iniciar();
  }, { signal: abort.signal });
  canvas.addEventListener("pointermove", (evento) => {
    const caixa = canvas.getBoundingClientRect();
    ponteiro = { x: evento.clientX - caixa.left, y: evento.clientY - caixa.top };
  }, { signal: abort.signal });
  canvas.addEventListener("pointerleave", () => { ponteiro = null; }, { signal: abort.signal });
  iniciar();

  return () => {
    pausar();
    abort.abort();
    observer?.disconnect();
    resizeObserver?.disconnect();
    contexto.clearRect(0, 0, largura, altura);
    pontos = [];
  };
}

export function iniciarMagnetismo(root = globalThis.document) {
  const janela = root.defaultView;
  if (!janela?.matchMedia?.("(hover: hover) and (pointer: fine)").matches
      || janela.matchMedia("(prefers-reduced-motion: reduce)").matches) return () => {};
  const abort = new AbortController();
  const alvos = root.querySelectorAll("[data-magnetic]");
  const animations = new WeakMap();
  const mover = (rotulo, x, y) => {
    animations.get(rotulo)?.cancel();
    const animation = rotulo.animate(
      [{ transform: "translate(0, 0)" }, { transform: `translate(${x}px, ${y}px)` }],
      { duration: 140, easing: "ease-out", fill: "forwards" },
    );
    animations.set(rotulo, animation);
  };
  for (const alvo of alvos) {
    const rotulo = alvo.querySelector(".magnetic-label") || alvo;
    alvo.addEventListener("pointermove", (evento) => {
      const caixa = alvo.getBoundingClientRect();
      const dx = Math.max(-12, Math.min(12, (evento.clientX - caixa.left - caixa.width / 2) * 0.12));
      const dy = Math.max(-8, Math.min(8, (evento.clientY - caixa.top - caixa.height / 2) * 0.12));
      mover(rotulo, dx, dy);
    }, { signal: abort.signal });
    alvo.addEventListener("pointerleave", () => {
      mover(rotulo, 0, 0);
    }, { signal: abort.signal });
  }
  return () => {
    abort.abort();
    for (const alvo of alvos) {
      const rotulo = alvo.querySelector(".magnetic-label") || alvo;
      animations.get(rotulo)?.cancel();
    }
  };
}
