# Tarefas de implementação

Cada pasta contém um desenho aprovado internamente, um plano executável e um prompt para o agente responsável. Estes documentos não significam que a implementação já foi realizada.

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
na020**, após aprovação do backend na019. API/testes HTTP não incluem telas
provisórias. A tarefa 009 foi implementada no workspace; runtime web e stack ML
instalada/importada passaram em Ubuntu 24.04/Python 3.12. Inferência com pesos e
validação integrada continuam pendentes. As tarefas 010–020 seguem planejadas.

Ler o [contrato comum de execução](WEB-CONTRATO-EXECUCAO.md) e o
[contrato de migrations](WEB-MIGRACOES.md). A autorização de commit/push dos
pacotes antigos não se estende automaticamente aos novos; publicação e ações
de infraestrutura dependem de autorização explícita vigente.

| ID | Tarefa / desenho | Executor previsto | Estado |
|---|---|---|---|
| 009 | [Fundação web e compatibilidade Linux](009-web-fundacao-linux/DESENHO.md) | Luna 6, esforço High | API e instalação/importação ML Linux concluídas; inferência com pesos pendente; veja [RESULTADO.md](009-web-fundacao-linux/RESULTADO.md) |
| 010 | [Contas, autenticação, professor responsável e auditoria](010-web-autenticacao-autorizacao/DESENHO.md) | Luna 6, esforço High | Planejada; não implementada |
| 011 | [Três referências, cadastro pendente e versionamento biométrico](011-web-referencias-cadastro-pendente/DESENHO.md) | Luna 6, esforço High | Planejada; não implementada |
| 012 | [Worker facial único, fila limitada e temporários](012-web-worker-fila/DESENHO.md) | Luna 6, esforço High | Planejada; não implementada |
| 013 | [Desafio facial no servidor e verificação 1:1](013-web-desafio-verificacao-1a1/DESENHO.md) | Luna 6, esforço High | Planejada; não implementada |
| 014 | [API de cadastro por link e aprovação](014-web-api-cadastro-aprovacao/DESENHO.md) | Luna 6, esforço High | Planejada; não implementada |
| 015 | [Sessões, tentativas e presença por API](015-web-api-sessoes-presencas/DESENHO.md) | Luna 6, esforço High | Planejada; não implementada |
| 016 | [CRUD autorizado, revisão manual, auditoria e CSV](016-web-gestao-revisao-relatorios/DESENHO.md) | Luna 6, esforço High | Planejada; não implementada |
| 017 | [Backup cifrado, retenção e restauração](017-web-backup-retencao/DESENHO.md) | Luna 6, esforço High | Planejada; não implementada |
| 018 | [Artefatos de implantação Ubuntu, Compose e Caddy](018-web-infraestrutura-compose/DESENHO.md) | Luna 6, esforço High | Planejada; não implementada |
| 019 | [Validação integrada do backend e gate para a interface](019-web-validacao-backend/DESENHO.md) | Luna 6, esforço High | Planejada; não implementada |
| 020 | [Interface web responsiva e validação ponta a ponta](020-web-interface-final/DESENHO.md) | Luna 6, esforço High | Planejada; não implementada |

Começar pelo [prompt009](009-web-fundacao-linux/PROMPT.md).
Executar uma task de cada vez e ler o resultado das dependências. A020 não
pode começar com testes apenas preparados: exige gate019 aprovado. Testes de
navegador/câmera e acessibilidade ficam na020, depois da construção da interface.
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
3. O executor lê o desenho e o plano, implementa, testa, documenta e faz commit + push na `main`, conforme autorização explícita do usuário registrada no prompt.

A tarefa 001 foi implementada, verificada e publicada conforme o resultado registrado em [001-qualidade-captura/RESULTADO.md](001-qualidade-captura/RESULTADO.md). Não há tarefas de datasets externos neste pacote.

A tarefa 002 parte do código concluído da 001. A implementação optativa, os testes e os limites das evidências estão registrados em [002-consistencia-temporal/RESULTADO.md](002-consistencia-temporal/RESULTADO.md).

A tarefa 003 parte das duas implementações anteriores. Seu [desenho](003-rejeicao-ambiguidade/DESENHO.md) define a comparação entre as duas melhores identidades; o [plano](003-rejeicao-ambiguidade/PLANO.md) cobre integração e testes. Implementação, validações, limites e publicação estão em [003-rejeicao-ambiguidade/RESULTADO.md](003-rejeicao-ambiguidade/RESULTADO.md).

A tarefa 004 aprofunda o benchmark existente conforme a ordem proposta nesta conversa: [desenho](004-benchmark-matching/DESENHO.md), [plano](004-benchmark-matching/PLANO.md) e [resultado](004-benchmark-matching/RESULTADO.md), com três JSONs agregados em [evidencias](004-benchmark-matching/evidencias/). A numeração das tarefas não replica a lista de prioridades do AGENTS.md: múltiplas referências por pessoa continuam adiadas. O estado de publicação é informado na resposta da execução.

A tarefa 005 consolida o estado atual e prepara uma demonstração offline: [desenho](005-consolidacao-demonstracao/DESENHO.md), [plano](005-consolidacao-demonstracao/PLANO.md) e [prompt](005-consolidacao-demonstracao/PROMPT.md). É uma entrega documental, distinta da Etapa 5 histórica de ML. Reutiliza as evidências de 001–004, sem novos datasets ou mudanças operacionais.

O resultado 005 registra as divergências reconciliadas, os comandos offline executados e seus limites: [005-consolidacao-demonstracao/RESULTADO.md](005-consolidacao-demonstracao/RESULTADO.md).
