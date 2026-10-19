# Tarefas de implementação

Cada pasta contém um desenho aprovado internamente, um plano executável e um prompt para o agente responsável. Estes documentos não significam que a implementação já foi realizada.

## Regra obrigatória para todas as tarefas

Antes de qualquer commit ou push, o executor deve ler ou reler o `AGENTS.md`
da raiz e seguir as instruções vigentes. Commits devem ser em PT-BR, sem
`Co-authored-by` ou identificação do executor como Co Author, usando somente a
identidade e as credenciais Git do solicitante. Quando houver muitos arquivos
ou unidades lógicas distintas, dividir em commits organizados por escopo e
revisar o staging antes de cada commit. Em 18/10/2026, o solicitante autorizou
permanentemente os commits necessários e o push para `main` ao pedir a
implementação de uma tarefa; não pedir nova autorização, salvo instrução
posterior em contrário. Isso não autoriza force push, publicar alterações
alheias ou fazer deploy.

| ID | Tarefa | Executor previsto | Estado |
|---|---|---|---|
| 001 | Qualidade de captura: nitidez, iluminação e tamanho da face | Luna 6, esforço High | Concluída; implementação publicada na main |
| 002 | Consistência temporal e validade da identificação antes do registro | Luna 6, esforço High | Concluída; implementação publicada na main |
| 003 | Rejeição por ambiguidade entre identidades candidatas | Luna 6, esforço High | Concluída; implementação publicada na main |
| 004 | Benchmark de matching: equivalência, latência e memória | Luna 6, esforço High | Implementação, testes e três medições concluídos; veja o resultado |
| 005 | Consolidação documental e demonstração acadêmica offline | Luna 6, esforço High | Documentação e verificações concluídas; veja [RESULTADO.md](005-consolidacao-demonstracao/RESULTADO.md) e a confirmação na resposta da execução |
| 006 | Landmarks faciais na prévia de cadastro | Luna 6, esforço High | Correção técnica validada no workspace; inspeção visual manual pendente; veja [RESULTADO.md](006-facial-landmarks/RESULTADO.md) |
| 007 | Captura automática no cadastro e registro de presença | Luna 6, esforço High | Implementação e verificações concluídas; veja [RESULTADO.md](007-captura-automatica/RESULTADO.md) |
| 008 | Turmas, vínculos de alunos e presença por turma | Luna 6, esforço High | Migration 0004 aplicada ao PostgreSQL local; 955 unitários, Ruff, mypy, formato e `alembic check` aprovados; testes de integração/BDD pendentes; veja [RESULTADO.md](008-turmas/RESULTADO.md) |

## Como executar

### FaceDiff web — novo ciclo 009–020

Decisão de 17/10/2026: **funcionalidades e testes primeiro; interface somente
na tarefa 020**, após aprovação do backend na tarefa 019. API/testes HTTP não incluem telas
provisórias. As tarefas 009–016 foram implementadas no workspace; 010, 013,
014, 015 e 016 foram publicadas na `main`. A migration 0011 da task016 está
aplicada ao banco local `escola` e validada em PostgreSQL descartável. As migrations
0006–0010 foram validadas
em PostgreSQL descartável. A stack ML foi
instalada/importada em Ubuntu 24.04/Python 3.12; a tarefa 013 também validou o
provider MediaPipe Linux com modelo local e entrada sintética em WSL/Python 3.14.
As migrations 0006–0010 foram verificadas em PostgreSQL descartável e revertidas
pela fixture. Nenhuma validação biométrica com pessoas nem deploy foi executado.
Os artefatos da tarefa 018 estão implementados e parcialmente validados no
workspace: configuração Compose estática e testes passaram; build das imagens,
validação do Caddy e execução integrada aguardam um Docker Engine acessível.
Nenhum serviço foi iniciado. A tarefa 017 tem implementação no workspace, com
roundtrip real PostgreSQL/rclone e Drive ainda pendentes; consulte seu resultado
e os resultados 012–016.
Tarefa 010 foi implementada e publicada na `main`; revisão `0005` aplicada ao
banco local `escola`, 3 testes PostgreSQL descartáveis aprovados e
`alembic check` limpo; sem deploy; veja
[RESULTADO.md](010-web-autenticacao-autorizacao/RESULTADO.md).
Em 18/10/2026, o usuário autorizou migrations e testes com escrita em bancos
locais de desenvolvimento/teste do projeto, inclusive reset/seed sintético;
consulte o [contrato de migrations](WEB-MIGRACOES.md) para os limites.

Ler o [contrato comum de execução](WEB-CONTRATO-EXECUCAO.md) e o
[contrato de migrations](WEB-MIGRACOES.md). A autorização permanente registrada
no `AGENTS.md` cobre commits organizados e push para `main` quando o usuário pede
a implementação de uma tarefa; não cobre deploy ou operações de infraestrutura.

| ID | Tarefa / desenho | Executor previsto | Estado |
|---|---|---|---|
| 009 | [Fundação web e compatibilidade Linux](009-web-fundacao-linux/DESENHO.md) | Luna 6, esforço High | API e instalação/importação ML Linux concluídas; inferência com pesos pendente; veja [RESULTADO.md](009-web-fundacao-linux/RESULTADO.md) |
| 010 | [Contas, autenticação, professor responsável e auditoria](010-web-autenticacao-autorizacao/DESENHO.md) | Luna 6, esforço High | Concluída e publicada na `main`; migration local e integração PostgreSQL validadas; sem deploy; veja [RESULTADO.md](010-web-autenticacao-autorizacao/RESULTADO.md) |
| 011 | [Três referências, cadastro pendente e versionamento biométrico](011-web-referencias-cadastro-pendente/DESENHO.md) | Luna 6, esforço High | Backend e migration 0006 implementados; 1011 unitários, PostgreSQL, Ruff e mypy aprovados no workspace; API/worker foram conectados na tarefa 014; sem interface ou deploy; veja [RESULTADO.md](011-web-referencias-cadastro-pendente/RESULTADO.md) |
| 012 | [Worker facial único, fila limitada e temporários](012-web-worker-fila/DESENHO.md) | Luna 6, esforço High | Implementada e validada no workspace; migration 0007 em banco descartável e depois em `escola` na cadeia da tarefa 016; processadores e rotas conectados na 014/015; sem deploy; veja [RESULTADO.md](012-web-worker-fila/RESULTADO.md) |
| 013 | [Desafio facial no servidor e verificação 1:1](013-web-desafio-verificacao-1a1/DESENHO.md) | Luna 6, esforço High | Implementada e publicada na `main`; migration 0008 e worker validados em banco descartável, 1084 unitários e 5 testes PostgreSQL aprovados; sem interface nem validação biométrica real; veja [RESULTADO.md](013-web-desafio-verificacao-1a1/RESULTADO.md) |
| 014 | [API de cadastro por link e aprovação](014-web-api-cadastro-aprovacao/DESENHO.md) | Luna 6, esforço High | Implementada e publicada na `main`; migration 0009 e 1 teste PostgreSQL validados em banco descartável; 1127 unitários com cobertura 81,87%; sem interface, deploy ou validação com pessoas; veja [RESULTADO.md](014-web-api-cadastro-aprovacao/RESULTADO.md) |
| 015 | [Sessões, tentativas e presença por API](015-web-api-sessoes-presencas/DESENHO.md) | Luna 6, esforço High | Implementada e publicada na `main`; migration 0010 e 5 testes PostgreSQL validados em banco descartável, 11 testes HTTP, 1160 unitários e cobertura de 80,09%; veja [RESULTADO.md](015-web-api-sessoes-presencas/RESULTADO.md) |
| 016 | [CRUD autorizado, revisão manual, auditoria e CSV](016-web-gestao-revisao-relatorios/DESENHO.md) | Luna 6, esforço High | Concluída; 1209 aprovados, 80 ignorados, 80,23% de cobertura; dois testes PostgreSQL e `alembic check` aprovados; migration 0011 aplicada a `escola`; sem deploy; veja [RESULTADO.md](016-web-gestao-revisao-relatorios/RESULTADO.md) |
| 017 | [Backup cifrado, retenção e restauração](017-web-backup-retencao/DESENHO.md) | Luna 6, esforço High | Parcial e publicada na `main`; testes unitários e verificações locais registrados; roundtrip PostgreSQL/rclone e Drive pendentes; veja [RESULTADO.md](017-web-backup-retencao/RESULTADO.md) |
| 018 | [Artefatos de implantação Ubuntu, Compose e Caddy](018-web-infraestrutura-compose/DESENHO.md) | Luna 6, esforço High | Artefatos implementados; configuração Compose estática e 24 testes focados aprovados; build/execução pendentes por Docker Engine inacessível; veja [RESULTADO.md](018-web-infraestrutura-compose/RESULTADO.md) |
| 019 | [Validação integrada do backend e gate para a interface](019-web-validacao-backend/DESENHO.md) | Luna 6, esforço High | Validação sintética e PostgreSQL concluída; gate do backend bloqueado por falta do rclone para restore cifrado local; operação com dados reais pendente; veja [RESULTADO.md](019-web-validacao-backend/RESULTADO.md) |
| 020 | [Interface web responsiva e validação ponta a ponta](020-web-interface-final/DESENHO.md) | Luna 6, esforço High | Planejada; não implementada |

Começar pelo [prompt da tarefa 009](009-web-fundacao-linux/PROMPT.md).
Executar uma tarefa de cada vez e ler o resultado das dependências. A tarefa 020 não
pode começar com testes apenas preparados: exige o gate da tarefa 019 aprovado. Testes de
navegador/câmera e acessibilidade ficam na tarefa 020, depois da construção da interface.
Medição real da VPS, conexão Drive e dados reais continuam sujeitos a gates
operacionais próprios e autorização; não são aprovados por testes sintéticos.

Os documentos consolidados estão no [planejamento](../docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md),
[arquitetura](../docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md) e
[roadmap](../docs/FACEDIFF-WEB-ROADMAP.md).

### Ciclo anterior — 001–008

Tarefa **008 — turmas e presença por turma**: [desenho](008-turmas/DESENHO.md), [plano de migração e resultado da aplicação](008-turmas/MIGRACAO.md), [plano](008-turmas/PLANO.md), [prompt para Luna 6 High](008-turmas/PROMPT.md) e [resultado](008-turmas/RESULTADO.md). A entrega implementa matrícula global única, vínculo N:N, contexto de turma e preservação do histórico legado. A migration `0004` foi aplicada ao PostgreSQL local configurado; os testes de integração continuam pendentes e exigem bancos descartáveis identificados.

Tarefa **007 — captura automática no cadastro e na presença**: [desenho](007-captura-automatica/DESENHO.md), [plano](007-captura-automatica/PLANO.md), [prompt](007-captura-automatica/PROMPT.md) e [resultado](007-captura-automatica/RESULTADO.md). O fluxo padrão busca ao abrir a câmera, exige sequência válida de 5 segundos configuráveis e realiza uma operação por sessão, sem ESPAÇO/ENTER. `FACE_AUTO_CAPTURE_ENABLED=false` recupera o modo manual. Nenhuma dependência nova.

Tarefa **006 — landmarks faciais na prévia de cadastro**: [desenho](006-facial-landmarks/DESENHO.md), [dependências](006-facial-landmarks/DEPENDENCIAS.md), [plano](006-facial-landmarks/PLANO.md), [prompt](006-facial-landmarks/PROMPT.md), [correção de compatibilidade](006-facial-landmarks/PLANO-CORRECAO.md) e [resultado](006-facial-landmarks/RESULTADO.md). A aplicação usa um worker MediaPipe em ambiente local separado. A inspeção visual manual permanece pendente.

1. Abra uma sessão no repositório com Luna 6 e esforço High.
2. Envie o prompt da tarefa escolhida: [001 — qualidade](001-qualidade-captura/PROMPT.md), [002 — consistência temporal](002-consistencia-temporal/PROMPT.md), [003 — ambiguidade](003-rejeicao-ambiguidade/PROMPT.md), [004 — benchmark](004-benchmark-matching/PROMPT.md), [005 — consolidação e demonstração](005-consolidacao-demonstracao/PROMPT.md), [006 — landmarks](006-facial-landmarks/PROMPT.md), [007 — captura automática](007-captura-automatica/PROMPT.md) ou [008 — turmas](008-turmas/PROMPT.md).
3. O executor lê o desenho e o plano, implementa, testa e documenta. Só publica na `main` quando houver autorização explícita vigente para a execução; antes de qualquer commit ou push, relê `AGENTS.md` e aplica a regra acima.

A tarefa 001 foi implementada, verificada e publicada conforme o resultado registrado em [001-qualidade-captura/RESULTADO.md](001-qualidade-captura/RESULTADO.md). Não há tarefas de datasets externos neste pacote.

A tarefa 002 parte do código concluído da 001. A implementação optativa, os testes e os limites das evidências estão registrados em [002-consistencia-temporal/RESULTADO.md](002-consistencia-temporal/RESULTADO.md).

A tarefa 003 parte das duas implementações anteriores. Seu [desenho](003-rejeicao-ambiguidade/DESENHO.md) define a comparação entre as duas melhores identidades; o [plano](003-rejeicao-ambiguidade/PLANO.md) cobre integração e testes. Implementação, validações, limites e publicação estão em [003-rejeicao-ambiguidade/RESULTADO.md](003-rejeicao-ambiguidade/RESULTADO.md).

A tarefa 004 aprofunda o benchmark existente conforme a ordem proposta nesta conversa: [desenho](004-benchmark-matching/DESENHO.md), [plano](004-benchmark-matching/PLANO.md) e [resultado](004-benchmark-matching/RESULTADO.md), com três JSONs agregados em [evidencias](004-benchmark-matching/evidencias/). A numeração das tarefas não replica a lista de prioridades do AGENTS.md: múltiplas referências por pessoa continuam adiadas. O estado de publicação é informado na resposta da execução.

A tarefa 005 consolida o estado atual e prepara uma demonstração offline: [desenho](005-consolidacao-demonstracao/DESENHO.md), [plano](005-consolidacao-demonstracao/PLANO.md) e [prompt](005-consolidacao-demonstracao/PROMPT.md). É uma entrega documental, distinta da Etapa 5 histórica de ML. Reutiliza as evidências de 001–004, sem novos datasets ou mudanças operacionais.

O resultado 005 registra as divergências reconciliadas, os comandos offline executados e seus limites: [005-consolidacao-demonstracao/RESULTADO.md](005-consolidacao-demonstracao/RESULTADO.md).
