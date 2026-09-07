# Sistema de Reconhecimento Facial

## Instalação

Recomendado: Python 3.10 ou 3.11 em ambiente virtual.

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

1. Escolha `1` para cadastrar um aluno.
2. Digite o nome e a matrícula (aceita letras e números).
3. Posicione apenas um rosto na câmera.
4. Pressione ESPAÇO para capturar.
5. Escolha `2` para iniciar o reconhecimento.
6. Quando o aluno for reconhecido, pressione ENTER para registrar a presença.
7. ESC fecha a câmera.

As imagens de referência vão para `STORAGE_DIR` (padrão `./storage/faces`),
que é criado na primeira gravação e fica fora do Git.

## Observações

- A câmera precisa estar disponível para o computador.
- Na primeira execução, o DeepFace pode baixar os modelos e demorar.
- A matrícula é validada antes de a câmera ser acionada: matrícula duplicada
  ou nome vazio falham de imediato, sem pedir o rosto do aluno.

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

## Testes

```bash
pytest
```

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

O SQLite deixou de ser usado pela aplicação. `escola.db` permanece no disco
apenas como origem do ETL.

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

## Dados sensíveis

`escola.db`, `fotos/`, `storage/` e `.env` estão no `.gitignore` e não devem
ser versionados. O `escola.db` foi removido do índice do Git, mas **ainda
existe no histórico** — a limpeza do histórico depende de decisão explícita
do responsável (ver `REFACTORING_PLAN.md` §10).
