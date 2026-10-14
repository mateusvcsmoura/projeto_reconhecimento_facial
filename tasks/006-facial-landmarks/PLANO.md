# Plano de implementação — 006: landmarks faciais

> Executor Luna 6 High: implementação original seguida de correção de compatibilidade concluída no workspace. A correção e suas evidências estão em [PLANO-CORRECAO.md](PLANO-CORRECAO.md) e [RESULTADO.md](RESULTADO.md). Esta execução não faz commit nem push.

**Objetivo:** pontos e contornos na prévia de cadastro, preservando pixels originais e decisões biométricas.

**Arquitetura:** provider isolado MediaPipe Tasks, DTOs numéricos e desenho no viewer. Instância por janela, flag false e fallback para indisponibilidade.

**Stack final:** processo principal na `.venv-app` com `opencv-python`/NumPy existentes; worker local em `.venv-landmarks`, MediaPipe 0.10.35 e `opencv-contrib-python` isolado; bundle oficial local. Testes unitários na `.venv-ml` com doubles.

**Especificação:** [DESENHO.md](DESENHO.md) e [DEPENDENCIAS.md](DEPENDENCIAS.md).

## 1. Baseline e dependências

- [x] Ler AGENTS.md, CLAUDE.md, instructions/ e este pacote; registrar branch/HEAD/status e preservar alterações alheias. Preparação em `f116a95` na main.
- [x] Inspecionar remoto/divergência conforme prompt antes de editar.
- [x] Confirmar viewer/menu/main/settings e testes existentes. Não abrir `.env` nem imagens reais.
- [x] Criar `requirements-landmarks.txt`, mantendo pins atuais; executar dry-run e instalar conforme DEPENDENCIAS.md.
- [x] Criar regra `/models/*.task` em `.gitignore` e `models/README.md`; obter bundle oficial, registrar origem/hash/termos; confirmar import e smoke sintético. Não versionar pesos.
- [x] Diagnosticar que a wheel 0.10.31 declara tag Linux incompatível. Corrigir por processo auxiliar; não alterar metadata da wheel nem instalar OpenCV concorrente no mesmo ambiente.

## 2. Provider de landmarks

Criar `src/domain/services/facial_landmarks.py`, `src/infrastructure/face_recognition/mediapipe_landmarks.py`, `tests/unit/test_mediapipe_landmarks.py`.

- [x] Escrever testes com MediaPipe/cv2 dublados para transformação de BGR em RGB, array contíguo, não mutação da entrada e resize proporcional limitado a 640.
- [x] Cobrir zero/um/dois rostos, resultado numérico imutável, opções CPU/VIDEO e inferência usando timestamp recebido.
- [x] Implementar DTOs/Protocol e adaptador; importar MediaPipe somente no momento da criação habilitada. Usar constantes Tasks da versão instalada para contornos.
- [x] Testar criação única por sessão, fechamento idempotente, ausência de modelo/dependência e falhas sem imagens/coordenadas nos logs; erros de configuração do provider são tratados na fronteira da janela.
- [x] A implementação original não registrou uma execução vermelha; a correção de compatibilidade seguiu RED/GREEN em `test_mediapipe_landmarks_process.py`.

## 3. Overlay e integração no viewer

Criar `src/presentation/cli/landmarks_overlay.py`, `tests/unit/test_landmarks_overlay.py`; alterar `src/presentation/cli/viewer.py` e `tests/unit/test_viewer.py`.

- [x] Testar conversão em frames de proporções/tamanhos diferentes, bordas 0/1, NaN/Inf, fora do intervalo e índices inválidos. Pular conexões com qualquer ponta inválida.
- [x] Desenhar pontos e contornos conforme especificação, sobre cópia; zero/dois rostos sem malha e com estado adequado. Não importar MediaPipe no renderer.
- [x] Injetar factory/relógio opcionais, preservando construtor existente e `mostrar(frame, linhas)`.
- [x] Testar monotonicidade estrita mesmo com relógio repetido; não reutilizar resultado em ausência de face.
- [x] Desenhar textos após geometria, preservar teclas, garantir pixel a pixel que input não muda mesmo com desenhador que altera arrays.
- [x] Cobrir modelo ausente/corrompido, dependência ausente, exceção de inferência, criação de janela falhando, fechamento lançando exceção: fallback sem spam e cleanup completo; nunca capturar BaseException.

## 4. Configuração e composição

Alterar `src/config/settings.py`, `.env.example`, `src/main.py`; criar `tests/unit/test_main_landmarks.py`, ampliar `test_prompts_e_settings.py` e regressões pertinentes de `test_menu.py`.

- [x] Implementar flag false e caminho de modelo relativo à raiz. Com flag false, não tocar no modelo/import pesado.
- [x] Injetar provider somente em `Cadastro facial`; reconhecimento permanece sem landmarks. Preservar assinatura do Protocol Janela/menu.
- [x] Provar com spies: false não cria provider; true só cria ao entrar na janela correta; sair e reabrir cria nova sessão; outras janelas não criam.
- [x] Provar que ESPAÇO retorna frame bruto, ESC cancela e consentimento ainda antecede a abertura da câmera. Não usar imagem enviada ou webcam real como teste.
- [x] Atualizar docstrings que diziam haver somente dois imports cv2.
- [x] Não foi necessário acrescentar override mypy para `mediapipe.*`.

## 5. Verificações e documentação

- [x] Rodar os testes novos e módulos afetados primeiro, na `.venv-ml`, com `-p no:cacheprovider --basetemp` apontando a diretório temporário exclusivo.
- [x] Após aprovar os focados, rodar `python -m pytest tests/unit` nesse ambiente com as mesmas opções. Não executar integração/BDD que abram banco.
- [x] Rodar Ruff, mypy e Ruff format --check nos arquivos Python alterados; corrigir problemas pertinentes.
- [x] Na `.venv-app` e `.venv-landmarks`, executar `pip check`; smoke de CPU pelo processo principal com modelo local e frame sintético. Não houve validação com rostos.
- [x] Conferir `git diff --check`, links locais, bundle ignorado e index vazio; não há arquivos staged.
- [x] Atualizar README.md e ARCHITECTURE.md; criar `docs/FACIAL-LANDMARKS.md` com setup, flags, recuperação de erro, limites, rollback e roteiro manual.
- [x] Registrar a inspeção visual manual como pendente; não executar com dados pessoais nesta tarefa.
- [x] Criar `tasks/006-facial-landmarks/RESULTADO.md`, atualizar índice e registro atual de evidências. Não modificar evidências históricas 001–005.

## 6. Revisar e encerrar

- [x] Revisar as alterações da correção sem incorporar nem descartar mudanças pré-existentes.
- [x] Deixar a implementação no workspace para revisão. O prompt desta correção proíbe commit e push automáticos.

Condição de parada técnica: overlay implementado e testado, dependências/smoke reais validados, privacidade de pixels preservada e limitações documentadas. A avaliação visual manual pendente deve ser explicitada; não equivale a falha dos testes sintéticos nem autoriza afirmar qualidade biométrica. A publicação não faz parte desta execução.
