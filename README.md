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

```bat
python cadastro.py
```

## Uso

1. Escolha `1` para cadastrar um aluno.
2. Digite nome e ID/matrícula numérica.
3. Posicione apenas um rosto na câmera.
4. Pressione ESPAÇO para capturar.
5. Escolha `2` para iniciar o reconhecimento.
6. Quando o aluno for reconhecido, pressione ENTER para registrar a presença.
7. ESC fecha a câmera.

A pasta `fotos` é criada automaticamente.

## Observações

- A câmera precisa estar disponível para o computador.
- Na primeira execução, o DeepFace pode baixar os modelos e demorar.
- O banco `escola.db` é local e foi mantido separado do arquivo original.

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

## Estratégia de transição (estado atual)

A Fase 1 entregou a infraestrutura PostgreSQL. O `cadastro.py` **ainda grava
em SQLite** — a troca da camada de aplicação é o primeiro item da Fase 2.

Enquanto as duas persistências coexistirem:

- executar `python cadastro.py` grava em `escola.db`, **não** no PostgreSQL;
- para sincronizar, reexecute o ETL (é idempotente);
- o PostgreSQL é a fonte de verdade a partir da Fase 2.

## Dados sensíveis

`escola.db`, `fotos/`, `storage/` e `.env` estão no `.gitignore` e não devem
ser versionados. O `escola.db` foi removido do índice do Git, mas **ainda
existe no histórico** — a limpeza do histórico depende de decisão explícita
do responsável (ver `REFACTORING_PLAN.md` §10).
