# Runtime web e compatibilidade Linux

Atualizado em 19/10/2026 pelas tarefas
009 — fundação web,
010 — autenticação e
012 — worker/fila e
013 — desafio e verificação 1:1 e
014 — API de cadastro e aprovação e
015 — sessões e presença por API.
O fechamento 019A adicionou rate limits às rotas públicas de cadastro, corrigiu
falhas do runtime Compose e aprovou o gate do backend com restore local cifrado;
veja `019A — resultado`.
Este documento descreve o runtime HTTP e a validação local; não declara deploy
nem validação biométrica real. A migration `0005` foi aplicada ao banco local
`escola`; `0007`–`0010` foram validadas em bancos descartáveis, não em `escola`.

## Isolamento e dependências

O novo serviço ASGI usa `src.web_main:create_web_app` e a fábrica
`src.presentation.web.app:create_app`. A API não importa `src.main`, OpenCV,
DeepFace, TensorFlow, PyTorch ou MediaPipe; o processo de CLI permanece
separado. `requirements-web.txt` instala FastAPI/Uvicorn, NumPy, Pydantic
Settings, SQLAlchemy/psycopg e Argon2. O ambiente web não tem fornecedor de `cv2`.
`requirements.txt` mantém a CLI/stack facial e fixa o `retina-face` compatível,
além de incluir o índice CPU oficial do PyTorch.

Os pins do serviço web são FastAPI 0.144.0, Uvicorn 0.54.0, SQLAlchemy 2.0.52,
NumPy 2.5.3, psycopg 3.3.5, Pydantic Settings 2.15.0, `argon2-cffi==25.1.0` e
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
| Compose Linux task019A | Targets app/worker/migrate/backup/PostgreSQL/Caddy construídos; migrations 0011, healthchecks, UID/rootfs, Caddy local e persistência após recriação aprovados | Projeto local descartável; sem deploy, firewall, KVM2 ou certificado público |

O primeiro smoke em Ubuntu mínimo falhou ao carregar `cv2` porque faltava
`libxcb.so.1`; com as bibliotecas de runtime listadas acima, a stack importou.
Isso prova compatibilidade das dependências e dos binários nesse container, não
funcionamento biométrico. O smoke com pesos da task012 foi sintético e executado
no Windows. A task013 também carregou o modelo real do Face Landmarker no Linux
e recebeu uma imagem sintética; isso não comprova pose nem comportamento com uma
pessoa. O pipeline HTTP ponta a ponta sintético e o worker no Compose Linux
foram validados na task019A. Recursos de produção, host/VPS, dados legítimos e
validação biométrica com pessoas permanecem para ensaios autorizados futuros.

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

`WEB_PURPOSE_END_AT` define até quando a finalidade de cadastro pode ser usada.
O Compose local fornece `2027-12-31T23:59:59-03:00` como prazo demonstrativo
de desenvolvimento, sobrescrevível pelo `.env`; o Compose de deploy exige um
valor explícito. Sem esse prazo, a emissão de links de cadastro falha fechada
com HTTP 503.

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
limit. Os defaults iniciais são 40 operações por minuto por origem/contexto
(uma turma de 20 se cadastrando pelo mesmo IP),
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
`WEB_CAPTURE_MAX_BYTES_PER_CAPTURE=2097152`, `WEB_CAPTURE_MAX_FRAMES=3`,
`WEB_CAPTURE_STORAGE_QUOTA_BYTES=314572800`, `WEB_JOB_RESERVATION_SECONDS=300`,
`WEB_JOB_DEADLINE_SECONDS=900` e `WEB_JOB_LEASE_SECONDS=120`. São parâmetros de
laboratório, não capacidade aprovada para produção.

Qualidade da captura no worker (padrões entre parênteses, heurísticas sem
calibração com rostos): `WEB_FACE_QUALITY_MIN_FACE_PX` (80),
`WEB_FACE_QUALITY_MIN_BRIGHTNESS` (40) e `WEB_FACE_QUALITY_MAX_BRIGHTNESS` (215),
brilho médio do recorte em 0–255, e `WEB_FACE_QUALITY_MIN_SHARPNESS` (100),
variância do Laplaciano. `WEB_FACE_QUALITY_DIM_BRIGHTNESS` (80) separa o escuro
do borrado: recorte sem nitidez com brilho abaixo dele é recusado como
`IluminacaoInsuficiente` (motivo `iluminacao_insuficiente`), e o navegador usa o
flash frontal (tela branca por cerca de 1 s) nas capturas seguintes daquela
coleta ou tentativa. O guia do navegador mede o rosto com o mesmo limite
(`LUMINOSIDADE_ESCURA` em `camera.mjs`, fixo em 80) e, abaixo dele por cerca de
1 s, mostra a dica de brilho e liga o flash já na primeira captura; ao mudar o
env, ajuste também essa constante. Cada recusa grava no log do worker o tipo e os valores
medidos (`Captura recusada pela qualidade: RostoSemNitidez (nitidez=…
luminosidade=…)`); calibre por esses valores. Em INFO, o worker também registra
as medidas de cada captura aceita, uma linha por etapa de presença (ids internos
de job e aluno, resultado, motivo, orientação e distância mediana) e por
cadastro, e o brilho do quadro inteiro quando nenhum rosto é detectado. A API
registra, com o mesmo id de job, o `diagnostico` que o navegador envia em cada
captura (flash usado e brilho do rosto medido pelo guia antes do flash; "sem
medida" quando o guia não rodou); o campo não entra em nenhuma decisão. Nunca
registra imagem, embedding, nome ou matrícula. No compose de `deploy/web`, defina-as no env do host e recrie
só o `face-worker`.

Limites pensados para uma turma no mesmo Wi-Fi, onde todos saem pelo mesmo IP
público (padrões entre parênteses):

- `WEB_JOB_QUEUE_WAITING_LIMIT` (30): trabalhos aguardando na fila facial. Uma
  tentativa de presença ocupa vaga durante todo o desafio; acima do limite a
  API responde 503 com `Retry-After`.
- `WEB_PRESENCE_START_LIMIT_PER_WINDOW` (60) e
  `WEB_PRESENCE_CAPTURE_LIMIT_PER_WINDOW` (300): inícios de tentativa e envios
  de captura por link e IP a cada 15 minutos (20 alunos x 3 tentativas x 3
  etapas = 180 capturas).

Cada trabalho reserva três capturas na cota temporária. A API recusa iniciar
se `WEB_CAPTURE_STORAGE_QUOTA_BYTES` não comportar `3 x
WEB_CAPTURE_MAX_BYTES_PER_CAPTURE x (WEB_JOB_QUEUE_WAITING_LIMIT + 1)`; com os
padrões, 6 MiB x 31 = 186 MiB, dentro dos 300 MiB. Para turmas maiores, aumente
a fila, os limites por janela e, se preciso, a cota e o tmpfs de capturas. Com as mesmas variáveis
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
| `GET /api/v1/auth/csrf`, `/api/v1/me` | Token CSRF recuperável e estado mínimo da conta autenticada, incluindo seu usuário |
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

O tratamento HTTP atribui códigos estáveis por status e mantém mensagens
seguras em português. Login inválido retorna `credenciais_invalidas`; sessão
ausente retorna `autenticacao_necessaria`; falhas de CSRF e origem têm códigos
próprios. Detalhes de erros 4xx só são encaminhados quando curtos e imprimíveis;
falhas 5xx nunca encaminham detalhes internos, embora handlers específicos
possam retornar mensagens públicas próprias. O cliente web usa mensagens de
contingência correspondentes quando uma resposta não contém o envelope esperado.

O admin inicial exige `python -m scripts.criar_admin_web`, com senha em prompt
oculto e sem argumentos de credencial. A revisão `0005` está aplicada ao banco
local; veja [FACEDIFF-WEB-AUTH.md](FACEDIFF-WEB-AUTH.md) e o resultado da tarefa.

## Validação e reversão

### Runtime local pelo Docker Compose

O Compose raiz mantém o PostgreSQL existente e oferece o perfil `web`, que
inicia a API e o `face-worker` juntos. A API precisa de `WEB_CAPTURE_TEMP_DIR`
para aceitar capturas; o worker consome a mesma fila e monta exatamente o mesmo
volume temporário. Esse volume é um `tmpfs` limitado a 300 MiB, sem persistência
em disco. Os pesos locais são montados somente para leitura no worker.

Configure no `.env` as variáveis `WEB_DATABASE_URL` (URL acessível de dentro do
container: `db:5432`, o serviço do compose, que funciona no Docker Desktop e
no Docker do Linux, onde `host.docker.internal` não existe), `WEB_SECRET_KEY` e
`WEB_LOCAL_DEEPFACE_WEIGHTS_HOST_DIR`, conforme o `.env.example`. A origem
local padrão é `http://127.0.0.1:8000`; mantenha `WEB_PUBLIC_ORIGIN` igual ao
endereço usado no navegador para que as mutações autenticadas passem pela
validação de origem e CSRF. Depois, na raiz do projeto, use:

```powershell
docker compose --profile web up -d --build
docker compose --profile web ps
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

O primeiro comando também inicia o serviço `db` se ele estiver parado; não
recria o volume PostgreSQL existente. A readiness da API confirma o banco. O
worker leva mais tempo para ficar saudável porque carrega os modelos locais;
acompanhe `docker compose --profile web logs -f face-worker` até o healthcheck
ficar `healthy`. Sem pesos locais válidos, o Compose mostra o worker como
indisponível e o processamento permanece incompleto. A tela de captura não deve
ser usada até API e worker estarem saudáveis.

Para parar somente os serviços web, preserve banco e volumes com
`docker compose --profile web stop web face-worker`. Não use `down -v`.

O `face-worker` local tem teto de memória `WEB_WORKER_MEMORY_LIMIT` (padrão
`3g`, o mesmo valor recomendado no deploy). No Windows com Docker Desktop/WSL2,
limite também a VM em `%USERPROFILE%\.wslconfig`, por exemplo com
`[wsl2] memory=4GB` e `[experimental] autoMemoryReclaim=dropCache`. Sem isso a
VM pode reter até metade da RAM em cache de arquivos, contabilizado pelo Windows
como memória comprometida. Em 22/10/2026, esse cache somado a outros programas
esgotou a memória virtual do host durante builds repetidos da imagem do worker.
O `.wslconfig` vale após `wsl --shutdown` ou reinício.

A validação Linux usa containers descartáveis Ubuntu 24.04 amd64/Python 3.12.3:
um para `requirements-dev.txt`, testes sintéticos e smoke HTTP; outro para
`requirements.txt`, `pip check` e imports da stack ML com bibliotecas de sistema.
Os comandos e números exatos da validação Linux da tarefa 009 estão em
RESULTADO.md da tarefa009; aquela
validação não acessou banco, webcam, imagem ou peso de modelo. A task010 usou
somente o banco local de desenvolvimento e um PostgreSQL descartável, conforme
o resultado 010.

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
`benchmark-fake-20261019.json`.
