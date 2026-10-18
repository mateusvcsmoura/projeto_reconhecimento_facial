# Resultado — tarefa 009: fundação web e compatibilidade Linux

**Estado: concluída no escopo da tarefa.** A API, sua configuração isolada e a
stack ML instalada/importada passaram em Ubuntu 24.04 x86_64 com Python 3.12.3.
Inferência com pesos, desempenho, banco real, implantação e validação biométrica
continuam pendentes dos gates posteriores.

## Diagnóstico e decisão

O trabalho começou na branch `main`, HEAD
`97909962938bccf5022adacb9cb7dd9bfdec8e77`. Os diretórios temporários
`.pytest-stage4-tmp-20261010` e sufixos `-b`, `-c`, `-d` já estavam sem
versionamento e foram preservados. Nenhuma migration, dado, ambiente de
aplicação ou modelo local foi alterado.

No `.venv-app` existente: Windows AMD64, Python `3.12.0rc2`, pip `26.2.1`,
`deepface==0.0.92`, `retina-face==0.0.18`, `opencv-python==4.13.0.92`,
`tensorflow==2.21.0`, `torch==2.14.0` e `numpy==2.5.3`. `pip check` passou.
Esse ambiente já tinha somente `opencv-python`; nenhum interpretador foi
substituído. Como `3.12.0rc2` é pré-release, a prova Linux desta tarefa usou
Python estável `3.12.3` em Ubuntu 24.04.

O `.venv-ml` atual é Python `3.14.3`/pip `25.3`; sincronizei somente esse
ambiente de desenvolvimento com `requirements-dev.txt` para rodar os testes e
mypy que agora incluem a fundação web. `.venv-app` e `.venv-landmarks` não foram
instalados nem alterados durante essa sincronização.

A resolução Linux sem restrição adicional mostrou que DeepFace aceita
`retina-face>=0.0.1` e escolhia `retina-face==0.0.19`, que adicionava
`opencv-contrib-python-headless` ao `opencv-python` já fixado. São dois pacotes
que instalam o mesmo namespace `cv2`, condição que a documentação oficial do
OpenCV orienta evitar. A versão oficial `retina-face==0.0.18` é aceita pelo
DeepFace e seus metadados declaram o mesmo `opencv-python` usado pela aplicação.

A solução mínima foi fixar `retina-face==0.0.18` em `requirements.txt` e
declarar o índice CPU oficial do PyTorch nesse arquivo. Assim, uma instalação
normal de `requirements.txt` escolhe `torch==2.14.0+cpu` em Linux. A resolução
real no container confirmou uma única distribuição OpenCV. Não foram usados
`--no-deps`, metadata alterada ou fornecedores simultâneos de `cv2`.

## Implementação entregue

- `src/config/web_settings.py` fornece configurações `WEB_*` obrigatórias,
  segredos mascarados, ambientes `development/test/production` e guardas para
  banco descartável. Não lê `.env` nem importa defaults da CLI.
- `src/presentation/web/` implementa a fábrica FastAPI, contratos de saúde,
  erros sanitizados com request ID e `/api/v1/openapi.json`. `/docs` e `/redoc`
  ficam desativados.
- `src/web_main.py` compõe o runtime sem carregar DeepFace, TensorFlow, Torch,
  OpenCV ou MediaPipe. O probe de prontidão usa apenas `SELECT 1`; a engine é
  liberada no shutdown.
- `requirements-web.txt` separa o runtime HTTP da pilha biométrica;
  `requirements-dev.txt` inclui as dependências web e ferramentas de teste.
- `requirements.txt` explicita o pin compatível de RetinaFace e o índice oficial
  CPU do PyTorch.
- Testes novos cobrem fábrica sem imports de ML, configuração, payloads HTTP,
  readiness e ciclo de vida com serviços/engine fakes.

## Arquivos alterados

- Implementação: `src/config/web_settings.py`, `src/presentation/web/`,
  `src/web_main.py`.
- Dependências: `requirements.txt`, `requirements-web.txt` e
  `requirements-dev.txt`.
- Testes: `tests/unit/test_web_fundacao.py` e
  `tests/integration/test_web_runtime.py`.
- Documentação: `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`,
  `docs/FACEDIFF-WEB-ROADMAP.md`, `docs/FACEDIFF-WEB-RUNTIME.md`,
  `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`, `tasks/README.md`,
  `tasks/WEB-CONTRATO-EXECUCAO.md` e os `DESENHO.md`/`PLANO.md` desta task.

## Validação executada

| Verificação | Resultado |
|---|---|
| Testes focados (`test_web_fundacao.py` + `test_web_runtime.py`) | 16 passaram |
| Suíte unitária (`tests/unit`) em `.venv-ml` | 970 passaram em 11,41 s |
| Ruff check nos 7 arquivos Python alterados | Passou |
| Ruff format check nos 7 arquivos Python alterados | 7 já formatados |
| Mypy `src scripts` em `.venv-ml` sincronizado com `requirements-dev.txt` | Nenhum problema em 86 arquivos |
| `pip check` em `.venv-app` Windows | `No broken requirements found` |
| `pip check` em `.venv-ml` | `No broken requirements found` |
| Instalação de `requirements.txt` e `pip check` em Ubuntu 24.04/Python 3.12.3 | Passaram; `No broken requirements found` |
| Imports Linux de OpenCV, NumPy, Torch, TensorFlow, DeepFace e RetinaFace | Passaram; Torch CPU, `torch.version.cuda is None`; apenas `opencv-python==4.13.0.92` fornece `cv2` |
| `git diff --check` | Exit code 0; somente avisos do Git sobre conversão LF/CRLF no checkout Windows |

O smoke de runtime executou Uvicorn em loopback no container web e consultou
`GET /health/live`: HTTP 200, corpo `{"status":"live"}` e header
`X-Request-ID`. Não foi chamada a rota `/health/ready`, então nenhum PostgreSQL
foi acessado.

O primeiro import de OpenCV no Ubuntu mínimo falhou por ausência de
`libxcb.so.1`. Repetimos a instalação num container descartável após instalar
`libgl1`, `libglib2.0-0`, `libxcb1`, `libxkbcommon0`, `libxkbcommon-x11-0`,
`libxcb-cursor0` e `libxcb-xinerama0`; `cv2` e os outros módulos então
importaram. O runtime HTTP usa `requirements-web.txt`, não instala OpenCV e não
precisa dessas bibliotecas.

Comandos de validação do repositório:

```powershell
.\.venv-ml\Scripts\python.exe -m pytest tests/unit/test_web_fundacao.py tests/integration/test_web_runtime.py -p no:cacheprovider --basetemp "$env:TEMP\pytest-task009-focused-20261018"
.\.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider --basetemp "$env:TEMP\pytest-task009-final-20261018"
.\.venv-ml\Scripts\python.exe -m ruff check src/config/web_settings.py src/presentation/web/__init__.py src/presentation/web/app.py src/presentation/web/schemas.py src/web_main.py tests/unit/test_web_fundacao.py tests/integration/test_web_runtime.py
.\.venv-ml\Scripts\python.exe -m ruff format --check src/config/web_settings.py src/presentation/web/__init__.py src/presentation/web/app.py src/presentation/web/schemas.py src/web_main.py tests/unit/test_web_fundacao.py tests/integration/test_web_runtime.py
.\.venv-ml\Scripts\python.exe -m mypy src scripts
.\.venv-ml\Scripts\python.exe -m pip check
git diff --check
```

A validação full-stack Linux instalou `requirements.txt` em um venv dentro de
`ubuntu:24.04` amd64/Python 3.12.3, após instalar os pacotes de sistema listados
acima; então executou `python -m pip check` e importou os seis módulos. O
container foi removido ao fim. O smoke não abriu câmera, consultou banco,
construiu modelos ou baixou pesos.

Comandos dentro do container full-stack (a etapa de import usou um script
temporário montado no workspace, removido depois da execução):

```sh
apt-get update -qq
apt-get install -y python3.12 python3.12-venv ca-certificates libgl1 libglib2.0-0 libxcb1 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-xinerama0
python3.12 -m venv /tmp/facediff
/tmp/facediff/bin/python -m pip install --upgrade pip
/tmp/facediff/bin/python -m pip install -r requirements.txt
/tmp/facediff/bin/python -m pip check
/tmp/facediff/bin/python /workspace/.task009-linux-smoke.py
```

## Limitações, rollback e estado Git

Importar os pacotes confirma instalação/carregamento nativo, mas não comprova
inferência com FaceNet512, MiniFASNet, Face Landmarker, desempenho nem qualidade
biométrica. Nenhum peso foi baixado. Não houve teste visual com pessoa, webcam,
PostgreSQL real, migration, proxy ou deploy; estas etapas continuam sujeitas aos
respectivos gates e autorizações.

Para desativar o runtime, basta não iniciar
`uvicorn src.web_main:create_web_app --factory`; a CLI permanece independente
em `python -m src.main`. Não existe alteração de schema ou dados para reverter.
Se for necessário reverter o código, revisar os arquivos da tarefa 009 no diff
e remover apenas suas alterações; preservar ambientes e arquivos locais alheios.

Arquivos de implementação e documentação foram deixados no workspace para
revisão. Não houve commit nem push. O estado desta task é **concluído**; o gate
de integração/inferência da task019 permanece pendente.
