/** Horário do agendador: segmentos de hora e minuto escolhidos num mostrador de relógio. */

const PASSO_MINUTOS = 5;
// Fração do raio do mostrador: 00–11 no anel externo e 12–23 no interno, como no relógio 24 h do Android.
const RAIO_ANEL = { externo: 0.8, interno: 0.52 };
const NOMES_PARTE = { hora: "Hora", minuto: "Minutos" };
const pad = (numero) => String(numero).padStart(2, "0");
const ciclo = (numero, total) => ((numero % total) + total) % total;

export function ajustarHorario(valor, parte, passos) {
  const [hora, minuto] = String(valor).split(":").map(Number);
  if (parte === "hora") return `${pad(ciclo(hora + passos, 24))}:${pad(minuto)}`;
  const indice = ciclo(Math.round(minuto / PASSO_MINUTOS) + passos, 60 / PASSO_MINUTOS);
  return `${pad(hora)}:${pad(indice * PASSO_MINUTOS)}`;
}

export function opcoesHorario(parte) {
  return parte === "hora"
    ? Array.from({ length: 24 }, (_, indice) => pad(indice))
    : Array.from({ length: 60 / PASSO_MINUTOS }, (_, indice) => pad(indice * PASSO_MINUTOS));
}

/** Posição de cada valor no mostrador, em % do lado; ângulo 0° às 12 horas, sentido horário. */
export function posicoesRelogio(parte) {
  const arredondar = (numero) => Math.round(numero * 100) / 100;
  return opcoesHorario(parte).map((valor, indice) => {
    const anel = parte === "hora" && indice >= 12 ? "interno" : "externo";
    const angulo = (indice % 12) * 30;
    const raio = RAIO_ANEL[anel] * 50;
    const radianos = (angulo * Math.PI) / 180;
    return { valor, anel, angulo, raio, x: arredondar(50 + raio * Math.sin(radianos)), y: arredondar(50 - raio * Math.cos(radianos)) };
  });
}

const segmento = (parte, rotulo, valor, id) => `<button class="time-picker__segment" type="button" data-time-part="${parte}" aria-expanded="false" aria-controls="${id}-opcoes" aria-label="${NOMES_PARTE[parte]} do ${rotulo}: ${valor}">${valor}</button>`;

/** Vai dentro do card de data: o mostrador abre no próprio card em vez de flutuar e ser cortado. */
export function seletorHorarioMarkup({ id, rotulo, valor, atributo }) {
  const [hora, minuto] = valor.split(":");
  return `<div class="time-picker"><span class="time-picker__label" id="${id}-rotulo">Horário</span><input type="hidden" value="${valor}" ${atributo}><div class="time-picker__value" role="group" aria-labelledby="${id}-rotulo">${segmento("hora", rotulo, hora, id)}<span aria-hidden="true">:</span>${segmento("minuto", rotulo, minuto, id)}</div></div><div class="time-picker__options" id="${id}-opcoes" data-time-options hidden></div>`;
}

/** Cada [data-time-picker] mantém o input oculto e dispara "change", que o agendador já escuta. */
export function iniciarSeletoresHorario(raiz) {
  // Safari não foca botões ao clicar, então o focusout não basta: abrir uma grade fecha as demais.
  const fecharTodos = [];
  raiz.querySelectorAll("[data-time-picker]").forEach((seletor) => {
    const entrada = seletor.querySelector('input[type="hidden"]');
    const opcoes = seletor.querySelector("[data-time-options]");
    const segmentos = [...seletor.querySelectorAll("[data-time-part]")];
    const rotulo = seletor.dataset.rotulo;
    let parteAberta = null;
    const partes = () => entrada.value.split(":");
    const segmentoDe = (parte) => seletor.querySelector(`[data-time-part="${parte}"]`);
    const definir = (valor) => {
      entrada.value = valor;
      const [hora, minuto] = partes();
      for (const item of segmentos) {
        const atual = item.dataset.timePart === "hora" ? hora : minuto;
        item.textContent = atual;
        item.setAttribute("aria-label", `${NOMES_PARTE[item.dataset.timePart]} do ${rotulo}: ${atual}`);
      }
      entrada.dispatchEvent(new Event("change", { bubbles: true }));
    };
    const fechar = () => {
      parteAberta = null;
      opcoes.hidden = true;
      segmentos.forEach((item) => item.setAttribute("aria-expanded", "false"));
    };
    fecharTodos.push(fechar);
    const abrir = (parte) => {
      fecharTodos.forEach((outro) => { if (outro !== fechar) outro(); });
      parteAberta = parte;
      const [hora, minuto] = partes();
      const atual = parte === "hora" ? hora : minuto;
      opcoes.dataset.part = parte;
      const posicoes = posicoesRelogio(parte);
      const unidade = parte === "hora" ? "h" : "min";
      opcoes.innerHTML = `<p class="clock__titulo">${parte === "hora" ? "Escolha a hora" : "Escolha os minutos"}</p><div class="clock" role="group" aria-label="${NOMES_PARTE[parte]} do ${rotulo}"><span class="clock__hand" aria-hidden="true"></span><span class="clock__center" aria-hidden="true"></span>${posicoes.map((item) => `<button class="clock__option clock__option--${item.anel}" type="button" data-time-option="${item.valor}" aria-label="${item.valor} ${unidade}" aria-pressed="${item.valor === atual}">${item.valor}</button>`).join("")}</div>`;
      // A CSP bloqueia style inline no HTML; posições e ponteiro vão pelo CSSOM, que ela permite.
      opcoes.querySelectorAll("[data-time-option]").forEach((botao, indice) => {
        botao.style.left = `${posicoes[indice].x}%`;
        botao.style.top = `${posicoes[indice].y}%`;
      });
      const relogio = opcoes.querySelector(".clock");
      const selecionada = posicoes.find((item) => item.valor === atual);
      if (selecionada) {
        relogio.style.setProperty("--angulo", `${selecionada.angulo}deg`);
        relogio.style.setProperty("--raio", `${selecionada.raio}%`);
      } else relogio.classList.add("clock--sem-ponteiro");
      opcoes.hidden = false;
      segmentos.forEach((item) => item.setAttribute("aria-expanded", String(item.dataset.timePart === parte)));
    };
    seletor.addEventListener("click", (evento) => {
      const opcao = evento.target.closest("[data-time-option]");
      if (opcao) {
        const parte = opcoes.dataset.part;
        const [hora, minuto] = partes();
        definir(parte === "hora" ? `${opcao.dataset.timeOption}:${minuto}` : `${hora}:${opcao.dataset.timeOption}`);
        // Como num relógio de celular: depois da hora, segue direto para os minutos.
        if (parte === "hora") abrir("minuto");
        else fechar();
        segmentoDe("minuto")?.focus();
        return;
      }
      const alvo = evento.target.closest("[data-time-part]");
      if (!alvo) return;
      if (parteAberta === alvo.dataset.timePart) fechar();
      else abrir(alvo.dataset.timePart);
    });
    seletor.addEventListener("keydown", (evento) => {
      if (evento.key === "Escape" && parteAberta) {
        evento.preventDefault();
        const parte = parteAberta;
        fechar();
        segmentoDe(parte)?.focus();
        return;
      }
      const alvo = evento.target.closest("[data-time-part]");
      if (!alvo || (evento.key !== "ArrowUp" && evento.key !== "ArrowDown")) return;
      evento.preventDefault();
      definir(ajustarHorario(entrada.value, alvo.dataset.timePart, evento.key === "ArrowUp" ? 1 : -1));
      if (parteAberta === alvo.dataset.timePart) abrir(parteAberta);
    });
    // Clicar numa célula não tira o foco do segmento; assim o focusout abaixo não fecha a grade antes do clique.
    opcoes.addEventListener("pointerdown", (evento) => evento.preventDefault());
    seletor.addEventListener("focusout", (evento) => {
      if (!seletor.contains(evento.relatedTarget)) fechar();
    });
  });
}
