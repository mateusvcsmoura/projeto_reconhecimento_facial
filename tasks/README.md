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

## Como executar

Tarefa **006 — landmarks faciais na prévia de cadastro**: [desenho](006-facial-landmarks/DESENHO.md), [dependências](006-facial-landmarks/DEPENDENCIAS.md), [plano](006-facial-landmarks/PLANO.md), [prompt](006-facial-landmarks/PROMPT.md), [correção de compatibilidade](006-facial-landmarks/PLANO-CORRECAO.md) e [resultado](006-facial-landmarks/RESULTADO.md). A aplicação usa um worker MediaPipe em ambiente local separado. A inspeção visual manual permanece pendente.

1. Abra uma sessão no repositório com Luna 6 e esforço High.
2. Envie o prompt da tarefa escolhida: [001 — qualidade](001-qualidade-captura/PROMPT.md), [002 — consistência temporal](002-consistencia-temporal/PROMPT.md), [003 — ambiguidade](003-rejeicao-ambiguidade/PROMPT.md), [004 — benchmark](004-benchmark-matching/PROMPT.md) ou [005 — consolidação e demonstração](005-consolidacao-demonstracao/PROMPT.md).
3. O executor lê o desenho e o plano, implementa, testa, documenta e faz commit + push na `main`, conforme autorização explícita do usuário registrada no prompt.

A tarefa 001 foi implementada, verificada e publicada conforme o resultado registrado em [001-qualidade-captura/RESULTADO.md](001-qualidade-captura/RESULTADO.md). Não há tarefas de datasets externos neste pacote.

A tarefa 002 parte do código concluído da 001. A implementação optativa, os testes e os limites das evidências estão registrados em [002-consistencia-temporal/RESULTADO.md](002-consistencia-temporal/RESULTADO.md).

A tarefa 003 parte das duas implementações anteriores. Seu [desenho](003-rejeicao-ambiguidade/DESENHO.md) define a comparação entre as duas melhores identidades; o [plano](003-rejeicao-ambiguidade/PLANO.md) cobre integração e testes. Implementação, validações, limites e publicação estão em [003-rejeicao-ambiguidade/RESULTADO.md](003-rejeicao-ambiguidade/RESULTADO.md).

A tarefa 004 aprofunda o benchmark existente conforme a ordem proposta nesta conversa: [desenho](004-benchmark-matching/DESENHO.md), [plano](004-benchmark-matching/PLANO.md) e [resultado](004-benchmark-matching/RESULTADO.md), com três JSONs agregados em [evidencias](004-benchmark-matching/evidencias/). A numeração das tarefas não replica a lista de prioridades do AGENTS.md: múltiplas referências por pessoa continuam adiadas. O estado de publicação é informado na resposta da execução.

A tarefa 005 consolida o estado atual e prepara uma demonstração offline: [desenho](005-consolidacao-demonstracao/DESENHO.md), [plano](005-consolidacao-demonstracao/PLANO.md) e [prompt](005-consolidacao-demonstracao/PROMPT.md). É uma entrega documental, distinta da Etapa 5 histórica de ML. Reutiliza as evidências de 001–004, sem novos datasets ou mudanças operacionais.

O resultado 005 registra as divergências reconciliadas, os comandos offline executados e seus limites: [005-consolidacao-demonstracao/RESULTADO.md](005-consolidacao-demonstracao/RESULTADO.md).
