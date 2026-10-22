function chave(tipo, sufixo) {
  return `${tipo}.${sufixo}`;
}

/**
 * Guarda o token do convite compartilhado separadamente da credencial curta
 * emitida para uma solicitacao individual.
 */
export function registrarTokenCompartilhado(estado, tipo, token) {
  if (!token) return { ...estado };
  return { ...estado, [chave(tipo, "token_link")]: token };
}

/**
 * Descarta somente o estado transitório de uma pessoa, para que o mesmo
 * convite da turma possa emitir uma nova credencial para o proximo cadastro.
 */
export function limparSolicitacaoPublica(estado, tipo) {
  const token = estado[chave(tipo, "token_link")];
  const proximo = Object.fromEntries(
    Object.entries(estado).filter(([nome]) => !nome.startsWith(`${tipo}.`)),
  );
  return registrarTokenCompartilhado(proximo, tipo, token);
}

export function caminhoParaNovoAcessoPublico(estado, tipo) {
  const token = estado[chave(tipo, "token_link")];
  return typeof token === "string" && token ? `/${tipo}/${encodeURIComponent(token)}` : null;
}
