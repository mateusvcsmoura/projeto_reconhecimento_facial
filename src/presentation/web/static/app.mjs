import { ApiError, criarClienteApi, criarPollerSerial, acompanharOperacao } from "./api.mjs";
import { criarControladorCamera } from "./camera.mjs";
import { iniciarHero, iniciarMagnetismo } from "./hero.mjs";
import { iniciarCursorMagnetico } from "./magnetic_cursor.mjs";
import { iniciarRevelacaoScroll } from "./scroll_reveal.mjs";

const api = criarClienteApi();
const root = document.querySelector("#app");
const live = document.querySelector("#anuncios");
const camera = criarControladorCamera();
const ESTADO_CHAVE = "facediff.web.v1";
let cleanup = [];
let sessao = null;
let turmaAtual = null;
let carregando = false;

const escapeHtml = (valor) => String(valor ?? "").replace(/[&<>"']/g, (caractere) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[caractere]);
const texto = (valor, fallback = "—") => valor === null || valor === undefined || valor === ""
  ? fallback : escapeHtml(valor);
const dataLocal = (valor) => {
  if (!valor) return "—";
  const data = new Date(valor);
  return Number.isNaN(data.valueOf()) ? escapeHtml(valor) : escapeHtml(data.toLocaleString("pt-BR"));
};
const apiPath = (path) => `/api/v1${path}`;
const mensagem = (valor, tipo = "") => `<div class="notice ${tipo ? `notice--${tipo}` : ""}" role="status">${escapeHtml(valor)}</div>`;
const button = (rotulo, action, extra = "") => `<button class="button ${extra}" type="button" data-action="${escapeHtml(action)}">${escapeHtml(rotulo)}</button>`;
const field = (label, name, attrs = "", hint = "") => `<div class="field"><label for="${escapeHtml(name)}">${escapeHtml(label)}</label><input id="${escapeHtml(name)}" name="${escapeHtml(name)}" ${attrs}>${hint ? `<p class="field-hint">${escapeHtml(hint)}</p>` : ""}</div>`;
const htmlBody = (title, content) => `<div class="page-shell"><header class="app-header"><a class="app-identity" href="/" aria-label="FaceDiff, início"><strong>FaceDiff</strong><span>Presença acadêmica</span></a><div class="app-header__actions"><a class="button button--quiet" href="/">Página inicial</a>${button("Sair", "logout", "button--quiet")}</div></header><div class="app-body"><aside class="app-sidebar"><nav aria-label="Navegação do professor">${navLinks(lerView().view)}</nav></aside><main class="app-main" id="conteudo" tabindex="-1"><div class="page-title"><div><p class="eyebrow">Área do professor</p><h1 tabindex="-1">${escapeHtml(title)}</h1></div></div>${content}</main></div></div>`;

function navLinks(ativo = "painel") {
  const links = [
    ["painel", "Painel"], ["turmas", "Turmas e vínculos"], ["cadastros", "Cadastros"],
    ["presencas", "Sessões e presenças"], ["revisoes", "Revisões"], ["relatorios", "Relatórios CSV"],
  ];
  if (sessao?.papel === "admin") links.push(["administracao", "Administração"]);
  return links.map(([id, nome]) => `<a href="/professor?view=${id}" data-view="${id}" ${id === ativo ? 'aria-current="page"' : ""}>${nome}</a>`).join("");
}

function limparRecursos() {
  for (const liberar of cleanup.splice(0)) {
    try { liberar(); } catch { /* Encerramento best effort dos recursos da tela. */ }
  }
  camera.encerrar(document.querySelector("#camera-video"));
}

function avisar(mensagemTexto) {
  if (live) live.textContent = mensagemTexto;
}

function render(conteudo) {
  limparRecursos();
  root.innerHTML = conteudo;
  root.setAttribute("aria-busy", "false");
  window.scrollTo({ top: 0, behavior: "instant" });
}

function mostrarErro(erro) {
  return erro instanceof ApiError ? erro.message : "Não foi possível concluir a ação. Verifique a conexão e tente novamente.";
}

function formularioErro(container, erro) {
  let area = container.querySelector("[data-form-error]");
  if (!area) {
    area = document.createElement("div");
    area.dataset.formError = "";
    area.className = "notice notice--error error-summary";
    area.tabIndex = -1;
    area.setAttribute("role", "alert");
    container.prepend(area);
  }
  area.textContent = mostrarErro(erro);
  area.focus();
  avisar(area.textContent);
}

function estadoSalvo() {
  try { return JSON.parse(sessionStorage.getItem(ESTADO_CHAVE) || "{}"); }
  catch { return {}; }
}

function salvarEstado(chave, valor) {
  const estado = estadoSalvo();
  if (valor === null || valor === undefined) delete estado[chave];
  else estado[chave] = valor;
  try { sessionStorage.setItem(ESTADO_CHAVE, JSON.stringify(estado)); }
  catch { /* Sessão privada indisponível: continua sem persistência local. */ }
}

function limparEstadoPublico(tipo) {
  const estado = estadoSalvo();
  for (const chave of Object.keys(estado)) if (chave.startsWith(`${tipo}.`)) delete estado[chave];
  try { sessionStorage.setItem(ESTADO_CHAVE, JSON.stringify(estado)); } catch { /* Sem armazenamento local. */ }
}

function cameraMarkup() {
  return `<section class="camera-panel" aria-labelledby="titulo-camera"><h2 id="titulo-camera">Câmera</h2><p>O navegador pedirá permissão quando você iniciar. A imagem fica apenas em memória durante esta etapa.</p><div class="camera-stage camera-stage--mirror"><video id="camera-video" autoplay playsinline muted aria-label="Prévia da câmera"></video><div class="camera-stage__placeholder" id="camera-placeholder"><span class="camera-frame" aria-hidden="true"></span><span>A prévia da câmera aparecerá aqui.</span></div><span class="camera-frame" aria-hidden="true"></span></div><div class="field"><label for="camera-device">Dispositivo de câmera</label><select id="camera-device"><option value="">Câmera padrão</option></select></div><div class="button-row">${button("Iniciar câmera", "camera-start", "button--dark")}${button("Encerrar câmera", "camera-stop", "button--quiet")}</div><canvas id="capture-canvas" class="sr-only" aria-hidden="true"></canvas><p class="field-hint" data-camera-status aria-live="polite">Nenhuma câmera está ativa.</p></section>`;
}

function bindCamera(onCapture, { autoCaptureMs = 3000, onStart = () => {} } = {}) {
  const video = document.querySelector("#camera-video");
  const placeholder = document.querySelector("#camera-placeholder");
  const status = document.querySelector("[data-camera-status]");
  const deviceSelect = document.querySelector("#camera-device");
  if (!video || !status || !deviceSelect) return;
  const captureButton = document.querySelector('[data-action="capture-step"]');
  let automaticTimer = null;
  let capturing = false;
  const setStatus = (value, type = "") => {
    status.className = type ? `notice notice--${type}` : "field-hint";
    status.textContent = value;
  };
  const scheduleAutomaticCapture = () => {
    if (autoCaptureMs === null || !camera.stream || !video.isConnected || capturing || captureButton?.disabled) return;
    clearTimeout(automaticTimer);
    setStatus("Captura automática em 3 segundos. Você também pode capturar antes ou encerrar a câmera.");
    automaticTimer = setTimeout(() => { void takeCapture(); }, autoCaptureMs);
  };
  const takeCapture = async () => {
    clearTimeout(automaticTimer);
    if (capturing || !camera.stream) return;
    capturing = true;
    try {
      const captura = camera.capturar(video, document.querySelector("#capture-canvas"));
      await onCapture(captura);
    } catch (erro) {
      setStatus(erro.message || "A imagem ainda não está pronta.", "error");
    } finally {
      capturing = false;
      if (video.isConnected && camera.stream && !captureButton?.disabled) scheduleAutomaticCapture();
    }
  };
  const start = async () => {
    try {
      await camera.iniciar(video, deviceSelect.value || null);
      const modo = camera.stream?.getVideoTracks?.()[0]?.getSettings?.().facingMode;
      const stage = video.closest(".camera-stage");
      if (modo === "environment" || (!modo && deviceSelect.value)) stage?.classList.remove("camera-stage--mirror");
      else stage?.classList.add("camera-stage--mirror");
      placeholder.hidden = true;
      setStatus("Câmera pronta. Siga a orientação exibida e use o controle de captura.", "success");
      await onStart();
      const devices = await camera.enumerar();
      deviceSelect.replaceChildren(new Option("Câmera padrão", ""));
      devices.forEach((item, index) => deviceSelect.add(new Option(item.label || `Câmera ${index + 1}`, item.deviceId)));
      scheduleAutomaticCapture();
    } catch (erro) {
      setStatus(erro.message || "Não foi possível abrir a câmera.", "error");
      placeholder.hidden = false;
    }
  };
  const stop = () => {
    clearTimeout(automaticTimer);
    camera.encerrar(video);
    placeholder.hidden = false;
    setStatus("Câmera encerrada.");
  };
  document.querySelector('[data-action="camera-start"]')?.addEventListener("click", () => { void start(); });
  document.querySelector('[data-action="camera-stop"]')?.addEventListener("click", stop);
  deviceSelect.addEventListener("change", () => { if (camera.stream) void start(); });
  captureButton?.addEventListener("click", () => { void takeCapture(); });
  cleanup.push(stop);
}

function landing() {
  render(`<header class="site-header"><a class="wordmark" href="/" aria-label="FaceDiff, página inicial"><span class="wordmark__symbol" aria-hidden="true">FD</span><span>FaceDiff</span></a><nav class="site-nav site-nav--desktop" aria-label="Navegação principal"><a href="#como-funciona">Como funciona</a><a href="#duvidas">Dúvidas</a><a class="button button--dark" href="/login" data-magnetic><span class="magnetic-label">Entrar como professor</span></a></nav><details class="mobile-nav"><summary aria-label="Abrir navegação"><span aria-hidden="true">Menu</span></summary><nav class="mobile-nav__panel" aria-label="Navegação compacta"><a href="#como-funciona">Como funciona</a><a href="#duvidas">Dúvidas</a><a href="/login">Entrar como professor</a></nav></details></header><main id="conteudo"><section class="hero" aria-labelledby="hero-title"><div class="hero__copy"><p class="eyebrow eyebrow--inverse">Registro de presença acadêmica</p><h1 id="hero-title">Presença, no seu tempo de aula.</h1><p>O professor compartilha o link. O aluno acessa a câmera e verifica sua presença durante a sessão.</p><div class="hero__actions"><a class="button button--light" href="/login" data-magnetic><span class="magnetic-label">Entrar como professor</span></a><a class="button button--outline-light" href="#como-funciona">Como funciona</a></div><p class="hero__note">Alunos acessam pelos links compartilhados pelo professor.</p></div><div class="hero__art" aria-hidden="true"><canvas id="hero-particles"></canvas></div><div class="hero__frame" aria-hidden="true"><svg viewBox="0 0 64 64" fill="none"><path d="M12 22V12h10M42 12h10v10M52 42v10H42M22 52H12V42" stroke="currentColor" stroke-width="1.4"/><circle cx="32" cy="28" r="8" stroke="currentColor" stroke-width="1.4"/><path d="M18 48c2.4-8 7-12 14-12s11.6 4 14 12" stroke="currentColor" stroke-width="1.4"/></svg></div></section><section class="section wrap" id="como-funciona"><div class="section-heading"><div><p class="eyebrow">Um fluxo simples</p><h2>Da sessão ao registro.</h2></div><p>O painel acompanha o estado informado pelo serviço. A confirmação aparece somente quando o servidor conclui o registro.</p></div><div class="steps"><article class="step"><span class="step__number">01 / PROFESSOR</span><h3>Crie uma sessão</h3><p>Escolha a turma e compartilhe o link com os alunos.</p></article><article class="step"><span class="step__number">02 / ALUNO</span><h3>Acesse o link</h3><p>Informe sua matrícula, permita a câmera e siga o desafio orientado.</p></article><article class="step"><span class="step__number">03 / RESULTADO</span><h3>Acompanhe o estado</h3><p>O resultado é exibido depois da validação e persistência no servidor.</p></article></div></section><section class="section section--soft" id="duvidas"><div class="wrap faq-layout"><div class="faq-intro"><p class="eyebrow">Informação clara</p><h2>Dúvidas frequentes.</h2><p>O FaceDiff apoia o registro de presença. A decisão e os dados permanecem sob controle do serviço.</p></div><div class="faq-list"><details class="faq-item"><summary>Preciso instalar um aplicativo?</summary><div class="faq-item__answer"><p>Não. Abra o link em um navegador atualizado. A câmera exige HTTPS ou acesso local seguro.</p></div></details><details class="faq-item"><summary>Por que liberar a câmera?</summary><div class="faq-item__answer"><p>A câmera fornece as capturas usadas pela verificação da sessão. O navegador solicita permissão antes de iniciar; você pode negar e procurar uma forma alternativa de registro.</p></div></details><details class="faq-item"><summary>Preciso estar na sala?</summary><div class="faq-item__answer"><p>O link define as regras da sessão. O sistema pode permitir acesso remoto; confirme as orientações da disciplina com o professor.</p></div></details><details class="faq-item"><summary>O que acontece se a verificação falhar?</summary><div class="faq-item__answer"><p>A tentativa pode ser recusada ou encaminhada para revisão. Siga as orientações exibidas e use a opção acessível quando o desafio de movimento não for possível.</p></div></details><details class="faq-item"><summary>O cadastro já confirma minha presença?</summary><div class="faq-item__answer"><p>Não. Um cadastro facial fica pendente até a conferência por um professor responsável. Presença e cadastro são fluxos separados.</p></div></details><details class="faq-item"><summary>Como meus dados são tratados?</summary><div class="faq-item__answer"><p>O aviso apresentado antes da coleta explica finalidade e retenção. As capturas são processadas conforme esse aviso e não são usadas para inferir emoção, idade ou gênero.</p></div></details></div></div></section></main><footer class="site-footer"><div class="wrap site-footer__row"><div><a class="wordmark wordmark--inverse" href="/">FaceDiff</a><p>Projeto acadêmico de registro de presença.</p></div><div><p>O professor acompanha estados e metadados necessários à gestão.</p><a href="/login">Acesso do professor</a></div></div></footer>`);
  const canvas = document.querySelector("#hero-particles");
  if (canvas) cleanup.push(iniciarHero(canvas));
  cleanup.push(iniciarRevelacaoScroll(document.querySelector("#conteudo")));
  cleanup.push(iniciarMagnetismo(document));
  cleanup.push(iniciarCursorMagnetico(document));
}

async function loginPage() {
  render(`<div class="login-layout"><aside class="login-aside"><a class="wordmark wordmark--inverse" href="/">FaceDiff</a><div><p class="eyebrow eyebrow--inverse">Acesso institucional</p><h1>Gestão da presença.</h1></div><p>Entre com sua conta autorizada para gerenciar turmas e sessões.</p></aside><main class="login-main" id="conteudo"><h2>Entrar como professor</h2><p>Use as credenciais fornecidas pela instituição.</p><form class="login-form" data-form="login" novalidate>${field("Usuário", "usuario", 'autocomplete="username" required maxlength="160"')}${field("Senha", "senha", 'type="password" autocomplete="current-password" required maxlength="256"')}<button class="button button--dark" type="submit">Entrar</button><a class="inline-link" href="/">Voltar à página inicial</a></form></main></div>`);
}

async function trocarSenha() {
  render(`<div class="login-layout"><aside class="login-aside"><a class="wordmark wordmark--inverse" href="/">FaceDiff</a><div><p class="eyebrow eyebrow--inverse">Segurança da conta</p><h1>Atualize sua senha.</h1></div><p>Escolha uma senha longa e exclusiva.</p></aside><main class="login-main" id="conteudo"><h2>Trocar senha</h2><p>O acesso exige uma senha nova com pelo menos 12 caracteres.</p><form class="login-form" data-form="trocar-senha">${field("Senha atual, se solicitada", "senha_atual", 'type="password" autocomplete="current-password" maxlength="256"')}${field("Nova senha", "nova_senha", 'type="password" autocomplete="new-password" required minlength="12" maxlength="256"')}<button class="button button--dark" type="submit">Salvar nova senha</button></form></main></div>`);
}

async function obterSessao() {
  if (sessao) return sessao;
  try {
    sessao = await api.get(apiPath("/me"));
    api.setCsrfToken((await api.get(apiPath("/auth/csrf"))).csrf_token);
  } catch (erro) {
    sessao = null;
    if (!(erro instanceof ApiError) || erro.status !== 401) throw erro;
  }
  return sessao;
}

function lerView() {
  const parametros = new URLSearchParams(location.search);
  return { view: parametros.get("view") || "painel", turmaId: Number(parametros.get("turma")) || null };
}

async function fetchTurmas() {
  return api.get(apiPath("/turmas"));
}

async function professor() {
  const conta = await obterSessao();
  if (!conta) {
    location.replace("/login");
    return;
  }
  if (conta.troca_senha_obrigatoria) {
    location.replace("/trocar-senha");
    return;
  }
  const { view, turmaId } = lerView();
  const allowed = ["painel", "turmas", "cadastros", "presencas", "revisoes", "relatorios", "administracao"];
  const atual = allowed.includes(view) && (view !== "administracao" || conta.papel === "admin") ? view : "painel";
  root.innerHTML = `<div class="loading-screen" role="status">Carregando dados autorizados…</div>`;
  root.setAttribute("aria-busy", "true");
  try {
    const turmas = await fetchTurmas();
    turmaAtual = turmas.find((turma) => turma.id === turmaId) || turmas[0] || null;
    const body = await construirTelaProfessor(atual, turmas, turmaAtual);
    render(htmlBody(tituloView(atual), body));
    root.querySelector(`[data-view="${atual}"]`)?.setAttribute("aria-current", "page");
    root.querySelector("#conteudo h1")?.focus({ preventScroll: true });
    bindProfessor(turmas, turmaAtual);
  } catch (erro) {
    render(`<main class="not-found wrap" id="conteudo"><p class="eyebrow">Área do professor</p><h1>Não foi possível carregar.</h1>${mensagem(mostrarErro(erro), "error")}<a class="button button--dark" href="/login">Voltar ao acesso</a></main>`);
  }
}

function tituloView(view) {
  return ({ painel: "Painel da turma", turmas: "Turmas e vínculos", cadastros: "Solicitações de cadastro", presencas: "Sessões de presença", revisoes: "Revisões de presença", relatorios: "Relatórios CSV", administracao: "Administração de contas" })[view] || "Painel";
}

function seletorTurma(turmas, atual) {
  if (!turmas.length) return `<p class="empty-state">Nenhuma turma está vinculada a esta conta.</p>`;
  return `<div class="field"><label for="selecionar-turma">Turma</label><select id="selecionar-turma">${turmas.map((turma) => `<option value="${turma.id}" ${turma.id === atual?.id ? "selected" : ""}>${texto(turma.materia)} · ${texto(turma.periodo)}</option>`).join("")}</select></div>`;
}

function tabelaTurmas(turmas) {
  if (!turmas.length) return `<p class="empty-state">Nenhuma turma cadastrada.</p>`;
  return `<div class="table-wrap" role="region" aria-label="Turmas" tabindex="0"><table><thead><tr><th>Turma</th><th>Período</th><th>Responsável</th><th>Ações</th></tr></thead><tbody>${turmas.map((turma) => `<tr><td>${texto(turma.materia)}</td><td>${texto(turma.periodo)}</td><td>${texto(turma.responsavel_professor_id)}</td><td><div class="table-actions">${button("Abrir", `select-class:${turma.id}`, "button--quiet")}<details><summary class="button button--quiet">Editar</summary><form class="form-grid" data-form="editar-turma" data-id="${turma.id}"><div class="field"><label for="materia-${turma.id}">Disciplina ou turma</label><input id="materia-${turma.id}" name="materia" value="${escapeHtml(turma.materia)}" required maxlength="120"></div><div class="field"><label for="periodo-${turma.id}">Período</label><select id="periodo-${turma.id}" name="periodo"><option value="matutino" ${turma.periodo === "matutino" ? "selected" : ""}>Matutino</option><option value="diurno" ${turma.periodo === "diurno" ? "selected" : ""}>Diurno</option><option value="noturno" ${turma.periodo === "noturno" ? "selected" : ""}>Noturno</option></select></div><button class="button button--dark" type="submit">Salvar alterações</button></form></details><details><summary class="button button--quiet">Excluir</summary><form class="form-grid" data-form="excluir-turma" data-id="${turma.id}">${field("Justificativa", "justificativa", 'required maxlength="500"')}<button class="button button--quiet" type="submit">Confirmar exclusão</button></form></details></div></td></tr>`).join("")}</tbody></table></div>`;
}

async function construirTelaProfessor(view, turmas, atual) {
  const seletor = seletorTurma(turmas, atual);
  if (view === "turmas") return `<section class="section-block"><h2>Turmas acessíveis</h2>${tabelaTurmas(turmas)}</section><section class="section-block"><h2>Criar turma</h2><form class="form-grid" data-form="criar-turma">${field("Disciplina ou turma", "materia", 'required maxlength="120"') }<div class="field"><label for="periodo">Período</label><select id="periodo" name="periodo" required><option value="matutino">Matutino</option><option value="diurno">Diurno</option><option value="noturno">Noturno</option></select></div><div class="field field--wide"><button class="button button--dark" type="submit">Criar turma</button></div></form></section>${atual ? `<section class="section-block"><h2>Vínculos de alunos — ${texto(atual.materia)}</h2><form class="toolbar" data-form="vincular-aluno"><input aria-label="Matrícula do aluno" name="matricula" placeholder="Matrícula" maxlength="32" required><button class="button button--dark" type="submit">Vincular aluno existente</button></form><div data-lista-alunos>${await listaAlunos(atual.id)}</div><p class="field-hint">O vínculo não cria nem aprova cadastro facial.</p></section><section class="section-block"><h2>Link de cadastro</h2><p>O link dá acesso ao fluxo de coleta com aviso e consentimento. Compartilhe-o apenas com a pessoa destinada.</p>${button("Criar link de cadastro", "invite-create", "button--dark")}<div class="result-region" data-result="invite"></div></section>` : ""}`;
  if (!atual && view !== "administracao") return `<section class="section-block"><h2>Comece por uma turma</h2><p>Crie ou vincule uma turma antes de abrir sessões.</p><a class="button button--dark" href="/professor?view=turmas">Ver turmas</a></section>`;
  if (view === "cadastros") {
    if (!atual) return `${seletor}<p class="empty-state">Selecione uma turma para revisar solicitações.</p>`;
    const payload = await api.get(apiPath(`/turmas/${atual.id}/cadastros?estado=pendente_aprovacao`));
    const itens = payload.itens || [];
    return `${seletor}<section class="section-block"><p>Esta lista contém apenas dados necessários à conferência. Imagens e embeddings não são exibidos neste painel.</p>${itens.length ? `<ul class="plain-list">${itens.map((item) => `<li><div class="row-between"><div><strong>${texto(item.nome)}</strong><div class="field-hint">Matrícula ${texto(item.matricula)} · ${texto(item.estado)} · solicitada ${dataLocal(item.criado_em)}</div></div><span>ID ${texto(item.id)}</span></div><form class="form-grid" data-form="decidir-cadastro" data-id="${escapeHtml(item.id)}"><div class="field"><label for="metodo-${item.id}">Conferência independente</label><select id="metodo-${item.id}" name="metodo_identidade"><option value="documento_presencial">Documento presencial</option><option value="codigo_institucional">Código institucional</option><option value="contato_institucional">Contato institucional</option></select></div>${field("Justificativa da decisão", "justificativa", 'required minlength="10" maxlength="500"') }<div class="button-row field--wide"><button class="button button--dark" name="decisao" value="aprovar">Aprovar cadastro</button><button class="button button--quiet" name="decisao" value="rejeitar">Rejeitar</button></div></form></li>`).join("")}</ul>` : `<p class="empty-state">Não há solicitações aguardando aprovação.</p>`}</section>`;
  }
  if (view === "painel") return `${seletor}<section class="section-block"><div class="row-between"><h2>Atividade registrada</h2>${button("Atualizar agora", "refresh-panel", "button--quiet")}</div><div class="status-line"><span data-updated>Atualização ainda não consultada</span><span data-poll-error></span></div><div data-panel class="panel-region"><p class="empty-state">Consultando painel autorizado…</p></div></section>`;
  if (view === "presencas") return `${seletor}<section class="section-block"><h2>Abrir sessão</h2><form class="form-grid" data-form="criar-sessao">${field("Título", "titulo", 'required maxlength="120"')}${field("Início", "inicio_em", 'type="datetime-local" required')}${field("Fim", "fim_em", 'type="datetime-local" required')}<div class="field field--wide"><button class="button button--dark" type="submit">Criar sessão</button></div></form><div class="result-region" data-result="session"></div></section><section class="section-block"><h2>Sessões recentes</h2><div data-panel><p class="empty-state">Carregando sessões…</p></div></section>`;
  if (view === "revisoes") return `${seletor}<section class="section-block"><h2>Revisões abertas</h2><div data-reviews><p class="empty-state">Carregando revisões…</p></div></section>`;
  if (view === "relatorios") return `${seletor}<section class="section-block"><h2>Exportar presenças</h2><p>O arquivo é gerado pela API autorizada; o navegador não recalcula a decisão biométrica.</p><form class="form-grid" data-form="csv"><div class="field"><label for="filtro-csv">Intervalo</label><select id="filtro-csv" name="tipo"><option value="mes">Um mês</option><option value="datas">Datas de início e fim</option></select></div><div class="field" data-csv-mes><label for="mes">Mês</label><input id="mes" name="mes" type="month" required></div><div class="field" data-csv-inicio hidden><label for="inicio">Data inicial</label><input id="inicio" name="inicio" type="date"></div><div class="field" data-csv-fim hidden><label for="fim">Data final</label><input id="fim" name="fim" type="date"></div><div class="field field--wide"><button class="button button--dark" type="submit">Baixar CSV</button></div></form><div class="result-region" data-result="csv"></div></section>`;
  if (view === "administracao") return `<section class="section-block"><h2>Criar conta</h2><p>A credencial temporária é exibida uma vez. Entregue-a por canal institucional apropriado.</p><form class="form-grid" data-form="criar-conta">${field("Usuário", "usuario", 'required maxlength="160"') }<div class="field"><label for="papel">Papel</label><select id="papel" name="papel"><option value="professor">Professor</option><option value="admin">Administrador</option></select></div>${field("Justificativa", "justificativa", 'required maxlength="500"')}<div class="field field--wide"><button class="button button--dark" type="submit">Criar conta</button></div></form><div class="result-region" data-result="admin"></div></section><section class="section-block"><h2>Redefinir senha ou desativar conta</h2><p>Informe o identificador da conta consultado em canal autorizado. As ações ficam auditadas pelo servidor.</p><form class="form-grid" data-form="admin-conta">${field("ID da conta", "conta_id", 'type="number" min="1" required')}${field("Referência de verificação", "referencia_verificacao", 'required maxlength="160"')}${field("Justificativa", "justificativa", 'required maxlength="500"')}<div class="button-row field--wide"><button class="button button--dark" name="acao" value="reset">Redefinir senha</button><button class="button button--quiet" name="acao" value="desativar">Desativar conta</button></div></form><div class="result-region" data-result="admin-conta"></div></section>${atual ? `<section class="section-block"><h2>Transferir responsabilidade de turma</h2>${seletor}<form class="form-grid" data-form="transferir"><input type="hidden" name="turma_id" value="${atual.id}">${field("ID do novo professor responsável", "professor_id", 'type="number" min="1" required')}${field("Justificativa", "justificativa", 'required maxlength="500"')}<div class="field field--wide"><button class="button button--dark" type="submit">Transferir</button></div></form></section>` : ""}`;
  return `${seletor}<section class="section-block"><h2>Visão da turma</h2><div data-panel><p class="empty-state">Carregando atividade…</p></div></section>`;
}

async function listaAlunos(turmaId) {
  const alunos = await api.get(apiPath(`/turmas/${turmaId}/alunos`));
  if (!alunos.length) return `<p class="empty-state">Ainda não há alunos vinculados.</p>`;
  return `<ul class="plain-list">${alunos.map((aluno) => `<li class="row-between"><span>${texto(aluno.nome)} <span class="field-hint">${texto(aluno.matricula)}</span></span>${button("Desvincular", `unlink:${aluno.aluno_id}`, "button--quiet")}</li>`).join("")}</ul>`;
}

function renderPainel(payload) {
  if (!payload?.sessoes?.length) return `<p class="empty-state">Não há sessões recentes para esta turma.</p>`;
  return `<ul class="plain-list">${payload.sessoes.map((sessao) => `<li><div class="row-between"><strong>${texto(sessao.titulo)}</strong><span>${sessao.revogada ? "Revogada" : "Ativa"}</span></div><p class="field-hint">${dataLocal(sessao.inicio_em)} – ${dataLocal(sessao.fim_em)}</p><p>Presentes: ${texto(sessao.presencas_presentes, "0")} · Anuladas: ${texto(sessao.presencas_anuladas, "0")} · Revisões abertas: ${texto(sessao.revisoes_abertas, "0")}</p><details><summary>Estado das tentativas</summary><pre class="code-line">${escapeHtml(JSON.stringify(sessao.tentativas_por_estado || {}, null, 2))}</pre></details></li>`).join("")}</ul>`;
}

function bindProfessor(turmas, atual) {
  document.querySelector("#selecionar-turma")?.addEventListener("change", (event) => {
    const url = new URL(location.href);
    url.searchParams.set("turma", event.target.value);
    history.pushState({}, "", url);
    void professor();
  });
  document.querySelectorAll("[data-view]").forEach((link) => link.addEventListener("click", (event) => {
    event.preventDefault();
    const url = new URL(link.href);
    if (atual) url.searchParams.set("turma", String(atual.id));
    history.pushState({}, "", url);
    void professor();
  }));
  const panel = document.querySelector("[data-panel]");
  const selected = document.querySelector("#selecionar-turma")?.value || atual?.id;
  const updatePanel = async () => {
    if (!selected || !panel) return null;
    return api.get(apiPath(`/turmas/${selected}/painel`));
  };
  if (panel && selected && ["painel", "presencas"].includes(lerView().view)) {
    const poller = criarPollerSerial(updatePanel, {
      intervaloMs: 15000,
      aoAtualizar: (payload) => {
        panel.innerHTML = renderPainel(payload);
        const atualizado = document.querySelector("[data-updated]");
        if (atualizado) atualizado.textContent = `Atualizado ${dataLocal(payload.atualizado_em)}`;
        const erro = document.querySelector("[data-poll-error]");
        if (erro) erro.textContent = "";
      },
      aoFalhar: (erro) => {
        const aviso = document.querySelector("[data-poll-error]");
        if (aviso) aviso.textContent = `Falha ao atualizar: ${mostrarErro(erro)}`;
      },
    });
    poller.iniciar();
    cleanup.push(() => poller.parar());
  }
  document.querySelector('[data-action="refresh-panel"]')?.addEventListener("click", () => {
    const refresh = document.querySelector('[data-action="refresh-panel"]');
    refresh.disabled = true;
    void updatePanel().then((payload) => {
      if (payload && panel) panel.innerHTML = renderPainel(payload);
      const atualizado = document.querySelector("[data-updated]");
      if (atualizado && payload) atualizado.textContent = `Atualizado ${dataLocal(payload.atualizado_em)}`;
    }).catch((erro) => {
      const area = document.querySelector("[data-poll-error]");
      if (area) area.textContent = mostrarErro(erro);
    }).finally(() => { refresh.disabled = false; });
  });
  document.querySelector('[data-form="criar-turma"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const dados = new FormData(form);
    try {
      await api.post(apiPath("/turmas"), { materia: dados.get("materia"), periodo: dados.get("periodo") });
      location.assign("/professor?view=turmas");
    } catch (erro) { formularioErro(form, erro); }
  });
  document.querySelectorAll('[data-form="editar-turma"]').forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const dados = new FormData(form);
    try {
      await api.patch(apiPath(`/turmas/${form.dataset.id}`), { materia: dados.get("materia"), periodo: dados.get("periodo") });
      location.reload();
    } catch (erro) { formularioErro(form, erro); }
  }));
  document.querySelectorAll('[data-form="excluir-turma"]').forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!window.confirm("Excluir esta turma? A operação será registrada pelo servidor e pode afetar os vínculos existentes.")) return;
    const dados = new FormData(form);
    try {
      await api.delete(apiPath(`/turmas/${form.dataset.id}`), { justificativa: dados.get("justificativa") });
      location.assign("/professor?view=turmas");
    } catch (erro) { formularioErro(form, erro); }
  }));
  document.querySelector('[data-form="vincular-aluno"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const dados = new FormData(form);
    try {
      await api.post(apiPath(`/turmas/${atual.id}/alunos`), { matricula: dados.get("matricula") });
      const lista = document.querySelector("[data-lista-alunos]");
      if (lista) lista.innerHTML = await listaAlunos(atual.id);
      form.reset();
      avisar("Vínculo atualizado.");
    } catch (erro) { formularioErro(form, erro); }
  });
  document.querySelectorAll("[data-action^='unlink:']").forEach((element) => element.addEventListener("click", async () => {
    const alunoId = element.dataset.action.split(":")[1];
    const justificativa = window.prompt("Justificativa para desvincular o aluno:");
    if (!justificativa) return;
    try {
      await api.delete(apiPath(`/turmas/${atual.id}/alunos/${alunoId}`), { justificativa });
      const lista = document.querySelector("[data-lista-alunos]");
      if (lista) lista.innerHTML = await listaAlunos(atual.id);
      avisar("Aluno desvinculado da turma.");
    } catch (erro) { avisar(mostrarErro(erro)); }
  }));
  document.querySelector('[data-action="invite-create"]')?.addEventListener("click", async () => {
    const result = document.querySelector('[data-result="invite"]');
    try {
      const link = await api.post(apiPath(`/turmas/${atual.id}/links-cadastro`), {});
      const href = `${location.origin}/cadastro/${encodeURIComponent(link.token)}`;
      result.innerHTML = `<div class="notice"><p>Link de uso único. Copie e compartilhe apenas com a pessoa destinada.</p><a class="code-line" href="${escapeHtml(href)}">${escapeHtml(href)}</a><p class="field-hint">Expira em ${dataLocal(link.expira_em)}. Não atualize a página antes de copiar.</p></div>`;
      result.querySelector("a")?.focus();
    } catch (erro) { result.innerHTML = mensagem(mostrarErro(erro), "error"); }
  });
  document.querySelectorAll('[data-form="decidir-cadastro"]').forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const dados = new FormData(form);
    const decisao = event.submitter?.value || "aprovar";
    const id = form.dataset.id;
    try {
      if (decisao === "aprovar") {
        await api.post(apiPath(`/cadastros/${id}/aprovar`), {
          metodo_identidade: dados.get("metodo_identidade"), justificativa: dados.get("justificativa"),
        });
      } else {
        await api.post(apiPath(`/cadastros/${id}/rejeitar`), { justificativa: dados.get("justificativa") });
      }
      location.reload();
    } catch (erro) { formularioErro(form, erro); }
  }));
  document.querySelector('[data-form="criar-sessao"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const dados = new FormData(form);
    const result = document.querySelector('[data-result="session"]');
    try {
      const criada = await api.post(apiPath(`/turmas/${atual.id}/sessoes`), {
        titulo: dados.get("titulo"), inicio_em: new Date(dados.get("inicio_em")).toISOString(), fim_em: new Date(dados.get("fim_em")).toISOString(),
      });
      const link = await api.post(apiPath(`/sessoes/${criada.id}/links`), {});
      const href = `${location.origin}/presenca/${encodeURIComponent(link.token)}`;
      result.innerHTML = `<div class="notice"><p>Sessão criada. O link é de uso único; copie e compartilhe com a turma.</p><a class="code-line" href="${escapeHtml(href)}">${escapeHtml(href)}</a><p>Início ${dataLocal(criada.inicio_em)} · fim ${dataLocal(criada.fim_em)} · expira ${dataLocal(link.expira_em)}</p></div>`;
      result.querySelector("a")?.focus();
      form.reset();
    } catch (erro) { formularioErro(form, erro); }
  });
  document.querySelector('[data-form="csv"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const dados = new FormData(form);
    const tipo = dados.get("tipo");
    const query = tipo === "mes" ? `mes=${encodeURIComponent(dados.get("mes"))}` : `inicio=${encodeURIComponent(dados.get("inicio"))}&fim=${encodeURIComponent(dados.get("fim"))}`;
    try {
      const resposta = await api.get(apiPath(`/turmas/${atual.id}/presencas.csv?${query}`));
      const blob = await resposta.blob();
      const url = URL.createObjectURL(blob);
      const ancora = document.createElement("a");
      ancora.href = url;
      ancora.download = `presencas-turma-${atual.id}.csv`;
      ancora.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      document.querySelector('[data-result="csv"]').textContent = "Arquivo gerado pela API e baixado.";
    } catch (erro) { formularioErro(form, erro); }
  });
  document.querySelector("#filtro-csv")?.addEventListener("change", (event) => {
    const mes = event.target.value === "mes";
    document.querySelector("[data-csv-mes]").hidden = !mes;
    document.querySelector("#mes").required = mes;
    document.querySelector("[data-csv-inicio]").hidden = mes;
    document.querySelector("#inicio").required = !mes;
    document.querySelector("[data-csv-fim]").hidden = mes;
    document.querySelector("#fim").required = !mes;
  });
  document.querySelector('[data-form="criar-conta"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const dados = new FormData(form);
    try {
      const criada = await api.post(apiPath("/admin/contas"), Object.fromEntries(dados));
      document.querySelector('[data-result="admin"]').innerHTML = `<div class="notice notice--warning"><strong>Credencial temporária — exibição única</strong><p class="code-line">${escapeHtml(criada.credencial_temporaria)}</p><p>Expira em ${dataLocal(criada.expira_em)}. Entregue em canal institucional e solicite a troca no primeiro acesso.</p></div>`;
      form.reset();
    } catch (erro) { formularioErro(form, erro); }
  });
  document.querySelector('[data-form="admin-conta"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const dados = new FormData(form);
    const id = Number(dados.get("conta_id"));
    try {
      if (event.submitter?.value === "desativar") {
        await api.post(apiPath(`/admin/contas/${id}/desativar`), { justificativa: dados.get("justificativa") });
        document.querySelector('[data-result="admin-conta"]').innerHTML = mensagem("Conta desativada pelo servidor.", "success");
      } else {
        const resposta = await api.post(apiPath(`/admin/contas/${id}/redefinir-senha`), { justificativa: dados.get("justificativa"), referencia_verificacao: dados.get("referencia_verificacao") });
        document.querySelector('[data-result="admin-conta"]').innerHTML = `<div class="notice notice--warning"><strong>Credencial temporária — exibição única</strong><p class="code-line">${escapeHtml(resposta.credencial_temporaria)}</p><p>Expira em ${dataLocal(resposta.expira_em)}. A troca de senha é obrigatória.</p></div>`;
      }
    } catch (erro) { formularioErro(form, erro); }
  });
  document.querySelector('[data-form="transferir"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const dados = new FormData(event.currentTarget);
    try {
      await api.post(apiPath(`/admin/turmas/${dados.get("turma_id")}/responsavel`), { professor_id: Number(dados.get("professor_id")), justificativa: dados.get("justificativa") });
      avisar("Responsabilidade transferida.");
    } catch (erro) { formularioErro(event.currentTarget, erro); }
  });
  const reviewRegion = document.querySelector("[data-reviews]");
  if (reviewRegion && atual) void carregarRevisoes(atual.id, reviewRegion);
}

async function carregarRevisoes(turmaId, region) {
  try {
    const itens = await api.get(apiPath(`/turmas/${turmaId}/revisoes?estado=aberta`));
    if (!itens.length) {
      region.innerHTML = `<p class="empty-state">Não há revisões abertas.</p>`;
      return;
    }
    region.innerHTML = `<ul class="plain-list">${itens.map((item) => `<li><strong>Revisão ${texto(item.id)}</strong><p>${texto(item.nome)} · matrícula ${texto(item.matricula)} · solicitada ${dataLocal(item.solicitada_em)} · estado ${texto(item.estado)} · versão ${texto(item.versao_presenca, "0")}</p><form class="form-grid" data-form="decidir-revisao" data-id="${escapeHtml(item.id)}" data-versao="${escapeHtml(item.versao_presenca ?? 0)}"><div class="field"><label for="decisao-${escapeHtml(item.id)}">Decisão</label><select id="decisao-${escapeHtml(item.id)}" name="decisao"><option value="presente">Registrar como presente</option><option value="anulada">Anular presença</option></select></div>${field("Justificativa", "justificativa", 'required maxlength="500"')}<label class="check-field"><input name="identidade_confirmada" type="checkbox" required><span>Confirmei a identidade por procedimento institucional independente.</span></label><div class="field field--wide"><button class="button button--dark" type="submit">Aplicar decisão auditada</button></div></form></li>`).join("")}</ul>`;
    region.querySelectorAll('[data-form="decidir-revisao"]').forEach((form) => form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const dados = new FormData(form);
      try {
        await api.post(apiPath(`/revisoes/${encodeURIComponent(form.dataset.id)}/decidir`), {
          decisao: dados.get("decisao"), justificativa: dados.get("justificativa"), versao_esperada: Number(form.dataset.versao), identidade_confirmada: dados.get("identidade_confirmada") === "on",
        });
        await carregarRevisoes(turmaId, region);
      } catch (erro) { formularioErro(form, erro); }
    }));
  } catch (erro) { region.innerHTML = mensagem(mostrarErro(erro), "error"); }
}

function guardarCredencialPublica(tipo, acesso) {
  salvarEstado(`${tipo}.credencial`, acesso.credencial);
  salvarEstado(`${tipo}.expira_em`, acesso.expira_em);
  if (acesso.sessao_id) salvarEstado(`${tipo}.sessao_id`, acesso.sessao_id);
}

async function credencialDoLink(tipo, token) {
  if (token) {
    const acesso = await api.post(apiPath("/acessos-link"), { token }, { csrf: false });
    if (acesso.finalidade !== tipo) throw new ApiError("Este link não corresponde a este fluxo.", { status: 404 });
    guardarCredencialPublica(tipo, acesso);
    history.replaceState({}, "", `/${tipo}`);
    return acesso.credencial;
  }
  return estadoSalvo()[`${tipo}.credencial`] || null;
}

function studentLayout(title, intro, content, context = "") {
  render(`<div class="student-shell"><header class="student-header"><a class="wordmark" href="/" aria-label="FaceDiff, página inicial"><span class="wordmark__symbol" aria-hidden="true">FD</span><span>FaceDiff</span></a><span class="field-hint">${escapeHtml(context)}</span></header><main class="student-main" id="conteudo"><p class="eyebrow">Acesso por link</p><h1 tabindex="-1">${escapeHtml(title)}</h1><p>${escapeHtml(intro)}</p>${content}</main><footer class="student-footer">Não compartilhe este link. O resultado depende da resposta do servidor e pode exigir revisão.</footer></div>`);
}

function codigoErroPublico(erro) {
  if (!(erro instanceof ApiError)) return mostrarErro(erro);
  if (erro.status === 401 || erro.status === 404) return "Este link expirou, foi revogado ou já foi utilizado. Solicite um novo link ao professor.";
  return erro.message;
}

async function paginaCadastro(token) {
  let credencial;
  try { credencial = await credencialDoLink("cadastro", token); }
  catch (erro) {
    studentLayout("Cadastro facial", "Use o link enviado pelo professor.", mensagem(codigoErroPublico(erro), "error"));
    return;
  }
  if (!credencial) {
    studentLayout("Cadastro facial", "Abra o link enviado pelo professor para iniciar.", mensagem("Link indisponível. Solicite um convite válido ao professor.", "error"));
    return;
  }
  const estado = estadoSalvo();
  if (estado["cadastro.id"]) {
    try {
      const atual = await api.get(apiPath(`/cadastros/${estado["cadastro.id"]}`), { headers: { Authorization: `Bearer ${credencial}` } });
      if (atual.estado !== "em_coleta") {
        if (["pendente_aprovacao", "aprovada", "aprovado", "rejeitado", "rejeitada", "expirada"].includes(atual.estado)) {
          mostrarEstadoCadastro(atual.estado);
        } else {
          iniciarAcompanhamentoCadastro(credencial, estado["cadastro.id"]);
        }
        return;
      }
      if (estado["cadastro.desafio"]) {
        mostrarColetaCadastro(credencial, estado["cadastro.id"], estado["cadastro.desafio"]);
        return;
      }
    } catch (erro) {
      studentLayout("Cadastro facial", "Não foi possível retomar esta solicitação.", mensagem(codigoErroPublico(erro), "error"));
      return;
    }
  }
  await mostrarFormularioCadastro(credencial);
}

async function mostrarFormularioCadastro(credencial, erroInicial = null) {
  let aviso;
  try { aviso = await api.get(apiPath("/avisos/biometria")); }
  catch (erro) {
    studentLayout("Cadastro facial", "Leia o aviso antes de decidir sobre a coleta.", mensagem(mostrarErro(erro), "error"));
    return;
  }
  const content = `${mensagem(aviso.texto)}<p>O cadastro não confirma presença. A solicitação permanece pendente até conferência independente por um professor.</p><p>As capturas são temporárias durante o envio. Você pode interromper o processo antes de consentir.</p>${erroInicial ? mensagem(erroInicial, "error") : ""}<form class="student-form" data-form="cadastro-iniciar">${field("Nome", "nome", 'autocomplete="name" required maxlength="255"')}${field("Matrícula", "matricula", 'autocomplete="off" required maxlength="32"')}<label class="check-field"><input type="checkbox" name="consentimento" required><span>Li o aviso e concordo com o processamento descrito para este cadastro.</span></label><button class="button button--dark" type="submit">Continuar para as capturas</button></form><a class="inline-link" href="/">Sair do cadastro</a>`;
  studentLayout("Cadastro facial", "Confira a finalidade e decida se deseja continuar.", content);
  document.querySelector('[data-form="cadastro-iniciar"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const dados = new FormData(form);
    try {
      const cadastro = await api.post(apiPath("/cadastros"), {
        nome: dados.get("nome"), matricula: dados.get("matricula"), aviso_versao: aviso.versao,
        consentimento: dados.get("consentimento") === "on",
      }, { headers: { Authorization: `Bearer ${credencial}` } });
      salvarEstado("cadastro.id", cadastro.id);
      salvarEstado("cadastro.desafio", cadastro.desafio);
      mostrarColetaCadastro(credencial, cadastro.id, cadastro.desafio);
    } catch (erro) { formularioErro(form, erro); }
  });
}

function mostrarColetaCadastro(credencial, id, desafio) {
  const sequencia = Array.isArray(desafio?.sequencia) ? desafio.sequencia : ["frente", "movimento indicado", "frente"];
  let capturas = [];
  const labels = { frente: "Olhe para a câmera", esquerda: "Vire levemente para a esquerda", direita: "Vire levemente para a direita" };
  studentLayout("Três capturas guiadas", "Siga a sequência emitida pelo servidor. As imagens permanecem apenas na memória até o envio.", `<ol class="progress-list" aria-label="Progresso da captura">${sequencia.map((passo, indice) => `<li ${indice === 0 ? 'aria-current="step"' : ""} data-progress="${indice}">Etapa ${indice + 1}</li>`).join("")}</ol><p class="challenge-step"><span class="challenge-step__number" data-stage-number>1</span><span data-stage-instruction>${texto(labels[sequencia[0]] || sequencia[0])}</span></p><p class="field-hint">Câmera frontal espelhada na prévia. A orientação e a validação são definidas pelo servidor.</p>${cameraMarkup()}<div class="button-row">${button("Capturar esta etapa", "capture-step", "button--dark")}${button("Interromper", "student-cancel", "button--quiet")}</div><div data-capture-result role="status" aria-live="polite"></div>`, "Cadastro facial");
  bindCamera(async (captura) => {
    capturas.push(captura.base64);
    const etapa = capturas.length;
    document.querySelector(`[data-progress="${etapa - 1}"]`)?.setAttribute("aria-current", "step");
    const numero = document.querySelector("[data-stage-number]");
    const orientacao = document.querySelector("[data-stage-instruction]");
    const botao = document.querySelector('[data-action="capture-step"]');
    if (etapa < 3) {
      if (numero) numero.textContent = String(etapa + 1);
      if (orientacao) orientacao.textContent = labels[sequencia[etapa]] || sequencia[etapa];
      document.querySelectorAll("[data-progress]").forEach((item, index) => {
        if (index === etapa) item.setAttribute("aria-current", "step");
        else item.removeAttribute("aria-current");
      });
      avisar(`Captura ${etapa} recebida localmente. Siga a próxima orientação.`);
      return;
    }
    botao.disabled = true;
    const result = document.querySelector("[data-capture-result]");
    result.innerHTML = mensagem("Enviando as três capturas ao serviço…");
    camera.encerrar(document.querySelector("#camera-video"));
    try {
      const idempotency = estadoSalvo()["cadastro.idempotency"] || crypto.randomUUID();
      salvarEstado("cadastro.idempotency", idempotency);
      await api.post(apiPath(`/cadastros/${id}/capturas`), { nonce: desafio.nonce, capturas }, {
        headers: { Authorization: `Bearer ${credencial}`, "Idempotency-Key": idempotency },
      });
      capturas = [];
      salvarEstado("cadastro.desafio", null);
      iniciarAcompanhamentoCadastro(credencial, id);
      result.innerHTML = mensagem("Capturas recebidas. Acompanhe o estado informado pelo serviço.");
    } catch (erro) {
      result.innerHTML = `${mensagem(mostrarErro(erro), "error")}<p>As imagens continuam somente na memória desta página. Você pode tentar enviar novamente enquanto ela permanecer aberta.</p>${button("Tentar envio novamente", "cadastro-retry", "button--dark")}`;
      document.querySelector('[data-action="cadastro-retry"]')?.addEventListener("click", async () => {
        try {
          await api.post(apiPath(`/cadastros/${id}/capturas`), { nonce: desafio.nonce, capturas }, { headers: { Authorization: `Bearer ${credencial}`, "Idempotency-Key": estadoSalvo()["cadastro.idempotency"] } });
          capturas = [];
          salvarEstado("cadastro.desafio", null);
          iniciarAcompanhamentoCadastro(credencial, id);
          result.innerHTML = mensagem("Capturas recebidas. A solicitação está em processamento.");
        } catch (falha) { result.innerHTML = mensagem(mostrarErro(falha), "error"); }
      });
    }
  });
  document.querySelector('[data-action="student-cancel"]')?.addEventListener("click", () => {
    camera.encerrar(document.querySelector("#camera-video"));
    capturas = [];
    studentLayout("Coleta interrompida", "Nenhuma imagem foi enviada. Você pode retomar a mesma solicitação sem criar outra.", `${mensagem("A etapa atual foi reiniciada; siga novamente a sequência do servidor.")} ${button("Retomar capturas", "cadastro-resume", "button--dark")}`);
    document.querySelector('[data-action="cadastro-resume"]')?.addEventListener("click", () => mostrarColetaCadastro(credencial, id, desafio));
  });
}

function mostrarEstadoCadastro(estado) {
  const mensagens = {
    pendente_aprovacao: ["Solicitação pendente", "A coleta foi recebida. Um professor responsável precisa conferir a identidade antes de aprovar o cadastro."],
    aprovada: ["Cadastro aprovado", "A decisão foi registrada pelo serviço. Isso não confirma presença em uma sessão."],
    rejeitado: ["Cadastro não aprovado", "A solicitação não foi aprovada. Procure o professor responsável para uma alternativa de registro."],
    rejeitada: ["Cadastro não aprovado", "A solicitação não foi aprovada. Procure o professor responsável para uma alternativa de registro."],
    expirada: ["Solicitação expirada", "O prazo desta solicitação terminou. Solicite ao professor um novo link se ainda for necessário."],
  };
  const [titulo, textoEstado] = mensagens[estado] || ["Cadastro em processamento", "O serviço ainda está processando a solicitação. O status será atualizado automaticamente."];
  studentLayout(titulo, textoEstado, `<div class="notice ${["aprovada", "aprovado"].includes(estado) ? "notice--success" : ""}" role="status">Estado informado pelo serviço: <strong>${escapeHtml(estado)}</strong></div><p class="field-hint">Atualização automática com intervalo progressivo. Não feche a página se quiser acompanhar.</p>${button("Atualizar estado", "cadastro-status", "button--quiet")}`);
  document.querySelector('[data-action="cadastro-status"]')?.addEventListener("click", () => {
    const estadoSalvoAtual = estadoSalvo();
    void consultarCadastro(estadoSalvoAtual["cadastro.credencial"], estadoSalvoAtual["cadastro.id"]);
  });
}

async function consultarCadastro(credencial, id, signal = undefined) {
  try {
    return await api.get(apiPath(`/cadastros/${id}`), { headers: { Authorization: `Bearer ${credencial}` }, signal });
  } catch (erro) {
    if (erro?.name === "AbortError") throw erro;
    throw new ApiError(codigoErroPublico(erro), { status: erro.status, code: erro.code });
  }
}

function iniciarAcompanhamentoCadastro(credencial, id) {
  studentLayout("Cadastro em processamento", "O serviço está verificando a solicitação. A aprovação depende de conferência do professor.", `<p data-status-state role="status">Aguardando a resposta do serviço…</p><p data-status-error class="field-hint"></p>${button("Consultar agora", "cadastro-status", "button--quiet")}`);
  const controller = new AbortController();
  cleanup.push(() => controller.abort());
  const terminal = new Set(["pendente_aprovacao", "aprovada", "aprovado", "rejeitado", "rejeitada", "expirada"]);
  void acompanharOperacao(() => consultarCadastro(credencial, id, controller.signal), {
    concluida: (atual) => terminal.has(atual.estado),
    signal: controller.signal,
    aoAtualizar: (atual) => {
      const area = document.querySelector("[data-status-state]");
      if (area) area.textContent = `Estado informado pelo serviço: ${atual.estado}`;
    },
  }).then((atual) => mostrarEstadoCadastro(atual.estado)).catch((erro) => {
    if (erro.name !== "AbortError") {
      const area = document.querySelector("[data-status-error]");
      if (area) area.textContent = mostrarErro(erro);
    }
  });
  document.querySelector('[data-action="cadastro-status"]')?.addEventListener("click", async () => {
    try { const atual = await consultarCadastro(credencial, id); if (terminal.has(atual.estado)) mostrarEstadoCadastro(atual.estado); else avisar(`Estado informado pelo serviço: ${atual.estado}`); }
    catch (erro) { avisar(mostrarErro(erro)); }
  });
}

async function paginaPresenca(token) {
  let credencial;
  try { credencial = await credencialDoLink("presenca", token); }
  catch (erro) {
    studentLayout("Verificação de presença", "Use o link da sessão enviado pelo professor.", mensagem(codigoErroPublico(erro), "error"));
    return;
  }
  if (!credencial) {
    studentLayout("Verificação de presença", "Abra o link da sessão enviado pelo professor.", mensagem("Link indisponível. Solicite um novo link ao professor.", "error"));
    return;
  }
  const estado = estadoSalvo();
  const sessaoId = estado["presenca.sessao_id"];
  if (!sessaoId) {
    studentLayout("Verificação de presença", "Não foi possível identificar a sessão deste link.", mensagem("Sessão indisponível. Solicite um link válido ao professor.", "error"));
    return;
  }
  if (estado["presenca.revisao_solicitada"]) {
    studentLayout("Solicitação recebida", "A revisão foi registrada pelo serviço. O protocolo não representa presença confirmada.", `<div class="notice" role="status">Protocolo ${texto(estado["presenca.revisao_protocolo"])} · estado ${texto(estado["presenca.revisao_estado"])}</div>`, "Presença");
    return;
  }
  if (estado["presenca.tentativa_id"] && estado["presenca.credencial_captura"]) {
    try {
      const atual = await consultarTentativa(estado);
      if (terminalPresenca(atual.estado)) { finalizarPresenca(atual.estado); return; }
      await continuarTentativa(estado, atual);
      return;
    } catch (erro) {
      studentLayout("Retomar tentativa", "A tentativa existente não foi recriada para preservar a quota.", `${mensagem(codigoErroPublico(erro), "error")}<p>Solicite ajuda ao professor se o link ou prazo expirou.</p>`);
      return;
    }
  }
  mostrarFormularioPresenca(credencial, sessaoId);
}

function mostrarFormularioPresenca(credencial, sessaoId, erroInicial = null) {
  const conteudo = `${erroInicial ? mensagem(erroInicial, "error") : ""}<p>Informe a matrícula vinculada à turma. A matrícula sozinha não comprova identidade nem registra presença.</p><form class="student-form" data-form="iniciar-tentativa">${field("Matrícula", "matricula", 'autocomplete="off" required maxlength="32"')}<button class="button button--dark" type="submit">Iniciar verificação</button></form><section class="accessibility-note"><h2>Precisa de uma forma acessível?</h2><p>Se o movimento solicitado não for possível, solicite revisão manual com uma justificativa. O professor fará a conferência por procedimento independente.</p><form class="student-form" data-form="revisao-acessivel">${field("Matrícula", "matricula", 'autocomplete="off" required maxlength="32"')}${field("Justificativa", "justificativa", 'required maxlength="500"') }<button class="button button--quiet" type="submit">Solicitar revisão acessível</button></form></section>`;
  studentLayout("Verificação de presença", "Siga o desafio emitido para esta sessão. O navegador não decide identidade nem presença.", conteudo, "Presença");
  document.querySelector('[data-form="iniciar-tentativa"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const dados = new FormData(form);
    const idempotency = estadoSalvo()["presenca.idempotency"] || crypto.randomUUID();
    salvarEstado("presenca.idempotency", idempotency);
    try {
      const inicio = await api.post(apiPath(`/sessoes/${sessaoId}/tentativas`), { matricula: dados.get("matricula") }, { headers: { Authorization: `Bearer ${credencial}`, "Idempotency-Key": idempotency } });
      salvarEstado("presenca.tentativa_id", inicio.id);
      salvarEstado("presenca.credencial_captura", inicio.credencial_captura);
      salvarEstado("presenca.desafio", inicio.desafio || null);
      salvarEstado("presenca.sessao_id", sessaoId);
      await continuarTentativa(estadoSalvo(), inicio);
    } catch (erro) { formularioErro(form, erro); }
  });
  document.querySelector('[data-form="revisao-acessivel"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const dados = new FormData(form);
    try {
      const resposta = await api.post(apiPath("/revisoes"), { sessao_id: Number(sessaoId), matricula: dados.get("matricula"), justificativa: dados.get("justificativa"), via_acessivel: true }, { headers: { Authorization: `Bearer ${credencial}` } });
      salvarEstado("presenca.revisao_solicitada", true);
      salvarEstado("presenca.revisao_protocolo", resposta.protocolo);
      salvarEstado("presenca.revisao_estado", resposta.estado);
      studentLayout("Solicitação recebida", "A revisão foi registrada pelo serviço. O protocolo não representa presença confirmada.", `<div class="notice" role="status">Protocolo ${texto(resposta.protocolo)} · estado ${texto(resposta.estado)}</div>`);
    } catch (erro) { formularioErro(form, erro); }
  });
}

function terminalPresenca(estado) {
  return ["concluida", "rejeitada", "expirada"].includes(estado);
}

function finalizarPresenca(estado) {
  salvarEstado("presenca.tentativa_id", null);
  salvarEstado("presenca.credencial_captura", null);
  salvarEstado("presenca.idempotency", null);
  salvarEstado("presenca.desafio", null);
  const confirmou = estado === "concluida";
  if (confirmou) {
    studentLayout("Presença confirmada", "O servidor confirmou a persistência do registro para esta sessão.", `<div class="notice notice--success" role="status">Estado informado pelo serviço: <strong>${escapeHtml(estado)}</strong></div>`, "Presença");
    limparEstadoPublico("presenca");
  } else {
    mostrarFormularioRevisaoFinal(estadoSalvo(), estado);
  }
}

function mostrarFormularioRevisaoFinal(estado, resultado) {
  const credencial = estado["presenca.credencial"];
  const sessaoId = estado["presenca.sessao_id"];
  if (!credencial || !sessaoId) return;
  mostrarFormularioRevisaoAcessivel(
    credencial,
    sessaoId,
    `Estado informado pelo serviço: ${resultado}. A matrícula informada antes não prova identidade. Você pode solicitar revisão se acredita que houve um erro ou se o desafio não foi possível.`,
  );
}

function mostrarFormularioRevisaoAcessivel(credencial, sessaoId, instrucao) {
  const conteudo = `${mensagem(instrucao, "warning")}<form class="student-form" data-form="revisao-final">${field("Matrícula", "matricula", 'autocomplete="off" required maxlength="32"')}${field("Justificativa", "justificativa", 'required maxlength="500"')}<button class="button button--quiet" type="submit">Solicitar revisão manual</button></form>`;
  studentLayout("Solicitar revisão manual", "O protocolo confirma somente que a solicitação foi recebida; o professor avalia o caso.", conteudo, "Presença");
  document.querySelector('[data-form="revisao-final"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const dados = new FormData(form);
    try {
      const resposta = await api.post(apiPath("/revisoes"), { sessao_id: Number(sessaoId), matricula: dados.get("matricula"), justificativa: dados.get("justificativa"), via_acessivel: true }, { headers: { Authorization: `Bearer ${credencial}` } });
      salvarEstado("presenca.revisao_solicitada", true);
      salvarEstado("presenca.revisao_protocolo", resposta.protocolo);
      salvarEstado("presenca.revisao_estado", resposta.estado);
      studentLayout("Solicitação recebida", "A revisão foi registrada pelo serviço; o protocolo não confirma presença.", `<div class="notice" role="status">Protocolo ${texto(resposta.protocolo)} · estado ${texto(resposta.estado)}</div>`, "Presença");
    } catch (erro) { formularioErro(form, erro); }
  });
}

async function consultarTentativa(estado, signal = undefined) {
  return api.get(apiPath(`/tentativas/${encodeURIComponent(estado["presenca.tentativa_id"])}`), { headers: { Authorization: `Bearer ${estado["presenca.credencial_captura"]}` }, signal });
}

async function continuarTentativa(estado, atual) {
  if (terminalPresenca(atual.estado)) { finalizarPresenca(atual.estado); return; }
  if (atual.desafio) {
    mostrarDesafioPresenca(estado, atual.desafio);
    return;
  }
  mostrarAguardandoPresenca(estado, atual.estado);
}

function mostrarAguardandoPresenca(estado, status) {
  studentLayout("Verificação em andamento", "A tentativa existente continua vinculada à sessão. Atualizaremos seu estado sem abrir outra tentativa.", `<div class="notice" role="status" data-attempt-state>Estado informado pelo serviço: ${escapeHtml(status)}</div><p data-attempt-error class="field-hint"></p><p class="field-hint">As consultas usam intervalo progressivo. Não recarregue para iniciar uma nova tentativa.</p>${button("Consultar agora", "presenca-status", "button--quiet")}`);
  const controller = new AbortController();
  cleanup.push(() => controller.abort());
  void acompanharOperacao(() => consultarTentativa(estado, controller.signal), {
    concluida: (valor) => terminalPresenca(valor.estado) || Boolean(valor.desafio),
    signal: controller.signal,
    aoAtualizar: (valor) => {
      const area = document.querySelector("[data-attempt-state]");
      if (area) area.textContent = `Estado informado pelo serviço: ${valor.estado}`;
    },
  }).then((valor) => continuarTentativa(estado, valor)).catch((erro) => {
    if (erro.name !== "AbortError") {
      const area = document.querySelector("[data-attempt-error]");
      if (area) area.textContent = mostrarErro(erro);
    }
  });
  document.querySelector('[data-action="presenca-status"]')?.addEventListener("click", async () => {
    try { await continuarTentativa(estado, await consultarTentativa(estado)); }
    catch (erro) { avisar(mostrarErro(erro)); }
  });
}

function mostrarDesafioPresenca(estado, desafio) {
  salvarEstado("presenca.desafio", desafio);
  const orientacao = desafio.orientacao || desafio.direcao_movimento || "siga a orientação do servidor";
  const instrucoes = { frente: "Olhe para a câmera", esquerda: "Vire levemente para a esquerda", direita: "Vire levemente para a direita" };
  const instrucao = instrucoes[orientacao] || orientacao;
  studentLayout(`Etapa ${texto(desafio.etapa)}`, "Siga a orientação atual emitida pelo servidor. A captura é enviada para validação; este navegador não avalia movimento nem identidade.", `<p class="challenge-step"><span class="challenge-step__number">${texto(desafio.etapa)}</span><strong>${escapeHtml(instrucao)}</strong></p><p class="field-hint">Prazo indicado pelo serviço: ${dataLocal(desafio.expira_em || estado["presenca.expira_em"])}</p>${cameraMarkup()}<div class="button-row">${button("Enviar captura desta etapa", "capture-step", "button--dark")}${button("Encerrar câmera", "camera-stop", "button--quiet")}</div><div data-capture-result role="status" aria-live="polite"></div><section class="accessibility-note"><h2>O desafio não é possível?</h2><p>Interrompa a câmera e solicite revisão manual na tela de início, com uma justificativa.</p>${button("Solicitar revisão acessível", "presenca-accessible", "button--quiet")}</section>` , "Presença");
  bindCamera(async (captura) => {
    const boton = document.querySelector('[data-action="capture-step"]');
    const resultado = document.querySelector("[data-capture-result]");
    boton.disabled = true;
    resultado.textContent = "Enviando captura da etapa informada…";
    try {
      await api.post(apiPath(`/tentativas/${encodeURIComponent(estado["presenca.tentativa_id"])}/capturas`), {
        etapa: Number(desafio.etapa), nonce: desafio.nonce, captura_base64: captura.base64,
      }, { headers: { Authorization: `Bearer ${estado["presenca.credencial_captura"]}` } });
      camera.encerrar(document.querySelector("#camera-video"));
      salvarEstado("presenca.desafio", null);
      const atual = await consultarTentativa(estadoSalvo());
      await continuarTentativa(estadoSalvo(), atual);
    } catch (erro) {
      boton.disabled = false;
      resultado.textContent = mostrarErro(erro);
      resultado.className = "notice notice--error";
    }
  }, { autoCaptureMs: 3000, onStart: () => avisar("Câmera pronta. Posicione-se conforme a orientação; a captura começa em três segundos. Você pode capturar antes.") });
  document.querySelector('[data-action="presenca-accessible"]')?.addEventListener("click", () => {
    camera.encerrar(document.querySelector("#camera-video"));
    const original = estadoSalvo();
    mostrarFormularioRevisaoAcessivel(original["presenca.credencial"], original["presenca.sessao_id"], "A câmera foi encerrada. A tentativa atual não foi recriada. A matrícula sozinha não confirma identidade.");
  });
}

async function iniciar() {
  const path = location.pathname;
  if (path === "/") { landing(); return; }
  if (path === "/login") {
    try { if (await obterSessao()) { location.replace("/professor"); return; } } catch { /* Formulário exibirá erros no envio. */ }
    await loginPage();
    return;
  }
  if (path === "/trocar-senha") {
    try { if (!(await obterSessao())) { location.replace("/login"); return; } } catch { location.replace("/login"); return; }
    await trocarSenha();
    return;
  }
  if (path === "/professor" || path.startsWith("/professor/")) { await professor(); return; }
  if (path === "/cadastro" || path.startsWith("/cadastro/")) {
    await paginaCadastro(path === "/cadastro" ? "" : decodeURIComponent(path.slice("/cadastro/".length)));
    return;
  }
  if (path === "/presenca" || path.startsWith("/presenca/")) {
    await paginaPresenca(path === "/presenca" ? "" : decodeURIComponent(path.slice("/presenca/".length)));
    return;
  }
  render(`<main class="not-found wrap" id="conteudo"><p class="eyebrow">FaceDiff</p><h1>Esta página não existe.</h1><a class="button button--dark" href="/">Voltar ao início</a></main>`);
}

document.addEventListener("submit", async (event) => {
  const form = event.target.closest("form");
  if (!form) return;
  if (form.matches('[data-form="login"]')) {
    event.preventDefault();
    const dados = new FormData(form);
    try {
      const resposta = await api.post(apiPath("/auth/login"), { usuario: dados.get("usuario"), senha: dados.get("senha") }, { csrf: false });
      sessao = resposta.conta;
      api.setCsrfToken(resposta.csrf_token);
      location.replace(sessao.troca_senha_obrigatoria ? "/trocar-senha" : "/professor");
    } catch (erro) { formularioErro(form, erro); }
  } else if (form.matches('[data-form="trocar-senha"]')) {
    event.preventDefault();
    const dados = new FormData(form);
    try {
      await api.post(apiPath("/auth/trocar-senha"), { senha_atual: dados.get("senha_atual") || null, nova_senha: dados.get("nova_senha") });
      api.clearCsrfToken();
      sessao = null;
      form.innerHTML = `${mensagem("Senha alterada. Entre novamente com a nova senha.", "success")}<a class="button button--dark" href="/login">Ir para o acesso</a>`;
      form.focus();
    } catch (erro) { formularioErro(form, erro); }
  }
});

document.addEventListener("click", async (event) => {
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "logout") {
    try { await api.post(apiPath("/auth/logout"), {}); } catch { /* A sessão pode já estar encerrada no servidor. */ }
    api.clearCsrfToken();
    sessao = null;
    location.assign("/");
  }
  if (action?.startsWith("select-class:")) {
    event.preventDefault();
    const id = action.slice("select-class:".length);
    const url = new URL(location.href);
    url.searchParams.set("turma", id);
    history.pushState({}, "", url);
    void professor();
  }
});

window.addEventListener("popstate", () => { void iniciar(); });
window.addEventListener("pagehide", () => {
  limparRecursos();
  camera.encerrar();
});

void iniciar();
