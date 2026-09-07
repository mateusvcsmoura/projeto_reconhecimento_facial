# ADR-001 — Migração de SQLite para PostgreSQL

- **Status:** aceito
- **Data:** 2026-09-07
- **Fase:** 1 (`REFACTORING_PLAN.md`)

---

## Problema

O protótipo persistia em SQLite, com o schema criado pela própria aplicação
no boot via `CREATE TABLE IF NOT EXISTS`. Isso produziu três defeitos
verificados no banco real (`escola.db`):

1. **Divergência silenciosa de schema.** `preparar_banco()` declarava
   `nome TEXT NOT NULL`, mas `escola.db` tinha a coluna sem `NOT NULL` —
   `CREATE TABLE IF NOT EXISTS` não altera tabela existente e não havia
   migrations.
2. **Regra de negócio quebrada.** `presencas.data_hora` era TEXT livre. As
   39 linhas existentes estavam em `dd/mm/aaaa HH:MM:SS`, formato que a
   função `date()` do SQLite não interpreta: `SELECT COUNT(*) FROM presencas
   WHERE date(data_hora) IS NULL` retornava **39 de 39**. O dedup "uma
   presença por dia" não enxergava nenhum registro histórico.
3. **Sem integridade referencial nem índices.** `PRAGMA foreign_key_list` e
   `PRAGMA index_list` vazios nas duas tabelas; `PRAGMA foreign_keys` nunca
   era ligado na conexão.

Some-se a isso: o arquivo `escola.db`, contendo nome real de pessoa ligado a
eventos biométricos, estava versionado no Git.

## Alternativas consideradas

### Banco

| Opção | A favor | Contra |
|---|---|---|
| Manter SQLite e corrigir os defeitos | Zero dependência nova | Não resolve concorrência nem controle de acesso; `CLAUDE.md` §4 define PostgreSQL como banco oficial |
| **PostgreSQL** | Constraints e tipos ricos (`TIMESTAMPTZ`, `IDENTITY`), integridade sempre ativa, controle de acesso por usuário | Exige um serviço rodando; novo pré-requisito de ambiente |

### Camada de acesso

| Opção | A favor | Contra |
|---|---|---|
| `psycopg` 3 puro + arquivos `.sql` numerados | Mínimo de dependências; SQL explícito | Exige um runner de migration caseiro — código sem valor didático |
| SQLAlchemy Core + Alembic | Sem "mágica" de ORM | Ainda exige mapear resultados à mão |
| **SQLAlchemy 2.0 ORM + Alembic** | Alembic opera sobre o metadata do SQLAlchemy; `CLAUDE.md` §2 aponta a ausência de ORM como lacuna | Dependência maior; risco de N+1 se usado sem atenção |
| Django ORM | Migrations excelentes | Traz um framework web inteiro para uma CLI |

### Modelagem do dia da presença

| Opção | Avaliação |
|---|---|
| Coluna gerada `(registrado_em AT TIME ZONE 'America/Sao_Paulo')::date` | **Impossível.** `AT TIME ZONE` com zona literal sobre `timestamptz` é `STABLE`, não `IMMUTABLE`; o PostgreSQL recusa em coluna gerada e em índice |
| Só `TIMESTAMPTZ` + dedup por `SELECT` prévio | Reproduz o defeito original: regra em código, sujeita a corrida |
| **`TIMESTAMPTZ` + coluna `DATE` própria + `UNIQUE(aluno_id, data_referencia)`** | A regra vira constraint do banco; o "dia" é decidido pela aplicação em `APP_TIMEZONE` |

## Decisão

1. **PostgreSQL 18** como banco oficial, provisionado por `docker-compose.yml`
   (porta 5433 por padrão, para não colidir com instalação nativa na 5432).
2. **SQLAlchemy 2.0 ORM + Alembic + psycopg 3** como camada de acesso e
   ferramenta de migrations. O ORM fica confinado a `src/infrastructure/`.
3. **Schema redesenhado**, não transportado:
   - `matricula` separada da chave primária (no SQLite, `id` acumulava PK +
     matrícula + `biometria_id`);
   - `biometria_id` eliminada — era cópia literal de `id`;
   - `foto_path` absoluto vira `foto_arquivo` relativo a `STORAGE_DIR`;
   - `data_hora TEXT` vira `registrado_em TIMESTAMPTZ` + `data_referencia DATE`;
   - `UNIQUE(aluno_id, data_referencia)`, FK com `ON DELETE CASCADE`,
     `CHECK` de nome/matrícula não vazios, índice em `data_referencia`;
   - chaves primárias como `GENERATED ALWAYS AS IDENTITY`.
4. **A aplicação nunca cria nem altera schema.** `alembic upgrade head` é
   comando explícito.
5. **`DATABASE_URL` só via ambiente**, validada por `pydantic-settings`; o
   boot falha se ausente.
6. **Dados legados migrados, não descartados**, por
   `scripts/import_legacy_sqlite.py` — dry-run por padrão, transação única,
   idempotente, com relatório JSON de tudo que não entrou.

## Justificativa

Cada defeito da seção "Problema" passa a ser impossível por construção, e
não por disciplina de quem escreve o código:

- divergência de schema → migrations versionadas + `alembic check` no CI;
- data em formato livre → `TIMESTAMPTZ` e `DATE` tipados;
- dedup furado e sujeito a corrida → `UNIQUE` + `ON CONFLICT DO NOTHING`;
- presença órfã → `FOREIGN KEY`, sempre ativa no PostgreSQL;
- varredura completa no dedup → índice implícito da constraint única.

Alembic e SQLAlchemy foram adotados juntos porque o primeiro opera sobre o
metadata do segundo: adotar um sem o outro custaria mais.

## Trade-offs aceitos

| Ganho | Custo |
|---|---|
| Schema reproduzível e versionado | Docker (ou PostgreSQL local) vira pré-requisito de desenvolvimento |
| Regra de negócio garantida pelo banco | As 39 marcações legadas do mesmo aluno no mesmo dia colapsam em 1 presença (as 38 restantes ficam registradas no relatório do ETL, e o `escola.db` de origem não é alterado) |
| Tipos ricos e integridade referencial | Duas dependências novas (SQLAlchemy, Alembic) + driver |
| Identidade interna estável | Os ids do SQLite não são preservados; a rastreabilidade passa por `matricula` |

## Consequências

- `cadastro.py` **ainda usa SQLite** ao fim desta fase. A troca da camada de
  aplicação é o primeiro item da Fase 2 — ver "Estratégia de transição" no
  README.
- Enquanto as duas persistências coexistirem, execuções do protótipo gravam
  em `escola.db` e não no PostgreSQL. O ETL é idempotente e pode ser
  reexecutado para sincronizar.
- `escola.db` foi removido do versionamento (`git rm --cached`), mas
  **continua presente no histórico do Git**. A limpeza do histórico exige
  decisão explícita do responsável — ver `REFACTORING_PLAN.md` §10.
