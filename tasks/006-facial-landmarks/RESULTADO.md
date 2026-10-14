# Resultado — tarefa 006: compatibilidade do MediaPipe no Windows

**Estado: correção técnica concluída.** Os gates de dependências e software passaram nos ambientes atuais. A inspeção visual manual da prévia com uma pessoa permanece pendente. O smoke sintético comprova inicialização, inferência e encerramento, não qualidade visual nem desempenho biométrico.

## Causa-raiz

No início desta correção, `.venv-app` executava CPython `3.12.0rc2` em Windows AMD64, com pip `26.2.1`. As tags suportadas incluíam `cp312-cp312-win_amd64`. A wheel oficial `mediapipe==0.10.31` se chamava externamente `mediapipe-0.10.31-py3-none-win_amd64.whl`, mas o arquivo interno `WHEEL` declarava `cp39-cp39-linux_x86_64`. O `pip check` reproduziu `mediapipe 0.10.31 is not supported on this platform`.

A causa confirmada é a tag interna inconsistente da wheel. Essa tag Linux/CPython 3.9 também não seria aceita em Windows com CPython 3.12 estável. O Python pré-release é uma limitação de reprodutibilidade separada: `py -0p` não listou outro interpretador estável instalado, então não troquei o Python. Um CPython 3.12 estável ainda deve ser usado numa validação futura de instalação limpa.

## Versões avaliadas e decisão

Inspecionei wheels e metadados oficiais, incluindo tags externas e internas, `Requires-Dist` e presença do módulo Face Landmarker Tasks:

| Versão | Evidência no artefato Windows | Avaliação |
|---|---|---|
| 0.10.14 | Wheel `cp312-cp312-win_amd64`, tag interna correta, Tasks API presente; hash local conferiu com PyPI | Compatível com Python 3.12, mas declara `opencv-contrib-python`; não pode coexistir de forma sustentável com `opencv-python` do DeepFace no mesmo ambiente. |
| 0.10.21 | Wheel `cp312-cp312-win_amd64`, tag interna correta, Tasks API presente; hash local conferiu com PyPI | Também declara contrib e ainda exige `numpy<2`, divergindo do NumPy 2.5.3 atual. |
| 0.10.30 | Nome externo Windows genérico, tag interna `cp39-cp39-linux_x86_64` | Repete a incompatibilidade. |
| 0.10.31 | Nome externo Windows genérico, tag interna `cp39-cp39-linux_x86_64` | Falha reproduzida no app. |
| 0.10.32 | Wheel e tag interna `py3-none-win_amd64`, Tasks API presente | Tag corrigida, mas declara `opencv-contrib-python` e `matplotlib`. |
| 0.10.35 | Wheel e tag interna `py3-none-win_amd64`; SHA-256 publicado no PyPI: `b08f001cf3c3cd0d88d9ed68f3368dc8a4913f568281a93117f083115aa672ba` | Mantém a linha Tasks usada pelo provider; smoke com o modelo local passou. Requer contrib, então foi instalada somente no worker. |
| 1.1.0 | Wheel Windows `py3-none-win_amd64` | Também requer `opencv-contrib-python` e `matplotlib`; não havia motivo para migrar a implementação para essa linha. |

O DeepFace 0.0.92 declara `opencv-python`. `opencv-python` e `opencv-contrib-python` instalam o mesmo namespace `cv2`; mantê-los simultaneamente num ambiente causaria disputa de arquivos e comportamento imprevisível. As versões antigas com wheel correta não removem essa dependência; a 0.10.21 também força downgrade do NumPy. A Estratégia A, portanto, não atende aos critérios. A Estratégia C também não é necessária porque a Tasks API existente está funcional na versão testada.

Escolhi a Estratégia B: um processo filho local persistente durante a janela de cadastro, executado em `.venv-landmarks`. A aplicação principal mantém DeepFace, TensorFlow e `opencv-python`; o worker tem MediaPipe, `opencv-contrib-python` e NumPy, sem fornecedor concorrente de `cv2` dentro de qualquer um dos ambientes. O transporte é por stdin/stdout binários locais, sem rede e sem arquivos de frame. O startup tem timeout de 20 segundos e cada frame tem timeout de 5 segundos, cobrindo envio e resposta; a falha encerra o processo e as threads de transporte, permitindo o fallback da prévia.

## Dependências antes e depois

| Ambiente | Antes | Depois e `pip check` |
|---|---|---|
| `.venv-app` | CPython 3.12.0rc2 AMD64; MediaPipe 0.10.31; `opencv-python` 4.13.0.92; NumPy 2.5.3; DeepFace 0.0.92; TensorFlow 2.21.0. `pip check` falhava no MediaPipe. | MediaPipe e `opencv-contrib-python` ausentes; `opencv-python`, NumPy, DeepFace e TensorFlow preservados. `pip check`: `No broken requirements found.` |
| `.venv-landmarks` | Não existia. | CPython 3.12.0rc2 AMD64; MediaPipe 0.10.35; `opencv-contrib-python` 4.13.0.92; NumPy 2.5.3; `opencv-python`, DeepFace e TensorFlow ausentes. `pip check`: `No broken requirements found.` |

O `requirements-landmarks.txt` fixa somente as dependências diretas do worker (`mediapipe==0.10.35`, `opencv-contrib-python==4.13.0.92`, `numpy==2.5.3`). As transitivas foram instaladas pelo resolver e verificadas por `pip check`. Nenhuma instalação usou `--no-deps` ou metadata alterada. `requirements.txt` do app permanece separado.

## Arquivos modificados

- Provider e protocolo local: `src/infrastructure/face_recognition/mediapipe_landmarks.py`, `mediapipe_landmarks_protocol.py` e `mediapipe_landmarks_worker.py`.
- Configuração e composição: `src/config/settings.py`, `.env.example` e `src/main.py`.
- Dependências e testes do provider/configuração: `requirements-landmarks.txt` e os testes unitários de landmarks, overlay, viewer, settings e composição.
- Desenho, plano, prompt original anotado como histórico, dependências e este resultado em `tasks/006-facial-landmarks/`; setup, rollback e limites em `docs/FACIAL-LANDMARKS.md`; estado do projeto em `README.md`, `ARCHITECTURE.md`, `tasks/README.md` e `docs/ESTADO-ATUAL-E-EVIDENCIAS.md`.

O overlay continua opt-in (`FACE_LANDMARKS_ENABLED=false`), apenas na janela `Cadastro facial`; preserva o frame original e não muda embeddings, MiniFASNet, threshold `0.30` ou as regras de reconhecimento. Landmarks não são prova de vida e não são persistidos.

## Validações executadas

Comandos finais executados no workspace:

```powershell
.\.venv-ml\Scripts\python.exe -m pytest tests/unit/test_mediapipe_landmarks_process.py -q -p no:cacheprovider --basetemp=.pytest-stage6-startup-timeout-20261014
.\.venv-ml\Scripts\python.exe -m pytest tests/unit/test_mediapipe_landmarks.py tests/unit/test_mediapipe_landmarks_process.py tests/unit/test_landmarks_overlay.py tests/unit/test_main_landmarks.py tests/unit/test_viewer.py tests/unit/test_prompts_e_settings.py -p no:cacheprovider --basetemp=.pytest-stage6-focused-final2-20261014
.\.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider --basetemp=.pytest-stage6-unit-final4-20261014
.\.venv-ml\Scripts\python.exe -m ruff check src tests
.\.venv-ml\Scripts\python.exe -m mypy
.\.venv-ml\Scripts\python.exe -m ruff format --check <15 arquivos Python alterados>
.\.venv-app\Scripts\python.exe -m pip check
.\.venv-landmarks\Scripts\python.exe -m pip check
```

Resultados finais: regressões do processo auxiliar **10 passaram**; testes focados **97 passaram em 1,32 s**; suíte unitária completa **841 passaram em 9,10 s**; Ruff `All checks passed!`; mypy `Success: no issues found in 74 source files`; formatação dos 15 arquivos Python alterados aprovada; ambos os `pip check` retornaram `No broken requirements found.` `git diff --check` também passou. O index do Git permaneceu vazio.

Também rodei `ruff format --check src tests`. Esse gate amplo continua reprovando em 15 arquivos preexistentes e não relacionados à tarefa: `src/infrastructure/database/models.py`, dois repositórios PostgreSQL, dois arquivos BDD, dois testes de integração PostgreSQL e oito testes unitários antigos (`test_avaliacao_classificadores.py`, `test_calibrar_limiar.py`, `test_classificadores_binarios.py`, `test_evaluate_model.py`, `test_experimento_classificacao_binaria.py`, `test_graficos_classificacao.py`, `test_matcher.py`, `test_opencv_camera.py`). O comando informou 88 arquivos já formatados. Não reformatei esses 15 arquivos para evitar alterações fora do escopo; todos os arquivos Python alterados passaram no gate direcionado.

O smoke real usou `.venv-app`, o modelo local `models/face_landmarker.task` e um array preto sintético 480×640. Resultado final: Python do app `3.12.0rc2`, MediaPipe ausente do processo principal, worker iniciou em `1,461 s`, inferência levou `0,031 s`, retornou zero faces e 124 conexões, a thread de transporte foi liberada e o processo filho terminou com código 0. Nenhuma webcam, banco, imagem de pessoa ou dado operacional foi aberto. Esses tempos são apenas desse smoke e não indicam FPS de câmera ou desempenho biométrico.

## Ativação, rollback e limitações

Para criar o ambiente auxiliar na raiz do projeto:

```powershell
.\.venv-app\Scripts\python.exe -m venv .venv-landmarks
.\.venv-landmarks\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-landmarks.txt
.\.venv-app\Scripts\python.exe -m pip check
.\.venv-landmarks\Scripts\python.exe -m pip check
```

O modelo deve existir localmente em `models/face_landmarker.task`; a aplicação não o baixa. Configure `FACE_LANDMARKS_ENABLED=true` para ativar e inicie o app com `.\.venv-app\Scripts\python.exe -m src.main`. Para rollback, volte a flag para `false` e reinicie. O ambiente auxiliar pode permanecer sem ser iniciado. O procedimento está em [docs/FACIAL-LANDMARKS.md](../../docs/FACIAL-LANDMARKS.md).

Limitações restantes: não foi possível validar numa instalação limpa com CPython 3.12 estável nesta máquina; a validação visual manual com pessoa e câmera permanece pendente; não houve medição de reconhecimento, anti-spoofing, acurácia ou prova de vida. O teste com pixels sintéticos é integração de software somente.

O estado final da tarefa é **correção técnica concluída, com inspeção visual manual pendente**.
