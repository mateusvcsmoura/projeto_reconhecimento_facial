# Sistema de Reconhecimento Facial para Controle de Presença

Projeto acadêmico da disciplina de IA da Fatec, não um TCC. Aplicação CLI que
cadastra referências faciais e apoia o registro de presença após confirmação
do operador. PostgreSQL e arquitetura em camadas. O registro do estado atual,
das fontes, verificações e limitações das tarefas 001–004 está em
[`docs/ESTADO-ATUAL-E-EVIDENCIAS.md`](docs/ESTADO-ATUAL-E-EVIDENCIAS.md). Os
812 testes unitários são o resultado registrado na tarefa 004 em 13/10/2026;
a suíte completa mais recente registrada continua sendo histórica (597 testes
na Etapa 4).

| | |
|---|---|
| **Arquitetura** | [`ARCHITECTURE.md`](ARCHITECTURE.md) — diagramas e estrutura |
| **Decisões** | [`docs/adr/`](docs/adr/) — quatro ADRs com alternativas descartadas |
| **Dados pessoais** | [`docs/lgpd.md`](docs/lgpd.md) — o que é tratado, por quê e por quanto tempo |
| **Apresentação** | [`docs/apresentacao.md`](docs/apresentacao.md) — roteiro de demonstração |
| **Estado e evidências** | [`docs/ESTADO-ATUAL-E-EVIDENCIAS.md`](docs/ESTADO-ATUAL-E-EVIDENCIAS.md) — implementação, fontes, testes e limites |
| **Como chegou aqui** | [`REFACTORING_PLAN.md`](REFACTORING_PLAN.md) e [`docs/baseline-arquitetura.md`](docs/baseline-arquitetura.md) |

---

## Requisitos

- **Python 3.12 ou 3.13.** A faixa é estreita porque duas dependências a
  apertam pelos dois lados: o TensorFlow publica wheels até 3.13, e o
  `numpy==2.5.3` só a partir de 3.12.
- **Docker** (ou um PostgreSQL 16+ local).
- **Webcam**, para cadastro e reconhecimento.

---

## Instalação

```powershell
# 1. Configuração — o .env real nunca vai para o Git
copy .env.example .env
#    edite POSTGRES_PASSWORD e as duas URLs

# 2. Banco
docker compose up -d

# 3. Dependências
py -3.12 -m venv .venv-app
.venv-app\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Schema — a aplicação NUNCA cria tabelas, só migrations
alembic upgrade head

# 5. Banco de teste (opcional, para rodar a suíte)
docker exec escola_postgres psql -U escola -d postgres `
  -c "CREATE DATABASE escola_test OWNER escola;"
```

A instalação baixa TensorFlow e PyTorch: ~500 MB e alguns minutos.

O container publica na porta **5433** por padrão, para não colidir com um
PostgreSQL nativo na 5432.

---

## Executar

```powershell
python -m src.main
```

```text
1 - Cadastrar aluno
2 - Reconhecer aluno
3 - Listar alunos
4 - Presencas de hoje
5 - Excluir aluno e seus dados
6 - Sair
```

**Cadastrar (1)** — informe nome e matrícula, leia o termo de consentimento
e confirme. **Sem o aceite a câmera nem liga.** Posicione apenas um rosto e
pressione ESPAÇO; ESC cancela.

Com `FACE_QUALITY_ENABLED=true`, dimensão, iluminação e nitidez são
checadas após a detecção. Se a captura for recusada, ajuste o enquadramento
e capture de novo; nome, matrícula e consentimento não são solicitados
novamente. ESC cancela sem persistir a tentativa recusada.

**Reconhecer (2), modo padrão** — o overlay mostra o nome e um indicador
derivado da distância ao limiar, apresentado em porcentagem. Esse valor **não
é probabilidade nem foi calibrado**. Abaixo de 40% avisa "confiança baixa"
— vale conferir antes de registrar. Uma recusa de qualidade mostra uma
orientação amarela e remove o candidato anterior; ENTER nesse ciclo não
registra presença. ENTER registra uma presença reconhecida, ESC sai.

Com `FACE_TEMPORAL_ENABLED=true`, ENTER só fica habilitado após três
identificações consecutivas da mesma pessoa, feitas nos ciclos de comparação
(um a cada oito frames), dentro de uma janela de 5 s. A observação mais
recente precisa ter até 2 s. Ao pressionar ENTER, o sistema lê outro frame e
faz uma identificação nova; só registra se ela ainda reconhecer a mesma
pessoa. Desconhecido, troca de identidade, qualidade insuficiente e expiração
interrompem a sequência. Uma presença registrada ou já existente consome a
confirmação. Isso pode adicionar uma inferência no ENTER elegível.

Com `FACE_AMBIGUITY_ENABLED=true`, o matcher também compara as duas menores
distâncias de **identidades distintas**, depois de verificar se a melhor está
no limiar `FACE_THRESHOLD`. A segunda identidade conta mesmo se sua distância
ficar acima do limiar. Margem zero recusa apenas empates exatos calculados;
uma margem positiva recusa gaps menores que o valor configurado, e igualdade
positiva com a margem é aceita. Não há margem calibrada ou recomendada. Uma
recusa mostra orientação amarela e, no modo temporal, limpa a sequência.
Desconhecido significa que ninguém passou pelo limiar; múltiplos rostos são
uma falha de captura distinta; ambiguidade significa um rosto com identidades
candidatas próximas. A política pode aumentar recusas, e um gap grande não
garante que a identidade esteja correta. Com a flag desligada, inclusive o
desempate pela primeira linha continua como antes.

As observações de frames consecutivos são correlacionadas: consistência
temporal verifica o fluxo de decisão, mas não comprova melhora biométrica e
pode repetir uma identificação errada. O marco de tempo ocorre antes da
leitura da câmera; buffers do dispositivo podem manter frames antigos. O modo
não rastreia a pessoa continuamente nem elimina a latência da câmera.

**Listar (3)** — matrícula, nome e situação. Alunos marcados como *sem
embedding* existem no cadastro mas **não serão reconhecidos**; rode o
backfill antes da aula.

**Presenças de hoje (4)** — horário de chegada, matrícula e nome.

**Excluir (5)** — remove cadastro, imagem, embedding e presenças. Mostra
quem será apagado e pede confirmação.

Na primeira execução o modelo é carregado **antes** de qualquer câmera
abrir, com aviso na tela: os pesos do DeepFace são baixados nesse momento e
isso demora. Sem esse pré-aquecimento, a espera aconteceria com o aluno já
parado na frente da câmera.

---

## Configuração

Tudo vem do `.env`. `DATABASE_URL` não tem default: a aplicação falha no
boot se ela faltar, em vez de apontar silenciosamente para o banco errado.

| Variável | Padrão | Para quê |
|---|---|---|
| `DATABASE_URL` | — | **Obrigatória** |
| `TEST_DATABASE_URL` | — | Banco da suíte; precisa ser diferente |
| `APP_TIMEZONE` | `America/Sao_Paulo` | Define o "dia" da presença |
| `LOG_LEVEL` | `INFO` | |
| `CAMERA_INDEX` | `0` | |
| `CAMERA_LARGURA` / `CAMERA_ALTURA` | `1280` / `720` | Recorte de rosto maior melhora embedding e anti-spoofing |
| `CAMERA_BACKEND` | `auto` | DirectShow no Windows — ver *Problemas conhecidos* |
| `FACE_MODEL` | `Facenet512` | Trocar exige backfill |
| `FACE_DETECTOR` | `opencv` | |
| `FACE_THRESHOLD` | `0.30` | Ainda não calibrado — [ADR-004](docs/adr/ADR-004-limiar-de-reconhecimento.md) |
| `FACE_ANTI_SPOOFING` | `true` | Recusa foto impressa e tela |
| `FACE_QUALITY_ENABLED` | `false` | Ativa checagens heurísticas de captura; opt-in |
| `FACE_QUALITY_MIN_FACE_PX` | `80` | Menor dimensão informada pelo detector, em pixels |
| `FACE_QUALITY_MIN_BRIGHTNESS` / `FACE_QUALITY_MAX_BRIGHTNESS` | `40` / `215` | Faixa fechada da luminosidade média, de 0 a 255 |
| `FACE_QUALITY_MIN_SHARPNESS` | `100` | Variância mínima do Laplaciano discreto |
| `FACE_TEMPORAL_ENABLED` | `false` | Exige sequência consistente antes de ENTER; opt-in |
| `FACE_TEMPORAL_MIN_OBSERVATIONS` | `3` | Identificações consecutivas (não frames exibidos) |
| `FACE_TEMPORAL_WINDOW_SECONDS` | `5.0` | Janela máxima das observações |
| `FACE_TEMPORAL_MAX_AGE_SECONDS` | `2.0` | Idade máxima da observação mais recente |
| `FACE_AMBIGUITY_ENABLED` | `false` | Opt-in da rejeição entre identidades próximas |
| `FACE_AMBIGUITY_MIN_MARGIN` | `None` | Obrigatória ao ativar; diferença mínima `d2 - d1`, finita entre 0 e 2 |
| `STORAGE_DIR` | `./storage/faces` | Fora do Git |
| `RETENCAO_PRESENCAS_DIAS` | `1825` | 5 anos; `0` desliga o expurgo |

Os limites de qualidade são heurísticas iniciais, não calibradas com rostos.
Com a flag desligada, a aceitação anterior continua como baseline; a flag
não altera `FACE_THRESHOLD` nem o anti-spoofing. Testes com imagens
sintéticas demonstram apenas comportamento funcional, não acurácia facial.
Os limites temporais também são parâmetros iniciais de engenharia, sem
calibração biométrica. A flag temporal não muda o limiar, a qualidade de
captura ou o anti-spoofing; esses controles podem ser habilitados de forma
independente. A política de ambiguidade também é independente e não altera
o limiar ou o anti-spoofing. Ao ativá-la, escolha a margem explicitamente;
`0.0` significa rejeitar somente empates exatos, não uma margem recomendada.
Nenhum teste sintético calibra valores nem mede desempenho biométrico.

---

## Benchmark de matching

O benchmark de engenharia usa apenas embeddings sintéticos de 512 dimensões.
Compara o matcher vetorizado com um laço Python que chama `NumPy dot` por
embedding e valida as decisões antes de cronometrar. O protocolo padrão usa
galerias de 10, 50, 200 e 1000 IDs, seed 1234 e limiar local 0.30; os cenários
de referência, ortogonalidade e empate são artificiais.

```powershell
python -m scripts.benchmark_matcher
python -m scripts.benchmark_matcher --saida-json resultado.json
```

O primeiro comando mostra latência por chamada, montagem da matriz e picos
observados por `tracemalloc`; o segundo também grava um JSON agregado em um
arquivo novo. `tracemalloc` não mede RSS ou toda alocação nativa, e o payload
dos arrays não é a memória total do processo. O laço de referência não
representa `DeepFace.verify()` nem inferência facial. Nenhuma dessas medições
avalia acurácia biométrica, calibra margens ou compara com `pgvector`.

Os resultados atuais e os três artefatos reproduzíveis estão em
[`tasks/004-benchmark-matching/RESULTADO.md`](tasks/004-benchmark-matching/RESULTADO.md)
e [`tasks/004-benchmark-matching/evidencias/`](tasks/004-benchmark-matching/evidencias/).

---

## Operação

### Migrations

```bash
alembic upgrade head            # aplica
alembic downgrade -1            # desfaz a última
alembic check                   # acusa divergência entre modelos e banco
alembic revision --autogenerate -m "descricao"
```

Toda revisão implementa `downgrade()`. O autogenerate é ponto de partida: a
revisão gerada deve ser **revisada à mão** — ele não emite `CHECK` nem
`IDENTITY` de forma confiável.

### Trocar de modelo de reconhecimento

Vetores de modelos diferentes **não são comparáveis**. O modelo fica gravado
junto do vetor, e uma divergência levanta erro em vez de identificar a
pessoa errada em silêncio.

Depois de mudar `FACE_MODEL`, recalcule:

```bash
python -m scripts.backfill_embeddings            # simula
python -m scripts.backfill_embeddings --apply    # efetiva
```

O mesmo script preenche embeddings de alunos cadastrados antes da Fase 5.

### Retenção de presenças

```bash
python -m scripts.expurgar_presencas            # simula
python -m scripts.expurgar_presencas --apply    # efetiva
```

Feito para rodar agendado. Não requer câmera nem DeepFace. A retenção vale
para o histórico de presença, nunca para o cadastro do aluno.

### Menor privilégio no banco

A aplicação não deve conectar com o dono do banco.

```bash
psql -U escola -d escola \
     -v senha="'SENHA_DA_APLICACAO'" \
     -f scripts/sql/criar_usuario_aplicacao.sql
```

Depois aponte o `DATABASE_URL` da aplicação para `escola_app`, e mantenha o
usuário dono apenas para `alembic upgrade`. O papel executa somente
`SELECT`, `INSERT`, `UPDATE` e `DELETE`; toda tentativa de alterar o schema
é recusada pelo PostgreSQL.

### Importar um banco SQLite legado

```bash
python -m scripts.import_legacy_sqlite --sqlite caminho/escola.db
python -m scripts.import_legacy_sqlite --sqlite caminho/escola.db --apply
```

Abre a origem em modo somente leitura e nunca a altera. Roda em transação
única, é idempotente e grava um relatório JSON em `storage/etl/` com **toda**
linha que não entrou e o motivo.

Aceita datas em `dd/mm/aaaa HH:MM:SS` e `aaaa-mm-dd HH:MM:SS`. Qualquer
outro formato é **rejeitado e relatado** — nunca adivinhado.

---

## Desenvolvimento

```bash
pip install -r requirements-dev.txt

pytest tests/unit                       # unitários, sem PostgreSQL
pytest                                   # suíte completa; integração usa PostgreSQL de teste
pytest --cov=src --cov-report=term       # com cobertura
ruff check .                             # lint
mypy                                     # tipos
```

`requirements-dev.txt` **não** inclui `opencv-python` nem `deepface`: a
suíte inteira roda sem eles, usando dublês de módulo injetados em
`sys.modules`. Se algum dia um teste passar a exigir OpenCV ou TensorFlow,
ele quebra — e essa quebra é o aviso de que uma fronteira vazou.

```text
tests/
├── unit/          domínio, casos de uso, CLI, adaptadores (com dublês)
├── integration/   PostgreSQL real: schema, constraints, repositories, ETL
└── features/      24 cenários BDD em Gherkin (pytest-bdd)
```

Os testes de integração usam `TEST_DATABASE_URL`, que precisa apontar para
um banco **diferente** do de desenvolvimento: a suíte cria e destrói o
schema. Nenhum teste lê dado real — os legados de teste são sintéticos.

### Avaliação do modelo (≠ teste de software)

Teste de software verifica se o pipeline faz o que promete; avaliação de
modelo mede se o modelo **acerta**.

```bash
# estrutura + divisão treino/validação/teste por identidade (sem modelo)
python -m scripts.evaluate_model --dataset avaliacao/datasets/<nome> --validar-divisao

# exploratório: FAR, FRR, EER, AUC sobre todos os pares (exige DeepFace)
python -m scripts.evaluate_model --dataset avaliacao/datasets/<nome>

# Etapa 1: calibração supervisionada do limiar (DeepFace + requirements-experimentos.txt)
python -m scripts.calibrar_limiar --dataset avaliacao/datasets/lfw
```

Espera um diretório por pessoa, com 2+ imagens cada, e conta toda imagem
rejeitada por motivo. O modo exploratório sugere limiar e mede o erro sobre
os **mesmos** pares — não serve para calibrar. A calibração divide por
identidade, escolhe o limiar na validação e abre o teste uma única vez,
comparando-o ao `FACE_THRESHOLD` atual: resultado medido em
[`docs/ML-ETAPA-1-RESULTADO.md`](docs/ML-ETAPA-1-RESULTADO.md). Ela **não**
altera o `FACE_THRESHOLD`. Estrutura, fontes de dados permitidas e
descarte: [`docs/ML-EXPERIMENT-SETUP.md`](docs/ML-EXPERIMENT-SETUP.md).
`avaliacao/` é ignorado pelo Git; **nunca use imagens dos alunos cadastrados.**

A matemática vive em `scripts/metricas.py` e é coberta por testes que
rodam sem o modelo — um erro de cálculo ali levaria a calibrar o
`FACE_THRESHOLD` no valor errado.

### CI

`.github/workflows/ci.yml` roda a cada push e PR: lint, tipos, migrations
(sobem e descem), `alembic check`, testes com piso de 80% de cobertura, e
uma verificação de que nenhum arquivo sensível foi versionado.

---

## Problemas conhecidos

### `ImportError: Keras cannot be imported`

O DeepFace liga `TF_USE_LEGACY_KERAS=1`. A partir do TensorFlow 2.16 o Keras
3 virou o padrão, e o `tf.keras` legado passou a viver num pacote separado.
O `requirements.txt` já fixa `tf-keras==2.21.0`. Se instalou antes disso:

```powershell
pip install tf-keras==2.21.0
```

### `You must install torch ... to use face anti spoofing`

O anti-spoofing roda em PyTorch, não em TensorFlow. Já está no
`requirements.txt` (`torch==2.14.0`, ~118 MB).

### Cadastro recusado com "apresentação de foto" — mas você está ao vivo

Falso positivo do modelo MiniFASNet, não erro de configuração. Na ordem de
eficácia:

1. **Iluminação.** Luz forte atrás de você — janela, luminária — é a causa
   mais comum. Vire-se de modo que a luz venha de frente.
2. **Resolução.** Aumente `CAMERA_LARGURA` e `CAMERA_ALTURA`; a aplicação
   avisa em log se a câmera não atender ao pedido.
3. **Aproxime o rosto** da câmera.
4. `FACE_DETECTOR=retinaface` recorta melhor que o Haar. É mais lento.
5. Mantenha `FACE_ANTI_SPOOFING=true`; desativá-lo remove a proteção contra
   foto impressa e tela. A qualidade de captura é uma checagem separada.

O número no log é a confiança da classificação escolhida, não a
probabilidade de ser real: "96%" com o frame recusado significa *96% de
confiança de que é uma fraude*.

### A câmera demora muito para abrir

Era o backend. No Windows o OpenCV usa Media Foundation por padrão, lento
para abrir e ainda mais lento para aceitar mudança de resolução:

| Backend | Abrir | Ajustar resolução | Total |
|---|---:|---:|---:|
| Media Foundation (padrão do OpenCV) | 9,9 s | 17,8 s | **27,0 s** |
| DirectShow | 0,3 s | 0,5 s | **0,8 s** |

`CAMERA_BACKEND=auto` já escolhe DirectShow no Windows. Se a sua câmera não
funcionar com ele, `CAMERA_BACKEND=msmf` volta ao anterior.

### Mensagens do TensorFlow no start

```text
oneDNN custom operations are on...
All log messages before absl::InitializeLog() is called are written to STDERR
```

São informativas, não erros. Para silenciá-las:

```powershell
$env:TF_ENABLE_ONEDNN_OPTS = "0"
$env:TF_CPP_MIN_LOG_LEVEL = "2"
```

### A primeira execução parece travada

Não está: o DeepFace baixa os pesos do Facenet512 (~90 MB) e, no primeiro
cadastro, os do anti-spoofing (~4 MB).

---

## Dados sensíveis

`*.db`, `/fotos/`, `/storage/`, `.env` e os ambientes virtuais estão no
`.gitignore`. Política completa em [`docs/lgpd.md`](docs/lgpd.md).

O banco SQLite legado — que continha o nome real de uma pessoa ligado a 39
registros de presença — foi removido de todo o histórico do Git em
2026-09-07. Decisão e risco residual em
[`ADR-003`](docs/adr/ADR-003-limpeza-do-historico.md).

```bash
git rev-list --all --objects | grep escola.db   # não deve retornar nada
```
