# Runtime web e compatibilidade Linux

Atualizado em 19/10/2026 pelas tarefas
[009 — fundação web](../tasks/009-web-fundacao-linux/RESULTADO.md),
[010 — autenticação](../tasks/010-web-autenticacao-autorizacao/RESULTADO.md) e
[012 — worker/fila](../tasks/012-web-worker-fila/RESULTADO.md) e
[013 — desafio e verificação 1:1](../tasks/013-web-desafio-verificacao-1a1/RESULTADO.md) e
[014 — API de cadastro e aprovação](../tasks/014-web-api-cadastro-aprovacao/RESULTADO.md) e
[015 — sessões e presença por API](../tasks/015-web-api-sessoes-presencas/RESULTADO.md).
O fechamento 019A adicionou rate limits às rotas públicas de cadastro e
atualizou a matriz de validação; veja
[`019A — resultado parcial`](../tasks/019a-fechamento-backend/RESULTADO.md).
Este documento descreve o runtime HTTP e a validação local; não declara deploy
nem validação biométrica real. A migration `0005` foi aplicada ao banco local
`escola`; `0007`–`0010` foram validadas em bancos descartáveis, não em `escola`.

## Isolamento e dependências

O novo serviço ASGI usa `src.web_main:create_web_app` e a fábrica
`src.presentation.web.app:create_app`. A API não importa `src.main`, OpenCV,
DeepFace, TensorFlow, PyTorch ou MediaPipe; o processo de CLI permanece
separado. `requirements-web.txt` instala FastAPI/Uvicorn, Pydantic Settings,
SQLAlchemy/psycopg e Argon2. O ambiente web não tem fornecedor de `cv2`.
`requirements.txt` mantém a CLI/stack facial e fixa o `retina-face` compatível,
além de incluir o índice CPU oficial do PyTorch.

Os pins do serviço web são FastAPI 0.144.0, Uvicorn 0.54.0, SQLAlchemy 2.0.52,
psycopg 3.3.5, Pydantic Settings 2.15.0, `argon2-cffi==25.1.0` e
`argon2-cffi-bindings==26.1.0`. A suíte usa HTTPX2 2.13.1 através de
`requirements-dev.txt`; não é requisito de runtime.

### Matriz de evidências

| Stack | Evidências disponíveis | Limite |
|---|---|---|
| API base (009) | `requirements-dev.txt`, `pip check`, 970 testes unitários e smoke Uvicorn em Ubuntu 24.04 amd64 / Python 3.12.3 | Não inclui PostgreSQL real, proxy nem implantação |
| Autenticação task010 | Testes HTTP/unitários em SQLite; 3 testes PostgreSQL em banco descartável; `0005` aplicada a `escola`; `alembic check` limpo | Sem deploy, proxy real ou teste de carga concorrente |
| Stack ML do app | `requirements.txt` instalado em Ubuntu 24.04/Python 3.12.3; `pip check` e imports nativos passaram | Sem pesos, inferência facial ou teste de desempenho |
| TensorFlow / tf-keras | 2.21.0 / 2.21.0 importados | CPU; sem modelo carregado |
| PyTorch CPU / NumPy | 2.14.0+cpu (`torch.version.cuda is None`) / 2.5.3 importados | Sem MiniFASNet ou inferência |
| OpenCV | 4.13.0.92 importado; único fornecedor de `cv2` é `opencv-python` | Exigiu `libgl1`, `libglib2.0-0`, `libxcb1`, `libxkbcommon0`, `libxkbcommon-x11-0`, `libxcb-cursor0`, `libxcb-xinerama0`; sem câmera/display |
| DeepFace / RetinaFace | 0.0.92 / 0.0.18 importados | Sem construção de modelo ou download de pesos |
| MediaPipe 0.10.35 | Ambiente filho Linux isolado; `pip check` limpo; modelo local iniciou e inferiu em entrada sintética | Python 3.14.4/WSL; `libGLESv2.so.2` foi disponibilizada em diretório temporário; sem validação de pose com pessoa |
| Worker e presença task012–015 | Migration 0010, escritor CLI legado, concorrência de tentativas, limite de três emissões e revogação durante o processamento em PostgreSQL descartável; contratos HTTP e suíte unitária | Sem tmpfs de produção, validação visual/biométrica com pessoa ou medição na VPS |

O primeiro smoke em Ubuntu mínimo falhou ao carregar `cv2` porque faltava
`libxcb.so.1`; com as bibliotecas de runtime listadas acima, a stack importou.
Isso prova compatibilidade das dependências e dos binários nesse container, não
funcionamento biométrico. O smoke com pesos da task012 foi sintético e executado
no Windows. A task013 também carregou o modelo real do Face Landmarker no Linux
e recebeu uma imagem sintética; isso não comprova pose nem comportamento com uma
pessoa. O pipeline HTTP ponta a ponta, worker em host de produção, recursos do
host e validação integrada permanecem para tasks futuras.

`retina-face==0.0.18` foi fixado porque DeepFace 0.0.92 aceita
`retina-face>=0.0.1` e os metadados oficiais da versão 0.0.18 declaram
`opencv-python`. A resolução sem esse pin escolheu 0.0.19 e adicionou
`opencv-contrib-python-headless`, que também instala o namespace `cv2`. O
projeto OpenCV orienta instalar somente uma de suas distribuições por ambiente.
O pin passou no `pip check` e no smoke; reavaliar ao atualizar DeepFace ou
RetinaFace. Referências: [metadata retina-face 0.0.18](https://pypi.org/pypi/retina-face/0.0.18/json),
[retina-face 0.0.19](https://pypi.org/project/retina-face/0.0.19/) e
[regra de instalação OpenCV](https://pypi.org/project/opencv-python/).

As referências oficiais das wheels são [TensorFlow 2.21.0](https://pypi.org/project/tensorflow/2.21.0/),
[tf-keras 2.21.0](https://pypi.org/project/tf-keras/2.21.0/),
[PyTorch CPU](https://download.pytorch.org/whl/cpu/torch/),
[NumPy 2.5.3](https://pypi.org/project/numpy/2.5.3/) e
[OpenCV 4.13.0.92](https://pypi.org/project/opencv-python/4.13.0.92/).

## Configuração web

`WebSettings` lê somente variáveis `WEB_*`; não abre `.env` e não reutiliza os
defaults da CLI. `WEB_ENVIRONMENT`, `WEB_DATABASE_URL`, `WEB_SECRET_KEY` e
`WEB_RETENTION_DAYS` são obrigatórias. A URL deve usar o driver
`postgresql+psycopg` e é marcada como segredo. A chave exige no mínimo 32 caracteres e erros de configuração
ocultam valores de entrada.

`WEB_DATABASE_DISPOSABLE` assume `false`. Em ambiente `test`, deve ser `true` e
o nome do banco deve conter `test`, `tests`, `testing`, `disposable` ou
`descartavel`. Hosts locais só são aceitos quando marcados explicitamente como
descartáveis. Em `production`, hosts de loopback e bancos descartáveis são
recusados. O código não consulta comentário/identidade do PostgreSQL e não
executa DDL; um teste que venha a aplicar migrations ainda precisa seguir o
opt-in, a identificação e a autorização exigidos pelo contrato de migrations.

`WEB_PUBLIC_ORIGIN` é obrigatória em produção e deve usar HTTPS; sem origem
configurada, a API recusa mutações de autenticação. `WEB_TRUSTED_PROXY_CIDRS`
deve listar somente redes controladas pelo serviço; sem isso, cabeçalhos
`X-Forwarded-For` não são confiáveis.

Exemplo para iniciar o serviço atrás de um proxy local. O endereço e as
credenciais abaixo são marcadores; substitua-os por valores fornecidos por um
gestor de segredos e banco de produção configurado. Não grave segredos no Git.

```sh
python3.12 -m venv .venv-web
.venv-web/bin/python -m pip install -r requirements-web.txt
export WEB_ENVIRONMENT=production
export WEB_DATABASE_URL='postgresql+psycopg://usuario:senha@postgres:5432/facediff'
export WEB_SECRET_KEY="$(.venv-web/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export WEB_RETENTION_DAYS=10
export WEB_DATABASE_DISPOSABLE=false
export WEB_PUBLIC_ORIGIN='https://presenca.example.edu'
# Configure WEB_TRUSTED_PROXY_CIDRS somente com o CIDR exato do proxy controlado.
.venv-web/bin/uvicorn src.web_main:create_web_app --factory --host 127.0.0.1 --port 8000
```

As rotas públicas de cadastro também usam o repositório persistente de rate
limit. Os defaults iniciais são 10 operações por minuto por origem/contexto,
60 consultas por minuto por credencial e teto agregado de 600 por minuto por
origem; configure-os com `WEB_PUBLIC_REGISTRATION_CONTEXT_LIMIT_PER_MINUTE`,
`WEB_PUBLIC_REGISTRATION_QUERY_LIMIT_PER_MINUTE` e
`WEB_PUBLIC_REGISTRATION_ORIGIN_LIMIT_PER_MINUTE`. Os valores são guardas
iniciais, ainda sem calibração operacional. O `X-Forwarded-For` só informa a
origem quando a conexão vem de uma rede em `WEB_TRUSTED_PROXY_CIDRS`. Sem
limitador/segredo em produção, a API falha fechada com 503.

O comando configura e cria uma engine SQLAlchemy sem abrir conexão. A conexão
ocorre somente em `/health/ready`. O exemplo não provisiona PostgreSQL nem
constitui instrução de deploy; o proxy e a infraestrutura ainda pertencem à
task018.

O worker roda em processo separado, sem porta HTTP e com as dependências faciais
de `requirements.txt`; a API permanece no ambiente leve `requirements-web.txt`.
Crie `.venv-worker` e instale `requirements.txt` antes de iniciá-lo. Para a pose,
crie também um ambiente filho Linux e instale `requirements-landmarks-linux.txt`;
configure `WEB_MEDIAPIPE_MODEL_PATH` e `WEB_MEDIAPIPE_PYTHON_EXECUTABLE` para o
modelo local e o interpretador filho. O processo principal usa `opencv-python`;
o filho usa `opencv-contrib-python`, sem instalar ambos no mesmo ambiente. Em
Ubuntu mínimo o runtime filho precisa de `libgles2` (`libGLESv2.so.2`). Em Linux,
API e worker precisam compartilhar a mesma montagem tmpfs privada. Configure
`WEB_CAPTURE_TEMP_DIR` para essa raiz; os limites iniciais são
`WEB_CAPTURE_MAX_BYTES_PER_CAPTURE=8388608`, `WEB_CAPTURE_MAX_FRAMES=3`,
`WEB_CAPTURE_STORAGE_QUOTA_BYTES=314572800`, `WEB_JOB_RESERVATION_SECONDS=300`,
`WEB_JOB_DEADLINE_SECONDS=900` e `WEB_JOB_LEASE_SECONDS=120`. São parâmetros de
laboratório, não capacidade aprovada para produção. Com as mesmas variáveis
`WEB_*` do serviço, inicie o processo separado por
`.venv-worker/bin/python -m src.face_worker_main`. Em produção, o startup exige
tmpfs e pesos locais, sem download automático. A task014 conecta cadastro por
link ao worker e reutiliza a análise de pose MediaPipe isolada da task013. Para
processar cadastro e presença, configure `WEB_REFERENCE_STORAGE_DIR`,
`WEB_MEDIAPIPE_MODEL_PATH` e `WEB_MEDIAPIPE_PYTHON_EXECUTABLE` no processo worker,
além do diretório temporário. A task015 conecta as rotas de presença à mesma fila
e ao desafio 1:1, mantendo a persistência sob transação PostgreSQL.
Se uma inferência nativa ficar bloqueada indefinidamente, esta implementação
não encerra o processo por watchdog: mantém o slot ocupado até o executor
retornar ou um reinício controlado invalidar o job. A supervisão automática
precisa ser definida/validada antes da operação na task019/018.

## Contratos expostos

| Rota | Resultado |
|---|---|
| `GET /health/live` | HTTP 200 `{"status":"live"}`; não consulta dependências |
| `GET /health/ready` | HTTP 200 com status `ready` ou HTTP 503 com `not_ready`; retorna nomes de componentes e estados, sem exceções |
| `GET /api/v1/openapi.json` | Contrato OpenAPI JSON |
| `POST /api/v1/auth/login`, `/logout`, `/trocar-senha` | Login, logout e troca de senha com Origin/CSRF |
| `GET /api/v1/auth/csrf`, `/api/v1/me` | Token CSRF recuperável e estado mínimo da conta |
| `/api/v1/admin/contas` e operações de redefinição/desativação | Gestão auditada; credencial temporária entregue uma vez |
| `GET /api/v1/turmas/{id}`, `POST /api/v1/admin/turmas/{id}/responsavel` | Ownership por professor e transferência administrativa auditada |
| `GET /api/v1/operacoes/{id}` | Status autenticado por `Authorization: Bearer <credencial>`; credencial incorreta recebe 404 genérico |
| `POST /api/v1/turmas/{id}/links-cadastro`, `POST /api/v1/links/{id}/revogar` | Professor responsável emite link de cadastro de 7 dias e pode revogá-lo |
| `POST /api/v1/acessos-link` | Troca token do link por credencial curta; resposta inclui finalidade e prazo |
| `GET /api/v1/avisos/biometria`, `POST /api/v1/cadastros` | Aviso versionado, nome/matrícula e consentimento antes da captura |
| `POST /api/v1/cadastros/{id}/capturas`, `GET /api/v1/cadastros/{id}` | Três frames com nonce e sequência frente/virada/retorno; status exige credencial da solicitação |
| `GET /api/v1/turmas/{id}/cadastros`, `POST /api/v1/cadastros/{id}/aprovar`, `/rejeitar` | Revisão e aprovação/rejeição por professor autorizado, sem serializar artefatos biométricos |
| `POST /api/v1/solicitacoes-biometria`, `POST /api/v1/cadastros/{id}/consentimento`, `POST /api/v1/admin/solicitacoes-biometria/{id}/aprovar` | Solicitação de atualização, consentimento do aluno e aprovação administrativa |
| `POST /api/v1/turmas/{id}/sessoes`, `POST /api/v1/sessoes/{id}/links`, `/revogar` | Professor cria e revoga sessões; link compartilhado fica limitado à turma e à sessão |
| `POST /api/v1/sessoes/{id}/tentativas`, `POST /api/v1/tentativas/{id}/capturas`, `GET /api/v1/tentativas/{id}` | Início idempotente, até três tentativas, envio das etapas no prazo do servidor e consulta autenticada por credencial de captura |
| `/docs`, `/redoc` | Desabilitadas; nenhuma interface web foi criada |

A task014 integra cadastro ao worker e a task015 integra presença por sessão.
O rate limit das rotas de presença usa somente hash HMAC de link/ação/IP e não
armazena o IP; limites gerais para todas as rotas públicas seguem como gate
operacional. Jobs sem handler habilitado são recusados com segurança. A consulta
de status usa `Cache-Control: no-store`.

Os erros têm `{codigo, mensagem, request_id}` e o mesmo identificador no header
`X-Request-ID`. Erros HTTP, validação e falhas internas não retornam detalhes
brutos ou tracebacks. A fábrica recebe settings e serviços por injeção; o
relógio exige `datetime` com UTC explícito. O probe de banco executa apenas
`SELECT 1`.

O admin inicial exige `python -m scripts.criar_admin_web`, com senha em prompt
oculto e sem argumentos de credencial. A revisão `0005` está aplicada ao banco
local; veja [FACEDIFF-WEB-AUTH.md](FACEDIFF-WEB-AUTH.md) e o resultado da tarefa.

## Validação e reversão

A validação Linux usa containers descartáveis Ubuntu 24.04 amd64/Python 3.12.3:
um para `requirements-dev.txt`, testes sintéticos e smoke HTTP; outro para
`requirements.txt`, `pip check` e imports da stack ML com bibliotecas de sistema.
Os comandos e números exatos da validação Linux da tarefa 009 estão em
[RESULTADO.md da tarefa009](../tasks/009-web-fundacao-linux/RESULTADO.md); aquela
validação não acessou banco, webcam, imagem ou peso de modelo. A task010 usou
somente o banco local de desenvolvimento e um PostgreSQL descartável, conforme
o [resultado 010](../tasks/010-web-autenticacao-autorizacao/RESULTADO.md).

Para parar o runtime, encerre Uvicorn e o worker; deixe de iniciar
`src.web_main:create_web_app` e `src.face_worker_main`. A CLI continua iniciada
por `python -m src.main` com `requirements.txt`. Para reverter a fundação/runtime
web ou a task012, reverta os commits correspondentes após revisar dependências e
parar ambos os processos. A migration `0007` precisa ser revertida separadamente
e somente quando não houver jobs a preservar; consulte o resultado da task012.
Preserve os diretórios temporários preexistentes e outros trabalhos locais. Não
remova `.venv-app`, `.venv-landmarks` nem modelos locais.

## Benchmark sintético da task019

Execute `python -m scripts.benchmark_web` para exportar JSON agregado de
admissão e processamento nas cargas 1/2/5/10/excesso. A ferramenta usa a fila
em memória e um processador fake com bytes sintéticos; não abre webcam, não lê
fotos, não executa inferência facial e não estima capacidade de produção. Pode
simular inicialização fria, tempo quente, taxa de chegada e falhas com
`--atraso-frio-ms`, `--atraso-quente-ms`, `--chegada-por-segundo` e
`--falha-falsa-a-cada`. CPU, RAM e RSS são coletados onde o sistema fornece os
contadores; PSS depende de `/proc` e será `null` fora do Linux. O relatório da
execução sintética Windows está em
[`benchmark-fake-20261019.json`](../tasks/019-web-validacao-backend/evidencias/benchmark-fake-20261019.json).
