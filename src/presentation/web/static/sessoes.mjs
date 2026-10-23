/** Textos das sessões para o professor: sem JSON nem códigos internos na tela. */

// Estados de EstadoTentativaPresenca agrupados como o professor os entende.
const GRUPOS_TENTATIVA = [
  ["em andamento", "em andamento", ["iniciada", "recebida", "enfileirada", "processando"]],
  ["confirmada", "confirmadas", ["concluida"]],
  ["recusada", "recusadas", ["rejeitada"]],
  ["expirada", "expiradas", ["expirada"]],
];

export function resumoTentativas(porEstado = {}) {
  const partes = GRUPOS_TENTATIVA.map(([singular, plural, estados]) => {
    const total = estados.reduce((soma, estado) => soma + (Number(porEstado?.[estado]) || 0), 0);
    return total ? `${total} ${total === 1 ? singular : plural}` : "";
  }).filter(Boolean);
  return partes.length ? `Tentativas: ${partes.join(" · ")}` : "Nenhuma tentativa de verificação ainda.";
}

export function situacaoSessao(sessao, agora = new Date()) {
  if (sessao.revogada) return "Revogada";
  if (new Date(sessao.fim_em) <= agora) return "Encerrada";
  if (new Date(sessao.inicio_em) > agora) return "Agendada";
  return "Aberta agora";
}

// Valores de presencas.origem (CHECK no banco) traduzidos para o professor.
const ORIGEM_PRESENCA = { biometrica: "reconhecimento facial", manual: "revisão do professor", legado: "registro anterior" };

export function linhaPresenca({ status, origem, registrado_em: registradoEm }) {
  const instante = new Date(registradoEm);
  const partes = [
    Number.isNaN(instante.valueOf()) ? "horário indisponível" : new Intl.DateTimeFormat("pt-BR", { timeStyle: "short" }).format(instante),
    ORIGEM_PRESENCA[origem] || origem,
  ];
  if (status === "anulada") partes.push("anulada");
  return partes.join(" · ");
}

export function periodoSessao(inicioIso, fimIso) {
  const inicio = new Date(inicioIso);
  const fim = new Date(fimIso);
  if (Number.isNaN(inicio.valueOf()) || Number.isNaN(fim.valueOf())) return "Período indisponível";
  const data = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" });
  const hora = new Intl.DateTimeFormat("pt-BR", { timeStyle: "short" });
  return data.format(inicio) === data.format(fim)
    ? `${data.format(inicio)} · ${hora.format(inicio)} – ${hora.format(fim)}`
    : `${data.format(inicio)} ${hora.format(inicio)} – ${data.format(fim)} ${hora.format(fim)}`;
}
