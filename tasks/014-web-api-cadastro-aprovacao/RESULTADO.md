# Resultado — tarefa 014: API de cadastro por link e aprovação

**Estado: implementada, validada e publicada na `main`; não implantada.**
Execução em 18/10/2026. Branch inicial `main`, HEAD inicial
`040ac75607909cace4dda0a9cd7d6af67c750223`. A implementação foi feita no
workspace existente e preservou os diretórios temporários de testes que já
estavam presentes.

## Entrega

A API emite links de cadastro aleatórios de 256 bits, escopados à turma e com
validade limitada a sete dias. O banco guarda somente o hash do token; a troca
do link produz credencial efêmera. Professor responsável pode revogar o link,
cancelando coletas relacionadas. Cadastro público exige credencial própria,
nome/matrícula e consentimento de aviso versionado antes de aceitar mídia.

A submissão exige três imagens Base64 e um desafio emitido pelo servidor. O
nonce de 256 bits é devolvido uma vez, armazenado apenas como SHA-256 e expira
em até 120 segundos. O worker valida uma face por frame, sequência frente/
virada aleatória/retorno, qualidade, anti-spoofing e continuidade entre
embeddings antes de anexar três referências privadas e deixar a solicitação
pendente de aprovação. O professor confirma identidade por método e justificativa
independentes; a resposta não inclui fotos, embeddings ou caminhos privados.
Solicitações de atualização biométrica usam credencial própria e só recebem o
desafio após o consentimento do aluno; aprovação administrativa continua
separada.

O fluxo de cadastro por lote reaproveita a análise de pose da tarefa 013, mas
não cria identidade de presença nem é prova biométrica independente de
vivacidade. O pipeline CLI, FaceNet512, MiniFASNet, threshold `0.30` e regras
existentes de reconhecimento não foram alterados.

## Decisões de implementação

- **Reuso do desafio da tarefa 013:** o protocolo 013 vincula etapas e nonce a
  um job de presença individual. O cadastro 014 recebe três frames como lote.
  Mantive o contrato HTTP de lote e usei nonce hash-only, direção aleatória e
  validação de pose frente/virada/retorno dentro do worker. Risco aceito: o
  desafio de lote não prova sozinho que as imagens foram capturadas ao vivo ou
  em tempo real; qualidade e anti-spoofing continuam requisitos independentes.
- **Atualização biométrica:** o servidor emite o desafio somente depois do
  aceite do aviso versionado e devolve o nonce uma vez nessa resposta. O cliente
  precisa mantê-lo até enviar os três frames.
- **Persistência:** a migration `0009` adiciona links, credenciais efêmeras,
  associações da solicitação com link/job e campos hash-only do desafio. O
  downgrade recusa remover esses dados quando ainda existirem registros.

## Arquivos

- Implementação: `src/application/use_cases/gerenciar_links.py`,
  `src/application/use_cases/solicitar_cadastro_web.py`,
  `src/application/use_cases/solicitar_atualizacao_biometrica.py`,
  `src/infrastructure/repositories/postgres_link_repository.py`,
  `src/infrastructure/repositories/postgres_solicitacao_repository.py`,
  `src/infrastructure/face_recognition/processador_cadastro_web.py`,
  `src/presentation/web/routes/links.py`, `src/presentation/web/routes/cadastros.py`,
  `src/presentation/web/dependencies.py`, composições web/worker, configurações,
  DTOs e migration `migrations/versions/0009_links_cadastro_api.py`.
- Testes: `tests/unit/test_api_cadastro_web.py`,
  `tests/unit/test_gerenciar_links.py`,
  `tests/unit/test_postgres_link_repository.py`,
  `tests/unit/test_processador_cadastro_web.py`,
  `tests/unit/test_composicao_web_task014.py`,
  `tests/unit/test_composicao_worker_task014.py`, ajustes nos testes de
  repositório/fundação existentes e `tests/integration/test_cadastro_web_api.py`.
- Documentação: este resultado, `DESENHO.md`, `PLANO.md`, `tasks/README.md`,
  `tasks/WEB-MIGRACOES.md`, `tasks/WEB-CONTRATO-EXECUCAO.md`,
  `docs/FACEDIFF-WEB-RUNTIME.md`, `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`,
  `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md` e `AGENTS.md`.

## Verificações executadas

Ambiente de teste: Windows, `.venv-ml`, Python 3.14.3. Os testes usaram
embeddings, contas e registros sintéticos; não abriram webcam nem usaram imagens
faciais reais.

- Focados da API, composição, worker, repositórios e processor: **42 passaram**.
- Suíte unitária com a configuração de cobertura do CI: **1.127 passaram**,
  cobertura total **81,87%** (mínimo 80%).
- Integração PostgreSQL: **1 passou**; a migration foi aplicada até `head`,
  `alembic check` passou, o fluxo de solicitação/revogação foi verificado e a
  fixture reverteu o banco descartável a `base`.
- `ruff check` nos arquivos Python alterados: aprovado.
- `ruff format --check` nos arquivos Python alterados: aprovado.
- `mypy src scripts`: aprovado, sem erros.
- `pip check` em `.venv-ml`: `No broken requirements found`.
- `git diff --check`: aprovado.

Comandos de verificação executados (PowerShell, na raiz do repositório):

```powershell
.venv-ml\Scripts\python.exe -m pytest tests/unit/test_api_cadastro_web.py tests/unit/test_composicao_web_task014.py tests/unit/test_composicao_worker_task014.py tests/unit/test_processador_cadastro_web.py tests/unit/test_repositorio_solicitacao_web.py -q -p no:cacheprovider --basetemp .pytest-task014-coverage-tests-b-20261018 --tb=short
.venv-ml\Scripts\python.exe -m pytest tests/unit --cov=src --cov=scripts.metricas --cov=scripts.divisao_por_identidade --cov=scripts.evaluate_model --cov=scripts.calibrar_limiar --cov-report=term-missing --cov-fail-under=80 -p no:cacheprovider --basetemp .pytest-task014-unit-second-20261018 --tb=short
.venv-ml\Scripts\python.exe -m mypy src scripts
.venv-ml\Scripts\python.exe -m ruff check src tests
.venv-ml\Scripts\python.exe -m pip check
git diff --check
```

`ruff format --check` também foi executado sobre os 25 arquivos Python alterados
ou adicionados nesta tarefa; todos estavam formatados. A verificação global
`ruff format --check src tests` identifica oito arquivos preexistentes fora do
escopo desta tarefa. O teste PostgreSQL `tests/integration/test_cadastro_web_api.py`
foi executado por wrapper local com autorização explícita e URL apontada ao
banco descartável descrito abaixo; a URL e credenciais não foram registradas.

O banco usado foi `task014_cadastro_api_test_20261018`, identificado pelo
comentário `projeto_reconhecimento_facial: task 014 disposable registration database`.
Na execução original da task014, `escola` não recebeu a migration 0009. Em
19/10/2026, `0009` foi aplicada a `escola` como parte da cadeia `0006–0011` da
tarefa 016. A validação PostgreSQL desta task cobriu migration e revogação
transacional, não carga ou concorrência de produção.

## Ativação e reversão

Para ativar em um ambiente configurado, aplique a migration 0009 depois de
backup/revisão do schema, configure `WEB_CAPTURE_TEMP_DIR`,
`WEB_REFERENCE_STORAGE_DIR`, `WEB_MEDIAPIPE_MODEL_PATH` e
`WEB_MEDIAPIPE_PYTHON_EXECUTABLE` no worker, e inicie separadamente a API ASGI e
`python -m src.face_worker_main`. O ambiente Python do MediaPipe permanece
isolado; o modelo deve existir localmente e não é baixado durante a execução.
O runtime web/produção e os caminhos privados ainda exigem validação própria.

Para reverter código, pare API e worker e reverta os commits da tarefa após
revisar dependências. Mantenha a migration enquanto existirem links,
credenciais ou solicitações/jobs/desafios associados. O downgrade 0009 só é
permitido quando esses registros foram eliminados segundo uma política
autorizada; o downgrade testado em fixture foi feito no banco descartável vazio.

## Limitações restantes

- Nenhum teste visual, webcam, modelo real ou pessoa foi usado nesta tarefa;
  a eficácia de pose/anti-spoofing e a latência continuam sem avaliação real.
- Não foram validados tmpfs compartilhado Linux, permissões/ACL de produção,
  proxy, deployment, capacidade da VPS ou carga concorrente.
- Rate limiting contra abuso das rotas públicas ainda precisa ser tratado na
  validação operacional/backend posterior.
- Rotas de sessão e presença pertencem à tarefa 015; não há interface nesta
  entrega.

## Publicação

Alterações organizadas em commits PT-BR e enviadas por push normal para
`origin/main`, usando a identidade Git já configurada do solicitante. Nenhuma
alteração alheia foi incluída; não houve force push ou deploy.
