# Estado atual e evidências

**Base analisada:** 13/10/2026, revisão `f116a9574925708e99d7684c2013683fd07d6f50` (`main`); mudanças locais da tarefa 006 ainda não publicadas.
**Finalidade:** projeto da disciplina de Inteligência Artificial da Fatec,
para estudar identificação facial aberta 1:N como apoio ao registro de
presença. Não é um TCC. Este registro separa o que o código implementa, o que
foi verificado com dados sintéticos e o que ainda depende de avaliação
biométrica autorizada.

## Pipeline e política operacional

A CLI usa OpenCV para captura/detecção e DeepFace com FaceNet512 pré-treinado
para gerar embeddings de 512 dimensões. O adaptador exige uma face e aplica
anti-spoofing; embeddings normalizados são comparados por distância cosseno
com a galeria carregada para a sessão. O limiar operacional permanece
`FACE_THRESHOLD=0.30`. A presença só é persistida após confirmação do
operador; PostgreSQL guarda os registros.

O overlay mostra uma porcentagem derivada linearmente da distância em relação
ao limiar. Esse indicador não é probabilidade de identidade nem foi calibrado.

| Tarefa | Comportamento e configuração | Fontes e testes | Limite da evidência |
|---|---|---|---|
| 001 — qualidade de captura | Opt-in (`FACE_QUALITY_ENABLED=false`). Quando ativa, verifica menor dimensão da face (80 px), luminância média (40–215) e variância do Laplaciano (mínimo 100); exige a área original do detector. O adaptador já recusa zero ou múltiplas faces. | `src/domain/services/qualidade_captura.py`, `src/infrastructure/face_recognition/deepface_adapter.py`, `src/application/use_cases/cadastrar_aluno.py`, `src/presentation/cli/menu.py`; `tests/unit/test_qualidade_captura.py`; [resultado 001](../tasks/001-qualidade-captura/RESULTADO.md). | Limites são heurísticas; não há checagem explícita de orientação facial nem calibração com rostos. Testes usam recortes sintéticos. Qualidade não substitui anti-spoofing. |
| 002 — consistência temporal | Opt-in (`FACE_TEMPORAL_ENABLED=false`). Padrão de 3 identificações iguais, nos ciclos a cada 8 frames, dentro de 5 s; a mais recente precisa ter até 2 s. ENTER lê outro frame, identifica de novo e só registra o mesmo ID; tentativa concluída consome a sequência. | `src/domain/services/consistencia_temporal.py`, `src/presentation/cli/menu.py`, `src/main.py`; `tests/unit/test_consistencia_temporal.py` e testes de menu; [resultado 002](../tasks/002-consistencia-temporal/RESULTADO.md). | Observações correlacionadas não demonstram melhora de acurácia. Timestamp antes da leitura não garante frescor físico do sensor; câmeras podem bufferizar frames. |
| 003 — ambiguidade | Opt-in (`FACE_AMBIGUITY_ENABLED=false`; margem padrão `None`, obrigatória ao ativar). Primeiro o melhor candidato deve passar por `FACE_THRESHOLD`; depois calcula-se o gap para a menor distância de outra identidade, mesmo se ela estiver acima do limiar. Empate exato ou gap menor que a margem recusa; igualdade positiva aceita. Duplicatas do mesmo ID não concorrem. | `src/domain/services/matcher.py`, `src/application/use_cases/reconhecer_aluno.py`, `src/main.py`, `src/presentation/cli/menu.py`; `tests/unit/test_matcher_ambiguidade.py`; [resultado 003](../tasks/003-rejeicao-ambiguidade/RESULTADO.md). | Margem positiva não calibrada. Empate, desconhecido e múltiplas faces são decisões distintas. Recusar candidatos próximos não prova identidade correta. |
| 004 — benchmark de matching | Script compara a matriz NumPy vetorizada com referência independente de laço Python e um `NumPy dot` por embedding. Gera vetores sintéticos 512D; valida decisões e distâncias antes de cronometrar. | `scripts/benchmark_matcher.py`, `tests/unit/test_benchmark_matcher.py`; [resultado 004](../tasks/004-benchmark-matching/RESULTADO.md); [execuções agregadas](../tasks/004-benchmark-matching/evidencias/). | Não executa DeepFace, não usa dados faciais, não mede acurácia nem latência ponta a ponta, e não compara `pgvector`/ANN. `tracemalloc` não é RSS nem toda a memória nativa. |
| 006 — landmarks visuais no cadastro | Opt-in (`FACE_LANDMARKS_ENABLED=false`), provider MediaPipe Tasks em worker Python local isolado apenas na janela Cadastro facial. Desenha contornos sobre cópia; a imagem original segue inalterada. | `src/domain/services/facial_landmarks.py`, `src/infrastructure/face_recognition/mediapipe_landmarks.py`, `src/infrastructure/face_recognition/mediapipe_landmarks_worker.py`, `src/presentation/cli/landmarks_overlay.py`, `src/presentation/cli/viewer.py`, `src/main.py`; testes unitários sintéticos; [resultado 006](../tasks/006-facial-landmarks/RESULTADO.md). | 841 testes unitários; Ruff, mypy e formato dos arquivos alterados passaram; `pip check` passou nos dois ambientes. Smoke com o modelo local e frame sintético passou; inspeção visual manual ainda pendente. Não há evidência de reconhecimento, qualidade ou prova de vida. |

Anti-spoofing continua habilitado por padrão (`FACE_ANTI_SPOOFING=true`). Sua
eficácia contra ataques não foi medida. Qualidade, confirmação temporal,
ambiguidade e landmarks visuais ficam desligados por padrão. O overlay não
altera o limiar nem a decisão de identidade.

## Registro de evidências

As contagens unitárias seguintes são snapshots de execuções diferentes; não
se somam e não representam avaliação biométrica. Os relatórios individuais
contêm ambiente, comandos e limites.

| Fonte e data registrada | Resultado | Escopo |
|---|---|---|
| Tarefa 001, 13/10/2026 | 611 testes unitários; Ruff e mypy aprovados | Comportamento de software com doubles e arrays sintéticos; sem webcam, modelo ou banco. [Relatório](../tasks/001-qualidade-captura/RESULTADO.md). |
| Tarefa 002 | 707 testes unitários; Ruff e mypy aprovados | Serviço temporal e integração unitária com relógio/dados sintéticos. Frames consecutivos não são amostras independentes. [Relatório](../tasks/002-consistencia-temporal/RESULTADO.md). |
| Tarefa 003 | 776 testes unitários; Ruff e mypy aprovados | Decisão de margem com embeddings sintéticos; sem integração/BDD ou dados faciais. [Relatório](../tasks/003-rejeicao-ambiguidade/RESULTADO.md). |
| Tarefa 004, 13/10/2026 | 812 testes unitários; Ruff, mypy e formatação aprovados | Verificações de software registradas no [relatório](../tasks/004-benchmark-matching/RESULTADO.md); benchmark sintético em três execuções sequenciais. |
| Tarefa 006, 14/10/2026 | 839 testes unitários; Ruff, mypy, formatação e `pip check` dos dois ambientes aprovados | Worker MediaPipe local em doubles e array preto sintético com modelo; sem webcam, pessoas ou banco. A inspeção visual manual continua pendente; [relatório](../tasks/006-facial-landmarks/RESULTADO.md). |

Cada JSON da tarefa 004 registra `status=ok`, 240 consultas comparadas, zero
divergências de status/ID, zero divergências numéricas, zero distâncias não
finitas e erro absoluto máximo `1.1920928955078125e-7` (tolerância `1e-5`).
As configurações são iguais nos três arquivos: galerias de 10, 50, 200 e 1000
vetores; 10 consultas por cenário; 10 rodadas; 3 aquecimentos; seed 1234;
cenários artificiais de referência, ortogonalidade e empate. São evidências
históricas consultadas nesta consolidação; as medições longas não foram
repetidas.

Na tarefa 005, a seleção dos quatro módulos de teste passou com 167 testes em
13/10/2026. `--help` terminou com código 0; o smoke curto também terminou com
código 0, validou 12 comparações, registrou zero divergências e erro absoluto
máximo `1.1920928955078125e-7` ante tolerância `1e-5`, sem gravar JSON. Esses
resultados e os comandos estão em
[`tasks/005-consolidacao-demonstracao/RESULTADO.md`](../tasks/005-consolidacao-demonstracao/RESULTADO.md).
Essa seleção não é a suíte unitária inteira nem a suíte completa.

Na correção da tarefa 006, a suíte `tests/unit` passou com 839 testes. O
worker foi iniciado pelo ambiente do app, executou MediaPipe em CPU com o
bundle local e recebeu um frame preto sintético; o resultado não continha
rostos, e esse caso não avalia precisão. Os ambientes `.venv-app` e
`.venv-landmarks` passaram em `pip check` e mantêm fornecedores `cv2`
separados. A inspeção visual manual permanece pendente. Veja o
[resultado 006](../tasks/006-facial-landmarks/RESULTADO.md).

## Séries de numeração

- **Fases 0–9 de refatoração:** sequência do plano original em
  [`REFACTORING_PLAN.md`](../REFACTORING_PLAN.md), baseada no estado inicial
  preservado em [`baseline-arquitetura.md`](baseline-arquitetura.md).
- **Etapas 0–5 de ML:** experimentos e consolidação acadêmica em
  [`ML-CONSOLIDACAO-ACADEMICA.md`](ML-CONSOLIDACAO-ACADEMICA.md). A Etapa 5
  histórica não é esta tarefa 005.
- **Tarefas 001–006:** melhorias optativas de captura/decisão, benchmark,
  consolidação documental e overlay visual, indexadas em
  [`../tasks/README.md`](../tasks/README.md). Tarefa 005 não é a prioridade 5
  do AGENTS.md nem a Etapa 5 de ML.

## Pendências confirmadas

- Calibração biométrica 1:N e validação representativa do pipeline completo,
  condicionadas a fonte, finalidade, autorização e revisão institucional.
- Avaliação do anti-spoofing em protocolo apropriado; a integração atual não
  comprova eficácia contra ataques.
- Múltiplas referências operacionais por identidade; os testes de ML que
  aceitam galerias não significam que o cadastro operacional já as oferece.
- Checagem explícita de orientação facial, ausente nas heurísticas 001.
- A mensagem de consentimento da CLI ainda aponta para a opção 3 ao falar
  sobre exclusão; no menu atual, excluir aluno é a opção 5. A correção está
  fora do escopo documental da tarefa 005.
- Validação de instalação limpa por outra pessoa, pendente no plano original.
- Inspeção visual manual do overlay com uma pessoa, pendente conforme tarefa
  006. A incompatibilidade da wheel Windows 0.10.31 foi corrigida por worker
  MediaPipe isolado e não é mais um gate pendente.
- Neon e API autenticada continuam propostas; não presumir migração ou
  distribuição de credenciais.

Não foram usados novos datasets externos nem dados de alunos. Não há alegação
de acurácia atual, melhoria biométrica, aprovação ética ou licença nova. Veja
também [`ARCHITECTURE.md`](../ARCHITECTURE.md), o
[`README.md`](../README.md) e os relatórios vinculados acima.
