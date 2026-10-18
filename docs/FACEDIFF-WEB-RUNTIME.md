# Runtime web e compatibilidade Linux

Atualizado em 18/10/2026 pela tarefa
[009 — fundação web](../tasks/009-web-fundacao-linux/RESULTADO.md). Este
documento descreve o runtime HTTP implementado; não declara deploy, integração
PostgreSQL real nem validação biométrica.

## Isolamento e dependências

O novo serviço ASGI usa `src.web_main:create_web_app` e a fábrica
`src.presentation.web.app:create_app`. A API não importa `src.main`, OpenCV,
DeepFace, TensorFlow, PyTorch ou MediaPipe. O processo de CLI permanece
separado. `requirements-web.txt` instala apenas
FastAPI/Uvicorn, Pydantic Settings e o driver PostgreSQL/SQLAlchemy necessários
à API e ao probe de prontidão. O ambiente web não tem fornecedor de `cv2`.
`requirements.txt` mantém a CLI/stack facial e fixa o `retina-face` compatível,
além de incluir o índice CPU oficial do PyTorch.

Os pins do serviço web são FastAPI 0.144.0, Uvicorn 0.54.0, SQLAlchemy 2.0.52,
psycopg 3.3.5 e Pydantic Settings 2.15.0. A suíte usa HTTPX2 2.13.1 através de
`requirements-dev.txt`; não é requisito de runtime.

### Matriz de evidências

| Stack | Evidência desta tarefa | Limite |
|---|---|---|
| API web | `requirements-dev.txt`, `pip check`, 970 testes unitários e smoke Uvicorn em Ubuntu 24.04 amd64 / Python 3.12.3 | Não inclui PostgreSQL real, proxy nem implantação |
| Stack ML do app | `requirements.txt` instalado em Ubuntu 24.04/Python 3.12.3; `pip check` e imports nativos passaram | Sem pesos, inferência facial ou teste de desempenho |
| TensorFlow / tf-keras | 2.21.0 / 2.21.0 importados | CPU; sem modelo carregado |
| PyTorch CPU / NumPy | 2.14.0+cpu (`torch.version.cuda is None`) / 2.5.3 importados | Sem MiniFASNet ou inferência |
| OpenCV | 4.13.0.92 importado; único fornecedor de `cv2` é `opencv-python` | Exigiu `libgl1`, `libglib2.0-0`, `libxcb1`, `libxkbcommon0`, `libxkbcommon-x11-0`, `libxcb-cursor0`, `libxcb-xinerama0`; sem câmera/display |
| DeepFace / RetinaFace | 0.0.92 / 0.0.18 importados | Sem construção de modelo ou download de pesos |
| MediaPipe 0.10.35 | Mantido no ambiente isolado documentado | Não é dependência do serviço web nem foi importado nesta tarefa |

O primeiro smoke em Ubuntu mínimo falhou ao carregar `cv2` porque faltava
`libxcb.so.1`; com as bibliotecas de runtime listadas acima, a stack importou.
Isso prova compatibilidade das dependências e dos binários nesse container, não
funcionamento biométrico. Inferência com pesos, pipeline/worker, recursos do
host e validação integrada permanecem para a task019.

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
.venv-web/bin/uvicorn src.web_main:create_web_app --factory --host 127.0.0.1 --port 8000
```

O comando configura e cria uma engine SQLAlchemy sem abrir conexão. A conexão
ocorre somente em `/health/ready`. O exemplo não provisiona PostgreSQL nem
constitui instrução de deploy; o proxy e a infraestrutura ainda pertencem à
task018.

## Contratos expostos

| Rota | Resultado |
|---|---|
| `GET /health/live` | HTTP 200 `{"status":"live"}`; não consulta dependências |
| `GET /health/ready` | HTTP 200 com status `ready` ou HTTP 503 com `not_ready`; retorna nomes de componentes e estados, sem exceções |
| `GET /api/v1/openapi.json` | Contrato OpenAPI JSON |
| `/docs`, `/redoc` | Desabilitadas; nenhuma interface web foi criada |

Os erros têm `{codigo, mensagem, request_id}` e o mesmo identificador no header
`X-Request-ID`. Erros HTTP, validação e falhas internas não retornam detalhes
brutos ou tracebacks. A fábrica recebe settings e serviços por injeção; o
relógio exige `datetime` com UTC explícito. O probe de banco executa apenas
`SELECT 1`.

## Validação e reversão

A validação Linux usa containers descartáveis Ubuntu 24.04 amd64/Python 3.12.3:
um para `requirements-dev.txt`, testes sintéticos e smoke HTTP; outro para
`requirements.txt`, `pip check` e imports da stack ML com bibliotecas de sistema.
Os comandos e números exatos estão em
[RESULTADO.md da tarefa009](../tasks/009-web-fundacao-linux/RESULTADO.md). Nenhum
banco real, webcam, imagem ou peso de modelo foi acessado.

Para parar o runtime, encerre o processo Uvicorn e deixe de iniciar
`src.web_main:create_web_app`. A CLI continua iniciada por `python -m src.main`
com `requirements.txt`. Para reverter a implementação, revise e reverta apenas
os arquivos da tarefa009; preserve os diretórios temporários e qualquer outro
trabalho local. Não remova `.venv-app`, `.venv-landmarks` nem modelos locais.
