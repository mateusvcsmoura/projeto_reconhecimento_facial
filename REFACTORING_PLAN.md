# REFACTORING_PLAN.md

**Plano Oficial de Reestruturação**
Sistema de Reconhecimento Facial para Controle de Presença

| Campo | Valor |
|---|---|
| Papel emissor | Orquestrador Técnico |
| Data | 2026-09-07 |
| Commit base | `08116cf` — *feat: initial commit (before changes) \| raw project* |
| Documento de baseline | [`ARCHITECTURE.md`](ARCHITECTURE.md) (auditoria do estado atual, problemas P1–P14) |
| Status | **Plano para execução incremental — nenhuma alteração de código realizada** |

> Este documento é o plano. A auditoria detalhada do estado atual está em `ARCHITECTURE.md` e não é repetida aqui; as referências `P1`…`P14` apontam para a seção 18 daquele documento.

---

## 1. Objetivo

### Onde o projeto está

Um único arquivo, `cadastro.py` (364 linhas), concentra apresentação (CLI + janelas OpenCV), captura de câmera, inferência de rede neural (DeepFace/Facenet512), SQL bruto e regra de negócio. O banco é um SQLite versionado no Git contendo o nome real de uma pessoa e 39 eventos de presença. Não existem testes, migrations, configuração externa, logging, nem qualquer abstração entre o domínio e as bibliotecas de infraestrutura.

O sistema *funciona* como demonstração, mas hoje ele:

- **não roda com os dados que possui** — o único aluno cadastrado aponta para um caminho absoluto em outra máquina (`P3`), e o programa conclui *"Nenhuma foto de aluno está disponível."*;
- **tem a regra de negócio central quebrada** sobre os dados existentes — o dedup "uma presença por dia" não enxerga nenhum dos 39 registros legados, porque `date()` não interpreta o formato `dd/mm/aaaa` gravado por uma versão anterior (`P2`; verificado: 39/39 linhas retornam `NULL`);
- **não escala** — até `2N` inferências Facenet512 por ciclo de comparação (`P4`);
- **expõe dado biométrico** sem qualquer barreira, inclusive dentro do repositório Git (`P7`).

### Onde queremos chegar

Um sistema em camadas, pequeno e legível, no qual:

- PostgreSQL é o banco oficial, com schema versionado por migrations e constraints que expressam as regras de negócio;
- o domínio não importa `cv2`, `deepface` nem driver de banco;
- o reconhecimento facial é um *provider* substituível por trás de um contrato;
- embeddings de referência são calculados uma vez, no cadastro, e reutilizados;
- dado biométrico tem armazenamento, retenção e exclusão definidos;
- a lógica de negócio é testável sem webcam, sem GPU e sem PostgreSQL real;
- cada decisão arquitetural é justificável em uma apresentação acadêmica.

### O que explicitamente não queremos

Microserviços, mensageria, CQRS, event sourcing, Kubernetes, ou qualquer camada cuja única justificativa seja parecer sofisticada. O critério de aceitação de toda abstração proposta neste plano é: **ela resolve um problema concreto listado na seção 3?** Se não, ela não entra.

---

## 2. Baseline

### 2.1 Inventário de arquivos

```text
projeto_reconhecimento_facial/
├── cadastro.py          364 linhas — todo o sistema
├── escola.db            16 KB — SQLite, VERSIONADO NO GIT
├── fotos/               vazio
├── requirements.txt     3 dependências (1 órfã)
├── README.md            instruções de uso
├── ARCHITECTURE.md      auditoria do estado atual
├── CLAUDE.md            contrato do projeto
├── instructions/        4 agentes (orquestrador, arquiteto, dev, QA)
└── .gitignore           padrão Python — NÃO cobre escola.db nem fotos/
```

### 2.2 Dependências

| Pacote | Versão | Uso real |
|---|---|---|
| `opencv-python` | 4.13.0.92 | câmera, janelas, `imwrite`, `putText` |
| `deepface` | 0.0.92 | `extract_faces`, `verify` |
| `pyserial` | 3.5 | **nenhum** — dependência órfã (`P13`) |

Dependências transitivas relevantes e não declaradas: `tensorflow`, `numpy`, `retina-face`. O projeto não fixa o backend de ML — a instalação é não determinística.

### 2.3 Banco — esquema declarado no código (`cadastro.py:33-48`)

```sql
CREATE TABLE IF NOT EXISTS alunos (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    foto_path TEXT NOT NULL,
    biometria_id INTEGER
);
CREATE TABLE IF NOT EXISTS presencas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aluno_id INTEGER NOT NULL,
    data_hora TEXT NOT NULL
);
```

### 2.4 Banco — esquema realmente presente em `escola.db` (divergente)

```sql
CREATE TABLE alunos
   (id INTEGER PRIMARY KEY, nome TEXT, foto_path TEXT, biometria_id INTEGER);
CREATE TABLE presencas
   (id INTEGER PRIMARY KEY AUTOINCREMENT, aluno_id INTEGER, data_hora TEXT);
```

Nenhum `NOT NULL` foi aplicado. Causa: `CREATE TABLE IF NOT EXISTS` não altera tabela existente e não há migrations (`P1`). Isto é **evidência empírica** do problema, não hipótese.

Verificado por inspeção direta:

- `PRAGMA foreign_key_list` → vazio nas duas tabelas (sem integridade referencial);
- `PRAGMA index_list` → vazio nas duas tabelas (nenhum índice além dos PKs implícitos);
- `sqlite_sequence` → `('presencas', 39)`.

### 2.5 Dados existentes

| Tabela | Linhas | Observação |
|---|---|---|
| `alunos` | 1 | nome real de uma pessoa; `foto_path` absoluto para `%TEMP%` de outro usuário/máquina |
| `presencas` | 39 | todas do mesmo aluno, todas no mesmo dia, formato `dd/mm/aaaa HH:MM:SS` |

Fatos apurados:

- `SELECT COUNT(*) FROM presencas WHERE date(data_hora) IS NULL` → **39** (100% dos registros são invisíveis ao dedup);
- 39 presenças do mesmo aluno no mesmo dia — a regra "uma por dia" nunca foi efetivamente aplicada a esses dados;
- 0 presenças órfãs (por acaso, não por constraint);
- `foto_path` inutilizável neste ambiente e, à época, gravação de biometria em diretório temporário;
- `alunos.biometria_id` é uma cópia literal de `alunos.id` — coluna morta (`P13`);
- `fotos/` está vazia: nenhum cadastro foi feito pela versão atual do código.

### 2.6 Superfície de segurança atual

- `escola.db` está **rastreado pelo Git** (`git ls-files` confirma) e contém o nome real de uma pessoa vinculado a eventos biométricos;
- `.gitignore` existe mas **não** cobre `escola.db`, `fotos/` nem `.env`;
- fotos seriam gravadas como JPG em claro, nomeadas pela matrícula, sem controle de acesso;
- nenhuma credencial no código hoje — porque não há credencial nenhuma (SQLite local). Isso muda na Fase 1.

### 2.7 Mapa do pipeline de reconhecimento (código atual)

| Etapa | Onde está hoje | Situação |
|---|---|---|
| Camera | `cv2.VideoCapture(0)` — `cadastro.py:86`, `244` | índice hardcoded, duplicado em 2 funções |
| Frame | `camera.read()` — `:99`, `:259` | sem validação de resolução/qualidade |
| Detection | dentro de `DeepFace.extract_faces` (`:125`) e implícita em `DeepFace.verify` (`:273`) | detector `opencv` (Haar), hardcoded |
| Alignment | `align=True` (`:129`, `:279`) | resultado do cadastro é **descartado** (`P14`) |
| Embedding | interno ao `DeepFace.verify` | **nunca persistido**, recalculado sempre (`P4`) |
| Comparison | `DeepFace.verify` 1:1 em laço sobre N alunos (`:271-286`) | O(N) inferências; aceita o **primeiro** match, não o melhor |
| Identity | `verificacao.get("verified")` (`:282`) | threshold implícito da biblioteca, não configurável |
| Attendance | `registrar_presenca()` (`:176-211`) | `SELECT`-depois-`INSERT`, sujeito a corrida; dedup quebrado nos legados |

Etapas **inexistentes**: anti-spoofing/liveness, qualidade de imagem, ranking de candidatos, auditoria, tratamento de múltiplos rostos no reconhecimento.

### 2.8 Estado de QA

Zero testes. Zero infraestrutura de teste. Nenhuma função é testável sem webcam, exceto `preparar_banco()`. A regra de negócio (`registrar_presenca`) está soldada a `sqlite3` e a `print()`.

---

## 3. Problemas

Prioridade: 🔴 alta (bloqueia uso ou expõe dado) · 🟡 média (dívida estrutural) · 🟢 baixa (higiene).

| ID | Problema | Impacto | Evidência | Risco se não tratado | Prio |
|---|---|---|---|---|---|
| **A1** | ~~Dado pessoal versionado no Git~~ **RESOLVIDO** | Nome real de pessoa + 39 registros de presença, recuperáveis do histórico | `git ls-files` lista `escola.db`; tabela `alunos` com nome real | — | ✅ |
| **A2** | Schema é código executado no boot, sem versionamento | Ambientes divergem silenciosamente | `preparar_banco()` declara `NOT NULL`; `escola.db` não os tem (`P1`) | Toda futura alteração de schema tem o mesmo destino; ambiente irreprodutível | 🔴 |
| **A3** | Timestamp como TEXT livre; regra de negócio quebrada nos dados legados | A funcionalidade central (1 presença/dia) falha em silêncio | 39/39 linhas com `date(data_hora) IS NULL` (`P2`) | Registro oficial de presença incorreto e não detectável | 🔴 |
| **A4** | Dedup por `SELECT`-depois-`INSERT`, sem constraint | Condição de corrida; regra não garantida pelo banco | `cadastro.py:185-205` | Presenças duplicadas sob concorrência ou reentrada rápida | 🔴 |
| **A5** | Embeddings nunca persistidos; comparação O(N) com `verify()` | Até 2N inferências Facenet512 por ciclo; loop de vídeo congela | `cadastro.py:268-291` (`P4`, `P5`) | Sistema inviável acima de poucas dezenas de alunos | 🔴 |
| **A6** | `except Exception: continue` sem log no caminho crítico | Falha de modelo é indistinguível de "sem rosto" | `cadastro.py:288-291` (`P6`) | Sistema falha em silêncio; diagnóstico impossível | 🔴 |
| **A7** | Ausência de anti-spoofing | Presença burlável com foto impressa ou tela | `cadastro.py:125-130`, `273-280` (`P8`) | O sistema não cumpre a finalidade que declara | 🔴 |
| **A8** | Módulo único: UI + câmera + IA + SQL + regra acoplados | Nada é testável sem hardware; regressão concentrada | `cadastro.py` inteiro (`P9`) | Impede toda a evolução planejada | 🟡 |
| **A9** | Cobertura de testes = 0 | Nenhuma rede de segurança | projeto inteiro (`P10`) | A2 e A3 são exatamente o defeito que um teste trivial pegaria | 🟡 |
| **A10** | Sem FK, sem índice, sem unique | Presenças órfãs possíveis; varredura completa no dedup | `PRAGMA` vazios (`P11`) | Degradação linear e inconsistência de dados | 🟡 |
| **A11** | Caminho absoluto de foto persistido no banco | Banco não é portátil entre máquinas | `cadastro.py:73`,`160`; dado real quebrado (`P3`) | Backup/restauração inutiliza o reconhecimento | 🟡 |
| **A12** | Configuração hardcoded (modelo, detector, câmera, caminhos) | Impossível ajustar por ambiente | `cadastro.py:10-18` | Threshold e modelo não avaliáveis; sem separação dev/prod | 🟡 |
| **A13** | `print()` como único mecanismo de diagnóstico | Sem observabilidade, sem níveis, sem destino | 30+ ocorrências | Impossível auditar ou depurar execução real | 🟡 |
| **A14** | Foto de referência salva sem recorte; face alinhada descartada | Mais dado sensível armazenado; custo extra por comparação | `cadastro.py:125-136` (`P14`) | Volume biométrico desnecessário e acurácia mais variável | 🟡 |
| **A15** | Lista de alunos materializada uma vez ao entrar no modo | Cadastros novos invisíveis até reiniciar o modo | `cadastro.py:218-238` (`P12`) | Comportamento surpreendente para o operador | 🟢 |
| **A16** | `pyserial` órfão; `alunos.biometria_id` morto | Superfície e schema maiores que o necessário | `requirements.txt`; `cadastro.py:38`,`160` (`P13`) | Confunde quem lê o código; contraria CLAUDE.md §7.5 | 🟢 |
| **A17** | Recursos liberados sem `finally` | Câmera/janela vazam se houver exceção no laço | `cadastro.py:145-146`, `328-329` | Dispositivo travado exigindo reinício | 🟢 |
| **A18** | Aceita o **primeiro** match, não o melhor | Identidade errada quando há candidatos próximos | `cadastro.py:282-286` | Presença atribuída ao aluno errado | 🟡 |

---

## 4. Arquitetura alvo

### 4.1 Princípio

Quatro camadas, dependências apontando sempre para dentro. Nenhuma camada extra sem problema correspondente na seção 3.

```text
Presentation  (CLI, janela OpenCV, formatação)
     ↓
Application   (casos de uso, DTOs, orquestração)
     ↓
Domain        (entidades, regras, contratos/Protocols)
     ↓
Infrastructure (PostgreSQL, DeepFace, câmera, arquivos)
```

`Infrastructure` **implementa** contratos definidos em `Domain`; a inversão acontece por injeção na composição (`src/main.py`).

### 4.2 Árvore de diretórios alvo

```text
projeto_reconhecimento_facial/
├── src/
│   ├── main.py                          # composition root: monta e injeta dependências
│   │
│   ├── config/
│   │   ├── settings.py                  # pydantic-settings: lê .env, valida, tipa
│   │   └── logging.py                   # configuração do logging estruturado
│   │
│   ├── presentation/
│   │   └── cli/
│   │       ├── menu.py                  # laço do menu, roteamento de opções
│   │       ├── prompts.py               # coleta e validação de entrada do operador
│   │       └── viewer.py                # janela OpenCV: desenha overlay, lê teclas
│   │
│   ├── application/
│   │   ├── dto/
│   │   │   └── schemas.py               # DTOs de entrada/saída dos casos de uso
│   │   └── use_cases/
│   │       ├── cadastrar_aluno.py
│   │       ├── reconhecer_aluno.py
│   │       ├── registrar_presenca.py
│   │       ├── excluir_aluno.py         # exigência de LGPD (Fase 6)
│   │       └── listar_presencas.py
│   │
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── aluno.py                 # dataclass, sem dependência externa
│   │   │   ├── presenca.py
│   │   │   └── face_embedding.py        # vetor + modelo + dimensão
│   │   ├── repositories/
│   │   │   ├── aluno_repository.py      # Protocol
│   │   │   └── presenca_repository.py   # Protocol
│   │   ├── services/
│   │   │   ├── face_recognition_provider.py  # Protocol: detectar / gerar embedding
│   │   │   ├── camera_provider.py            # Protocol: frames
│   │   │   ├── image_storage.py              # Protocol: guardar/remover imagem
│   │   │   └── matcher.py                    # regra pura: escolhe melhor candidato
│   │   └── errors.py                    # exceções de domínio nomeadas
│   │
│   └── infrastructure/
│       ├── database/
│       │   ├── engine.py                # SQLAlchemy engine + session factory
│       │   └── models.py                # modelos ORM (tabelas)
│       ├── repositories/
│       │   ├── postgres_aluno_repository.py
│       │   └── postgres_presenca_repository.py
│       ├── face_recognition/
│       │   └── deepface_provider.py     # ÚNICO arquivo que importa deepface
│       ├── camera/
│       │   └── opencv_camera.py         # ÚNICO importador de cv2 para captura
│       └── storage/
│           └── local_image_storage.py
│
├── migrations/                          # Alembic
│   ├── env.py
│   └── versions/
│       └── 0001_schema_inicial.py
│
├── scripts/
│   ├── import_legacy_sqlite.py          # ETL pontual, executado uma vez
│   └── evaluate_model.py                # FAR/FRR/ROC — avaliação do modelo
│
├── tests/
│   ├── unit/                            # domínio e casos de uso, com fakes
│   ├── integration/                     # PostgreSQL real + migrations
│   └── features/                        # BDD/Gherkin (pytest-bdd)
│       ├── cadastro.feature
│       ├── reconhecimento.feature
│       └── presenca.feature
│
├── docs/
│   ├── adr/                             # decisões arquiteturais (ADR-001…)
│   ├── diagramas/
│   └── apresentacao.md
│
├── docker-compose.yml                   # PostgreSQL de desenvolvimento
├── alembic.ini
├── pyproject.toml                       # deps, pytest, ruff, mypy
├── .env.example                         # versionado; .env real nunca
├── ARCHITECTURE.md
├── REFACTORING_PLAN.md
├── CLAUDE.md
└── README.md
```

### 4.3 Contratos centrais

```python
# domain/services/face_recognition_provider.py
class FaceRecognitionProvider(Protocol):
    def detectar_face(self, imagem: Imagem) -> FaceDetectada: ...
    def gerar_embedding(self, face: FaceDetectada) -> FaceEmbedding: ...

# domain/repositories/aluno_repository.py
class AlunoRepository(Protocol):
    def obter_por_matricula(self, matricula: str) -> Aluno | None: ...
    def listar_com_embedding(self) -> list[Aluno]: ...
    def salvar(self, aluno: Aluno) -> Aluno: ...
    def excluir(self, aluno_id: int) -> None: ...

# domain/repositories/presenca_repository.py
class PresencaRepository(Protocol):
    def registrar_se_ausente(
        self, aluno_id: int, dia: date, momento: datetime
    ) -> bool: ...
```

`registrar_se_ausente` retorna `True` se inseriu, `False` se já existia — implementado por `INSERT ... ON CONFLICT DO NOTHING`, ou seja, a regra fica garantida **pelo banco**, não por um `SELECT` prévio (resolve A4).

### 4.4 O que este desenho deliberadamente **não** tem

| Não incluído | Por quê |
|---|---|
| API HTTP / FastAPI | Não há consumidor. A separação em camadas já permite adicioná-la depois sem tocar nos casos de uso. |
| Extensão `pgvector` | Com dezenas a poucas centenas de alunos, comparar 512 floats em NumPy custa microssegundos. Ver §9.3. |
| Autenticação/RBAC | Não há multiusuário. A Fase 6 trata do que é real: acesso ao banco, arquivos e secrets. |
| Camada de cache (Redis) | O único dado quente são os embeddings — cabem em memória. |
| Threads/async no reconhecimento | Resolver A5 (1 inferência por ciclo, não 2N) elimina a causa do congelamento; paralelizar antes disso seria mascarar. |

---

## 5. Roadmap

Nove fases, alinhadas a `CLAUDE.md` §10. Cada fase termina com o sistema **executável**. Nenhuma fase depende de uma fase futura.

---

### FASE 1 — Migração SQLite → PostgreSQL

**Objetivo**
Trocar o mecanismo de persistência, remover o dado biométrico do repositório e introduzir schema versionado — **sem alterar o comportamento funcional percebido pelo operador** (menu, câmera e reconhecimento continuam idênticos).

**Alterações**

1. Remover `escola.db` do versionamento e ampliar `.gitignore` (`escola.db`, `*.db`, `fotos/`, `storage/`, `.env`).
2. `docker-compose.yml` com PostgreSQL para desenvolvimento. *(Executado: PostgreSQL 18-alpine, publicado na porta 5433 — a 5432 já estava ocupada por uma instalação nativa na máquina de desenvolvimento.)*
3. `pyproject.toml` com dependências fixadas; remover `pyserial` (A16).
4. `src/config/settings.py` — `pydantic-settings`, lê `DATABASE_URL` e demais chaves do `.env`, falha no boot se ausente. `.env.example` versionado.
5. `src/infrastructure/database/models.py` — modelos SQLAlchemy 2.0 do schema revisado (§6.3).
6. Alembic inicializado; migration `0001_schema_inicial` gerada e **revisada à mão**.
7. `src/infrastructure/repositories/` — dois repositórios concretos com os métodos usados hoje.
8. `cadastro.py` alterado **apenas nos 4 pontos de acesso a dados**, passando a chamar os repositórios. Câmera, DeepFace, menu e mensagens permanecem intocados nesta fase.
9. `preparar_banco()` **eliminado** — a aplicação não cria mais tabelas no boot (`CLAUDE.md` §4).
10. `scripts/import_legacy_sqlite.py` — ETL pontual com conversão de formato de data (§6.7).

**Arquivos envolvidos**
`cadastro.py` (modificado), `escola.db` (removido do Git), `.gitignore`, `requirements.txt`→`pyproject.toml`, `docker-compose.yml`, `alembic.ini`, `migrations/`, `src/config/`, `src/infrastructure/database/`, `src/infrastructure/repositories/`, `scripts/import_legacy_sqlite.py`, `.env.example`, `README.md`.

**Dependências**
Nenhuma fase anterior. Requer Docker (ou PostgreSQL local) na máquina de desenvolvimento — **novo pré-requisito de ambiente**, a ser documentado no README.

**Riscos**

| Risco | Mitigação |
|---|---|
| Reescrever o histórico do Git é irreversível e afeta clones existentes | Executar somente após confirmação explícita; criar tag de backup do estado atual antes |
| O projeto deixa de rodar "só com `python cadastro.py`" | README documenta `docker compose up -d` como passo 1; `.env.example` com defaults locais prontos |
| Migration mal revisada fixa um schema ruim | A migration inicial é revisada manualmente, não apenas autogerada; validada em banco limpo |
| Credencial acidentalmente commitada | `.env` no `.gitignore` antes de qualquer conexão ser configurada |

**Testes**

- Integração: `alembic upgrade head` em banco vazio → todas as tabelas, constraints, FKs e índices presentes;
- Integração: `alembic downgrade base` → banco limpo (rollback funciona);
- Integração: repositório de presença — dois registros no mesmo dia para o mesmo aluno resultam em **uma** linha e a segunda chamada retorna `False` (prova de A4 resolvido);
- Integração: `INSERT` em `presencas` com `aluno_id` inexistente → violação de FK (prova de A10 resolvido);
- Unitário: `settings.py` falha no boot com `DATABASE_URL` ausente;
- Funcional (manual, roteirizado): cadastrar aluno → reconhecer → registrar presença, com PostgreSQL.

**Critério de conclusão**

- [ ] `grep -rn "sqlite3" src/ cadastro.py` retorna vazio (exceto o script de ETL pontual);
- [ ] `git ls-files` não lista nenhum `.db`, `.env` ou imagem;
- [ ] Nenhum `CREATE TABLE` executado em tempo de aplicação;
- [ ] Suíte de integração da fase passa contra PostgreSQL real;
- [ ] Fluxo manual completo validado;
- [ ] README atualizado com o novo procedimento de setup.

---

### FASE 2 — Separação em camadas

> **Executada em 2026-09-07, com escopo ampliado.** Extrair a infraestrutura de `cadastro.py` sem um tipo de retorno e sem um seam de teste não era possível, então os itens 19–22 da Fase 3 (entidade `Aluno`, `Protocol`s de repositório e serviço, `errors.py`, casos de uso `RegistrarPresenca` e `CadastrarAluno`) foram antecipados. Com a orquestração fora do script, manter um `cadastro.py` esvaziado seria código morto: ele foi **removido nesta fase**, e não na Fase 4 (item 27). Consequência: a Fase 4 passa a ser o trabalho de embeddings e do `matcher` — a escolha do *melhor* candidato (A18) depende da distância, informação que `DeepFace.verify()` não expõe de forma útil, e por isso só é resolvível junto com a Fase 5.

**Objetivo** Extrair de `cadastro.py` as responsabilidades de infraestrutura e apresentação, deixando um script fino.

**Alterações** `CameraProvider` + `OpenCVCamera` (com liberação em `finally` — resolve A17); `src/presentation/cli/` (menu, prompts, viewer); `src/config/logging.py` e substituição dos `print()` de diagnóstico por `logger` (A13); valores hardcoded movidos para `settings` (A12).

**Arquivos** `cadastro.py` (encolhe), `src/presentation/`, `src/infrastructure/camera/`, `src/config/logging.py`, `src/main.py`.

**Dependências** Fase 1 (settings e repositórios já existem).

**Riscos** Regressão de UX na janela OpenCV — mitigada mantendo os mesmos textos e teclas (ESPAÇO/ESC/ENTER) e validando com o roteiro manual da Fase 1.

**Testes** Unitário de `prompts` (matrícula não numérica, nome vazio) com entrada injetada; unitário de `viewer` com câmera falsa; roteiro manual de regressão.

**Critério de conclusão** `cadastro.py` não contém mais `cv2.VideoCapture` nem `input()`; nenhum `print()` usado para diagnóstico; a aplicação inicia por `python -m src.main`.

**Verificado na execução:** `cadastro.py` removido · `src/domain/` e `src/application/` sem `cv2`/`deepface`/`sqlalchemy` · `cv2`/`deepface` confinados a 4 módulos de infraestrutura e apresentação · zero `sqlite3` e zero `CREATE TABLE` na aplicação · zero chamadas de `print()` fora da apresentação · 82 testes passando, dos quais 44 unitários rodam sem webcam, sem OpenCV, sem DeepFace e sem PostgreSQL.

---

### FASE 3 — Domínio e casos de uso

**Objetivo** Tornar a regra de negócio testável e independente de infraestrutura.

**Alterações** Entidades `Aluno`, `Presenca`, `FaceEmbedding` (dataclasses puras); `Protocol`s de repositório e serviços; casos de uso `CadastrarAluno`, `ReconhecerAluno`, `RegistrarPresenca`; `domain/errors.py` com exceções nomeadas (`AlunoJaCadastrado`, `NenhumRostoDetectado`, `MultiplosRostosDetectados`, `CameraIndisponivel`, `ModeloIndisponivel`); injeção de dependências em `src/main.py`.

**Arquivos** `src/domain/`, `src/application/`, `src/main.py`, `src/presentation/cli/menu.py`.

**Dependências** Fase 2.

**Riscos** Criar abstração sem uso — controlado pela regra: **um `Protocol` só existe se houver ao menos um fake de teste e uma implementação real**.

**Testes** Unitários dos casos de uso com repositório e provider falsos, sem banco, sem câmera, sem DeepFace: matrícula duplicada, nome inválido, nenhum rosto, múltiplos rostos, câmera indisponível.

**Critério de conclusão** `grep -rn "import cv2\|from deepface\|sqlalchemy" src/domain/ src/application/` retorna vazio; casos de uso rodam na suíte unitária em menos de 1 segundo.

---

### FASE 4 — Isolamento do reconhecimento facial

**Objetivo** DeepFace passa a existir em um único arquivo, atrás de um contrato.

**Alterações** `infrastructure/face_recognition/deepface_provider.py` implementando `FaceRecognitionProvider`; tradução de exceções da biblioteca para erros de domínio — **fim do `except Exception: continue`** (A6); modelo, detector e threshold vindos de `settings` (A12); `domain/services/matcher.py` com a regra pura de seleção do **melhor** candidato abaixo do threshold, não do primeiro (A18).

**Arquivos** `src/infrastructure/face_recognition/`, `src/domain/services/matcher.py`, `src/application/use_cases/reconhecer_aluno.py`, `src/config/settings.py`.

**Dependências** Fase 3.

**Riscos** Mudança na convenção de distância ao sair de `verify()` para cálculo próprio — mitigada na Fase 5 com teste de equivalência numérica.

**Testes** Unitário do `matcher`: nenhum candidato abaixo do threshold; empate; melhor ≠ primeiro; lista vazia. Unitário do provider com biblioteca mockada verificando a tradução de cada erro.

**Critério de conclusão** `grep -rln "deepface" src/` retorna exatamente um arquivo; nenhum `except Exception` sem tratamento no repositório inteiro.

---

### FASE 5 — Performance: embeddings persistidos

> **Executada em 2026-09-07, fundida com a Fase 4.** As duas fases foram unidas porque o item 24 (matcher, escolha do melhor candidato — A18) depende da distância entre vetores, informação que `DeepFace.verify()` não expõe de forma útil: só existe depois que os embeddings passam a ser persistidos. O item 23 (provider atrás do contrato) e o 26 (fake sem TensorFlow) já haviam sido entregues na Fase 2. **Fechados aqui: A5, A14, A15, A18.** Medição da comparação em `docs/adr/ADR-002`.

**Objetivo** Eliminar o reprocessamento (A5, A14) — de até `2N` inferências por ciclo para **1**.

**Alterações** Migration adicionando `embedding`, `embedding_modelo`, `embedding_dim`; `CadastrarAluno` passa a calcular e persistir o embedding da face **recortada e alinhada**; `ReconhecerAluno` carrega a matriz de referência uma vez, extrai 1 embedding do frame e compara por distância cosseno vetorizada em NumPy; recarga da lista quando houver novo cadastro (A15).

**Arquivos** `migrations/versions/0002_*`, `src/infrastructure/database/models.py`, casos de uso, `matcher.py`, `scripts/` (backfill de embeddings).

**Dependências** Fase 4.

**Riscos** Embeddings existentes ficam inválidos se o modelo mudar — mitigado gravando `embedding_modelo` e recusando comparação entre modelos diferentes, com backfill explícito.

**Testes** Equivalência: para o mesmo par de imagens, a decisão do novo caminho coincide com `DeepFace.verify()`; benchmark comparando ciclos/segundo antes e depois com N sintético (10, 50, 200); unitário da comparação vetorizada contra cálculo ingênuo.

**Critério de conclusão** Uma única inferência por ciclo de comparação, medida; benchmark registrado no `ARCHITECTURE.md`; decisão idêntica à do baseline no conjunto de validação.

**Verificado na execução:** uma inferência por ciclo, provada por teste que conta as chamadas ao modelo com N=50 · benchmark real em `scripts/benchmark_matcher.py` (200 alunos: 0,0142 ms de comparação) · comparação vetorizada conferida contra o cálculo ingênuo sobre 50 vetores de 512 dimensões · 122 testes passando. **Pendente:** a comparação com `DeepFace.verify()` sobre imagens reais exige um ambiente Python 3.10/3.11 — ver *Limitações* no README.

---

### FASE 6 — Segurança e dados biométricos

**Objetivo** Tratar biometria como dado sensível de fato, não por declaração.

**Alterações** `anti_spoofing` habilitado com recusa de frames não reais (A7); usuário PostgreSQL da aplicação com privilégio mínimo (somente DML, sem DDL); armazenamento apenas do embedding e da face recortada, descartando o frame completo (A14); caso de uso `ExcluirAluno` (remove linha, arquivo e embedding; presenças caem por `ON DELETE CASCADE`); política de retenção configurável para presenças antigas; registro de consentimento no cadastro; revisão do logging para garantir ausência de PII, imagem e embedding.

**Arquivos** `src/application/use_cases/excluir_aluno.py`, `deepface_provider.py`, `migrations/versions/0003_*`, `src/config/logging.py`, `docs/adr/`, `docs/lgpd.md`.

**Dependências** Fase 5.

**Riscos** Anti-spoofing pode gerar falsos negativos em webcams ruins — mitigado por flag em `settings` com padrão ativado e mensagem de erro distinta de "não reconhecido".

**Testes** Unitário: frame marcado como não real nunca chega ao matcher; integração: exclusão de aluno remove presenças por cascade e apaga o arquivo; teste de log verificando que nenhum campo sensível é emitido.

**Critério de conclusão** Cadastro e reconhecimento recusam apresentação de foto/tela; existe caminho de exclusão completo; nenhum dado biométrico legível fora do diretório de armazenamento controlado.

---

### FASE 7 — QA

**Objetivo** Rede de segurança permanente (A9).

**Alterações** Suíte completa (§11), fixtures de banco por transação, `pytest-bdd` com os `.feature`, `scripts/evaluate_model.py` para FAR/FRR/ROC, meta de cobertura em `pyproject.toml`, CI rodando unitários + integração.

**Dependências** Fase 6 — embora testes sejam escritos em cada fase; esta consolida e fecha lacunas.

**Riscos** Testes que dependem de imagens reais — mitigado usando imagens públicas baixadas sob demanda e **nunca versionadas**.

**Testes** A própria fase.

**Critério de conclusão** Cobertura ≥ 80% em `domain/` e `application/`; todos os cenários obrigatórios de `instructions/03-qa.md` §6 cobertos; CI verde.

---

### FASE 8 — Interface

**Objetivo** Usabilidade e operação.

**Alterações** Menu com listar alunos, listar/exportar presenças do dia e excluir aluno; mensagens de erro acionáveis (distinguindo "sem rosto", "modelo indisponível", "spoof detectado"); overlay com nome, confiança e estado; feedback de progresso no primeiro download dos pesos.

**Dependências** Fase 7.

**Riscos** Escopo inflando para uma GUI — barrado: a CLI permanece a interface oficial.

**Testes** Unitários de formatação e roteiro manual de aceitação.

**Critério de conclusão** Roteiro de demonstração acadêmica executável do início ao fim sem intervenção no código.

---

### FASE 9 — Documentação

**Objetivo** Projeto apresentável.

**Alterações** `ARCHITECTURE.md` atualizado para o estado final; ADRs numerados; diagramas (componentes, sequência do reconhecimento, modelo de dados); README com setup reproduzível; `docs/apresentacao.md` com roteiro e números da avaliação do modelo.

**Dependências** Fase 8.

**Riscos** Documentação divergir do código — mitigado gerando o diagrama de dados a partir dos modelos e validando o README por um setup do zero.

**Testes** Setup do zero, em máquina limpa, seguindo apenas o README.

**Critério de conclusão** Todos os itens da §12.

---

## 6. Migração PostgreSQL

### 6.1 Driver e camada de acesso

**Decisão:** `SQLAlchemy 2.0` (ORM) + `psycopg` 3 (binário) + `Alembic`.

**Problema:** o schema precisa ser versionado, o SQL precisa sair dos casos de uso e o acesso a dados precisa ser substituível em teste.

**Alternativas consideradas**

| Opção | A favor | Contra |
|---|---|---|
| `psycopg` 3 puro + arquivos `.sql` numerados | Mínimo de dependências; SQL explícito e didático | Runner de migration caseiro (código sem valor didático); mapeamento manual repetitivo |
| `SQLAlchemy` Core + Alembic | Sem "mágica" de ORM; Alembic nativo | Ainda exige mapear resultados à mão |
| **`SQLAlchemy` ORM + Alembic** | Alembic autogenera a partir do metadata; `CLAUDE.md` §2 aponta a ausência de ORM como lacuna; `instructions/02-desenvolvedor.md` já o pressupõe; padrão de mercado | Dependência maior; risco de N+1 se usado sem atenção |
| `Django ORM` | Migrations excelentes | Traz um framework web inteiro para uma CLI — desproporcional |

**Escolha:** SQLAlchemy 2.0 ORM + Alembic + psycopg 3.

**Justificativa:** Alembic é a ferramenta madura de migrations no ecossistema Python e opera sobre o metadata do SQLAlchemy — adotar um sem o outro custa mais do que adotar os dois. O ORM fica **confinado a `infrastructure/`**; o domínio continua com dataclasses puras, então a dependência não contamina as regras de negócio.

**Impacto:** duas dependências novas; um diretório `migrations/`.

**Trade-off:** mais peso de biblioteca em troca de migrations versionadas, tipos declarativos e repositórios trocáveis. Aceito. → `docs/adr/ADR-001`.

### 6.2 Estratégia de configuração

```text
.env (nunca versionado)   →   pydantic-settings   →   Settings (tipado, validado)
.env.example (versionado) →   documenta as chaves, com valores de desenvolvimento
```

| Variável | Exemplo | Observação |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://app:SENHA@localhost:5432/escola` | **obrigatória**, sem default — falha no boot se ausente |
| `APP_ENV` | `development` | `development` \| `test` \| `production` |
| `APP_TIMEZONE` | `America/Sao_Paulo` | define o "dia" da regra de presença |
| `LOG_LEVEL` | `INFO` | |
| `CAMERA_INDEX` | `0` | |
| `FACE_MODEL` | `Facenet512` | |
| `FACE_DETECTOR` | `opencv` | |
| `FACE_THRESHOLD` | `0.30` | distância cosseno; hoje é implícito na biblioteca |
| `FACE_ANTI_SPOOFING` | `true` | Fase 6 |
| `STORAGE_DIR` | `./storage/faces` | fora de `fotos/`, com permissão restrita |

Regra: **nenhuma credencial no código, no `.env.example`, ou em log.** A senha de desenvolvimento do `docker-compose.yml` vale apenas para o container local e é documentada como tal.

### 6.3 Schema alvo

O schema é **redesenhado**, não transportado (`instructions/01-arquiteto.md` §4).

```sql
CREATE TABLE alunos (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    matricula        TEXT        NOT NULL UNIQUE,
    nome             TEXT        NOT NULL CHECK (length(trim(nome)) > 0),
    foto_arquivo     TEXT        NULL,       -- caminho RELATIVO a STORAGE_DIR
    embedding        BYTEA       NULL,       -- float32 little-endian (Fase 5)
    embedding_modelo TEXT        NULL,       -- ex.: 'Facenet512'
    embedding_dim    SMALLINT    NULL,
    consentimento_em TIMESTAMPTZ NULL,       -- Fase 6
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_alunos_embedding_completo CHECK (
        (embedding IS NULL AND embedding_modelo IS NULL AND embedding_dim IS NULL)
        OR
        (embedding IS NOT NULL AND embedding_modelo IS NOT NULL AND embedding_dim IS NOT NULL)
    )
);

CREATE TABLE presencas (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aluno_id        BIGINT      NOT NULL
                    REFERENCES alunos(id) ON DELETE CASCADE,
    registrado_em   TIMESTAMPTZ NOT NULL,
    data_referencia DATE        NOT NULL,   -- o "dia" da regra de negócio
    CONSTRAINT uq_presencas_aluno_dia UNIQUE (aluno_id, data_referencia)
);

CREATE INDEX ix_presencas_data_referencia ON presencas (data_referencia);
```

Notas de projeto:

- **`matricula` separada de `id`.** A matrícula é dado externo e pode vir a ser alfanumérica; a chave primária é interna e estável. Hoje `id` acumulava os dois papéis (e ainda era copiado em `biometria_id`).
- **`biometria_id` eliminada** (A16) — era cópia literal de `id`.
- **`data_referencia` é coluna própria, não expressão.** `(registrado_em AT TIME ZONE 'America/Sao_Paulo')::date` não é `IMMUTABLE` e portanto **não pode** ser coluna gerada nem indexada diretamente; o "dia" é decidido pela aplicação, usando `APP_TIMEZONE`, e persistido.
- **A regra de negócio vira constraint.** `UNIQUE (aluno_id, data_referencia)` + `INSERT ... ON CONFLICT DO NOTHING` resolve A3 e A4 de uma vez: o dedup deixa de ser um `SELECT` prévio sujeito a corrida.
- **`ON DELETE CASCADE`** existe para viabilizar o direito de exclusão (Fase 6).
- **`foto_arquivo` é relativo** a `STORAGE_DIR` (A11) — o banco volta a ser portátil.
- **Índices**: a constraint única já cria índice em `(aluno_id, data_referencia)`, que cobre as consultas por aluno; o índice extra em `data_referencia` atende ao relatório diário.

### 6.4 Transformação de tipos

| SQLite (atual) | PostgreSQL (alvo) | Transformação |
|---|---|---|
| `alunos.id INTEGER PK` | `alunos.matricula TEXT UNIQUE` | valor convertido para texto; nova PK `IDENTITY` gerada |
| `alunos.nome TEXT` (nullable) | `nome TEXT NOT NULL CHECK(...)` | rejeitar vazio/nulo na carga |
| `alunos.foto_path TEXT` (absoluto) | `foto_arquivo TEXT` (relativo) | extrair o nome do arquivo; **nulo** se o arquivo não existir |
| `alunos.biometria_id INTEGER` | — | descartada |
| `presencas.id INTEGER AUTOINCREMENT` | `BIGINT GENERATED ALWAYS AS IDENTITY` | não preservar; `AUTOINCREMENT`/`sqlite_sequence` não têm equivalente nem necessidade |
| `presencas.aluno_id INTEGER` | `BIGINT NOT NULL REFERENCES alunos(id)` | resolvido por lookup em `matricula` |
| `presencas.data_hora TEXT (dd/mm/aaaa HH:MM:SS)` | `registrado_em TIMESTAMPTZ` + `data_referencia DATE` | `strptime('%d/%m/%Y %H:%M:%S')`, localizado em `APP_TIMEZONE`; linhas que não fizerem parse são **rejeitadas e relatadas**, nunca convertidas por adivinhação |

Exemplo sintético da conversão: `'01/02/2026 08:00:00'` → `registrado_em = 2026-02-01T08:00:00-03:00`, `data_referencia = 2026-02-01`.

### 6.5 Constraints

`NOT NULL` em toda coluna obrigatória · `UNIQUE (matricula)` · `UNIQUE (aluno_id, data_referencia)` · `FOREIGN KEY presencas.aluno_id → alunos.id ON DELETE CASCADE` · `CHECK` de nome não vazio · `CHECK` de coerência do embedding.

Diferença conceitual em relação ao SQLite: `PRAGMA foreign_keys` precisava ser ligado por conexão e nunca era; em PostgreSQL a integridade referencial é **sempre** aplicada.

### 6.6 Migrations

- Alembic com `versions/` versionado; toda alteração de schema é uma revisão.
- `0001_schema_inicial` é **autogerada e depois revisada manualmente** — autogenerate não produz `CHECK`, nomes de constraint nem índices especiais de forma confiável.
- Toda revisão implementa `downgrade()` de verdade (requisito de rollback).
- A aplicação **nunca** executa migration no boot; é comando explícito (`alembic upgrade head`), coerente com `CLAUDE.md` §4.
- Convenção de nomes de constraint definida no `MetaData` (`ix_`, `uq_`, `ck_`, `fk_`, `pk_`) para que o `downgrade` seja determinístico.

### 6.7 Estratégia para os dados existentes

**Situação:** 1 aluno com foto inexistente + 39 presenças de teste do mesmo aluno, todas no mesmo dia, em formato de data incompatível. Não há valor operacional nesses dados — e há um problema de privacidade, já que o nome é real.

**Decisão (revisada na execução da Fase 1, por determinação do responsável):** os dados legados **são migrados**, não descartados. `escola.db` sai do versionamento do Git, mas permanece no disco como origem do ETL e nunca é alterado.

> Revisão em 2026-09-07. A proposta original deste plano era descartar os dados legados. O responsável determinou o contrário ("Não simplesmente descarte esses dados"), e a Fase 1 foi executada migrando-os. Resultado real: 1 aluno e 1 presença canônica gravados; as outras 38 marcações — todas do mesmo aluno, no mesmo dia — foram colapsadas pela constraint `UNIQUE(aluno_id, data_referencia)` e ficaram registradas, linha a linha e com o conteúdo original, no relatório JSON do ETL.

`scripts/import_legacy_sqlite.py` é executável sob demanda, e vale além da migração em si porque:

1. demonstra tratamento de dado legado (valor acadêmico);
2. torna a conversão de formato de data (A3) explícita e testável;
3. serve de exemplo caso exista outro `escola.db` real em posse do professor/turma.

Comportamento do script: modo `--dry-run` por padrão, relatório de linhas convertidas/rejeitadas com motivo, transação única, idempotente por `matricula` e por `(aluno_id, data_referencia)`. **Nunca** infere data ambígua: aceita `%d/%m/%Y %H:%M:%S` (formato legado) e `%Y-%m-%d %H:%M:%S` (formato atual do `cadastro.py`), ambos comprovados na história do projeto, e recusa qualquer linha que não case exatamente com um deles.

Quando há mais de uma marcação para o mesmo aluno no mesmo dia, sobrevive a **mais antiga** (a hora de chegada): o script valida e ordena por instante antes de inserir, de modo que o resultado não depende da ordem dos ids na origem.

### 6.8 Validação

1. `alembic upgrade head` em banco vazio → comparar o schema resultante com o esperado (constraints, FKs, índices, tipos);
2. `alembic downgrade base` → banco vazio, sem resíduo;
3. testes de integração da Fase 1 (lista em §5);
4. tentativa de violar cada constraint → erro esperado (é o teste de que a constraint existe de fato);
5. roteiro funcional manual: cadastrar → reconhecer → registrar → tentar registrar de novo no mesmo dia;
6. `scripts/import_legacy_sqlite.py --dry-run` sobre uma cópia de `escola.db` → relatório coerente com os fatos da §2.5 (1 aluno, 39 presenças, 38 rejeitadas por duplicidade de dia sob a nova constraint).

### 6.9 Rollback

| Nível | Procedimento |
|---|---|
| Código | Tag `baseline-sqlite` criada no commit `08116cf` **antes** de qualquer alteração; `git checkout` restaura o protótipo funcional |
| Schema | `alembic downgrade -1` (toda revisão tem `downgrade` implementado e testado) |
| Dados | `pg_dump` antes de qualquer migration destrutiva; container de desenvolvimento é descartável (`docker compose down -v`) |
| Arquivo legado | Cópia de `escola.db` guardada **fora do repositório**, em local privado, antes da remoção do Git — nunca reintroduzida |

---

## 7. Refatoração arquitetural

Ordem de extração de `cadastro.py`, do mais isolado ao mais entrelaçado. Cada passo deixa o sistema funcionando.

| # | O que sai | Por que nesta ordem | Depende de |
|---|---|---|---|
| 1 | **Configuração** (`PROJETO`, `CAMINHO_DB`, `PASTA_FOTOS`, `MODELO`, `DETECTOR`) | Nenhuma dependência; habilita todo o resto | — |
| 2 | **Acesso a dados** → repositórios | Já exigido pela Fase 1; as 4 chamadas SQL são o acoplamento mais fácil de cortar | 1 |
| 3 | **Câmera** → `CameraProvider` | Isolar `VideoCapture`/`release` remove a duplicação entre as duas funções e o vazamento de recurso (A17) | 1 |
| 4 | **Apresentação** (`input`, `print`, `imshow`, `putText`, `waitKey`) → `presentation/cli/` | Depois de câmera e dados, o que sobra nas funções longas é UI + regra | 3 |
| 5 | **Regra de presença** → `RegistrarPresenca` | É a menor regra pura e a mais crítica; primeira a ganhar teste unitário | 2 |
| 6 | **Regra de cadastro** → `CadastrarAluno` | Envolve validação, câmera, provider e persistência — precisa dos anteriores prontos | 2,3,4 |
| 7 | **Reconhecimento** → `FaceRecognitionProvider` + `matcher` | O mais entrelaçado (laço de vídeo + inferência + decisão); último a sair | 3,4,5,6 |
| 8 | **`cadastro.py` removido** | Só quando nada mais o referencia — verificado por `grep`, não por suposição (`CLAUDE.md` §7.5) | 1–7 |

Regra durante toda a extração: **extrair → testar → mover → testar → remover legado → testar** (`instructions/02-desenvolvedor.md` §10). Nada de reescrita de uma vez.

---

## 8. Reconhecimento facial

### 8.1 De onde para onde

```text
HOJE
CLI ──► DeepFace.verify(frame, foto_path) × N alunos ──► primeiro "verified"

ALVO
Caso de uso
     ↓ (Protocol)
FaceRecognitionProvider ── detectar_face / gerar_embedding
     ↓
DeepFaceProvider ── único importador de `deepface`
```

A decisão de identidade **sai** da biblioteca e passa para `domain/services/matcher.py`, que é código puro e testável: recebe o embedding do frame, a lista de embeddings de referência e o threshold; devolve o melhor candidato ou nenhum.

### 8.2 Responsabilidades por etapa

| Etapa | Componente alvo | Camada |
|---|---|---|
| Camera, Frame | `OpenCVCamera` | Infrastructure |
| Detection, Alignment | `DeepFaceProvider.detectar_face` | Infrastructure |
| Embedding | `DeepFaceProvider.gerar_embedding` | Infrastructure |
| Comparison, Identity | `matcher.melhor_candidato` | **Domain** (puro) |
| Attendance | `RegistrarPresenca` | Application |

### 8.3 Tratamento de erros

Cada falha da biblioteca vira uma exceção de domínio nomeada, e a CLI dá uma mensagem distinta para cada uma:

| Situação | Erro de domínio | Mensagem ao operador |
|---|---|---|
| Nenhum rosto no frame | `NenhumRostoDetectado` | "Nenhum rosto na câmera." |
| Mais de um rosto no cadastro | `MultiplosRostosDetectados` | "Deixe somente um rosto na câmera." |
| Pesos ausentes / TensorFlow quebrado | `ModeloIndisponivel` | "Modelo indisponível — verifique a instalação." |
| Frame marcado como falso (Fase 6) | `PossivelFraude` | "Apresentação de foto/tela detectada." |

Isto encerra A6: "não reconhecido" deixa de ser o destino de todo erro. Erro inesperado é **logado e propagado**, nunca engolido.

### 8.4 Substituibilidade do provider

O teste que prova a abstração: um `FakeFaceRecognitionProvider` que devolve embeddings determinísticos e permite testar todos os casos de uso **sem TensorFlow instalado**. Se esse fake precisar conhecer algo de DeepFace, a abstração vazou.

Trocar Facenet512 por ArcFace, ou `opencv` por `retinaface`, deve custar apenas mudança de variável de ambiente + backfill de embeddings (ver Fase 5).

---

## 9. Performance

### 9.1 O custo atual

Por ciclo de comparação (a cada 8 frames), para N alunos: `DeepFace.verify()` recalcula o embedding do frame **e** o da foto de referência, para cada aluno → até **2N inferências Facenet512**. As N inferências de referência são 100% desperdício: as fotos não mudam.

Agravante (A14): a foto de referência é o frame inteiro, então o detector precisa reprocessá-la a cada comparação.

### 9.2 O desenho alvo

```text
CADASTRO (uma vez por aluno)
frame → detectar_face (recorte + alinhamento) → gerar_embedding → normalizar → persistir (BYTEA)

RECONHECIMENTO (por ciclo)
frame → detectar_face → gerar_embedding → normalizar
      → distâncias cosseno vetorizadas contra a matriz (N × 512) já em memória
      → melhor candidato abaixo do threshold
```

Custo por ciclo: **1 inferência**, independente de N. A comparação passa a ser um produto matriz-vetor de 512 dimensões — microssegundos para N na casa das centenas.

### 9.3 Estratégia de armazenamento

**Decisão:** `BYTEA` com `float32` little-endian + comparação em NumPy na aplicação.

| Alternativa | Avaliação |
|---|---|
| Recalcular sempre (hoje) | Inviável — é o problema |
| Arquivo `.npy` ao lado da foto | Cria uma segunda fonte de verdade fora do banco; complica exclusão e backup |
| `REAL[]` (array PostgreSQL) | Legível em SQL, mas ~4× maior em disco e sem ganho prático |
| **`BYTEA` + NumPy** | ~2 KB por aluno; `np.frombuffer` é conversão sem cópia; comparação vetorizada trivial |
| `pgvector` + índice HNSW | Correto para milhões de vetores. Para dezenas/centenas, o índice aproximado é **mais lento** que a varredura exata e adiciona uma extensão ao pré-requisito de infraestrutura |

**Escolha:** `BYTEA` + NumPy, com `pgvector` documentado como caminho de evolução em `docs/adr/ADR-003`. A migração futura é uma migration de coluna — o repositório protege o resto do sistema. Dizer *por que não* pgvector, com o número na mão, vale academicamente mais do que adotá-lo sem necessidade.

### 9.4 Cuidados de correção

- **Normalização**: `DeepFace.represent()` não devolve vetor L2-normalizado. Normalizar na fronteira do provider e documentar, para que a distância cosseno calculada seja comparável ao threshold da biblioteca.
- **Equivalência**: teste comparando a decisão do caminho novo com `DeepFace.verify()` sobre o mesmo par — a refatoração de performance não pode mudar o veredito.
- **Coerência de modelo**: embedding gravado com `Facenet512` não é comparável a um gerado por `ArcFace`. `embedding_modelo` é verificado antes da comparação; divergência → erro explícito e instrução de backfill.
- **Invalidação**: recarregar a matriz de referência após cadastro/exclusão (A15).

### 9.5 O que fica de fora

Threading da inferência, GPU e batching **não** entram. Depois de reduzir 2N para 1 inferência por ciclo, a causa do congelamento (A5 / `P5`) desaparece. Otimizar antes de medir seria mascarar o problema real.

---

## 10. Segurança

Escopo real: um sistema local, monousuário, com dado biométrico. As medidas abaixo são proporcionais a isso — não há autenticação de API a implementar porque não há API.

| Alvo | Etapa | Fase |
|---|---|---|
| **Repositório** | Remover `escola.db` do versionamento e do histórico; `.gitignore` cobrindo `*.db`, `fotos/`, `storage/`, `.env` | 1 |
| **Secrets** | `DATABASE_URL` só via `.env`; `.env.example` sem valores reais; boot falha se ausente; nenhum secret em log ou exceção | 1 |
| **Imagens** | Deixar de gravar o frame completo; armazenar apenas a face recortada, sob `STORAGE_DIR`, com permissão restrita ao usuário da aplicação; caminho relativo no banco | 5–6 |
| **Embeddings** | Coluna `BYTEA` no banco, protegida pelo controle de acesso do PostgreSQL; nunca logados, nunca exportados por padrão | 5–6 |
| **Acesso ao banco** | Usuário da aplicação com privilégio mínimo: `SELECT/INSERT/UPDATE/DELETE` no schema da aplicação, **sem** DDL; migrations rodam com usuário separado | 1–6 |
| **Logs** | `logging` com níveis; proibido registrar nome completo em `INFO`, imagem, embedding ou credencial; identificar aluno por `id` interno nos logs de rotina | 2–6 |
| **Retenção** | Prazo configurável para presenças; comando de expurgo do que exceder | 6 |
| **Exclusão** | Caso de uso `ExcluirAluno`: apaga linha, arquivo de face e embedding; presenças caem por `ON DELETE CASCADE` | 6 |
| **Consentimento** | `consentimento_em` registrado no cadastro; sem consentimento, não cadastra | 6 |
| **Anti-spoofing** | `anti_spoofing` habilitado; frame não real é recusado com erro próprio | 6 |
| **Documentação** | `docs/lgpd.md`: quais dados, por que, por quanto tempo, como excluir | 9 |

### ~~Ponto que exige decisão do responsável~~ — RESOLVIDO em 2026-09-07

`escola.db` foi removido de **todo** o histórico do Git com `git filter-repo`
(opção 1, a recomendada), preservando as mensagens, a autoria e a estrutura
dos 33 commits. O arquivo também foi apagado do disco.

Uma correção de avaliação, apurada na execução: o blob continha **dado
pessoal**, não dado biométrico — um nome real, 39 registros de presença e um
caminho de arquivo. Nenhuma imagem facial e nenhum embedding jamais foram
versionados (`fotos/` estava vazia no commit inicial, e a coluna de embedding
sequer existia). O repositório também é privado. Os textos anteriores deste
plano descreviam o problema como "dados biométricos no histórico", o que
superestimava a gravidade.

Decisão, alternativas descartadas, verificação e **risco residual** (as refs
de Pull Request que o GitHub retém) em
[`docs/adr/ADR-003-limpeza-do-historico.md`](docs/adr/ADR-003-limpeza-do-historico.md).

---

## 11. QA

### 11.1 Pirâmide

```text
            Funcional (manual, roteirizado)  ~1 roteiro
                  BDD (pytest-bdd)           ~21 cenários
              Integração (PostgreSQL real)   ~15 testes
                Unitários (fakes)            maioria
```

### 11.2 Testes unitários — sem banco, sem câmera, sem DeepFace

| Alvo | Casos |
|---|---|
| `RegistrarPresenca` | primeira do dia; segunda do mesmo dia; aluno inexistente; falha do repositório |
| `CadastrarAluno` | válido; matrícula duplicada; nome vazio/em branco; nenhum rosto; múltiplos rostos; câmera indisponível |
| `matcher` | lista vazia; nenhum abaixo do threshold; melhor ≠ primeiro (A18); empate; modelo divergente |
| `Settings` | `DATABASE_URL` ausente; threshold fora da faixa |
| `prompts` | matrícula não numérica; nome só com espaços |
| Tradução de erros | cada exceção da biblioteca → erro de domínio correto |

Ferramentas: `pytest`, fakes escritos à mão para os `Protocol`s (mais legíveis que mocks para apresentação acadêmica).

### 11.3 Testes de integração — PostgreSQL real

Migrations sobem e descem · unicidade de `matricula` · unicidade `(aluno_id, data_referencia)` · FK rejeita aluno inexistente · `ON DELETE CASCADE` remove presenças · `INSERT ... ON CONFLICT DO NOTHING` retorna corretamente · round-trip de embedding `BYTEA` preserva os floats · transação faz rollback em erro.

Infraestrutura: banco de teste dedicado via `TEST_DATABASE_URL`, `alembic upgrade head` uma vez por sessão, cada teste dentro de transação com rollback. Sem `testcontainers` — o `docker-compose` já existe e a dependência extra não se paga.

### 11.4 Testes funcionais

Roteiro manual versionado em `docs/roteiro-aceitacao.md`, executado ao fim de cada fase: cadastrar → reconhecer → registrar → tentar duplicar → excluir. É o teste de regressão de UX que nenhuma suíte automatizada cobre bem, dado o hardware envolvido.

### 11.5 BDD / Gherkin

`tests/features/`, executados por `pytest-bdd` (não são documentação decorativa — falham de verdade).

```gherkin
Feature: Registro de presença

  Scenario: Primeira presença do dia
    Given um aluno cadastrado com embedding válido
    When o sistema reconhecer o aluno
    And o operador confirmar a presença
    Then a presença deve ser registrada para o dia de hoje

  Scenario: Tentativa de duplicação no mesmo dia
    Given um aluno com presença já registrada hoje
    When o operador confirmar a presença novamente
    Then nenhuma nova presença deve ser registrada
    And o operador deve ser informado de que a presença já existe
```

Cobrindo os cenários obrigatórios de `instructions/03-qa.md` §6: cadastro (7), reconhecimento (6), presença (4), banco (4).

### 11.6 Avaliação do modelo de IA — separada dos testes de software

`scripts/evaluate_model.py`, executado sob demanda, **fora do CI**:

- entrada: conjunto de pares genuínos e impostores;
- saída: FAR, FRR, EER, curva ROC, threshold ótimo, latência por inferência;
- uso: justificar o valor de `FACE_THRESHOLD` com número, em vez de aceitar o default da biblioteca;
- **restrição**: nenhuma imagem versionada. Usar dataset público baixado sob demanda (ex.: subconjunto de LFW) ou imagens locais em `storage/`, jamais no Git.

Este é o item de maior peso acadêmico: distingue "o software funciona" de "o modelo acerta", exatamente como `instructions/03-qa.md` §4 exige.

### 11.7 Pontos difíceis de testar — e o tratamento

| Ponto | Tratamento |
|---|---|
| Câmera física | `CameraProvider` com fake que devolve frames sintéticos |
| Inferência DeepFace | `FakeFaceRecognitionProvider` com embeddings determinísticos |
| Janela OpenCV / teclas | Extrair a decisão para função pura; a janela só desenha |
| Download de pesos (primeira execução) | Fora do escopo de teste; documentado no README |
| Acurácia do modelo | Não é teste de software — vai para §11.6 |
| Anti-spoofing | Fake do provider marcando `is_real=False`; validação real é manual |

---

## 12. Critérios de pronto

O projeto está concluído quando **todos** os itens abaixo forem verdadeiros e verificáveis por comando:

**Arquitetura**
- [ ] `grep -rn "import cv2\|from deepface\|sqlalchemy" src/domain/ src/application/` → vazio
- [ ] `grep -rln "deepface" src/` → exatamente um arquivo
- [ ] `grep -rn "sqlite3" src/` → vazio
- [ ] Nenhum SQL fora de `infrastructure/repositories/`
- [ ] `cadastro.py` não existe mais; a aplicação inicia por `python -m src.main`

**Banco**
- [ ] `alembic upgrade head` e `alembic downgrade base` funcionam em banco limpo
- [ ] Todas as constraints da §6.3 presentes e cobertas por teste
- [ ] Nenhum `CREATE TABLE` executado em tempo de aplicação
- [ ] `DATABASE_URL` obrigatória; boot falha sem ela

**Reconhecimento e performance**
- [ ] Uma inferência por ciclo de comparação, medida e registrada
- [ ] Embeddings persistidos e reutilizados; `embedding_modelo` verificado
- [ ] Decisão idêntica à do baseline no conjunto de validação
- [ ] Trocar de modelo exige apenas variável de ambiente + backfill

**Segurança**
- [ ] Nenhum `.db`, `.env` ou imagem em `git ls-files`; histórico tratado
- [ ] Anti-spoofing ativo e recusando apresentação de foto/tela
- [ ] Caminho completo de exclusão de aluno funcionando
- [ ] Nenhum dado biométrico ou credencial em log
- [ ] Usuário do banco sem privilégio de DDL

**Qualidade**
- [ ] Cobertura ≥ 80% em `domain/` e `application/`
- [ ] Todos os cenários obrigatórios de `instructions/03-qa.md` §6 cobertos
- [ ] Nenhum `except Exception` sem tratamento e log
- [ ] Nenhum `print()` usado como diagnóstico
- [ ] `ruff` e `mypy` limpos; CI verde

**Documentação**
- [ ] `ARCHITECTURE.md` refletindo o estado final
- [ ] ADRs para: ORM+migrations, modelagem do schema, armazenamento de embedding, threshold
- [ ] Diagramas de componentes, sequência e dados
- [ ] README validado por setup do zero em máquina limpa
- [ ] `docs/apresentacao.md` com roteiro e números da avaliação do modelo

---

## 13. Ordem de execução

Cada item é uma mudança implementável, verificável e commitável isoladamente.

**Fase 1 — PostgreSQL**

1. Criar tag `baseline-sqlite` no commit `08116cf` (rede de segurança antes de qualquer alteração).
2. Ampliar `.gitignore` (`*.db`, `escola.db`, `fotos/`, `storage/`, `.env`) e copiar `escola.db` para fora do repositório.
3. Remover `escola.db` do versionamento e tratar o histórico do Git — **após confirmação explícita** (ver §10).
4. Atualizar as dependências com versões fixadas, removendo `pyserial`. *(Executado mantendo `requirements.txt`; a migração para `pyproject.toml` foi adiada por não ser necessária à Fase 1.)*
5. Criar `docker-compose.yml` com PostgreSQL 18 (porta 5433) e `.env.example`.
6. Implementar `src/config/settings.py` (pydantic-settings) com validação e falha no boot.
7. Implementar `src/infrastructure/database/engine.py` e `models.py` conforme §6.3.
8. Inicializar Alembic; gerar e **revisar manualmente** `0001_schema_inicial`.
9. Escrever os testes de integração de schema (constraints, FK, cascade, unicidade).
10. Implementar `PostgresAlunoRepository` e `PostgresPresencaRepository`, com `INSERT ... ON CONFLICT DO NOTHING`.
11. Ligar os 4 pontos de acesso a dados de `cadastro.py` aos repositórios; excluir `preparar_banco()`.
12. Escrever `scripts/import_legacy_sqlite.py` com `--dry-run`, conversão de data e relatório.
13. Validar o fluxo manual completo contra PostgreSQL; atualizar README.

**Fase 2 — Camadas**

14. Extrair configuração hardcoded para `settings`.
15. Extrair `CameraProvider` + `OpenCVCamera`, com liberação em `finally`.
16. Extrair `presentation/cli/` (menu, prompts, viewer).
17. Configurar `logging` e substituir os `print()` de diagnóstico.
18. Criar `src/main.py` como composition root.

**Fase 3 — Domínio**

19. Criar entidades e `domain/errors.py`.
20. Criar os `Protocol`s de repositório e de serviços.
21. Extrair `RegistrarPresenca` + testes unitários com fakes.
22. Extrair `CadastrarAluno` + testes unitários com fakes.

**Fase 4 — Reconhecimento**

23. Implementar `DeepFaceProvider` atrás do contrato, com tradução de erros (fim do `except Exception`).
24. Implementar `matcher` puro (melhor candidato, não o primeiro) + testes unitários.
25. Extrair `ReconhecerAluno` usando provider + matcher.
26. Implementar `FakeFaceRecognitionProvider` e provar que a suíte roda sem TensorFlow.
27. Remover `cadastro.py` após verificar por `grep` que nada o referencia.

**Fase 5 — Performance**

28. Migration `0002`: colunas `embedding`, `embedding_modelo`, `embedding_dim` + `CHECK` de coerência.
29. Persistir embedding e face recortada no cadastro; parar de salvar o frame inteiro.
30. Comparação vetorizada em NumPy contra a matriz de referência em memória.
31. Teste de equivalência com `DeepFace.verify()` e benchmark N = 10/50/200.
32. Backfill de embeddings para cadastros anteriores; invalidação da matriz após cadastro/exclusão.

**Fase 6 — Segurança**

33. Habilitar anti-spoofing com erro de domínio próprio.
34. Migration `0003`: `consentimento_em`; registrar consentimento no cadastro.
35. Implementar `ExcluirAluno` (linha + arquivo + embedding; presenças por cascade).
36. Implementar política de retenção e comando de expurgo.
37. Criar usuário PostgreSQL da aplicação sem privilégio de DDL; documentar.
38. Auditar logs quanto a PII, imagem, embedding e credencial.

**Fase 7 — QA**

39. Completar a suíte unitária até ≥ 80% em `domain/` e `application/`.
40. Completar a suíte de integração.
41. Escrever os `.feature` e ligá-los ao `pytest-bdd`.
42. Escrever `scripts/evaluate_model.py` (FAR/FRR/EER/ROC) e calibrar `FACE_THRESHOLD` com dado.
43. Configurar CI (unitários + integração + `ruff` + `mypy`).

**Fase 8 — Interface**

44. Adicionar listagem de alunos, relatório de presenças do dia e exclusão ao menu.
45. Melhorar mensagens de erro e o overlay da janela (nome, confiança, estado).

**Fase 9 — Documentação**

46. Escrever os ADRs (ORM+migrations, schema, embedding, threshold).
47. Atualizar `ARCHITECTURE.md` para o estado final e gerar os diagramas.
48. Reescrever o README e validá-lo por setup do zero.
49. Escrever `docs/apresentacao.md` e `docs/lgpd.md`.

---

## Anexo — Decisões que exigem confirmação antes da Fase 1

| # | Decisão | Recomendação | Impacto se recusada |
|---|---|---|---|
| 1 | Reescrever o histórico do Git para remover `escola.db` | Sim, com tag de backup antes | Dado biométrico permanece recuperável; repositório não deve ser publicado |
| 2 | ~~Descartar os 39 registros legados de presença~~ **RESOLVIDA: migrar** | Decisão do responsável: migrar. Executado na Fase 1 — 39 lidas, 1 inserida, 38 colapsadas pela regra "uma presença por dia" e preservadas no relatório do ETL | — |
| 3 | Adotar SQLAlchemy + Alembic (vs. psycopg puro + `.sql`) | Sim — ver §6.1 | Runner de migration caseiro, sem valor didático |
| 4 | PostgreSQL via Docker como pré-requisito de desenvolvimento | Sim | Instalação nativa do PostgreSQL exigida em cada máquina |
| 5 | `matricula` separada da chave primária | Sim — ver §6.3 | Mantém o acoplamento atual entre identidade interna e dado externo |
