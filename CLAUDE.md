# CLAUDE.md

# Sistema de Reconhecimento Facial para Controle de Presença

## 1. Objetivo do projeto

Este projeto é uma aplicação acadêmica da disciplina de Inteligência Artificial da Fatec para apoiar o controle de presença com reconhecimento facial. **Não é um TCC.** O objetivo é demonstrar conceitos de IA e engenharia de software, sem confundir funcionamento do código com desempenho biométrico comprovado.

O código deve demonstrar:

- organização arquitetural;
- aplicação adequada de conceitos de Engenharia de Software;
- utilização consciente de Inteligência Artificial;
- separação de responsabilidades;
- persistência de dados;
- tratamento de erros;
- testes automatizados;
- preocupação com segurança;
- preocupação com dados biométricos;
- documentação técnica;
- capacidade de evolução.

O sistema atual tem arquitetura em camadas, persistência PostgreSQL, embeddings FaceNet512, anti-spoofing e decisões de matching testáveis. Qualidade de captura, consistência temporal e rejeição por ambiguidade são optativas e desligadas por padrão. O limiar operacional continua em `0.30`. O registro verificável do estado, das evidências e das pendências está em [`docs/ESTADO-ATUAL-E-EVIDENCIAS.md`](docs/ESTADO-ATUAL-E-EVIDENCIAS.md).

A tarefa 008 prepara operações por turma e a migration Alembic `0004`, sem
aplicá-la. O código atual exige o schema novo; até haver implantação
coordenada e integração PostgreSQL autorizada, ele não deve ser conectado ao
banco operacional. Regras e procedimento estão em [`docs/TURMAS.md`](docs/TURMAS.md).

---

# 2. Baseline histórico do protótipo

O retrato abaixo descreve o estado inicial auditado em 2026-09-07; **não é
uma descrição da implementação atual**. A auditoria completa foi preservada
em [`docs/baseline-arquitetura.md`](docs/baseline-arquitetura.md), e o plano
histórico de execução está em [`REFACTORING_PLAN.md`](REFACTORING_PLAN.md).

O projeto originalmente possui:

- Python;
- OpenCV;
- DeepFace;
- modelo Facenet512;
- detector OpenCV;
- SQLite;
- interface CLI;
- webcam local;
- arquivo monolítico `cadastro.py`.

Naquele baseline, responsabilidades de apresentação, câmera, reconhecimento facial e persistência estavam fortemente acopladas.

O banco original utilizava SQLite e continha as entidades `alunos` e `presencas`; a aplicação atual usa PostgreSQL.

Naquele baseline, a implementação não possuía:

- arquitetura em camadas formal;
- ORM;
- migrations;
- testes automatizados;
- API;
- autenticação;
- logging estruturado;
- configuração por ambiente;
- abstração do mecanismo de reconhecimento;
- persistência de embeddings;
- anti-spoofing;
- métricas de avaliação do modelo.

Essas informações devem ser consideradas o baseline arquitetural do projeto.

---

# 3. Arquitetura atual

A aplicação segue uma arquitetura modular em camadas, com clara separação entre:

```text
Presentation
     ↓
Application
     ↓
Domain
     ↓
Infrastructure
```

Estrutura representativa:

```text
src/
├── presentation/
│   └── cli/
│
├── application/
│   ├── use_cases/
│   └── dto/
│
├── domain/
│   ├── entities/
│   ├── repositories/
│   └── services/
│
├── infrastructure/
│   ├── database/
│   ├── repositories/
│   ├── face_recognition/
│   ├── camera/
│   └── storage/
│
└── config/
```

Não aplicar arquitetura complexa sem justificativa.

---

# 4. Banco de dados

O banco oficial do projeto será:

**PostgreSQL**

A migração para PostgreSQL foi executada. SQLite aparece somente no histórico do protótipo e em fixtures sintéticas de compatibilidade.

A persistência deverá utilizar uma camada de acesso apropriada e migrations versionadas.

A conexão com PostgreSQL deverá ser configurável por variável de ambiente.

Exemplo conceitual:

```text
DATABASE_URL
```

Credenciais nunca devem ser gravadas no código.

O banco não deve ser criado ou alterado silenciosamente durante a execução da aplicação.

Schema e migrations pertencem ao processo de infraestrutura/desenvolvimento.

Conforme o registro de estado em `AGENTS.md`, a revisão `0004` foi aplicada ao
PostgreSQL local configurado na tarefa 008; em 19/10/2026, as revisões
`0006–0011` foram aplicadas ao banco local `escola`, que estava na `0005`.
Esses relatos não comprovam o estado atual de qualquer outro banco. Não execute
upgrade ou downgrade como parte de testes rotineiros: fixtures PostgreSQL
podem truncar tabelas e exigem opt-in e banco descartável com marcador.

O backend web foi desenvolvido nas tarefas 009–019. A tarefa 019A adicionou
rate limits configuráveis às rotas públicas de cadastro e aprovou o gate do
backend com roundtrip de backup/restore e runtime Docker/Compose Linux descartáveis.
Consulte `tasks/019a-fechamento-backend/RESULTADO.md`. A interface 020 tem
implementação parcial no workspace; inspeção visual e E2E em navegador estão
pendentes no resultado da tarefa. Operação com dados reais, deploy e validação
biométrica continuam pendentes e são gates separados.

---

# 5. Reconhecimento facial

O sistema utiliza atualmente:

- DeepFace;
- Facenet512;
- OpenCV;
- webcam local.

A arquitetura deve permitir futuramente substituir:

- modelo;
- detector;
- fonte de imagem;
- mecanismo de comparação;

sem exigir alterações nos casos de uso do sistema.

O domínio não deve depender diretamente de `DeepFace`, `cv2` ou PostgreSQL.

Exemplo conceitual:

```text
Application
     ↓
FaceRecognitionService
     ↓
FaceRecognitionProvider
     ↓
DeepFaceProvider
```

O uso direto de bibliotecas de infraestrutura dentro das regras de negócio deve ser evitado.

---

# 6. Embeddings

Os embeddings de referência são calculados no cadastro e persistidos; o fluxo de reconhecimento reutiliza as referências carregadas para comparar cada embedding de consulta.

O fluxo atual no cadastro e no reconhecimento é:

```text
Cadastro
   ↓
Imagem
   ↓
Detecção
   ↓
Embedding
   ↓
Persistência
```

e posteriormente:

```text
Frame da câmera
   ↓
Detecção
   ↓
Embedding
   ↓
Comparação com embeddings cadastrados
   ↓
Identidade
```

A estratégia concreta de armazenamento e comparação deverá ser definida pelo arquiteto após avaliar os requisitos e o tamanho esperado do conjunto de alunos.

---

# 7. Princípios obrigatórios

## 7.1 Separação de responsabilidades

Cada módulo deve possuir uma responsabilidade clara.

Evitar funções que simultaneamente:

- recebem input;
- acessam banco;
- controlam câmera;
- executam IA;
- exibem interface;
- implementam regras de negócio.

---

## 7.2 Dependency Inversion

Código de domínio e aplicação não deve depender diretamente de bibliotecas externas.

Preferir interfaces/protocolos quando houver benefício real.

---

## 7.3 Configuração externa

Valores configuráveis devem sair do código.

Exemplos:

- banco;
- câmera;
- modelo;
- detector;
- threshold;
- diretórios;
- ambiente;
- logging.

---

## 7.4 Código testável

Regras de negócio devem poder ser testadas sem:

- webcam;
- interface gráfica;
- PostgreSQL real;
- modelo de IA real.

---

## 7.5 Sem código morto

Não adicionar dependências sem utilização.

Não manter código legado apenas por segurança.

Antes de remover algo, verificar se existe alguma dependência real.

---

# 8. Segurança e biometria

O projeto trabalha com dados biométricos.

Toda implementação deve considerar:

- proteção das imagens;
- proteção dos embeddings;
- controle de acesso;
- armazenamento seguro;
- retenção;
- exclusão;
- logs;
- secrets;
- princípio do menor privilégio.

Nunca colocar dados biométricos reais no Git.

Nunca colocar credenciais no Git.

Nunca colocar `.env` real no Git.

---

# 9. Processo de desenvolvimento

Toda alteração significativa deverá seguir:

```text
Análise
   ↓
Decisão arquitetural
   ↓
Implementação
   ↓
Testes
   ↓
Validação
   ↓
Documentação
```

Não começar uma grande implementação antes de compreender as dependências existentes.

---

# 10. Fases do plano original (histórico)

As fases abaixo registram a sequência planejada para a refatoração inicial; não
devem ser lidas como uma lista de tarefas ainda não executadas. As fases 1–9
foram entregues conforme o histórico em `REFACTORING_PLAN.md`, com pendências
de validação ali identificadas. As melhorias posteriores 001–004 e suas
limitações estão no registro atual indicado na seção 1. Avaliação biométrica
representativa e calibração 1:N continuam pendentes. As tarefas 001–008 e
seus limites estão no registro indicado na seção 1; para 008, a revisão `0004`
e a integração PostgreSQL permanecem pendentes.

## Fase 0 — Baseline

Documentar o comportamento atual.

## Fase 1 — PostgreSQL

Migrar SQLite para PostgreSQL sem alterar desnecessariamente o comportamento funcional.

## Fase 2 — Arquitetura

Separar apresentação, aplicação, domínio e infraestrutura.

## Fase 3 — Domínio

Criar entidades, casos de uso e contratos.

## Fase 4 — Reconhecimento

Isolar o pipeline de reconhecimento facial.

## Fase 5 — Performance

Persistir/reutilizar embeddings e evitar processamento desnecessário.

## Fase 6 — Segurança

Implementar controles relacionados a dados biométricos.

## Fase 7 — QA

Criar testes unitários, integração e cenários BDD.

## Fase 8 — Interface

Melhorar a experiência de utilização.

## Fase 9 — Documentação

Atualizar arquitetura, README, diagramas e roteiro de apresentação.

---

# 11. Regras para o Claude

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
- utilizar SQLite após a migração oficial para PostgreSQL.

---

# 12. Agentes

Os agentes especializados estão em:

```text
instructions/
├── 00-orquestrador.md
├── 01-arquiteto.md
├── 02-desenvolvedor.md
└── 03-qa.md
```

Cada agente deve respeitar este documento.

Em caso de conflito:

```text
CLAUDE.md
    ↓
00-orquestrador.md
    ↓
01-arquiteto.md
02-desenvolvedor.md
03-qa.md
```

---

# 13. Critério de conclusão

Uma tarefa somente deve ser considerada concluída quando:

- implementação estiver realizada;
- testes relevantes passarem;
- comportamento esperado estiver validado;
- documentação necessária estiver atualizada;
- não houver erros conhecidos ignorados;
- alterações estiverem coerentes com a arquitetura.

Quando algo não puder ser concluído, declarar explicitamente:

- o que foi feito;
- o que não foi feito;
- motivo;
- impacto;
- próximo passo recomendado.
