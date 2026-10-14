# Landmarks visuais no cadastro

O recurso opcional mostra pontos e contornos estimados pelo MediaPipe Face Landmarker apenas na janela Cadastro facial. A solução foi validada tecnicamente no Windows com um processo auxiliar e o modelo local. A inspeção visual com uma pessoa real permanece pendente para validação manual autorizada.

## Arquitetura

O processo principal usa .venv-app e continua responsável por captura, DeepFace, anti-spoofing, reconhecimento e cadastro. Ele não importa MediaPipe. Quando a flag está ativa e a janela Cadastro facial é aberta, o provider inicia um processo local com o Python configurado em FACE_LANDMARKS_PYTHON_PATH.

O worker isolado usa .venv-landmarks, MediaPipe 0.10.35, opencv-contrib-python 4.13.0.92 e NumPy 2.5.3. O app usa opencv-python 4.13.0.92; os dois fornecedores de cv2 ficam em ambientes diferentes, nunca juntos no mesmo ambiente.

A comunicação usa stdin/stdout binários do processo filho local. O app envia um frame RGB reduzido e o timestamp; o worker devolve landmarks normalizados e conexões. Não há socket, rede ou arquivo intermediário. Frames e coordenadas existem apenas em memória. A inicialização tem timeout de 20 segundos e cada troca completa do frame (envio e resposta) tem timeout de 5 segundos. Ao fechar a janela ou ocorrer uma falha, o app fecha os pipes, aguarda o processo e encerra as threads de transporte. Timeout ou falha desativa o overlay e mantém o cadastro disponível.

## Configuração

Padrões em .env.example:

    FACE_LANDMARKS_ENABLED=false
    FACE_LANDMARKS_MODEL_PATH=models/face_landmarker.task
    FACE_LANDMARKS_PYTHON_PATH=.venv-landmarks/Scripts/python.exe

O bundle models/face_landmarker.task deve existir localmente. A aplicação não faz download do pacote nem do modelo. O caminho relativo é resolvido contra a raiz do projeto.

## Instalação no Windows

Na raiz do projeto, prepare o ambiente auxiliar:

    .\.venv-app\Scripts\python.exe -m venv .venv-landmarks
    .\.venv-landmarks\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-landmarks.txt

Confirme ambos os ambientes:

    .\.venv-app\Scripts\python.exe -m pip check
    .\.venv-landmarks\Scripts\python.exe -m pip check

O primeiro ambiente contém opencv-python, DeepFace e TensorFlow, sem MediaPipe ou opencv-contrib-python. O auxiliar contém MediaPipe e opencv-contrib-python, sem DeepFace ou TensorFlow. Não instale requirements-landmarks.txt no .venv-app.

Para ativar o overlay, defina FACE_LANDMARKS_ENABLED=true no .env. Ajuste FACE_LANDMARKS_MODEL_PATH ou FACE_LANDMARKS_PYTHON_PATH somente se os arquivos locais estiverem em outros caminhos. Depois, inicie a aplicação normalmente com o ambiente principal:

    .\.venv-app\Scripts\python.exe -m src.main

Com a flag false, o provider e o worker não são criados. O overlay nunca aparece na janela Reconhecimento. Espaço continua retornando o frame de captura sem overlay; Esc continua cancelando.

## Comportamento e limites

O worker executa Face Landmarker Tasks em CPU no modo VIDEO, com até duas faces. A prévia envia para inferência uma cópia RGB contígua, reduzida proporcionalmente a 640 px de largura. O frame original permanece intacto para cadastro, qualidade, anti-spoofing, embedding e armazenamento.

Os landmarks servem somente para desenhar. Não são prova de vida, não identificam a pessoa e não mudam embeddings FaceNet512, MiniFASNet, threshold 0.30, rejeição ou registro de presença. Não há blendshapes nem inferência de emoção, idade ou gênero. Coordenadas não são persistidas.

Se o executável, o modelo ou o processo auxiliar estiver ausente, ou se a inferência exceder o timeout, o viewer exibe o aviso de indisponibilidade uma vez e continua sem overlay. A dependência do worker e o seu modelo nunca são baixados durante o loop da câmera.

## Validação

As verificações automatizadas passaram com frames artificiais, doubles e o modelo oficial local: provider, framing local, conversão BGR/RGB, timeout/erro, preservação do frame e encerramento do processo. O smoke CPU retornou zero faces em um frame preto e 124 conexões disponíveis. Isso valida a integração de software, não detecção em pessoa, FPS real de câmera ou desempenho biométrico.

Validação visual manual pendente:

1. Ative a flag somente em uma sessão apropriada e com autorização para usar a câmera.
2. Abra Cadastro facial e verifique se os pontos e contornos acompanham o rosto na prévia.
3. Abra Reconhecimento e confirme que o overlay não aparece nessa janela.
4. Confirme Espaço para captura e Esc para cancelamento, sem usar uma sessão operacional sem autorização.
5. Feche o cadastro e verifique que o worker termina.

## Rollback

Para desativar a feature, defina FACE_LANDMARKS_ENABLED=false e reinicie o app. O ambiente auxiliar pode permanecer instalado sem ser iniciado.

Se também quiser remover o ambiente local, primeiro confirme que o diretório alvo é .venv-landmarks na raiz do projeto e então execute manualmente no PowerShell:

    Remove-Item -LiteralPath .venv-landmarks -Recurse

Não reinstale MediaPipe 0.10.31 no .venv-app: a tag Linux interna faz o pip check falhar. O histórico de versões, dependências e hashes consultados está em tasks/006-facial-landmarks/DEPENDENCIAS.md; comandos e resultados desta correção estão em tasks/006-facial-landmarks/RESULTADO.md.
