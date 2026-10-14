# Dependências e compatibilidade — tarefa 006

Verificado em 14/10/2026 no workspace Windows AMD64. A solução final mantém a inferência MediaPipe em um processo local separado porque nenhuma versão avaliada é adequada para coinstalação junto de DeepFace e opencv-python no mesmo ambiente.

## Causa-raiz e diagnóstico do ambiente

Antes da correção, o ambiente principal .venv-app executava CPython 3.12.0rc2 AMD64 com pip 26.2.1. As tags aceitas incluem cp312-cp312-win_amd64. O pacote mediapipe 0.10.31 instalado tinha nome de wheel externo py3-none-win_amd64, mas seu WHEEL interno declarava cp39-cp39-linux_x86_64. O pip check reproduziu “mediapipe 0.10.31 is not supported on this platform”.

A incompatibilidade da tag independe do pré-release: cp39-cp39-linux_x86_64 não é tag suportada no Windows, inclusive em Python 3.12 estável. O launcher py.exe não listou outros interpretadores instalados. Não trocamos o Python; 0.10.35 e as dependências do worker foram instalados e executados no Python atual. Um ambiente estável 3.12 não foi testado nesta máquina e permanece uma validação de portabilidade separada.

O .venv-app preserva opencv-python 4.13.0.92, NumPy 2.5.3, DeepFace 0.0.92 e TensorFlow 2.21.0. O DeepFace declara opencv-python. Os pacotes opencv-python e opencv-contrib-python instalam o mesmo namespace cv2; a orientação do projeto OpenCV é instalar apenas uma variante por ambiente.

## Versões oficiais comparadas

| Versão | Wheel Windows AMD64 / tag | Dependências relevantes | Resultado |
|---|---|---|---|
| mediapipe 0.10.14 | Wheel externa e interna `cp312-cp312-win_amd64`; SHA-256 baixado confere com PyPI | NumPy, protobuf `<5`, JAX/JAXLib, matplotlib, sounddevice e `opencv-contrib-python`; Tasks Face Landmarker presente | Funciona como candidato em Python 3.12, mas a dependência contrib mantém conflito de fornecedor com `opencv-python` no app. Isolamento ainda necessário. |
| mediapipe 0.10.21 | Wheel externa e interna `cp312-cp312-win_amd64`; SHA-256 baixado confere com PyPI | NumPy `<2`, protobuf `<5`, JAX/JAXLib, matplotlib, sentencepiece, sounddevice e `opencv-contrib-python`; Tasks Face Landmarker presente | Tag compatível, mas requer isolamento por OpenCV e também diverge do NumPy 2.5.3 atual. Não oferece vantagem sobre a versão selecionada. |
| mediapipe 0.10.30 | Nome externo py3-none-win_amd64; WHEEL interno cp39-cp39-linux_x86_64 | NumPy, sounddevice e flatbuffers; sem contrib | Não corrige a tag interna, portanto não passa pip check no Windows. |
| mediapipe 0.10.31 | Nome externo py3-none-win_amd64; WHEEL instalado cp39-cp39-linux_x86_64 | absl-py, NumPy, sounddevice e flatbuffers; sem contrib | Causa-raiz reproduzida no .venv-app. |
| mediapipe 0.10.32 | Wheel publicada como py3-none-win_amd64 | opencv-contrib-python e matplotlib | Dependência do fornecedor cv2 conflita no mesmo ambiente com a dependência declarada pelo DeepFace. |
| mediapipe 0.10.35 | Wheel publicada e WHEEL interno py3-none-win_amd64 | opencv-contrib-python, matplotlib, sounddevice, NumPy, flatbuffers, certifi e absl-py | API Tasks, pip check e smoke real aprovados no ambiente auxiliar. Selecionada para o worker isolado. |
| mediapipe 1.1.0 | Wheel publicada py3-none-win_amd64 | opencv-contrib-python e matplotlib, além das dependências base | Tag correta, mas também requer isolamento; não foi necessário migrar para a nova linha de versão. |

A wheel 0.10.35 foi obtida do PyPI oficial como mediapipe-0.10.35-py3-none-win_amd64.whl. SHA-256 publicado pelo PyPI: b08f001cf3c3cd0d88d9ed68f3368dc8a4913f568281a93117f083115aa672ba. O pip instalou a distribuição oficial pelo índice; não alteramos seu metadata. Para ampliar a comparação sem instalar versões candidatas, baixei as wheels oficiais 0.10.14, 0.10.21 e 0.10.32 sem dependências, li `WHEEL` e `METADATA`, confirmei os hashes de 0.10.14 e 0.10.21 contra o PyPI, e confirmei a presença do módulo Tasks Face Landmarker. As releases 0.10.14 e 0.10.21 publicam tags CPython 3.12 Windows corretas, mas ambas exigem `opencv-contrib-python`; a 0.10.21 também limita NumPy a `<2`. A 0.10.32 declara tag interna `py3-none-win_amd64` e também exige contrib. A referência oficial da versão selecionada lista a wheel Windows e o hash: https://pypi.org/project/mediapipe/0.10.35/.

A 0.10.35 foi escolhida por ser da mesma série integrada no código e por executar com o modelo local e a API Tasks já usada pelo provider. A instalação no worker satisfaz suas dependências sem instalar um segundo fornecedor cv2 no .venv-app. Não foi usado --no-deps.

## Ambientes depois da correção

| Ambiente | Python / MediaPipe | Fornecedor cv2 | Pacotes de ML compartilhados | pip check |
|---|---|---|---|---|
| .venv-app | Python 3.12.0rc2; MediaPipe ausente | opencv-python 4.13.0.92; contrib/headless ausentes | NumPy 2.5.3, DeepFace 0.0.92, TensorFlow 2.21.0 | No broken requirements found. |
| .venv-landmarks | Python 3.12.0rc2; MediaPipe 0.10.35 | opencv-contrib-python 4.13.0.92; opencv-python/headless ausentes | NumPy 2.5.3; DeepFace e TensorFlow ausentes | No broken requirements found. |

Pacotes transitivos resolvidos no worker: absl-py 2.5.1, certifi 2026.7.22, sounddevice 0.5.6, flatbuffers 25.12.19, matplotlib 3.11.2, cffi 2.1.1, contourpy 1.4.0, cycler 0.12.1, fonttools 4.66.1, kiwisolver 1.5.1, packaging 26.3, pillow 12.3.0, pyparsing 3.3.3, python-dateutil 2.9.0.post0, six 1.17.0 e pycparser 3.11. A instalação não abre nem usa microfone; sounddevice é exigido pelo metadata do MediaPipe.

O arquivo requirements-landmarks.txt agora descreve somente o processo auxiliar: mediapipe==0.10.35, opencv-contrib-python==4.13.0.92 e numpy==2.5.3. Não o instale no .venv-app. O arquivo requirements.txt do app continua sendo a fonte das dependências principais.

## Preparar ou reproduzir a instalação

Na raiz do projeto, criar o worker usando o mesmo interpretador do app:

    .\.venv-app\Scripts\python.exe -m venv .venv-landmarks
    .\.venv-landmarks\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-landmarks.txt
    .\.venv-app\Scripts\python.exe -m pip check
    .\.venv-landmarks\Scripts\python.exe -m pip check

A instalação foi primeiro verificada com pip install --dry-run --only-binary=:all: -r requirements-landmarks.txt e depois executada com o arquivo. Ambos retornaram código 0. O auxiliar existente já continha as mesmas versões exatas, então a execução final informou “Requirement already satisfied”.

Para remover a wheel 0.10.31 do ambiente principal anterior, foi executado:

    .\.venv-app\Scripts\python.exe -m pip uninstall -y mediapipe

Somente mediapipe 0.10.31 foi removido. NumPy, OpenCV, DeepFace, TensorFlow, sounddevice e outras dependências existentes foram preservadas. A remoção permite que o pip check do ambiente principal corresponda ao requirements.txt ativo.

## Modelo e privacidade

O bundle models/face_landmarker.task já está local, ignorado pelo Git e não é instalado pelo pip. A aplicação não baixa modelos. O worker recebe o caminho local do bundle ao iniciar, usa Face Landmarker em CPU/VIDEO, até duas faces, e encerra quando a janela de cadastro fecha.

Os frames RGB reduzidos são enviados somente por stdin/stdout de um processo filho local. Não são gravados em arquivos nem enviados pela aplicação pela rede. O worker devolve apenas coordenadas normalizadas temporárias e conexões; elas não são persistidas. O startup tem timeout de 20 segundos e a troca completa de cada frame tem timeout de 5 segundos; ambos encerram o processo e preservam o fallback. A flag continua false por padrão.

A Tasks API oficial para Python documenta o modelo local, execução IMAGE/VIDEO e retorno de landmarks: https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python. O recurso é apenas visual. Não altera FaceNet512, MiniFASNet, threshold 0.30, regras de reconhecimento ou prova de vida.
