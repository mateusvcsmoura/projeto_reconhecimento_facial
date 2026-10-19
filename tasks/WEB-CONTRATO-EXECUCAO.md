# Contrato de execução — FaceDiff web, tasks 009–020

Data: 18/10/2026. **As tarefas 009–015 foram implementadas no workspace; 010,
013, 014 e 015 foram publicadas na `main` após autorização explícita. As migrations
0006–0010 foram validadas em PostgreSQL descartável. A web não foi implantada.
As tarefas 016–020 continuam pendentes.** O runtime web passou em testes no
Ubuntu 24.04; a task 013 validou o provider MediaPipe Linux com modelo local e
imagem sintética em WSL/Python 3.14. Não houve validação biométrica real. Consulte
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

### Contratos estabelecidos na tarefa 011

- A revisão `0006` cria solicitações separadas de `Aluno`, conjuntos versionados
  e três referências por ordinal. Embeddings são persistidos como float32 de
  dimensão 512; cada captura guarda seu próprio consentimento/versão e caminho
  relativo privado. A revisão foi testada somente no banco descartável
  `task011_web_references_test_20261018`; `escola` continua sem `0006`.
- Cadastro pendente não reserva matrícula. A aprovação exige vínculo de turma
  autorizado e conferência independente; matrícula existente preserva nome,
  foto e embedding, adicionando apenas vínculo. Corridas usam unicidade SQL e
  reavaliação transacional.
- Atualização biométrica é solicitação separada e aprovação exclusiva de admin;
  nova versão é ativada atomicamente e a anterior deixa de ser ativa. Consultas
  internas de galeria retornam somente conjuntos ativos. Falha SQL na troca
  descarta o candidato e tenta remover seus arquivos; limpeza expirada/rejeitada
  registra estado e pode ser repetida.
- Na task011, o armazenamento passou a exigir root privado injetado e ACL
  restrita no Windows. A integração de referências com jobs e a revalidação da
  versão antes de persistir continuam a cargo dos consumidores futuros; a
  infraestrutura de fila/lease foi criada na task012. A task011 não criou rotas,
  convites, DTO HTTP ou interface.

### Contratos estabelecidos na tarefa 012

- A revisão `0007` cria `jobs_faciais_web` para reservas, estado, idempotência,
  prazo e hash de lease/credencial. A admissão e o claim serializam no
  PostgreSQL; o índice parcial protege um job `processando`, com até dez
  aguardando/reservados e um ativo adicional. Migração e quatro testes passaram
  somente no banco descartável `task012_web_worker_test_20261018`; `escola` não
  recebeu `0007`.
- `FilaFacial` limita capturas a três e 8 MiB cada por padrão de laboratório,
  com quota padrão de 300 MiB. Credenciais de operação são opacas; `GET
  /api/v1/operacoes/{id}` exige `Authorization: Bearer ...` e responde 404
  genérico para credencial incorreta. Fila cheia retorna 503 com `Retry-After`.
- `src.face_worker_main` mantém processo único por lock local e advisory lock
  PostgreSQL, aquece FaceNet512/MiniFASNet somente com pesos locais e processa
  jobs sequencialmente. Temporários ficam em raiz privada; o ambiente de
  produção exige tmpfs compartilhado e quota suficiente. Reinício invalida
  jobs ativos sem replay; resultado após lease/prazo não é aceito. O worker
  mantém o slot até o executor retornar. Não há watchdog para encerrar uma
  inferência nativa bloqueada indefinidamente; o slot permanece ocupado até
  retorno ou reinício controlado, com invalidação antes do próximo claim.
- Esta entrega não inclui rotas de upload/reserva/cancelamento nem handlers
  biométricos habilitados; sem handler o job é recusado. A task 014 conectou
  cadastro; task 015 conecta presença. Rate limit de abuso nas rotas públicas
  de submissão pertence a essas integrações; esta tarefa não declara limite de
  requisições
  para a consulta de status. Não houve validação de tmpfs Linux ou VPS.

### Contratos estabelecidos na tarefa 013

- A revisão `0008` cria `desafios_verificacao_web`, estado mínimo vinculado ao
  mesmo job, aluno e conjunto de referências: hash do nonce, direção, prazo,
  estado/etapas e motivo técnico. Não armazena frames, landmarks ou embeddings.
  Foi migrada, verificada com `alembic check`, exercitada e revertida no banco
  descartável task012; `escola` não recebeu `0008`. O downgrade recusa remover
  a tabela enquanto houver desafios persistidos.
- `VerificarIdentidade` compara exclusivamente três referências ativas,
  ordinais 1–3, da matrícula autorizada e do conjunto/versão selecionados. Exige
  vetores Facenet512/512D normalizados e finitos e usa a mediana das três
  distâncias cosseno `<= 0,30`. Esta política não foi calibrada; não altera o
  pipeline CLI, o threshold histórico nem o matching 1:N.
- `DesafioCaptura` emite nonce HMAC ligado ao UUID da reserva, persiste somente o
  hash e exige frente, virada aleatória e retorno, na ordem, dentro de até 120s
  limitados pelo prazo da reserva. O serviço reutiliza um job `presenca` e a fila
  única da 012; etapas validadas liberam o slot ativo, preservam quota e
  temporários, e retomadas recebem prioridade. Reenvio da mesma etapa com nonce
  válido é idempotente e não cancela uma tentativa concorrente.
- O worker valida rosto único, qualidade, anti-spoofing estrito, identidade 1:1,
  continuidade entre embeddings e pose calculada no backend. O provider de pose
  MediaPipe roda em processo/ambiente Linux separado por pipes locais; o app usa
  `opencv-python` e o ambiente filho usa `opencv-contrib-python`, sem coexistirem
  no mesmo ambiente. `requirements-landmarks-linux.txt` fixa MediaPipe 0.10.35;
  Ubuntu mínimo precisa disponibilizar `libGLESv2.so.2` (`libgles2`). A geometria
  de pose é heurística não calibrada.
- Antes do `cv2.imdecode`, Pillow lê apenas o cabeçalho e rejeita imagens acima
  de 4.194.304 pixels ou 8192 pixels por lado. A validação sintética confirmou
  que esse limite evita entregar imagens superdimensionadas ao decodificador.
  O worker retorna `ResultadoFacial` restrito ao backend e não grava presença.
- A task 013 não cria rotas HTTP, autenticação de aluno nem interface. O futuro
  consumidor precisa passar `aluno_id_autorizado` somente após aplicar a
  autorização correspondente. Testes não usaram pessoas ou dados biométricos
  reais; movimentos, acessibilidade, eficácia anti-spoofing e desempenho real
  permanecem sem validação.

### Contratos estabelecidos na tarefa 014

- A revisão `0009` cria links revogáveis de turma, hashes de tokens, credenciais
  efêmeras, vínculo de solicitação/job e campos para nonce hash-only, direção e
  prazo do desafio de cadastro. Foi aplicada, verificada com `alembic check`,
  testada e revertida no banco descartável `task014_cadastro_api_test_20261018`;
  `escola` não recebeu a revisão.
- A API expõe emissão/revogação de links, troca por credencial, cadastro,
  captura/status com credencial do solicitante, listagem/revisão por professor
  responsável e solicitação/consentimento/aprovação de atualização biométrica.
  O token do link é trocado por credencial curta e não é persistido em claro;
  respostas não incluem fotos, embeddings ou caminhos privados.
- O cadastro aceita exatamente três frames codificados em Base64 depois do
  consentimento. O nonce de 256 bits é devolvido uma vez, persiste apenas como
  SHA-256 e expira em até 120 segundos; direção aleatória exige frente/virada/
  retorno. O worker aplica pose da task013, face única, qualidade,
  anti-spoofing e continuidade antes de anexar referências pendentes.
- Essa sequência de coleta por lote não é uma sessão de presença nem prova
  biométrica autônoma de vivacidade. Não houve teste com pessoa, validação
  visual, tmpfs Linux, implantação ou avaliação de latência na VPS. A task015
  adiciona rate limit com chave HMAC nas rotas de presença; limites gerais para
  todas as rotas públicas continuam como gate operacional.

### Contratos estabelecidos na tarefa 015

- A revisão `0010` cria sessões de presença, tentativas com estados/ordinal,
  hashes de idempotência e de payload, buckets de rate limit e vínculos das
  presenças a sessão e tentativa. Foi aplicada até `head`, aprovada por
  `alembic check`, exercitada por cinco testes PostgreSQL e revertida pela
  fixture no banco descartável `task015_presenca_test_20261018`; `escola` não
  recebeu `0010`.
- A API publica criação de sessão e link de finalidade `presenca`, revogação,
  início com `Idempotency-Key`, upload das três etapas e consulta de estado.
  O aluno é resolvido pela matrícula informada, mas só pode iniciar quando há
  vínculo ativo e conjunto aprovado com as três referências. A matrícula não é
  autenticação.
- A janela de início é `[inicio, fim)`. O servidor recebe o payload completo
  até `min(início + 120s, fim + 120s)`, inclusive no instante-limite; timestamps
  enviados pelo cliente são rejeitados. Capturas idênticas podem ser repetidas
  sem persistir outra cópia; bytes diferentes na mesma etapa são recusados.
- Até três emissões por aluno/sessão são reservadas em transação, com no máximo
  uma ativa. A fila e o desafio 1:1 da task013 são reutilizados. A confirmação
  só ocorre após transação que revalida sessão, vínculo, conjunto/referência,
  desafio completo e lease; revogação durante processamento impede commit.
  Índices parciais preservam a presença diária da CLI e o ramo web é único por
  aluno/sessão.
- Os testes usaram dados e embeddings sintéticos; não houve inferência com
  pessoas, teste visual, uso de webcam, deploy, nem aplicação da migration ao
  banco `escola`. A interface continua exclusiva da task020.

## 5. Permissões para futuras execuções

Ao receber uma task para executar, implementar somente seu código/testes/docs.
Instalar dependências apenas em ambiente isolado do trabalho autorizado;
respeitar permissões do ambiente e não modificar ambientes pessoais/produção.

**Não há autorização implícita** para banco operacional, migrations online,
provisionamento/contratação, deploy, GoogleDrive, imagens reais, cadastro de
participantes, troca de limiar ou desligamento de antispoofing. Preparar os
artefatos, indicar bloqueio específico e concluir o que independe dele.
Integração que cria/migra/limpa banco exige autorização explícita de ambiente
descartável; nunca ler `.env` real como fallback.

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

**Autorização permanente de publicação registrada em 18/10/2026:** ao pedir a
implementação de uma task, o solicitante autoriza criar commits organizados e
fazer push para `main` ao concluir, sem nova confirmação. Aplicar salvo
instrução posterior em contrário. Isso não autoriza force push, publicação de
alterações alheias, deploy ou operações de infraestrutura.

Nenhum teste deve coletar webcam, buscar datasets ou baixar biometria da internet.
Pesos de modelos não são autorização para usar imagens de terceiros; registrar
origem/licença e download separado quando necessário. Nenhuma imagem da conversa
deve ser incorporada às fixtures.

## 6. Resultado e publicação

Criar RESULTADO.md somente após executar: HEAD/branch, escopo, comandos completos,
ambiente, testes aprovados/falhos/não executados, migrations só preparadas ou
aplicadas com autorização, riscos e condição de parada. Nenhum número de teste
histórico vira evidência da entrega atual. Não marcar skips como aprovação.

**A publicação está autorizada para tarefas de implementação pelo registro
permanente acima.** Ao concluir uma task:

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
