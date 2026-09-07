# Sistema de Reconhecimento Facial

## Instalação

Requer **Python 3.12 ou 3.13** em ambiente virtual.

A faixa e estreita porque duas dependencias a apertam pelos dois lados:
o TensorFlow (via DeepFace) publica wheels ate 3.13, e o `numpy==2.5.3`
so tem wheels a partir de 3.12.

### Windows

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Executar

Antes do primeiro uso, suba o banco e aplique as migrations (ver a seção
*Banco de dados*, abaixo).

```bat
python -m src.main
```

## Uso

```text
1 - Cadastrar aluno
2 - Reconhecer aluno
3 - Listar alunos
4 - Presencas de hoje
5 - Excluir aluno e seus dados
6 - Sair
```

**Cadastrar (1):** informe nome e matrícula, leia o termo de consentimento e
confirme — **sem o aceite a câmera nem liga**. Posicione apenas um rosto e
pressione ESPAÇO. ESC cancela.

**Reconhecer (2):** o overlay mostra o nome e a **confiança em porcentagem**.
Abaixo de 40% ele avisa "confiança baixa" — vale conferir antes de registrar.
ENTER registra a presença, ESC sai.

**Listar (3):** mostra matrícula, nome e situação. Alunos marcados como *sem
embedding* existem no cadastro mas **não serão reconhecidos** — rode o
backfill antes da aula.

**Presenças de hoje (4):** horário de chegada, matrícula e nome.

**Excluir (5):** remove cadastro, imagem, embedding e presenças. Pede
confirmação e mostra quem será apagado antes.

Na primeira execução o modelo é carregado **antes** de qualquer câmera abrir,
com aviso na tela — os pesos do DeepFace são baixados nesse momento e isso
demora. Sem esse pré-aquecimento, a espera aconteceria com o aluno já parado
na frente da câmera.

As imagens de referência vão para `STORAGE_DIR` (padrão `./storage/faces`),
que é criado na primeira gravação e fica fora do Git.

## Observações

- A câmera precisa estar disponível para o computador.
- Na primeira execução, o DeepFace pode baixar os modelos e demorar.
- A matrícula é validada antes de a câmera ser acionada: matrícula duplicada
  ou nome vazio falham de imediato, sem pedir o rosto do aluno.
- O anti-spoofing recusa foto impressa e tela de celular. Se o cadastro
  falhar com "apresentação detectada", é a pessoa real que precisa estar
  na frente da câmera.
- Toda mensagem de erro diz **o que fazer**, não apenas o que houve. "Modelo
  indisponível" vem acompanhado de "verifique a instalação do DeepFace e a
  conexão".
- A confiança exibida **não é probabilidade**: é uma leitura linear de quão
  longe do limiar a decisão ficou. Serve para o operador perceber um match
  fraco. Transformá-la em probabilidade real exigiria a calibração descrita
  em *Avaliação do modelo*.

---

# Banco de dados — PostgreSQL (Fase 1)

O banco oficial do projeto é PostgreSQL. Decisão e justificativa em
[`docs/adr/ADR-001-migracao-postgresql.md`](docs/adr/ADR-001-migracao-postgresql.md).

## Setup

```bash
# 1. Configuração (o .env real nunca vai para o Git)
cp .env.example .env
#    edite POSTGRES_PASSWORD e as duas URLs

# 2. Banco de desenvolvimento
docker compose up -d

# 3. Dependências
python -m venv .venv
.venv/Scripts/activate          # Windows
pip install -r requirements.txt

# 4. Schema (a aplicação NUNCA cria tabelas — só migrations)
alembic upgrade head
```

A porta publicada é **5433** por padrão, para não colidir com uma instalação
nativa do PostgreSQL na 5432. Ajuste `POSTGRES_PORT` no `.env` se preferir.

## Migrations

```bash
alembic upgrade head            # aplica
alembic downgrade -1            # desfaz a última
alembic downgrade base          # zera o schema
alembic check                   # acusa divergência entre modelos e banco
alembic revision --autogenerate -m "descricao"
```

Toda revisão implementa `downgrade()`. O autogenerate é ponto de partida:
a revisão gerada deve ser **revisada à mão** (ele não emite `CHECK` nem
`IDENTITY` de forma confiável).

## Importar os dados do SQLite legado

```bash
# simulação — não grava nada
python -m scripts.import_legacy_sqlite --sqlite escola.db

# execução real
python -m scripts.import_legacy_sqlite --sqlite escola.db --apply
```

O script abre o SQLite em modo somente leitura e nunca o altera. Roda em
transação única, é idempotente (reexecutar não duplica) e grava um relatório
JSON em `storage/etl/` com **toda** linha que não entrou e o motivo.

Conversão de data: aceita `dd/mm/aaaa HH:MM:SS` (formato legado) e
`aaaa-mm-dd HH:MM:SS` (formato atual), localizando em `APP_TIMEZONE`.
Qualquer outro formato é **rejeitado e relatado** — nunca adivinhado.

## Testes e qualidade

```bash
pip install -r requirements-dev.txt

pytest                                   # 216 testes
pytest --cov=src --cov-report=term       # com cobertura
ruff check .                             # lint
mypy                                     # tipos
```

`requirements-dev.txt` **não** inclui `opencv-python` nem `deepface`: a suíte
inteira roda sem eles, usando dublês de módulo injetados em `sys.modules`. Se
algum dia um teste passar a exigir OpenCV ou TensorFlow, ele quebra — e essa
quebra é o aviso de que uma fronteira vazou.

Estrutura:

```text
tests/
├── unit/          domínio, casos de uso, CLI, adaptadores (com dublês)
├── integration/   PostgreSQL real: schema, constraints, repositories, ETL
└── features/      cenários BDD em Gherkin (pytest-bdd)
```

### BDD

Os `.feature` estão em português e são executados por `pytest-bdd` — não são
documentação decorativa, falham de verdade quando o comportamento muda.

```bash
pytest tests/features -v
```

Cobrem os cenários obrigatórios de `instructions/03-qa.md` §6: cadastro,
reconhecimento, presença e integridade do banco.

### Avaliação do modelo (≠ teste de software)

Teste de software verifica se o pipeline faz o que promete; avaliação de
modelo mede se o modelo **acerta**. São coisas diferentes.

```bash
python -m scripts.evaluate_model --dataset ./avaliacao/lfw-subset
```

Reporta FAR, FRR, EER, AUC e sugere um limiar por teto de FAR. Requer Python
3.12/3.13 com DeepFace. **Nunca versione o conjunto de imagens.**

A matemática das métricas vive em `scripts/metricas.py` e é coberta por 16
testes que rodam sem o modelo — um erro de cálculo ali levaria a calibrar o
`FACE_THRESHOLD` no valor errado.

### CI

`.github/workflows/ci.yml` roda a cada push e PR: lint, tipos, migrations
(sobem e descem), `alembic check`, testes com piso de 80% de cobertura, e uma
verificação de que nenhum arquivo sensível foi versionado.

Os testes de integração usam `TEST_DATABASE_URL`, que precisa apontar para um
banco **diferente** do de desenvolvimento: a suíte cria e destrói o schema.

```bash
docker exec escola_postgres psql -U escola -d postgres \
  -c "CREATE DATABASE escola_test OWNER escola;"
```

Nenhum teste lê o `escola.db` real — os dados legados de teste são sintéticos,
para que dado pessoal ou biométrico não entre na suíte nem no Git.

## Arquitetura (Fase 2)

O protótipo monolítico `cadastro.py` foi removido. A aplicação agora é
executada por `python -m src.main` e está separada em camadas:

```text
Presentation   src/presentation/cli/    menu, prompts, janela de vídeo
      ↓
Application    src/application/         casos de uso
      ↓
Domain         src/domain/              entidades, contratos, erros
      ↓
Infrastructure src/infrastructure/      PostgreSQL, OpenCV, DeepFace, arquivos
```

As dependências apontam sempre para dentro. `src/main.py` é o único módulo
que conhece as implementações concretas e as injeta.

Invariantes verificadas por `grep` e pela suíte:

- `src/domain/` e `src/application/` não importam `cv2`, `deepface` nem
  `sqlalchemy`;
- apenas quatro módulos de infraestrutura/apresentação importam `cv2` ou
  `deepface`;
- nenhum `sqlite3` e nenhum `CREATE TABLE` na aplicação;
- `print()` só existe na camada de apresentação — diagnóstico usa `logging`.

O SQLite deixou de ser usado pela aplicação, e o `escola.db` legado foi
apagado — do disco e do histórico do Git (ver
[`docs/adr/ADR-003-limpeza-do-historico.md`](docs/adr/ADR-003-limpeza-do-historico.md)).
O script de ETL continua no projeto e funciona com qualquer `escola.db` que
venha a ser fornecido pelo caminho `--sqlite`.

## Reconhecimento por embeddings (Fase 4/5)

Decisão e medições em
[`docs/adr/ADR-002-armazenamento-de-embeddings.md`](docs/adr/ADR-002-armazenamento-de-embeddings.md).

O embedding facial é calculado **uma vez, no cadastro**, e gravado em
`alunos.embedding` (`BYTEA`, float32 little-endian, L2-normalizado). No
reconhecimento, o sistema faz **uma** inferência por ciclo e compara o vetor
contra todos os cadastrados com um produto matriz-vetor.

Antes: até `2N` inferências Facenet512 por ciclo, com N alunos.
Agora: uma, independente de N.

```bash
# custo real da comparação, por número de alunos
python -m scripts.benchmark_matcher
```

### Trocar de modelo

`FACE_MODEL` e `FACE_THRESHOLD` vêm do `.env`. Vetores de modelos diferentes
**não são comparáveis** — o modelo fica gravado junto do vetor, e uma
divergência levanta erro em vez de identificar a pessoa errada em silêncio.

Depois de mudar `FACE_MODEL`, recalcule os vetores:

```bash
python -m scripts.backfill_embeddings            # simula
python -m scripts.backfill_embeddings --apply    # efetiva
```

O mesmo script preenche os embeddings de alunos cadastrados antes desta
fase, a partir das imagens já armazenadas.

## Problemas conhecidos na instalação

### `ImportError: Keras cannot be imported`

O DeepFace 0.0.92 liga `TF_USE_LEGACY_KERAS=1`. A partir do TensorFlow 2.16 o
Keras 3 virou o padrão, e o `tf.keras` legado passou a viver num pacote
separado. O `requirements.txt` já fixa `tf-keras==2.21.0` por causa disso.

Se você instalou antes dessa correção:

```powershell
pip install tf-keras==2.21.0
```

### Mensagens do TensorFlow no start

```text
oneDNN custom operations are on. You may see slightly different numerical results...
All log messages before absl::InitializeLog() is called are written to STDERR
```

São informativas, não erros. Para silenciá-las:

```powershell
$env:TF_ENABLE_ONEDNN_OPTS = "0"
$env:TF_CPP_MIN_LOG_LEVEL = "2"
```

### Cadastro recusado com "apresentação de foto ou tela" — mas você está ao vivo

Falso positivo do modelo de anti-spoofing (MiniFASNet), não erro de
configuração. Na ordem de eficácia:

1. **Iluminação.** Luz forte atrás de você — janela, luminária — é a causa
   mais comum. Vire-se de modo que a luz venha de frente.
2. **Resolução.** O padrão do OpenCV costuma ser 640x480, que produz um
   recorte de rosto pequeno. Aumente `CAMERA_LARGURA` e `CAMERA_ALTURA` no
   `.env` (padrão já é 1280x720). A aplicação avisa em log se a câmera não
   atender ao pedido.
3. **Aproxime o rosto** da câmera.
4. **Trocar o detector**: `FACE_DETECTOR=retinaface` recorta o rosto melhor
   que o `opencv` (Haar), o que costuma ajudar o anti-spoofing. É mais
   lento.
5. **Último recurso**: `FACE_ANTI_SPOOFING=false`. Isso **remove** a
   proteção contra foto impressa — use só em desenvolvimento.

Sobre o número no log: ele é a confiança da classificação escolhida, não a
probabilidade de ser real. "96%" com o frame recusado significa *96% de
confiança de que é uma fraude*.

### A câmera demora muito para abrir

Era o backend. No Windows o OpenCV usa Media Foundation por padrão, que é
lento para abrir dispositivo e ainda mais lento para aceitar mudança de
resolução. Medido nesta máquina:

| Backend | Abrir | Ajustar resolução | Total |
|---|---:|---:|---:|
| Media Foundation (padrão do OpenCV) | 9,9 s | 17,8 s | **27,0 s** |
| DirectShow | 0,3 s | 0,5 s | **0,8 s** |

`CAMERA_BACKEND=auto` (o padrão) já escolhe DirectShow no Windows. Se por
algum motivo a sua câmera não funcionar com ele, `CAMERA_BACKEND=msmf`
volta ao comportamento anterior — ao custo desses 27 segundos.

### A janela da câmera não acompanha o redimensionamento

Corrigido: a janela usa `WINDOW_NORMAL` e o vídeo escala junto. Com o padrão
do OpenCV (`WINDOW_AUTOSIZE`), maximizar só aumentava a moldura.

O tamanho da janela **não** afeta o reconhecimento nem o anti-spoofing — a
análise roda sobre o frame da câmera, não sobre o que aparece na tela.

### A primeira execução parece travada

Não está: o DeepFace baixa os pesos do Facenet512 (~90 MB) na primeira vez.
A aplicação avisa antes de começar, e por isso o modelo é carregado **antes**
de qualquer câmera abrir.

## Segurança e dados pessoais (Fase 6)

Política completa em [`docs/lgpd.md`](docs/lgpd.md).

### Anti-spoofing

Ligado por padrão. Frames classificados como apresentação — foto impressa,
tela de celular — são recusados **no cadastro e no reconhecimento**. Sem
isso, um controle de presença por rosto é burlável com uma fotografia.

Desligue apenas em desenvolvimento (`FACE_ANTI_SPOOFING=false`); a aplicação
registra um aviso no boot quando isso acontece.

### Menor privilégio no banco

A aplicação não deve conectar com o dono do banco. Crie o usuário restrito:

```bash
psql -U escola -d escola      -v senha="'SENHA_DA_APLICACAO'"      -f scripts/sql/criar_usuario_aplicacao.sql
```

Depois aponte o `DATABASE_URL` da aplicação para `escola_app`, e mantenha o
usuário dono apenas para `alembic upgrade`.

O papel `escola_app` executa somente `SELECT`, `INSERT`, `UPDATE` e
`DELETE`. Verificado: toda tentativa de alterar o schema, ou de escrever na
tabela de controle do Alembic, é recusada pelo PostgreSQL.

### Exclusão e retenção

Opção 3 do menu remove o aluno, o embedding, a imagem e as presenças.

```bash
python -m scripts.expurgar_presencas            # simula
python -m scripts.expurgar_presencas --apply    # efetiva
```

`RETENCAO_PRESENCAS_DIAS` controla o prazo; `0` desliga.

## Dados sensíveis

`*.db`, `/fotos/`, `/storage/` e `.env` estão no `.gitignore` e não devem ser
versionados.

O `escola.db` legado — que continha o nome real de uma pessoa ligado a 39
registros de presença — foi **removido de todo o histórico do Git** com
`git filter-repo`, e apagado do disco. Decisão, alternativas e risco
residual em
[`docs/adr/ADR-003-limpeza-do-historico.md`](docs/adr/ADR-003-limpeza-do-historico.md).

Verificação:

```bash
git rev-list --all --objects | grep escola.db   # não deve retornar nada
```
