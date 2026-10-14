# Plano de correção — compatibilidade MediaPipe no Windows

## Diagnóstico inicial confirmado

- Workspace antes da correção: branch `main`, HEAD `f116a9574925708e99d7684c2013683fd07d6f50`; havia alterações anteriores da feature e de outras tarefas, todas preservadas.
- `.venv-app`: CPython 3.12.0rc2 AMD64, pip 26.2.1. As tags aceitas incluem `cp312-cp312-win_amd64`.
- O `mediapipe==0.10.31` instalado declara no `WHEEL` `cp39-cp39-linux_x86_64`, apesar de a distribuição no PyPI se chamar `py3-none-win_amd64`. O `pip check` reproduz `mediapipe 0.10.31 is not supported on this platform`.
- A falha deriva da tag interna incorreta do artefato; ela também seria incompatível com Python 3.12 estável. O pré-release existente é um risco separado de reprodutibilidade, mas não a causa deste erro. Não há Python estável instalado no launcher desta máquina e o interpretador atual não será trocado sem necessidade comprovada.
- O ambiente principal tem `opencv-python==4.13.0.92`, NumPy 2.5.3, DeepFace 0.0.92 e TensorFlow 2.21.0; somente `opencv-python` fornece `cv2`. DeepFace declara `opencv-python` como dependência.
- A comparação oficial no PyPI mostra wheels Windows AMD64 com tag externa genérica `py3-none-win_amd64` para 0.10.32, 0.10.35 e 1.1.0. Essas versões declaram `opencv-contrib-python`; a 1.1.0 também declara matplotlib. Substituir o fornecedor OpenCV no mesmo ambiente deixaria a dependência declarada por DeepFace sem atendimento; instalar os dois fornecedores concorre pelo namespace `cv2`.

## Hipótese confirmada e solução escolhida

Não há uma versão atual que resolva simultaneamente o tag quebrado de 0.10.31 e as dependências do ambiente principal. A Estratégia B foi validada: manter o processo principal e `opencv-python` intactos e executar Face Landmarker em um processo Python local, persistente apenas durante a janela de cadastro, com ambiente virtual independente e consistente. A seleção final é `mediapipe==0.10.35`: a wheel instalada declara `py3-none-win_amd64`, a Tasks API usada pelo código está presente e a inferência com o modelo local passou no ambiente auxiliar.

O processo auxiliar receberá frames temporários por stdin/stdout binários locais, sem rede e sem arquivos intermediários; devolverá apenas landmarks normalizados e conexões. O adaptador e DTOs continuam respeitando o contrato existente. A implementação limita startup a 20 segundos e toda troca (escrita do frame e resposta) a 5 segundos; falhas, ausência do interpretador/modelo e timeout encerram o auxiliar e preservam o fallback do cadastro.

## Sequência

1. Inspecionar artefatos oficiais: tag interna, hash PyPI, `Requires-Dist`, presença da Tasks API e wheel Windows. Validado: `pip check` e smoke com modelo local sintético em `.venv-landmarks`; os tempos medidos são de engenharia, não biométricos.
2. [x] Acrescentar testes focados do contrato do adaptador/processo (pipes, retorno de pontos, falha/timeout, preservação do frame e encerramento) e confirmar a falha antes da implementação.
3. [x] Implementar worker persistente por stdin/stdout local, configuração do executável auxiliar e instalação em requisitos separados. MediaPipe não é importado pelo processo da aplicação; flag segue desligada por padrão e o provider só é composto na janela Cadastro facial.
4. [x] Atualizar comandos/setup, rollback, arquitetura e limitações em `DEPENDENCIAS.md`, `RESULTADO.md` e `docs/FACIAL-LANDMARKS.md`.
5. [x] Executar testes focados, suíte unitária, Ruff, mypy, formatação, `pip check` em ambos os ambientes e smoke CPU com o modelo real. Não abrir webcam, banco ou imagens biométricas.

## Critério de parada e integração

Critérios técnicos atendidos: ambos os ambientes passam em `pip check`, cada um contém apenas um fornecedor `cv2`, o modelo local foi executado no worker e o processo liberou recursos; suíte unitária e verificações estáticas passaram. A validação visual manual permanece pendente. Conforme a instrução explícita da correção, não fazer commit nem push; manter as alterações no workspace para revisão.
