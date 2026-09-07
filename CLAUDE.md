# CLAUDE.md

# Sistema de Reconhecimento Facial para Controle de Presença

## 1. Objetivo do projeto

Este projeto é um sistema acadêmico de Inteligência Artificial para controle de presença de alunos utilizando reconhecimento facial.

O projeto será utilizado como trabalho acadêmico, portanto o objetivo não é apenas fazer o sistema funcionar.

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

A implementação atual é um protótipo funcional, porém imaturo.

A missão deste processo é transformar gradualmente o protótipo em um sistema organizado, testável, sustentável e apresentável academicamente.

---

# 2. Estado inicial conhecido

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

Atualmente, responsabilidades de apresentação, câmera, reconhecimento facial e persistência estão fortemente acopladas.

O banco original utiliza SQLite e contém as entidades `alunos` e `presencas`.

A implementação atual não possui:

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

# 3. Arquitetura alvo

A arquitetura deverá evoluir para uma arquitetura modular em camadas, com clara separação entre:

```text
Presentation
     ↓
Application
     ↓
Domain
     ↓
Infrastructure
```

Uma possível estrutura inicial:

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

A estrutura final poderá ser ajustada pelo arquiteto após análise do projeto.

Não aplicar arquitetura complexa sem justificativa.

---

# 4. Banco de dados

O banco oficial do projeto será:

**PostgreSQL**

SQLite não deverá permanecer como banco principal após a migração.

A persistência deverá utilizar uma camada de acesso apropriada e migrations versionadas.

A conexão com PostgreSQL deverá ser configurável por variável de ambiente.

Exemplo conceitual:

```text
DATABASE_URL
```

Credenciais nunca devem ser gravadas no código.

O banco não deve ser criado ou alterado silenciosamente durante a execução da aplicação.

Schema e migrations pertencem ao processo de infraestrutura/desenvolvimento.

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

O sistema deve evoluir para evitar o recálculo desnecessário dos embeddings das faces cadastradas.

O fluxo alvo é conceitualmente:

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

# 10. Fases oficiais

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
