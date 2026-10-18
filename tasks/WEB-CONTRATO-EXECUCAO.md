# Contrato de execução — FaceDiff web, tasks 009–020

Data: 18/10/2026. **As tarefas 009 e 010 foram implementadas; a 010 foi
publicada na `main` após autorização explícita. A integração PostgreSQL passou;
as tarefas 011–020 continuam pendentes.** O runtime web separado passou em testes no
Ubuntu 24.04. A stack ML completa ainda não foi validada em Linux; consulte
[resultado 009](009-web-fundacao-linux/RESULTADO.md) e
[runtime web](../docs/FACEDIFF-WEB-RUNTIME.md). Não houve deploy.
Executor previsto para as próximas tasks: Luna 6, esforço High, execução inline.

## 1. Ordem e interface por último

Decisão mais recente: **primeiro todas as funcionalidades e testes do backend;
interface somente na020**. API, schemas HTTP, worker e testes de cliente não
são interface visual. Não criar templates, CSS, JavaScript de câmera, páginas
de login/painel ou protótipos de produto nas009–019. Documentação de endpoints
é permitida; não usar um frontend temporário para substituir testes.

A019 emite GATE_BACKEND_PARA_INTERFACE. Sem aprovação real, não iniciar020.
Testes de câmera/permissão, acessibilidade e E2E em navegador ficam na020 e são
necessariamente posteriores à construção da interface. Medição real da VPS,
restore real do Drive e biometria autorizada são gates operacionais separados;
ausência de autorização não pode ser escondida como teste aprovado.

## 2. Fontes obrigatórias e precedência

- [Planejamento consolidado](../docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md).
- [Arquitetura e operação](../docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md).
- [Roadmap atualizado](../docs/FACEDIFF-WEB-ROADMAP.md).
- [Transição de schema](WEB-MIGRACOES.md).
- AGENTS.md, CLAUDE.md, instructions relevantes, desenho/plano da task e
  RESULTADO das dependências; conferir código real, não só documentação.

A ordem009–020 substitui a ordenação W01–W12 anterior que intercalava interface
com funcionalidades. Não substitui requisitos de produto. Diretórios/nomes
propostos podem ser ajustados para reutilizar código existente, registrando o
mapeamento; não deixar contratos diferentes entre tarefas dependentes.

## 3. Requisitos transversais

| Requisito | Valor/contrato |
|---|---|
| Hospedagem | Hostinger KVM2, 2vCPU/8GB/100GB, Ubuntu24.04, Compose, Caddy, PostgreSQL local |
| Estrutura | FastAPI recomendado como nova apresentação; domínio/application sem dependência de HTTP, câmera ou SQL concreto |
| Professor | Usuário/senha, um responsável/turma; admin inicial seguro, reset administrativo sem e-mail |
| Turmas/alunos | Matéria e período obrigatórios; matutino/diurno/noturno; matrícula globalUK, N:N |
| Cadastro | Link7dias revogável; consentimento antes de upload; três capturas; aprovação independente; professor sem acesso à biometria |
| Existente | Matrícula não autentica, não sobrescrever referências/nome por link; novo vínculo autorizado |
| Verificação | Matrícula informada,1:1, FaceNet512,0,30, antispoofing obrigatório, desafio curto backend |
| Presença | Única por aluno/sessão, link compartilhado; nenhuma confirmação antes do commit |
| Prazo | Início dentro da janela; envio completo em prazo curto do servidor, teto fim+120s; processamento pode terminar depois |
| Tentativas | Três emissões por aluno/sessão, uma ativa; revisão manual auditada; alternativa acessível |
| Fila | Uma inferência ativa, dez aguardando como limite inicial incluindo reservas; banco/lease/idempotência |
| Gestão | CRUD autorizado, correção justificada, auditoria, CSV por turma/período sem biometria |
| Interface020 | Polling15s, responsiva, câmera explícita com captura automática, sem videoconferência/localização |
| Dados | EmbeddingsPG, fotos privadas persistentes, captura de presença transitória e fora do backup |
| Backup | Local+Drive cifrados, diário/manual, restauração comprovada; não contratar extra Hostinger |
| Finalidade | Demonstração~10dias, integrantes autorizados, sem reutilização para pesquisa; eliminação/encerramento documentados |

As recomendações da consolidação (mediana de três distâncias, TTL de tentativa,
fila SQL, três gerações de backup) são escolhas de engenharia para executar,
não evidência biométrica. Qualquer mudança deve ser documentada e testada,
sem alterar threshold/segurança por conveniência. Timeout de produção e capacidade
dependem da medição019 e do gate operacional.

## 4. Convenções de integração

- Composition root web separado; API não importa pesos de ML nem abre webcam.
  Serviços são construídos por injeção, com fakes em testes.
- Rotas sob `/api/v1`, mesma origem. UTC aware no banco, America/Sao_Paulo na
  apresentação/CSV. Relógio injetável; cliente não define horário autorizativo.
- Erros públicos tipados com request_id, sem traceback/segredo. Não expor nome,
  estado global de matrícula ou dados de outra turma para clientes anônimos.
- Sessão de autenticação é distinta de sessão de presença. Link tem finalidade
  validada; credencial efêmera identifica o acesso à tentativa, não autentica
  identidade biométrica. UUID/ID aleatório não substitui autorização.
- Uma transação para mutação+auditoria; arquivos requerem compensação/reconciliação.
  Idempotência e constraints SQL resolvem concorrência, não check-then-insert
  isolado. Resultado tardio revalida estado/versão/lease.
- Atualizar OpenAPI/DTOs e este contrato quando necessário, antes de tarefa
  consumidora. Não renomear endpoint silenciosamente na interface020.
- Testes podem usar fakes paraML; não usar mocks para alegar prova de constraint,
  lock ou migrationPostgreSQL. Dados sintéticos não provam acurácia.

### Contratos estabelecidos na tarefa 009

- `GET /health/live` retorna `{"status":"live"}` sem consultar dependências.
- `GET /health/ready` retorna `{"status":"ready|not_ready","componentes":{...}}`;
  indisponibilidade resulta em HTTP 503 e não inclui exceções.
- OpenAPI JSON fica em `/api/v1/openapi.json`; páginas `/docs` e `/redoc` ficam
  desabilitadas até a task de interface.
- Erros HTTP seguem `{"codigo":"...","mensagem":"...","request_id":"..."}`;
  o mesmo identificador aparece em `X-Request-ID`. Mensagens de validação e
  exceções internas não são encaminhadas ao cliente.
- A API é criada por `create_app(settings, services)` e não importa `src.main`,
  OpenCV, DeepFace, TensorFlow, PyTorch ou MediaPipe. `src.web_main` cria uma
  engine SQLAlchemy lazy; conexão ocorre somente no probe de readiness.
- `WebSettings` lê somente `WEB_*`, não carrega `.env`, exige ambiente, URL do
  banco, segredo e retenção. Testes exigem opt-in `WEB_DATABASE_DISPOSABLE=true`
  e marcador no nome do banco; produção rejeita loopback e banco descartável.
- O ambiente HTTP usa `requirements-web.txt`, sem fornecedor de `cv2` ou modelos.
  A CLI e seus requisitos permanecem separados.

### Contratos estabelecidos na tarefa 010

- Contas web têm usuário NFKC/casefold único, papéis `professor`/`admin`, hash
  Argon2id, estado ativo, troca obrigatória e versão de credencial.
- Sessão opaca em cookie `Secure`/`HttpOnly`/`SameSite=Lax`, expiração de 30
  minutos sem atividade e 8 horas absolutas; o banco guarda somente hashes.
- `Origin` configurado e token CSRF são exigidos em mutações. Login limita
  tentativas por conta e IP, com resposta não enumerável.
- Perfil de professor e responsável nullable para turmas legadas entram na
  revisão `0005`; sem responsável, turma fica inacessível a professores. A
  migration `0005` foi aplicada ao banco local `escola`; a integração PostgreSQL
  passou em banco descartável e `alembic check` não detectou drift.
- Auditoria de mutação compartilha a transação e trigger PostgreSQL impede
  atualização/exclusão de eventos. Admin inicial exige comando local explícito.
- Rotas, variáveis `WEB_PUBLIC_ORIGIN`/`WEB_TRUSTED_PROXY_CIDRS`, bootstrap e
  pendências estão em [FACEDIFF-WEB-AUTH.md](../docs/FACEDIFF-WEB-AUTH.md).

## 5. Permissões para futuras execuções

Ao receber uma task para executar, implementar somente seu código/testes/docs.
Instalar dependências apenas em ambiente isolado do trabalho autorizado;
respeitar permissões do ambiente e não modificar ambientes pessoais/produção.

**Não há autorização implícita** para banco operacional, migrations online,
provisionamento/contratação, deploy, GoogleDrive, imagens reais, cadastro de
participantes, troca de limiar, desligamento de antispoofing ou publicaçãoGit.
Preparar os artefatos, indicar bloqueio específico e concluir o que independe
dele. Integração que cria/migra/limpa banco exige autorização explícita de
ambiente descartável; nunca ler `.env` real como fallback.

**Autorização explícita registrada em 18/10/2026:** o usuário autorizou
migrations e testes com escrita em bancos locais de desenvolvimento/teste do
projeto, inclusive reset e seed sintético necessários. Para a task 010, pode-se
criar e usar banco PostgreSQL descartável identificado e, após validar o alvo,
aplicar a migration `0005` ao banco local do projeto. Confirmar host e banco
antes de qualquer escrita; esta autorização não alcança produção, banco remoto
ou compartilhado, nem imagens biométricas reais. O `DATABASE_URL` local pode
ser usado somente para identificar/conectar ao banco de desenvolvimento depois
de validar host e nome; nunca exibir a credencial ou usá-la como fallback para
as configurações `WEB_*`.

Nenhum teste deve coletar webcam, buscar datasets ou baixar biometria da internet.
Pesos de modelos não são autorização para usar imagens de terceiros; registrar
origem/licença e download separado quando necessário. Nenhuma imagem da conversa
deve ser incorporada às fixtures.

## 6. Resultado e publicação

Criar RESULTADO.md somente após executar: HEAD/branch, escopo, comandos completos,
ambiente, testes aprovados/falhos/não executados, migrations só preparadas ou
aplicadas com autorização, riscos e condição de parada. Nenhum número de teste
histórico vira evidência da entrega atual. Não marcar skips como aprovação.

**Commit e push não estão automaticamente autorizados nos novos pacotes.**
A restrição explícita da consolidação recente substitui a autorização herdada
dos prompts001–008. Se o usuário instruir commit+push na execução da task:

1. Antes de cada commit e novamente antes do push, reler `AGENTS.md` na raiz e
   seguir suas instruções. Usar apenas identidade/credenciais Git já
   configuradas do solicitante; mensagem PT-BR, sem se marcar como Co Author ou
   incluir `Co-authored-by`. Separar commits por escopo quando houver muitos
   arquivos ou unidades lógicas distintas.
2. Conferir branch/status/remoto/divergência e commits locais; publicar na main
   somente o trabalho autorizado. Não publicar commits desconhecidos.
3. Stage por caminhos explícitos, revisar diff e `git diff --cached --check`;
   sem `git add .`, `-A`, `commit -a`, dados, modelos ou segredos.
4. Push sem force/reset destrutivo e sem contornar hooks; confirmar hash/estado
   remoto. Push não é deploy nem autorização de migration.

## 7. Condição de parada

Finalizar só a task recebida. Preenchimento de checklist não substitui evidência.
Reportar o estado real, inclusive gates impedidos por falta de ambiente. Não
avançar à020 por pressão para concluir se019 não aprovou o backend.
