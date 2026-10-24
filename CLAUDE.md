# CLAUDE.md

# FaceDiff — Reconhecimento Facial para Controle de Presença

## 1. Objetivo do projeto

Aplicação acadêmica da disciplina de Inteligência Artificial da Fatec para
controle de presença com reconhecimento facial. **Não é um TCC.** O objetivo é
demonstrar conceitos de IA e engenharia de software, sem confundir
funcionamento do código com desempenho biométrico comprovado.

O código deve demonstrar organização arquitetural, separação de
responsabilidades, persistência, tratamento de erros, testes automatizados,
segurança, cuidado com dados biométricos, documentação técnica e capacidade
de evolução.

Regras operacionais, autorizações, histórico de ML e convenção de commits
estão em [`AGENTS.md`](AGENTS.md); leia-o antes de alterar o repositório. A
arquitetura e os comandos estão no [`README.md`](README.md). O registro de
estado, evidências e pendências está em
[`docs/ESTADO-ATUAL-E-EVIDENCIAS.md`](docs/ESTADO-ATUAL-E-EVIDENCIAS.md).

---

# 2. Estado atual

- **Interfaces:** web FaceDiff (FastAPI + SPA vanilla em
  `src/presentation/web`, principal em desenvolvimento) e CLI
  (`src/presentation/cli`, webcam local).
- **Reconhecimento:** DeepFace FaceNet512, detector OpenCV, anti-spoofing
  MiniFASNet, distância cosseno, limiar operacional `0.30`. A CLI faz
  identificação 1:N; a web faz verificação 1:1 pela mediana das distâncias às
  três referências do aluno.
- **Desafio de pose:** MediaPipe em subprocesso isolado no worker
  (`DesafioMovimentoAdapter`); no navegador, MediaPipe `tasks-vision` (WASM)
  serve só como guia visual.
- **Processamento web:** a API enfileira jobs em PostgreSQL (`FilaFacial`), e um
  único `face-worker` os processa em série (`src/face_worker_main.py`).
- **Persistência:** PostgreSQL 16 com SQLAlchemy 2 e Alembic (`0001`–`0011`).
- **Execução local:** `docker compose --profile web up -d --build` (API em
  `127.0.0.1:8000`, banco na porta 5433). Deploy previsto: `deploy/web/`
  (Caddy, Ubuntu); **nenhum deploy foi feito**.
- **Opcionais desligados por padrão (CLI):** qualidade de captura,
  consistência temporal e rejeição por ambiguidade.

Pendentes e fora de qualquer alegação: avaliação biométrica representativa,
calibração 1:N, validação do anti-spoofing com pessoas, deploy e operação com
dados reais.

O protótipo de origem (monolito `cadastro.py` com SQLite) está documentado em
[`docs/baseline-arquitetura.md`](docs/baseline-arquitetura.md).

---

# 3. Arquitetura

```text
Presentation   (cli, web)
     ↓
Application    (use_cases, services)
     ↓
Domain         (entities, repositories, services)
     ↑
Infrastructure (database, repositories, face_recognition, camera,
                storage, workers, backup)
```

```text
src/
├── main.py, web_main.py, face_worker_main.py   pontos de entrada
├── presentation/{cli,web}
├── application/{use_cases,services}
├── domain/{entities,repositories,services}
├── infrastructure/{database,repositories,face_recognition,camera,
│                   storage,workers,backup}
└── config/{settings.py,web_settings.py,logging.py}
```

Não aplicar arquitetura complexa sem justificativa.

---

# 4. Banco de dados

- O banco oficial é **PostgreSQL**. SQLite aparece apenas no histórico do
  protótipo, no importador `scripts/import_legacy_sqlite.py` e em fixtures
  sintéticas.
- A conexão vem de variável de ambiente (`DATABASE_URL`, `WEB_DATABASE_URL`).
  Credenciais nunca vão para o código.
- O banco não é criado nem alterado silenciosamente pela aplicação. Schema e
  migrations pertencem ao processo de infraestrutura/desenvolvimento.
- SQL fica nos repositórios `Postgres*` em `src/infrastructure/repositories`.
- Não execute upgrade/downgrade como parte de testes rotineiros. As fixtures
  PostgreSQL podem truncar tabelas e exigem opt-in e banco descartável com
  marcador (ver `docs/TURMAS.md`).
- O banco local `escola` estava na revisão `0011` em 19/10/2026. Isso não
  comprova o estado de qualquer outro banco.

---

# 5. Reconhecimento facial e embeddings

A arquitetura deve permitir trocar modelo, detector, fonte de imagem e
mecanismo de comparação sem alterar os casos de uso. O domínio não depende
de `DeepFace`, `cv2`, MediaPipe ou PostgreSQL:

```text
Caso de uso → FaceRecognitionProvider (protocolo no domínio)
            → DeepFaceAdapter (infraestrutura)
```

Os embeddings de referência são calculados no cadastro e persistidos com o
nome do modelo. O reconhecimento reutiliza as referências carregadas:

```text
Cadastro:   imagem → detecção → anti-spoofing → embedding → persistência
Presença:   frame  → detecção → anti-spoofing → embedding → comparação → identidade
```

Vetores de modelos diferentes não são comparáveis; trocar `FACE_MODEL` exige
`scripts.backfill_embeddings`.

---

# 6. Princípios obrigatórios

## 6.1 Separação de responsabilidades

Cada módulo tem uma responsabilidade clara. Evitar funções que
simultaneamente recebem input, acessam banco, controlam câmera, executam IA,
exibem interface e implementam regras de negócio.

## 6.2 Dependency Inversion

Domínio e aplicação não dependem diretamente de bibliotecas externas.
Preferir protocolos quando houver benefício real.

## 6.3 Configuração externa

Banco, câmera, modelo, detector, threshold, diretórios, ambiente, limites web
e logging saem do código (`settings.py`, `web_settings.py`, `.env`).

## 6.4 Código testável

Regras de negócio devem ser testáveis sem webcam, interface gráfica,
PostgreSQL real ou modelo de IA real.

## 6.5 Sem código morto

Não adicionar dependências sem uso. Não manter código legado apenas por
segurança. Antes de remover algo, verificar se existe dependência real.

---

# 7. Segurança e biometria

O projeto trabalha com dados biométricos. Toda implementação considera
proteção de imagens e embeddings, controle de acesso, armazenamento seguro,
retenção, exclusão, logs, secrets e menor privilégio.

- Nunca colocar dados biométricos reais no Git.
- Nunca colocar credenciais ou `.env` real no Git.
- Não alterar o limiar de produção `0.30` nem desativar o anti-spoofing sem
  decisão explícita do usuário.
- Não usar datasets externos de rostos nem imagens faciais reais sem
  autorização específica (ver `AGENTS.md`).

---

# 8. Processo de desenvolvimento

Toda alteração significativa segue:

```text
Análise → Decisão arquitetural → Implementação → Testes → Validação → Documentação
```

Não começar uma grande implementação antes de compreender as dependências
existentes. Verificações usuais:

```bash
pytest tests/unit
node --test tests/e2e/web/frontend.test.mjs
ruff check .
mypy
```

---

# 9. Regras para o Claude

Você deve:

- analisar antes de alterar;
- preservar funcionalidades existentes quando possível;
- propor mudanças incrementais;
- explicar decisões arquiteturais importantes;
- testar alterações;
- atualizar documentação quando necessário;
- apontar riscos;
- evitar overengineering.

Você não deve:

- reescrever tudo sem necessidade;
- criar abstrações inúteis;
- adicionar dependências sem justificativa;
- esconder erros;
- utilizar `except Exception` sem tratamento apropriado;
- colocar SQL espalhado em casos de uso;
- colocar lógica de negócio na interface;
- colocar chamadas de DeepFace diretamente no domínio;
- criar configurações hardcoded;
- utilizar SQLite como banco da aplicação.

Em caso de conflito, as regras do usuário em `AGENTS.md` (autorizações,
commits, dados) prevalecem sobre preferências de implementação.

---

# 10. Critério de conclusão

Uma tarefa só está concluída quando:

- a implementação estiver realizada;
- os testes relevantes passarem;
- o comportamento esperado estiver validado;
- a documentação necessária estiver atualizada;
- não houver erros conhecidos ignorados;
- as alterações estiverem coerentes com a arquitetura.

Quando algo não puder ser concluído, declarar explicitamente o que foi feito,
o que não foi feito, o motivo, o impacto e o próximo passo recomendado.
