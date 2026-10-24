# AGENTS.md — Regras e contexto do projeto (reconhecimento facial)

> Regras do solicitante e contexto para agentes (Codex CLI, Claude Code). **Não
> substitui a inspeção do repositório**: confirme implementações, nomes de
> arquivos, dependências e estado do Git antes de alterar qualquer coisa. A
> arquitetura e os comandos estão no [`README.md`](README.md); os princípios de
> código, no [`CLAUDE.md`](CLAUDE.md).

## 1. Objetivo e escopo

- Projeto acadêmico de uma **disciplina de Inteligência Artificial da Fatec**,
  **não é TCC**.
- Aplicação de reconhecimento facial para registro de presença, com interface
  web (FaceDiff) e CLI.
- Objetivo atual: aprimorar robustez, qualidade da decisão, eficiência e
  demonstração de conceitos de IA **sem depender de datasets externos de
  rostos**.
- Não alegar ganhos de acurácia biométrica sem experimentos reais e
  metodologicamente adequados.

## 2. Stack e estado (verificar no código)

- Python 3.12; FastAPI/Uvicorn na web; OpenCV; DeepFace com FaceNet512
  pré-treinado (embeddings de 512 dimensões); MiniFASNet para anti-spoofing;
  MediaPipe em processo isolado para o desafio de pose; NumPy; PostgreSQL 16
  com SQLAlchemy 2 e Alembic; Pytest e testes Node para o frontend.
- Comparação por distância cosseno, limiar operacional `FACE_THRESHOLD=0.30`.
  A CLI faz identificação aberta 1:N (`src/domain/services/matcher.py`); a web
  faz verificação 1:1 pela mediana das distâncias a três referências
  (`src/domain/services/verificacao_identidade.py`).
- Não confundir resultados obtidos com anti-spoofing desligado com o
  desempenho completo do sistema.
- A API web enfileira jobs em PostgreSQL; um único worker facial os processa
  (`src/face_worker_main.py`). Runtime local: perfil `web` do
  `docker-compose.yml`. Artefatos de deploy em `deploy/web/`; **nenhum deploy
  foi feito**. Opções de HTTPS/domínio em
  [`docs/FACEDIFF-WEB-HTTPS-DOMINIO.md`](docs/FACEDIFF-WEB-HTTPS-DOMINIO.md).
- Migrations `0001`–`0011`. Em 19/10/2026 o banco local `escola` foi levado de
  `0005` a `0011` e `alembic check` passou. Isso não comprova o estado de
  outros bancos; verifique cada ambiente separadamente.
- O registro de estado, evidências e pendências está em
  [`docs/ESTADO-ATUAL-E-EVIDENCIAS.md`](docs/ESTADO-ATUAL-E-EVIDENCIAS.md).
  Planejamento web futuro em
  [`docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`](docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md);
  é planejamento, não autorização para implementar, migrar, contratar
  hospedagem ou publicar.
- Possível migração futura do PostgreSQL para um serviço gerenciado (por
  exemplo, Neon). **Não presumir que foi implementada.** Para aplicações
  distribuídas, preferir API autenticada a distribuir credenciais do banco.

Os documentos de planejamento por tarefa (`tasks/`), os papéis de agentes
(`instructions/`), `REFACTORING_PLAN.md` e `ARCHITECTURE.md` foram removidos em
24/10/2026. As evidências citadas por eles continuam no histórico do Git (por
exemplo, `git show dfda402:tasks/019a-fechamento-backend/RESULTADO.md`).

## 3. Histórico dos experimentos de ML

- **Etapa 0, infraestrutura experimental:** experimentos reproduzíveis,
  separação por identidade, controles de cache e privacidade.
- **Etapa 1, calibração 1:1:** candidato `0.42817932706540435` para FAR ≤ 0,1%,
  **não aprovado para adoção operacional**. Resultados históricos com LFW,
  verificação 1:1 e sem anti-spoofing: 336 identidades, 1.099 imagens, 2.001
  pares genuínos, 601.350 impostores, ~11,8% de falha de extração. Em `0.30`:
  FAR ~0,0018%, FRR ~38,03%. No candidato: FAR ~0,063%, FRR ~16,39%;
  AUC ~0,9830. Esses números **não representam** sala de aula nem 1:N; o
  teste já foi consultado e não é holdout intocado. Proveniência do LFW e
  sobreposição com o pré-treinamento do FaceNet512 não foram resolvidas.
- **Etapa 2, aprendizado supervisionado:** M0 (`0.30`), M1 (limiar calibrado),
  M2 (regressão logística), M3 (Gaussian Naive Bayes), M4 (árvore de decisão),
  testados só com vetores sintéticos.
- **Etapa 3, identificação aberta 1:N:** galerias conhecidas/desconhecidas,
  FPIR/FNIR, top-1, variantes de limiar e galeria, 1 ou 3 referências,
  bootstrap agrupado. Sem avaliação com imagens biométricas autorizadas.
- **Etapa 4, não supervisionado:** DBSCAN (cosseno), K-Means, Silhouette,
  ARI/NMI, ruído/cobertura e PCA, com testes sintéticos.
- **Etapa 5, consolidação acadêmica:** `docs/ML-*.md` (consolidação, matriz de
  rastreabilidade, comparação de abordagens, reprodutibilidade, roteiro e
  perguntas).

**Não converter métricas históricas de testes sintéticos em alegações de
precisão de reconhecimento facial.**

## 4. Datasets externos: decisão atual

- Foram avaliados FEI, DFW, CelebA, LFW e Olivetti.
- **FEI**: permissão geral de uso em pesquisa, mas proíbe distribuição e
  reprodução. Ainda cabem cuidados com dados pessoais, finalidade e normas
  institucionais.
- **DFW**: exige acordo institucional assinado; burocracia excessiva para a
  necessidade atual.
- **CelebA**: pesquisa não comercial, distribuição proibida; rótulos de
  identidade só sob solicitação.
- **LFW**: o uso histórico na Etapa 1 não autoriza novas avaliações.
- **Decisão atual:** melhorar o sistema **sem importar novos datasets faciais
  externos**. Não fazer download, raspagem, extração de faces da internet ou
  uso de dados operacionais para pesquisa sem autorização adequada.

## 5. Prioridades e limites de evidência

Implementado com flags desligadas por padrão na CLI: qualidade de captura
(heurísticas não calibradas; orientação facial não é checada), consistência
temporal (frames correlacionados não provam ganho de acurácia) e rejeição por
ambiguidade (margem não calibrada). O benchmark de matching é sintético e não
cobre inferência.

Pendente: calibração biométrica real e 1:N, validação representativa do
anti-spoofing, piloto com voluntários e deploy. Essas decisões aguardam dados
autorizados e revisão institucional. Não alterar `FACE_THRESHOLD=0.30` sem
evidência e decisão explícita.

Evidências aceitáveis sem dataset externo:

- testes unitários e de integração com embeddings **sintéticos**;
- benchmarks de engenharia (latência, memória, throughput);
- piloto com voluntários **somente com autorização específica e avaliação
  dos requisitos institucionais e de privacidade**. O cadastro operacional de
  alunos não autoriza reutilização experimental.

Relatórios devem distinguir **comportamento funcional**, **desempenho
computacional** e **desempenho biométrico real**.

## 6. Instruções para o Codex CLI/Claude Code

### Fase atual: ajustes funcionais da aplicação

Desde 21/10/2026, o foco é ajustar, integrar e validar o funcionamento da
aplicação existente, sobretudo a interface web. Não é necessário abrir uma
tarefa numerada para cada ajuste funcional.

Autorização do solicitante: o PostgreSQL local de desenvolvimento da aplicação
pode ser usado para diagnosticar e testar fluxos funcionais. É permitido aplicar
migrations pendentes e criar dados sintéticos ou contas de teste quando necessários.
Preservar os dados existentes por padrão; restringir alterações à base local de
desenvolvimento e evitar reset ou exclusão de dados, salvo necessidade comprovada.
Nunca apontar esses testes para produção. Esta autorização não inclui deploy/VPS,
serviços externos, uso de imagens faciais reais, reutilização de dados operacionais
para pesquisa, mudança do limiar de produção ou desativação do anti-spoofing.

- Antes de propor mudanças, ler `AGENTS.md`, `CLAUDE.md`, o `README.md` e os
  módulos relevantes; confirmar o que realmente existe.
- Verificar `git status`, branch e alterações existentes. **Preservar trabalho do usuário**; não sobrescrever alterações não relacionadas.
- Para cada tarefa: explicar escopo, identificar riscos, propor mudanças pequenas, implementar testes e registrar evidências com comandos e resultados efetivamente executados.
- Usar workflows Superpowers se estiverem disponíveis no ambiente. **Aprovar internamente os próprios planos/especificações rotineiros e continuar a execução**, sem interromper para confirmações desnecessárias; isso **não** autoriza ignorar permissões obrigatórias do ambiente, consentimento, revisão institucional ou pedir menos autorização para ações destrutivas/irreversíveis.
- Migrations e alterações de dados na base local de desenvolvimento estão autorizadas nos limites da seção “Fase atual”; preservar dados e evitar reset ou exclusões salvo necessidade comprovada. Produção e dados biométricos reais continuam fora dessa autorização. Não publicar datasets, mudar o limiar de produção, desabilitar anti-spoofing ou criar commits sem instrução explícita.
- Não afirmar execução de testes, aprovação ética, licenças ou métricas que não tenham sido verificadas.
- Priorizar compatibilidade com o pipeline existente, testes de regressão e separação entre código experimental e operacional.
- Se o pedido envolver uso de imagens faciais reais, verificar antes a origem, permissão, finalidade, armazenamento, retenção e controles de acesso; em caso de incerteza, não ingerir esses dados.
- Antes de qualquer commit ou push, reler `AGENTS.md` na raiz e seguir suas instruções vigentes. Usar a convenção global **Conventional Commits**: `tipo(escopo): descrição`, com escopo quando aplicável e descrição em PT-BR (por exemplo, `feat(cadastro-web): limitar requisições públicas` ou `docs(repo): atualizar README`). Escolher o tipo adequado (`feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore` ou `revert`). Se a entrega envolver muitos arquivos ou unidades lógicas distintas, dividir em commits separados por escopo/unidade lógica e manter cada mensagem nessa convenção. Revisar o staging e seu diff antes de cada commit. Não se marcar como Co Author nem adicionar `Co-authored-by`; usar somente a identidade e as credenciais Git já configuradas do solicitante, sem reconfigurar autoria.

Autorização permanente do solicitante registrada em 18/10/2026: quando pedir a
implementação de uma tarefa, o usuário autoriza os commits necessários e o push
para `main` ao concluir. Não pedir nova autorização para essa publicação, salvo
se o usuário limitar ou revogar a instrução. Esta autorização não cobre force
push, publicação de trabalho alheio, deploy, nem operações de infraestrutura.

## 7. Gates pendentes

O gate operacional de dados reais segue `PENDENTE`: não houve deploy, VPS,
backup remoto em operação nem validação biométrica com pessoas. Testes de
integração PostgreSQL/BDD de turmas exigem bancos descartáveis com marcador e
continuam como validação separada. O projeto é de **disciplina de IA**, não
TCC; não transformar testes sintéticos ou benchmarks de engenharia em
alegações de acurácia.
