# Tarefas de implementação

Cada pasta contém um desenho aprovado internamente, um plano executável e um prompt para o agente responsável. Estes documentos não significam que a implementação já foi realizada.

| ID | Tarefa | Executor previsto | Estado |
|---|---|---|---|
| 001 | Qualidade de captura: nitidez, iluminação e tamanho da face | Luna 6, esforço High | Concluída; implementação publicada na main |
| 002 | Consistência temporal e validade da identificação antes do registro | Luna 6, esforço High | Concluída; implementação publicada na main |
| 003 | Rejeição por ambiguidade entre identidades candidatas | Luna 6, esforço High | Implementação concluída e validada; ver resultado |

## Como executar

1. Abra uma sessão no repositório com Luna 6 e esforço High.
2. Envie o prompt da tarefa escolhida: [001 — qualidade](001-qualidade-captura/PROMPT.md), [002 — consistência temporal](002-consistencia-temporal/PROMPT.md) ou [003 — ambiguidade](003-rejeicao-ambiguidade/PROMPT.md).
3. O executor lê o desenho e o plano, implementa, testa, documenta e faz commit + push na `main`, conforme autorização explícita do usuário registrada no prompt.

A tarefa 001 foi implementada, verificada e publicada conforme o resultado registrado em [001-qualidade-captura/RESULTADO.md](001-qualidade-captura/RESULTADO.md). Não há tarefas de datasets externos neste pacote.

A tarefa 002 parte do código concluído da 001. A implementação optativa, os testes e os limites das evidências estão registrados em [002-consistencia-temporal/RESULTADO.md](002-consistencia-temporal/RESULTADO.md).

A tarefa 003 parte das duas implementações anteriores. Seu [desenho](003-rejeicao-ambiguidade/DESENHO.md) define a comparação entre as duas melhores identidades; o [plano](003-rejeicao-ambiguidade/PLANO.md) cobre integração e testes. Implementação, validações e limites estão em [003-rejeicao-ambiguidade/RESULTADO.md](003-rejeicao-ambiguidade/RESULTADO.md); o prompt autoriza commit e push na `main`.
