# FaceDiff — Reconhecimento Facial para Controle de Presença

Projeto acadêmico da disciplina de Inteligência Artificial da Fatec, não um
TCC. O sistema cadastra referências faciais de alunos e registra presença por
reconhecimento facial, com PostgreSQL e arquitetura em camadas.

Há duas interfaces sobre o mesmo domínio:

- **Web (FaceDiff):** o professor gerencia turmas, links de cadastro, sessões
  de presença e revisões; o aluno usa a câmera do navegador. É a interface
  principal em desenvolvimento.
- **CLI:** menu de terminal com webcam local, usado desde o protótipo.

Os testes usam dados sintéticos e comprovam comportamento funcional, não
acurácia biométrica. Não houve deploy nem validação com pessoas reais. O
registro de estado, evidências e pendências está em
[`docs/ESTADO-ATUAL-E-EVIDENCIAS.md`](docs/ESTADO-ATUAL-E-EVIDENCIAS.md).

| | |
|---|---|
| **Índice da documentação** | [`docs/README.md`](docs/README.md) |
| **Decisões** | [`docs/adr/`](docs/adr/) — ADRs com alternativas descartadas |
| **Dados pessoais** | [`docs/lgpd.md`](docs/lgpd.md) — o que é tratado, por quê e por quanto tempo |
| **Web: runtime** | [`docs/FACEDIFF-WEB-RUNTIME.md`](docs/FACEDIFF-WEB-RUNTIME.md) — execução local, Linux e Compose |
| **Web: contas e gestão** | [`docs/FACEDIFF-WEB-AUTH.md`](docs/FACEDIFF-WEB-AUTH.md), [`docs/FACEDIFF-WEB-GESTAO.md`](docs/FACEDIFF-WEB-GESTAO.md) |
| **Web: implantação** | [`deploy/web/README.md`](deploy/web/README.md), [`docs/FACEDIFF-WEB-HTTPS-DOMINIO.md`](docs/FACEDIFF-WEB-HTTPS-DOMINIO.md) |
| **Turmas (CLI)** | [`docs/TURMAS.md`](docs/TURMAS.md) |
| **Material acadêmico** | [`docs/ML-CONSOLIDACAO-ACADEMICA.md`](docs/ML-CONSOLIDACAO-ACADEMICA.md) |
| **Baseline histórico** | [`docs/baseline-arquitetura.md`](docs/baseline-arquitetura.md) — o protótipo monolítico de origem |

---

## Arquitetura

```text
Presentation   src/presentation/cli, src/presentation/web (FastAPI + SPA)
     ↓
Application    src/application/use_cases, src/application/services
     ↓
Domain         src/domain/entities, src/domain/repositories, src/domain/services
     ↑
Infrastructure src/infrastructure/{database,repositories,face_recognition,
               camera,storage,workers,backup}
```

O domínio não importa `DeepFace`, `cv2`, MediaPipe nem SQLAlchemy. Ele declara
protocolos (`FaceRecognitionProvider`, repositórios, armazenamento, câmera,
desafio de captura), e a infraestrutura os implementa. Os casos de uso
recebem as dependências prontas, por isso a lógica de negócio é testada sem
webcam, banco ou modelo.

| Camada | Conteúdo principal |
|---|---|
| `presentation/cli` | Menus, prompts, viewer OpenCV, overlay de landmarks e captura automática |
| `presentation/web` | `app.py` (fábrica, CSP, assets), `routes/` (auth, cadastros, gestão, links, presenças, operações), `rate_limit.py`, `schemas.py`, `static/` (módulos ES sem build) e `templates/index.html` |
| `application/use_cases` | Cadastro, reconhecimento e presença da CLI; cadastro web, aprovação, links, sessões, tentativas, revisão, exportação CSV, contas e turmas |
| `application/services` | `FilaFacial` (fila PostgreSQL limitada), `WorkerFacial` (processamento serial) e orquestração de backup |
| `domain/services` | `matcher` (1:N vetorizado), `verificacao_identidade` (1:1), desafio de captura, autorização, qualidade, consistência temporal e captura automática |
| `infrastructure/face_recognition` | `DeepFaceAdapter` (FaceNet512, detector, anti-spoofing), `DesafioMovimentoAdapter` (pose via MediaPipe em subprocesso) e processadores de jobs web |
| `infrastructure/repositories` | Repositórios `Postgres*`; o SQL fica somente aqui |
| `infrastructure/storage` | Referências privadas, capturas temporárias e imagens legadas |
| `infrastructure/workers`, `backup` | Lock de instância única, gate de manutenção, healthcheck, `pg_dump`/restore e rclone |
| `config` | `settings.py` (CLI) e `web_settings.py` (variáveis `WEB_*`), validados com Pydantic |

Pontos de entrada:

- `src/main.py`: CLI.
- `src/web_main.py`: fábrica ASGI `create_web_app`, servida pelo Uvicorn.
- `src/face_worker_main.py`: worker facial que consome a fila.

### Fluxo web

```text
Professor                         Aluno (navegador)                Worker facial
─────────                         ─────────────────                ─────────────
cria turma e link de cadastro ──► abre link, aceita aviso,
                                  envia 3 frames com desafio ────► detecção, anti-spoofing,
                                  de pose (frente/virada/retorno)  pose e embeddings
aprova ou rejeita o cadastro ◄──────────────────────────────────── referências pendentes
cria sessão e link de presença ─► informa matrícula, cumpre
                                  o desafio, envia capturas ─────► verificação 1:1:
                                                                   mediana de 3 distâncias
                                                                   cosseno ≤ 0,30
consulta presenças, revisa,   ◄──────────────────────────────────── presença registrada
edita/exclui sessões, exporta CSV                                  ou recusa explicada
```

A API não carrega modelos. Ela grava cada captura em armazenamento temporário
privado e enfileira um job; o worker processa um job por vez e confirma o
resultado em transação. O navegador mostra landmarks com MediaPipe
`tasks-vision` (WASM) apenas como guia; a decisão é sempre do servidor.

### Fluxo CLI

```text
Cadastro:   frame → detecção → anti-spoofing → embedding → PostgreSQL
Presença:   frame → detecção → anti-spoofing → embedding → matcher 1:N → registro
```

Os embeddings de referência são calculados no cadastro e persistidos com o
nome do modelo; o reconhecimento compara cada consulta com a matriz já
carregada. Detalhes da decisão em
[`ADR-002`](docs/adr/ADR-002-armazenamento-de-embeddings.md).

---

## Requisitos

- **Python 3.12 ou 3.13.** O TensorFlow publica wheels até 3.13, e o
  `numpy==2.5.3` só a partir de 3.12.
- **Docker** (ou PostgreSQL 16+ local).
- **Webcam** para a CLI; navegador com câmera para a interface web.

---

## Instalação

```powershell
# 1. Configuração — o .env real nunca vai para o Git
copy .env.example .env
py -3.12 -c "import secrets; print(secrets.token_urlsafe(48))"   # valor de WEB_SECRET_KEY
notepad .env
```

No `.env`, uma variável por linha:

- `POSTGRES_PASSWORD`: use só letras e números, para não precisar codificar a
  senha nas URLs;
- a mesma senha em `DATABASE_URL` (`localhost:5433`) e em `WEB_DATABASE_URL`
  (`host.docker.internal:5433`);
- `WEB_SECRET_KEY`: o valor gerado acima;
- `WEB_LOCAL_DEEPFACE_WEIGHTS_HOST_DIR`: pasta dos pesos, preenchida por
  `scripts.baixar_modelos` (ver [Primeira vez: modelos](#primeira-vez-modelos)).

```powershell
# 2. Banco (porta 5433, para não colidir com um PostgreSQL nativo)
docker compose up -d db

# 3. Schema — a aplicação nunca cria tabelas, só migrations.
#    Ambiente leve, só para o Alembic, sem TensorFlow (versões do requirements.txt):
py -3.12 -m venv .venv-migrations
.venv-migrations\Scripts\python.exe -m pip install alembic==1.19.2 SQLAlchemy==2.0.52 "psycopg[binary]==3.3.5" pydantic-settings==2.15.0 tzdata
.venv-migrations\Scripts\python.exe -m alembic upgrade head
```

O `tzdata` é necessário no Windows, que não traz a base de fusos usada por
`APP_TIMEZONE`. Para usar a CLI, instale o ambiente completo, que também roda
o `alembic`. Ele baixa TensorFlow e PyTorch: ~500 MB e alguns minutos.

```powershell
py -3.12 -m venv .venv-app
.venv-app\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

| Arquivo | Para quê |
|---|---|
| `requirements.txt` | CLI completa: DeepFace, TensorFlow, PyTorch, OpenCV, SQLAlchemy, Alembic |
| `requirements-web.txt` | API web leve: FastAPI, Uvicorn, Pydantic, SQLAlchemy, sem modelos |
| `requirements-ml.txt` | Worker facial |
| `requirements-landmarks.txt` / `-linux.txt` | MediaPipe em ambiente isolado (outro fornecedor de `cv2`) |
| `requirements-dev.txt` | Testes, Ruff e mypy |
| `requirements-experimentos.txt` | Scripts de experimentos de ML |

---

## Executar a interface web

O caminho suportado é o perfil `web` do Docker Compose, que sobe banco, API e
worker com os mesmos volumes temporários. Faça antes a [instalação](#instalação)
(`.env`, banco e schema).

### Primeira vez: modelos

Os modelos ficam fora do Git, e o worker não acessa a internet. Baixe-os antes
do primeiro build; sem o `face_landmarker.task`, o build falha com
`"/models/face_landmarker.task": not found`.

```powershell
py -3.12 -m scripts.baixar_modelos
```

O script usa só a biblioteca padrão e baixa ~103 MB das URLs oficiais (as
mesmas que o DeepFace usa), conferindo o SHA-256 de cada arquivo:

- `models/face_landmarker.task`: copiado para a imagem no build;
- pesos do FaceNet512 e do anti-spoofing em `~/.deepface/weights`: montados no
  worker somente para leitura e usados também pela CLI.

Ele também grava no `.env`, se existir, `WEB_LOCAL_DEEPFACE_WEIGHTS_HOST_DIR`
com a pasta dos pesos deste computador. Arquivos já presentes e íntegros não
são baixados de novo, então rodar outra vez é seguro. Na VPS, use
`sudo python3 -m scripts.baixar_modelos --pasta-modelos /srv/facediff/models`,
que grava no layout do deploy e não mexe em `.env` (passo 6 de
[`deploy/web/README.md`](deploy/web/README.md)).

### Subir

```powershell
docker compose --profile web up -d --build   # o primeiro build demora
docker compose --profile web ps              # aguarde os 3 serviços healthy
Invoke-RestMethod http://127.0.0.1:8000/health/ready

# primeira vez: conta administrativa (usuário e senha pedidos no prompt)
docker compose exec web python -m scripts.criar_admin_web
```

Abra `http://127.0.0.1:8000` e entre com o administrador; contas de professor
são criadas pela tela de administração. A câmera do navegador só funciona em
`localhost` ou HTTPS. O worker demora a ficar `healthy` porque carrega os
modelos. Nas próximas vezes, com o Docker Desktop aberto,
`docker compose --profile web up -d` basta; use `--build` só depois de mudar
código.

Para parar sem perder dados, use
`docker compose --profile web stop web face-worker`. Não use `down -v`. Depois
de mudar só código da API ou do frontend, reconstrua apenas `web`:
`docker compose --profile web up -d --build web`.

No Windows com Docker Desktop, limite a VM do WSL2 em
`%USERPROFILE%\.wslconfig` (por exemplo `memory=4GB` e
`autoMemoryReclaim=dropCache`). O motivo está em
[`docs/FACEDIFF-WEB-RUNTIME.md`](docs/FACEDIFF-WEB-RUNTIME.md).

---

## Executar a CLI

```powershell
python -m src.main
```

```text
Menu principal:                     Menu de turma ativa:
1 - Criar turma                     1 - Cadastrar aluno novo
2 - Listar e selecionar turma       2 - Vincular matrícula existente
3 - Histórico de turmas excluídas   3 - Listar alunos da turma
4 - Administração global            4 - Reconhecer e registrar presença
5 - Sair                            5 - Consultar presenças
                                    6 - Remover vínculo
                                    7 - Atualizar matéria/período
                                    8 - Excluir turma
                                    9 - Voltar
```

- **Cadastro:** sem o aceite do termo de consentimento, a câmera nem liga. No
  modo automático, mantenha um rosto visível durante a sequência; ESC cancela.
- **Reconhecimento:** opera só na turma selecionada. A presença é registrada
  após 5 s de observações válidas, pelo menos três análises e uma
  reidentificação final da mesma pessoa. O percentual exibido deriva da
  distância ao limiar; **não é probabilidade nem foi calibrado**.
- `FACE_AUTO_CAPTURE_ENABLED=false` volta ao modo manual (ESPAÇO captura,
  ENTER registra, ESC sai).
- Excluir turma é lógico. A exclusão global de um aluno, com imagem, embedding
  e presenças, fica na administração e exige confirmação.

Na primeira execução, o modelo é carregado antes de a câmera abrir, e os pesos
do DeepFace são baixados nesse momento. Estados e limites da captura estão em
[`docs/CAPTURA-AUTOMATICA.md`](docs/CAPTURA-AUTOMATICA.md); turmas e vínculos,
em [`docs/TURMAS.md`](docs/TURMAS.md); o overlay de landmarks, em
[`docs/FACIAL-LANDMARKS.md`](docs/FACIAL-LANDMARKS.md).

---

## Configuração

Tudo vem do `.env` ou do ambiente. As variáveis obrigatórias não têm default:
a aplicação falha no boot em vez de apontar silenciosamente para o banco
errado.

### CLI e núcleo de reconhecimento

| Variável | Padrão | Para quê |
|---|---|---|
| `DATABASE_URL` | — | **Obrigatória** |
| `APP_TIMEZONE` | `America/Sao_Paulo` | Define o "dia" da presença |
| `LOG_LEVEL` | `INFO` | |
| `CAMERA_INDEX` | `0` | |
| `CAMERA_LARGURA` / `CAMERA_ALTURA` | `1280` / `720` | Recorte maior melhora embedding e anti-spoofing |
| `CAMERA_BACKEND` | `auto` | DirectShow no Windows; ver *Problemas conhecidos* |
| `FACE_MODEL` | `Facenet512` | Trocar exige backfill |
| `FACE_DETECTOR` | `opencv` | |
| `FACE_THRESHOLD` | `0.30` | Ainda não calibrado; ver [ADR-004](docs/adr/ADR-004-limiar-de-reconhecimento.md) |
| `FACE_ANTI_SPOOFING` | `true` | Recusa foto impressa e tela |
| `FACE_AUTO_CAPTURE_ENABLED` | `true` | `false` recupera ESPAÇO/ENTER |
| `FACE_AUTO_CAPTURE_WAIT_SECONDS` | `5.0` | Duração mínima da sequência válida |
| `FACE_AUTO_CAPTURE_SAMPLE_SECONDS` | `0.5` | Intervalo mínimo entre análises |
| `FACE_AUTO_CAPTURE_MAX_AGE_SECONDS` | `2.0` | Idade máxima das observações |
| `FACE_LANDMARKS_ENABLED` | `false` | Landmarks na prévia de cadastro da CLI |
| `FACE_LANDMARKS_MODEL_PATH` | `models/face_landmarker.task` | Bundle local |
| `FACE_LANDMARKS_PYTHON_PATH` | `.venv-landmarks/Scripts/python.exe` | Interpretador isolado do MediaPipe |
| `FACE_QUALITY_ENABLED` | `false` | Checagens heurísticas de nitidez, luz e tamanho (opt-in) |
| `FACE_TEMPORAL_ENABLED` | `false` | Sequência consistente antes de ENTER no modo manual (opt-in) |
| `FACE_AMBIGUITY_ENABLED` | `false` | Recusa identidades próximas; exige `FACE_AMBIGUITY_MIN_MARGIN` |
| `STORAGE_DIR` | `./storage/faces` | Fora do Git |
| `RETENCAO_PRESENCAS_DIAS` | `1825` | 5 anos; `0` desliga o expurgo |

Os limites de qualidade, temporais e de ambiguidade são parâmetros de
engenharia sem calibração biométrica e não alteram o limiar nem o
anti-spoofing. A lista completa, com os limites de cada checagem, está no
`.env.example`.

### Interface web

| Variável | Padrão | Para quê |
|---|---|---|
| `WEB_DATABASE_URL` | — | **Obrigatória** |
| `WEB_SECRET_KEY` | — | **Obrigatória**; assina sessões e credenciais |
| `WEB_RETENTION_DAYS` | — | **Obrigatória**; retenção dos dados web, em dias |
| `WEB_PURPOSE_END_AT` | — | Fim da finalidade do tratamento; obrigatória em produção |
| `WEB_PUBLIC_ORIGIN` | `http://127.0.0.1:8000` no Compose | Endereço aberto no navegador (validação de origem e CSRF) |
| `WEB_TRUSTED_PROXY_CIDRS` | vazio | Proxies cujo `X-Forwarded-For` é aceito |
| `WEB_JOB_QUEUE_WAITING_LIMIT` | `30` | Jobs aguardando na fila facial |
| `WEB_PRESENCE_START_LIMIT_PER_WINDOW` | `60` | Inícios de presença por link e IP a cada 15 min |
| `WEB_PRESENCE_CAPTURE_LIMIT_PER_WINDOW` | `300` | Capturas de presença por link e IP a cada 15 min |
| `WEB_PUBLIC_REGISTRATION_CONTEXT_LIMIT_PER_MINUTE` | `40` | Acessos públicos ao cadastro por minuto |
| `WEB_CAPTURE_MAX_BYTES_PER_CAPTURE` | `2 MiB` | Tamanho máximo de cada frame |
| `WEB_CAPTURE_STORAGE_QUOTA_BYTES` | `300 MiB` | Quota temporária; precisa ser ≥ 3 × máximo × (fila + 1) |

Os limites comportam uma turma inteira atrás do mesmo IP (Wi-Fi do campus).
Os demais parâmetros estão em `src/config/web_settings.py`.

---

## Operação

### Migrations

```bash
alembic upgrade head            # aplica
alembic downgrade -1            # desfaz a última
alembic check                   # acusa divergência entre modelos e banco
alembic revision --autogenerate -m "descricao"
```

As revisões vão de `0001` a `0011`. Toda revisão implementa `downgrade()`, e
o autogenerate é só ponto de partida: revise à mão, porque ele não emite
`CHECK` nem `IDENTITY` de forma confiável. A URL vem de `DATABASE_URL` (ou
`ALEMBIC_DATABASE_URL`).

### Trocar de modelo de reconhecimento

Vetores de modelos diferentes **não são comparáveis**. O modelo fica gravado
junto do vetor, e uma divergência levanta erro em vez de identificar a pessoa
errada em silêncio. Depois de mudar `FACE_MODEL`:

```bash
python -m scripts.backfill_embeddings            # simula
python -m scripts.backfill_embeddings --apply    # efetiva
```

### Retenção e backup

```bash
python -m scripts.expurgar_presencas            # CLI: simula
python -m scripts.expurgar_presencas --apply    # CLI: efetiva
```

A retenção vale para o histórico de presença, nunca para o cadastro. Na web,
retenção (`scripts.web_retencao`), backup cifrado (`scripts.web_backup`) e
prova de restauração (`scripts.web_restore_check`) fazem parte do deploy
descrito em [`deploy/web/README.md`](deploy/web/README.md).

### Menor privilégio no banco

A aplicação não deve conectar com o dono do banco:

```bash
psql -U escola -d escola \
     -v senha="'SENHA_DA_APLICACAO'" \
     -f scripts/sql/criar_usuario_aplicacao.sql
```

Aponte o `DATABASE_URL` da aplicação para `escola_app` e use o dono apenas no
`alembic upgrade`. No deploy web, os papéis `facediff_app` e
`facediff_migrator` são criados por `deploy/web/postgres-init/`.

### Importar um banco SQLite legado

```bash
python -m scripts.import_legacy_sqlite --sqlite caminho/escola.db          # simula
python -m scripts.import_legacy_sqlite --sqlite caminho/escola.db --apply  # efetiva
```

Abre a origem somente para leitura, roda em transação única, é idempotente e
grava em `storage/etl/` um relatório com toda linha rejeitada e o motivo.

### Benchmark de matching

```powershell
python -m scripts.benchmark_matcher
python -m scripts.benchmark_matcher --saida-json resultado.json
```

Compara o matcher vetorizado com um laço Python sobre embeddings sintéticos
512D (galerias de 10 a 1000 IDs). Mede latência e memória de engenharia, não
inferência facial nem acurácia.

---

## Desenvolvimento

```bash
pip install -r requirements-dev.txt

pytest tests/unit                        # unitários, sem PostgreSQL
pytest --cov=src --cov-report=term       # suíte com cobertura
node --test tests/e2e/web/frontend.test.mjs   # módulos do frontend
ruff check .                             # lint
mypy                                     # tipos
```

```text
tests/
├── unit/          domínio, casos de uso, CLI, rotas web, adaptadores (com dublês)
├── integration/   PostgreSQL real: schema, constraints, repositories, migrations
├── features/      cenários BDD em Gherkin (pytest-bdd)
└── e2e/web/       testes Node dos módulos ES do frontend
```

`requirements-dev.txt` não inclui OpenCV nem DeepFace: a suíte roda com
dublês injetados em `sys.modules`. Se um teste passar a exigir esses pacotes,
uma fronteira vazou.

Os testes de integração PostgreSQL são destrutivos: podem truncar tabelas.
Eles não leem o `.env` e só rodam com `FACE_TURMAS_TEST_DB_AUTORIZACAO`,
`FACE_TURMAS_TEST_DATABASE_URL` (e `FACE_TURMAS_MIGRATION_DATABASE_URL` para
migrations) apontando para bancos descartáveis com marcador; veja
[`docs/TURMAS.md`](docs/TURMAS.md). Sem isso são ignorados, e um skip não conta
como validação.

### CI

`.github/workflows/ci.yml` roda a cada push e PR: Ruff, mypy, migrations
(sobem e descem), `alembic check`, testes com piso de 80% de cobertura e uma
verificação de que nenhum arquivo sensível foi versionado.

### Avaliação do modelo (≠ teste de software)

Teste de software verifica se o pipeline faz o que promete; avaliação de
modelo mede se ele **acerta**.

```bash
python -m scripts.evaluate_model --dataset avaliacao/datasets/<nome> --validar-divisao
python -m scripts.evaluate_model --dataset avaliacao/datasets/<nome>
python -m scripts.calibrar_limiar --dataset avaliacao/datasets/lfw
```

A calibração divide por identidade, escolhe o limiar na validação e abre o
teste uma única vez; ela **não** altera o `FACE_THRESHOLD`. Resultados em
[`docs/ML-ETAPA-1-RESULTADO.md`](docs/ML-ETAPA-1-RESULTADO.md); fontes de dados
permitidas e descarte em
[`docs/ML-EXPERIMENT-SETUP.md`](docs/ML-EXPERIMENT-SETUP.md). `avaliacao/` é
ignorado pelo Git. **Nunca use imagens dos alunos cadastrados.**

---

## Problemas conhecidos

### `ImportError: Keras cannot be imported`

O DeepFace liga `TF_USE_LEGACY_KERAS=1`, e desde o TensorFlow 2.16 o
`tf.keras` legado vive num pacote separado. O `requirements.txt` fixa
`tf-keras==2.21.0`; se instalou antes, rode `pip install tf-keras==2.21.0`.

### `You must install torch ... to use face anti spoofing`

O anti-spoofing roda em PyTorch. Já está no `requirements.txt`
(`torch==2.14.0`).

### Cadastro recusado com "apresentação de foto", mas você está ao vivo

Falso positivo do MiniFASNet. Na ordem de eficácia:

1. **Iluminação:** luz forte atrás de você é a causa mais comum.
2. **Resolução:** aumente `CAMERA_LARGURA` e `CAMERA_ALTURA`.
3. **Aproxime o rosto** da câmera.
4. `FACE_DETECTOR=retinaface` recorta melhor que o Haar, mas é mais lento.

Mantenha `FACE_ANTI_SPOOFING=true`. O número no log é a confiança da classe
escolhida: "96%" num frame recusado significa 96% de confiança de fraude.

### A câmera da CLI demora para abrir

No Windows, o Media Foundation leva ~27 s para abrir e ajustar a resolução; o
DirectShow, ~0,8 s. `CAMERA_BACKEND=auto` já escolhe DirectShow. Se a câmera
não funcionar com ele, use `CAMERA_BACKEND=msmf`.

### Mensagens do TensorFlow no start

`oneDNN custom operations are on...` é informativo. Para silenciar:
`$env:TF_ENABLE_ONEDNN_OPTS = "0"` e `$env:TF_CPP_MIN_LOG_LEVEL = "2"`.

### A primeira execução parece travada

O DeepFace está baixando os pesos do Facenet512 (~90 MB) e, no primeiro
cadastro, os do anti-spoofing (~4 MB).

---

## Dados sensíveis

`*.db`, `/fotos/`, `/storage/`, `.env`, `/models/*.task` e os ambientes
virtuais estão no `.gitignore`. Política completa em
[`docs/lgpd.md`](docs/lgpd.md).

O banco SQLite do protótipo, que ligava o nome real de uma pessoa a 39
registros de presença, foi removido de todo o histórico do Git em 2026-09-07.
Decisão e risco residual em
[`ADR-003`](docs/adr/ADR-003-limpeza-do-historico.md).

```bash
git rev-list --all --objects | grep escola.db   # não deve retornar nada
```
