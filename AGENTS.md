# AGENTS.md — Contexto do projeto de IA (reconhecimento facial)

> Documento de contexto para o Codex CLI. Registra o que foi discutido; **não substitui a inspeção do repositório**. Confirme implementações, nomes de arquivos, dependências e estado do Git antes de alterar qualquer coisa.

## 1. Objetivo e escopo

- Projeto acadêmico de uma **disciplina de Inteligência Artificial da Fatec**, **não é TCC**.
- Aplicação de reconhecimento facial para registro de presença. O problema operacional é **identificação aberta 1:N**: comparar uma face capturada com referências de pessoas cadastradas e rejeitar desconhecidos quando necessário.
- Objetivo atual: aprimorar robustez, qualidade da decisão, eficiência e demonstração de conceitos de IA **sem depender de datasets externos de rostos**.
- Não alegar ganhos de acurácia biométrica sem experimentos reais e metodologicamente adequados.

## 2. Stack e arquitetura relatadas (verificar no código)

- Python; OpenCV para captura e detecção facial (Haar Cascade); DeepFace com FaceNet512 pré-treinado para embeddings de 512 dimensões; NumPy; PostgreSQL; Pytest.
- Mecanismo de comparação por distância cosseno e limiar operacional histórico `FACE_THRESHOLD=0.30`.
- Antispoofing com MiniFASNet; não confundir resultados obtidos com antispoofing desligado com o desempenho completo do sistema.
- Possível migração futura do PostgreSQL para Neon para compartilhar cadastros/presenças entre máquinas. **Não presumir que a migração foi implementada.** Para aplicações distribuídas, preferir API autenticada em vez de distribuir credenciais do banco nos clientes.
- Arquivos mencionados anteriormente, sujeitos a verificação: `src/domain/services/matcher.py`, `src/infrastructure/face_recognition/deepface_adapter.py`, `src/config/settings.py`, `src/main.py`, `ARCHITECTURE.md`, `docs/lgpd.md`, `docs/adr/ADR-004-limiar-de-reconhecimento.md`.

O estado confirmado das melhorias de captura, decisão e benchmark está em
[`docs/ESTADO-ATUAL-E-EVIDENCIAS.md`](docs/ESTADO-ATUAL-E-EVIDENCIAS.md).
Esse registro distingue o código atual dos resultados históricos e das
pendências biométricas.

A tarefa 008 implementa operações com contexto de turma, vínculo N:N e
presença por turma. A migration `0004` foi aplicada ao PostgreSQL local
configurado; a migration `0005` da autenticação web também foi aplicada ao
banco local `escola`. A migration `0006` de referências web foi validada em um
PostgreSQL descartável; em 19/10/2026, as migrations `0006–0011` também foram
aplicadas em sequência a `escola`, que estava na `0005`. Testes de integração
PostgreSQL/BDD da tarefa 008 permanecem pendentes. O código atual requer esse
schema para o menu de turmas; outros ambientes devem ser verificados
separadamente. Consulte
[`docs/TURMAS.md`](docs/TURMAS.md) e
[`tasks/008-turmas/RESULTADO.md`](tasks/008-turmas/RESULTADO.md) antes de
qualquer implantação.

A tarefa 011 implementa no workspace solicitações de cadastro pendentes,
conjuntos versionados com três referências privadas e casos de uso de aprovação,
atualização e limpeza. O fluxo de convite/API/worker foi conectado pela tarefa
014; não há interface. Consulte
[`tasks/011-web-referencias-cadastro-pendente/RESULTADO.md`](tasks/011-web-referencias-cadastro-pendente/RESULTADO.md).

A tarefa 012 implementa fila PostgreSQL limitada, reserva idempotente, leases,
storage temporário privado, worker serial e consulta autenticada do status. A
migration `0007` foi validada no banco descartável
`task012_web_worker_test_20261018`; em 19/10/2026, foi aplicada também a
`escola` como parte da cadeia `0006–0011` da tarefa 016. As rotas de cadastro e
presença reutilizam esse worker nas tarefas 014 e 015. Worker,
runtime Linux e implantação ainda precisam de
validação integrada na tarefa 019. Consulte
[`tasks/012-web-worker-fila/RESULTADO.md`](tasks/012-web-worker-fila/RESULTADO.md).

A tarefa 013 implementa no worker a verificação web fechada 1:1 com três
referências e desafio facial ordenado; a migration `0008` foi validada no banco
descartável task012; em 19/10/2026, foi aplicada também a `escola` como parte da
cadeia `0006–0011` da tarefa 016. A task014 reutiliza o desafio de pose em coleta
de cadastro; a task013 não possui rota própria, interface, deploy
ou validação biométrica com pessoas. Consulte
[`tasks/013-web-desafio-verificacao-1a1/RESULTADO.md`](tasks/013-web-desafio-verificacao-1a1/RESULTADO.md)
antes de integrar ou implantar.

A tarefa 014 implementa links de cadastro revogáveis, credencial curta,
consentimento, captura de três frames frente/virada/retorno, aprovação/rejeição
por professor e atualização biométrica. A migration `0009` foi validada e
revertida no banco descartável `task014_cadastro_api_test_20261018`. Em
19/10/2026, foi aplicada a `escola` como parte da cadeia `0006–0011` da tarefa
016. Foram aprovados 1127 testes unitários com 81,87% de
cobertura e um teste PostgreSQL transacional. Não há interface, deploy ou
validação com pessoas; limites operacionais gerais contra abuso das rotas
públicas continuam pendentes. Consulte
[`tasks/014-web-api-cadastro-aprovacao/RESULTADO.md`](tasks/014-web-api-cadastro-aprovacao/RESULTADO.md).

A tarefa 015 implementa sessões de presença, links por sessão, tentativas
limitadas/idempotentes, recebimento de capturas pelo servidor e commit
transacional revalidado pelo worker. A migration `0010` foi validada em banco
PostgreSQL descartável e revertida pela fixture. Em 19/10/2026, foi aplicada a
`escola` como parte da cadeia `0006–0011` da tarefa 016. Cinco testes
PostgreSQL, testes HTTP e 1160 unitários passaram, com cobertura
total de 80,09%. A entrega não inclui interface, deploy ou validação biométrica
com pessoas. O rate limit HMAC vale apenas para as rotas de presença. Consulte
[`tasks/015-web-api-sessoes-presencas/RESULTADO.md`](tasks/015-web-api-sessoes-presencas/RESULTADO.md).

A tarefa 016 implementa gestão web autorizada, revisão/correção manual de
presença versionada e auditada, painel agregado, CSV seguro e reativação
administrativa auditada de quota. A migration `0011` foi aplicada a `escola`
(que estava na `0005`) e validada em PostgreSQL descartável com dois testes,
incluindo lock/concorrência real. `alembic check` passou no banco descartável e
em `escola`. A suíte completa passou com 1209 testes, 80 ignorados e 80,23% de
cobertura; Ruff, formato e mypy passaram. Não houve validação biométrica com
pessoas, interface ou deploy. Consulte
[`tasks/016-web-gestao-revisao-relatorios/RESULTADO.md`](tasks/016-web-gestao-revisao-relatorios/RESULTADO.md)
e [`docs/FACEDIFF-WEB-GESTAO.md`](docs/FACEDIFF-WEB-GESTAO.md).

## 3. Histórico dos experimentos de ML

### Etapa 0 — Infraestrutura experimental

- Organização de experimentos reproduzíveis, separação por identidade, controles de cache e privacidade.

### Etapa 1 — Calibração de verificação 1:1

- Limiar histórico operacional: `0.30`.
- Candidato de validação previamente obtido: `0.42817932706540435` para meta de FAR <= 0,1%; **não aprovado para adoção operacional**.
- Resultados históricos com LFW, verificação **1:1**, sem antispoofing: 336 identidades; 1.099 imagens; 2.001 pares genuínos; 601.350 pares impostores; extração falhou em aproximadamente 11,8%.
- Para limiar `0.30`: FAR ~0,0018%, FRR ~38,03%. Para candidato calibrado: FAR ~0,063%, FRR ~16,39%; AUC ~0,9830.
- Esses resultados **não representam** desempenho em sala de aula ou identificação **1:N**. O teste histórico já foi consultado; não tratá-lo como holdout intocado. Origem/autorização de reutilização do LFW e possível sobreposição com o pré-treinamento do FaceNet512 não foram resolvidas.

### Etapa 2 — Aprendizado supervisionado

- Implementados experimentos para baseline M0 (`0.30`), M1 (limiar calibrado), M2 (regressão logística), M3 (Gaussian Naive Bayes), M4 (árvore de decisão).
- Testes com vetores sintéticos; **não houve treinamento/avaliação biométrica real autorizada**.

### Etapa 3 — Identificação aberta 1:N

- Infraestrutura experimental para galerias conhecidas/desconhecidas, FPIR/FNIR, top-1, variantes de limiar e tamanhos de galeria, 1 ou 3 embeddings de referência, bootstrap agrupado.
- **Sem avaliação real com imagens biométricas autorizadas**.

### Etapa 4 — Aprendizado não supervisionado

- Experimentos DBSCAN (distância cosseno), K-Means como baseline, Silhouette, ARI/NMI quando existem rótulos legítimos, ruído/cobertura, PCA.
- Testes sintéticos; **sem avaliação real com rostos autorizados**.
- Relato histórico: 597 testes da suíte completa passaram ao final desta etapa.

### Etapa 5 — Consolidação acadêmica

- Documentação, matriz de rastreabilidade, comparação de abordagens, guia de reprodutibilidade, roteiro de apresentação e perguntas para avaliação.
- Relato histórico: 518 testes unitários, Ruff e mypy passaram; a suíte completa não foi reexecutada nessa etapa.
- Conferir arquivos existentes em `docs/ML-ETAPA-*-RESULTADO.md`, `docs/ML-CONSOLIDACAO-ACADEMICA.md`, `docs/ML-MATRIZ-RASTREABILIDADE.md`, `docs/ML-COMPARACAO-ABORDAGENS.md`, `docs/ML-GUIA-REPRODUTIBILIDADE.md`, `docs/ML-ROTEIRO-APRESENTACAO.md`, `docs/ML-PERGUNTAS-BANCA.md`.
- **Não converter métricas históricas de testes sintéticos em alegações de precisão de reconhecimento facial.**

## 4. Datasets externos: decisão atual

- Foram avaliados FEI, DFW, CelebA, LFW e Olivetti.
- **FEI**: página informa permissão geral de uso por pesquisadores para pesquisa, mas proíbe distribuição e reprodução. Não há exigência explícita de solicitação individual nessa declaração. Ainda cabem cuidados com dados pessoais, finalidade e normas institucionais.
- **DFW**: acesso condicionado a acordo institucional, assinado por representante autorizado; burocracia excessiva para a necessidade atual.
- **CelebA**: uso em pesquisa não comercial; distribuição proibida; rótulos de identidade disponibilizados mediante solicitação, limitando avaliação supervisionada/1:N sem contato.
- **LFW**: uso histórico na Etapa 1 não equivale a autorização para novas avaliações; questões de proveniência e consentimento permanecem.
- **Decisão atual:** priorizar melhorias do sistema **sem importar novos datasets faciais externos**. Não fazer download, raspagem, extração de faces da internet ou uso de dados operacionais para pesquisa sem autorização adequada.

## 5. Prioridades de melhoria

Implementar incrementalmente, com desenho, testes e medições adequadas:

1. **Qualidade de captura — implementada na tarefa 001**: nitidez, iluminação e dimensão da face são checadas de forma optativa; múltiplas faces são recusadas pelo adaptador. **Orientação facial não é checada.** Os limites são heurísticas não calibradas.
2. **Consistência temporal — implementada na tarefa 002**: confirmação optativa de observações da mesma identidade e revalidação antes do registro. Frames consecutivos são correlacionados; isso não prova melhora de acurácia.
3. **Ambiguidade entre candidatos — implementada na tarefa 003**: recusa optativa por proximidade entre identidades. Margem positiva não calibrada; zero recusa empates exatos.
4. **Múltiplas referências por identidade — pendente**: somente considerar quando houver cadastros autorizados; avaliar agregação e impacto no desempenho.
5. **Desempenho — benchmark da tarefa 004**: comparação sintética de embeddings 512D, equivalência, latência e memória. Os resultados não são biométricos nem cobrem inferência.
6. **Calibração biométrica real — pendente**: aguardar dados autorizados e representativos; não alterar `FACE_THRESHOLD=0.30` sem evidência e decisão explícita.
7. **Operações por turma — tarefa 008**: matrícula global única, vínculo N:N e presença contextualizada; migration `0004` aplicada ao banco local configurado. Testes de integração PostgreSQL/BDD e atualização coordenada de outros ambientes continuam pendentes.

### Evidências aceitáveis sem dataset externo

- Testes unitários e de integração com embeddings **sintéticos** para lógica de matching, classificadores, clustering, rejeição, empates e bordas.
- Benchmarks de engenharia para latência, memória e throughput.
- Eventual piloto com voluntários **somente com autorização específica e avaliação dos requisitos institucionais e de privacidade**. Não presumir que o cadastro operacional de alunos autorize reutilização experimental.
- Relatórios devem distinguir claramente **comportamento funcional**, **desempenho computacional** e **desempenho biométrico real**.

## 6. Instruções para o Codex CLI/Claude Code

- Antes de propor mudanças, ler `AGENTS.md`, instruções adicionais do repositório (por exemplo, `CLAUDE.md`, `instructions/`, `ARCHITECTURE.md`) e os módulos relevantes; confirmar o que realmente existe.
- Verificar `git status`, branch e alterações existentes. **Preservar trabalho do usuário**; não sobrescrever alterações não relacionadas.
- Para cada tarefa: explicar escopo, identificar riscos, propor mudanças pequenas, implementar testes e registrar evidências com comandos e resultados efetivamente executados.
- Usar workflows Superpowers se estiverem disponíveis no ambiente. **Aprovar internamente os próprios planos/especificações rotineiros e continuar a execução**, sem interromper para confirmações desnecessárias; isso **não** autoriza ignorar permissões obrigatórias do ambiente, consentimento, revisão institucional ou pedir menos autorização para ações destrutivas/irreversíveis.
- Não executar migrações de banco, alterar dados reais, publicar datasets, mudar o limiar de produção, desabilitar antispoofing ou criar commits automaticamente sem instrução explícita.
- Não afirmar execução de testes, aprovação ética, licenças ou métricas que não tenham sido verificadas.
- Priorizar compatibilidade com o pipeline existente, testes de regressão e separação entre código experimental e operacional.
- Se o pedido envolver uso de imagens faciais reais, verificar antes a origem, permissão, finalidade, armazenamento, retenção e controles de acesso; em caso de incerteza, não ingerir esses dados.
- Antes de qualquer commit ou push, reler `AGENTS.md` na raiz e seguir suas instruções vigentes. Commits sempre em PT-BR; não se marcar como Co Author nem adicionar `Co-authored-by`; usar somente a identidade e as credenciais Git já configuradas do solicitante, sem reconfigurar autoria. Se a entrega envolver muitos arquivos ou unidades lógicas distintas, dividir em commits separados e organizados por escopo; revisar o staging e seu diff antes de cada commit.

Autorização permanente do solicitante registrada em 18/10/2026: quando pedir a
implementação de uma tarefa, o usuário autoriza os commits necessários e o push
para `main` ao concluir. Não pedir nova autorização para essa publicação, salvo
se o usuário limitar ou revogar a instrução. Esta autorização não cobre force
push, publicação de trabalho alheio, deploy, nem operações de infraestrutura.

## 7. Próxima direção sugerida

As tarefas 017–019 implementam backup/retencao, artefatos Compose e validação
sintética do backend. A tarefa 019A acrescenta limites às rotas públicas de
cadastro e amplia as provas integradas até painel/CSV. Seu resultado em
19/10/2026 é parcial: `GATE_BACKEND_PARA_INTERFACE` permanece
`BLOQUEADO_POR_AMBIENTE` porque não foi possível executar o roundtrip real
rclone/PostgreSQL nem iniciar o runtime Docker/Linux; ver
[`tasks/019a-fechamento-backend/RESULTADO.md`](tasks/019a-fechamento-backend/RESULTADO.md).
A interface da tarefa 020 não deve começar até o gate ser aprovado com as
provas reais faltantes.
O planejamento futuro da interface de câmera no navegador, operação e hospedagem está em
[`docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`](docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md).
Atualizar esse registro conforme novas decisões do usuário. É planejamento,
não autorização para implementar, migrar, contratar hospedagem ou publicar.

Manter o registro atual e as limitações das tarefas 001–019A atualizados. A
migration `0004` foi aplicada ao PostgreSQL local configurado; testes de
integração PostgreSQL/BDD da tarefa 008 continuam pendentes. Em 19/10/2026,
as migrations `0006–0011` foram aplicadas em sequência ao banco local `escola`,
que estava na `0005`; `alembic check` confirmou o schema em `0011`. Essas são
evidências registradas, não uma autorização para acessar esse banco nesta
tarefa. Consulte os respectivos `RESULTADO.md`. As decisões que dependem de
biometria real — calibração 1:N, validação representativa do anti-spoofing e
eventual piloto — aguardam autorização específica e revisão institucional.
Múltiplas referências operacionais também permanecem pendentes. O projeto é
de **disciplina de IA**, não TCC; não transformar testes sintéticos ou
benchmarks de engenharia em alegações de acurácia.
