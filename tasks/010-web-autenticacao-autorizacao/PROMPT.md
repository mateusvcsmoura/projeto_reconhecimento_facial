# Prompt de execução — 010 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório
`projeto_reconhecimento_facial`.

**Execute somente a task 010 — Contas, autenticação, professor responsável e auditoria. O desenho e o plano estão
definidos. Apenas execute o escopo autorizado, teste e documente; não reabra
brainstorming, não delegue e não avance automaticamente para outra task.**

## Leitura obrigatória

1. `AGENTS.md`, `CLAUDE.md`, instruções relevantes e arquitetura atual.
2. `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`.
3. `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`.
4. `tasks/WEB-CONTRATO-EXECUCAO.md` e `tasks/WEB-MIGRACOES.md`.
5. `tasks/010-web-autenticacao-autorizacao/DESENHO.md` e `tasks/010-web-autenticacao-autorizacao/PLANO.md`, integralmente.
6. Resultados reais das dependências: **009**.

Use Superpowers executing-plans quando disponível; aprove internamente escolhas
rotineiras, sem pedir confirmações de decisões já definidas. Isso não amplia
permissões de banco, dados reais, contratação ou publicação.

## Entrega específica

Criar contas com papel professor/admin, usuário normalizado único, senha Argon2id, conta ativa, troca obrigatória e versão de credencial. Professor é entidade/perfil associado à conta; turma web exige exatamente um responsável. Turmas legadas sem responsável permanecem inacessíveis pela web até atribuição administrativa explícita. Não criar professor fictício em migration.

Sessão de autenticação opaca com hash no banco, cookie Secure/HttpOnly/SameSite; proposta adotada para execução: 30 minutos de inatividade e 8h absolutas. Rotacionar no login, invalidar em logout/reset/desativação. CSRF obrigatório em mutações autenticadas; validar Origin. Login limitado por conta/IP, sem enumerar usuário. Hash não é reversível.

Bootstrap administrativo é comando explícito sem endpoint público, senha padrão, argumento de linha de comando com senha ou log de segredo. Reset por admin após verificação independente, credencial temporária de uso único com 30 minutos de validade, troca obrigatória e auditoria. Transferir turma é operação administrativa auditada.

Criar auditoria genérica append-only com evento mínimo (ator, ação, alvo, instante, justificativa, antes/depois permitidos). Auditoria de sucesso e mutação precisam da mesma transação. Não tornar toda operação uma segunda conexão que possa confirmar antes do registro auditado.

### Contratos que você deve respeitar

AutenticarProfessor.executar(usuario, senha, contexto_cliente) -> SessaoAutenticacao.
AutorizarTurma.exigir(ator, turma_id, acao) -> ContextoTurma; sempre lookup no servidor.
POST /api/v1/auth/login, /logout, /trocar-senha; POST /api/v1/admin/contas; POST /api/v1/admin/contas/{id}/redefinir-senha.
GET /api/v1/me retorna somente id/papel/estado necessário.
Auditoria.registrar(transacao, evento) compartilha unidade de trabalho; erro de auditoria reverte mutação.

### Provas mínimas

- Professor A não obtém nem altera turma B; admin é explícito; conta desativada perde sessões.
- Expiração em 30min idle/8h absoluta e reset revogam; credencial temporária não reutiliza.
- Falha de auditoria reverte; cookie/CSRF/Origin incorretos negam; senha/token não aparecem em logs.
- Bootstrap repetido não cria admin público nem substitui senha silenciosamente.

## Limites e conclusão

**Não criar interface, páginas, templates ou fluxo de câmera no navegador.** Use testes/cliente HTTP para provar a funcionalidade. UI fica exclusivamente na020.

Não executar migration, acessar banco operacional, conectar Google Drive,
provisionar VPS, realizar deploy ou usar rostos reais sem autorização específica
vigente. Preparar código/migration/testes não significa autorização para aplicá-los.
Não desabilitar antispoofing ou alterar threshold0,30 para fazer testes passarem.
Não interpretar matrícula informada como autenticação.

Autenticação e autorização exercitadas por HTTP/testes, sem interface. Migração preparada com transição legada documentada e nenhuma conta real criada.

Ao terminar, criar `tasks/010-web-autenticacao-autorizacao/RESULTADO.md`, atualizar índice e relatar comandos
efetivos, contratos, pendências e estado dos gates. **Não fazer commit/push por
autorização herdada de tasks001–008.** A restrição da consolidação atual prevalece;
se o usuário autorizar explicitamente publicação nesta execução, fazer commit
em PT-BR e push na main conforme procedimento do contrato comum. Não contratar
ou implantar como consequência do push.

## Regra obrigatória de commit e push

Antes de qualquer commit ou push, leia ou releia o arquivo AGENTS.md na raiz do repositório e siga suas instruções vigentes. A autorização desta tarefa pode limitar ou proibir a publicação; esta regra não amplia autorizações.

- Mensagens de commit sempre em PT-BR. Não se identifique como Co Author nem adicione Co-authored-by; use somente a identidade e as credenciais Git já configuradas do solicitante, sem reconfigurar autoria.
- Se a entrega envolver muitos arquivos ou unidades lógicas distintas, divida-a em commits separados e organizados por escopo; não agrupe mudanças independentes em um commit monolítico.
- Adicione ao staging apenas caminhos explícitos e revise git diff --cached --stat, git diff --cached --check e o conteúdo staged antes de cada commit. Faça push somente para o branch/remoto autorizado e sem force.
