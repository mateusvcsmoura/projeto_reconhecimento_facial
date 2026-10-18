# Resultado — tarefa 013: desafio facial e verificação 1:1

Data: 18/10/2026. Estado inicial: branch `main`, HEAD
`6c4c81c171ea3a07039fe609077c466e1d64deca`; workspace limpo antes da tarefa.
O código foi implementado no workspace e publicado em commits organizados na
`main`. Não houve deploy.

## Entrega

A verificação web compara a captura somente com as três referências ativas,
ordinais 1–3, do aluno previamente autorizado e do conjunto/versão fixados. A
regra exige embeddings Facenet512 de 512 dimensões, finitos e normalizados, e
aceita quando a mediana das três distâncias cosseno é `<= 0,30`. O threshold é
uma política inicial de engenharia, sem calibração biométrica; não altera o
pipeline da CLI nem executa busca 1:N.

O servidor emite um nonce HMAC ligado à reserva UUID e persiste somente seu hash.
O desafio requer frente, movimento leve para um lado aleatório e retorno, nessa
ordem, em até 120 segundos, sempre limitado pelo prazo da reserva. Cada frame
passa pela reserva existente de `presenca` e pela fila única da tarefa 012.
Etapas intermediárias devolvem o mesmo job ao estado de reserva, liberam o slot
de inferência e preservam quota e temporários. Reenvio válido de etapa já
recebida é idempotente; ele não grava um segundo frame nem cancela o job.

O worker exige rosto único, qualidade de captura, resultado estrito de
anti-spoofing, identidade 1:1, continuidade entre embeddings e pose calculada
no backend. Antes de `cv2.imdecode`, Pillow inspeciona o cabeçalho e recusa
frames acima de 4.194.304 pixels ou 8192 pixels por lado. O provider MediaPipe
roda em processo filho com pipes locais; o processo principal usa
`opencv-python`, enquanto o ambiente filho Linux usa `opencv-contrib-python`.
Não há dois fornecedores de `cv2` no mesmo ambiente. O resultado estruturado
permanece interno e nenhum componente grava presença.

A migration `0008` cria apenas o estado mínimo do desafio ligado ao job, aluno
e conjunto/versionamento. Não armazena imagem, landmarks ou embeddings. O
downgrade da revisão recusa apagar a tabela enquanto houver desafios persistidos.

## Diagnóstico e decisões

O primeiro teste PostgreSQL real revelou que a priorização do job retomado usava
`FOR UPDATE SKIP LOCKED` sobre uma consulta com `LEFT JOIN`; o PostgreSQL recusou
bloquear o lado anulável do join. A consulta agora bloqueia explicitamente só a
linha de `jobs_faciais_web`. A integração foi repetida com sucesso.

A revisão independente também identificou três riscos corrigidos antes da
publicação: a decodificação de uma imagem comprimida grande ocorria antes de
limitar pixels; retries concorrentes podiam marcar uma etapa válida como
inválida; e o downgrade podia apagar desafios. Pillow agora verifica o cabeçalho
antes da decodificação, retries válidos são tratados como duplicatas sem efeitos
colaterais e o downgrade protege qualquer estado persistido. Há testes de
regressão unitários e PostgreSQL para essas condições.

MediaPipe oficial `0.10.35` foi mantido: o Face Landmarker iniciou no Linux com
o modelo local e entrada sintética, sem conflito de fornecedores `cv2`. A
dependência de pose fica isolada em `requirements-landmarks-linux.txt`; a
investigação confirmou a necessidade de `libGLESv2.so.2` em Ubuntu mínimo. O
smoke usou a biblioteca oficial e o artefato local, sem baixar modelo durante o
funcionamento. Pillow `12.3.0` foi declarado diretamente para validar dimensões
antes que OpenCV aloque a imagem; a [distribuição oficial](https://pypi.org/project/pillow/12.3.0/)
declara Python `>=3.10` e classifica Python 3.12–3.14. O MediaPipe foi mantido
na versão [oficial 0.10.35](https://pypi.org/project/mediapipe/0.10.35/), em
ambiente isolado.

## Arquivos alterados

- Domínio e aplicação: `src/domain/services/verificacao_identidade.py`,
  `src/domain/services/desafio_captura.py`,
  `src/domain/services/face_recognition.py` e
  `src/application/use_cases/desafio_verificacao_web.py`.
- Worker e infraestrutura: fila/worker facial, composição `src/face_worker_main.py`,
  settings web, adapter MediaPipe de movimento, processador 1:1, repositórios
  PostgreSQL, `src/infrastructure/database/models.py` e migration `0008`.
- Dependências: `requirements.txt` (Pillow) e
  `requirements-landmarks-linux.txt` (ambiente MediaPipe isolado).
- Testes unitários para mediana/limiar, referências, nonce/ordem/expiração,
  repetição concorrente, pixels máximos, pose, anti-spoofing, fallback e
  resultado restrito. Testes PostgreSQL exercitam a migration, lock, prioridade,
  retomada do mesmo job e proteção contra downgrade com desafio persistido.
- Documentação atualizada: este resultado, desenho/plano/índice da tarefa,
  contrato web, contrato de migrations, runtime Linux e planejamento futuro.

## Validação executada

| Verificação | Resultado |
|---|---|
| `python -m pytest tests/unit -p no:cacheprovider --basetemp .pytest-task013-final-20261018 --tb=short` em `.venv-ml` | 1084 aprovados |
| `python -m pytest tests/integration/test_fila_facial_postgresql.py -p no:cacheprovider --tb=short`, com opt-in e URL definida somente para o banco descartável identificado | 5 aprovados; migration `0008` subiu até `head`, `alembic check` passou e a fixture retornou o banco a `base` |
| `python -m ruff check src tests` | aprovado |
| `python -m ruff format --check` nos 24 arquivos Python alterados/adicionados | aprovado |
| `python -m mypy src scripts` | `Success: no issues found in 120 source files` |
| `git diff --check` | aprovado |
| `python -m pip check` em `.venv-app`, `.venv-landmarks` e `.venv-ml` | `No broken requirements found` em cada ambiente |
| `pip check` nos ambientes Linux descartáveis do processo principal e MediaPipe isolado | `No broken requirements found` em cada ambiente |
| `alembic upgrade head --sql` | compilação offline da revisão `0008` aprovada |

Os cinco testes PostgreSQL rodaram no host local e no banco
`task012_web_worker_test_20261018`, cujo comentário foi verificado como
`projeto_reconhecimento_facial: task 012 disposable worker database`. O banco
`escola` não foi usado nem alterado nesta execução. A tentativa de downgrade
enquanto havia um desafio retornou erro e preservou tabela e linha; a fixture
removeu os dados sintéticos e reverteu todo o schema descartável a `base`.

## Smoke com modelo e limites

O Face Landmarker MediaPipe `0.10.35` carregou `models/face_landmarker.task`
no Linux/WSL x86-64 e processou uma imagem sintética preta de 224×224: startup
medido em 1,531 s, inferência em 0,009 s, resultado `ausente`, processo fechado
corretamente. O runtime de teste usou Python 3.14.4 e Ubuntu/WSL minimal; foi
necessário disponibilizar `libGLESv2.so.2` em diretório temporário via pacote
Ubuntu `libgles2`. Nenhum pacote foi instalado no sistema. O processo usou EGL
com renderização CPU/llvmpipe. Esse smoke comprova inicialização, troca local,
inferência sintética e liberação do processo — não comprova pose, detecção de
pessoa, acessibilidade, qualidade biométrica ou capacidade de produção.

O DeepFace/FaceNet512 e MiniFASNet também foram exercitados no Windows com uma
imagem preta sintética; o resultado foi a recusa esperada `NenhumRostoDetectado`.
No Windows, o frame JPEG sintético também percorreu o leitor de cabeçalho Pillow,
a decodificação OpenCV, o processo filho MediaPipe com o modelo local e o adapter
de pose. O provider iniciou em 1,038 s, inferiu em 0,003 s, retornou `ausente`
como esperado para a imagem preta e fechou o processo filho. Esses tempos são de
um smoke isolado, não uma medição de capacidade.
Nenhuma webcam foi aberta e nenhuma imagem de pessoa ou referência biométrica
real foi processada. Não houve avaliação de taxas de erro, segurança contra
replay/deepfake, eficácia do anti-spoofing, limiar operacional, latência sob
carga ou validação visual de movimento com participante.

## Ativação, rollback e limitações

A task 013 não cria rotas HTTP, autenticação de aluno, interface ou feature flag.
O próximo consumidor deve validar autorização e passar somente o
`aluno_id_autorizado`; matrícula declarada pelo cliente não autentica identidade.
Para habilitar o handler no worker de produção, são obrigatórios
`WEB_MEDIAPIPE_MODEL_PATH` e `WEB_MEDIAPIPE_PYTHON_EXECUTABLE`, apontando ao
modelo local e ao interpretador do ambiente Linux isolado. A aplicação/worker
usa `requirements.txt`; o filho MediaPipe usa `requirements-landmarks-linux.txt`
e precisa de `libgles2`. O diretório de capturas compartilhado deve continuar em
tmpfs com os limites e controles da task 012. Não há download automático de
modelo. O handler só é usado no job `presenca`; tarefa de cadastro sem handler
continua recusada.

Para rollback de schema em banco descartável, parar os consumidores, confirmar
que não há linhas em `desafios_verificacao_web` e executar
`alembic downgrade 0007`. A migration recusará o downgrade se restar qualquer
linha, sem apagar dados automaticamente. Para interromper o processamento,
parar o worker e retirar sua configuração/implantação antes de reverter o
código. Não existe runtime web público para desligar nesta entrega.

**Estado:** tarefa 013 concluída no escopo de backend, worker, migration,
testes e documentação; commits e push para `main` realizados. A liberação
pública continua pendente das rotas/autorização das tasks 014/015, validação
integrada posterior e ensaio biométrico autorizado. A geometria de pose e a
política de identidade permanecem heurísticas não calibradas.
