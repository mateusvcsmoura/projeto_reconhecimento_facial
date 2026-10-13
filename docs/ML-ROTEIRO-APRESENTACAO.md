# Roteiro de apresentação acadêmica — Machine Learning

**Duração:** 15 minutos, mais perguntas. Este roteiro apresenta o projeto como
atividade da disciplina de IA da Fatec, não como TCC. Não transforme teste de
software ou benchmark sintético em taxa de acerto biométrico.

| Bloco / tempo | Conteúdo | Fala sugerida | Conceito e limite |
|---|---|---|---|
| 1. Problema e escopo — 1 min | Identificação aberta 1:N para apoio ao registro de presença | “A aplicação compara uma captura com referências cadastradas; o operador confirma antes do registro.” | Finalidade acadêmica; identificação versus verificação |
| 2. Arquitetura e embeddings — 2 min | CLI, PostgreSQL, adaptador DeepFace/FaceNet512, vetor normalizado e distância cosseno | “O FaceNet512 é pré-treinado. O projeto gera embeddings e calcula o candidato mais próximo; o limiar operacional segue 0,30.” | Inferência não é treinamento; confiança exibida é indicador derivado, não probabilidade calibrada |
| 3. Controles 001–003 — 2 min | Qualidade, consistência temporal e rejeição por ambiguidade | “Os três controles são opt-in e desligados por padrão. A margem positiva não foi calibrada.” | Limites heurísticos; frames correlacionados; empate, desconhecido e múltiplas faces são casos diferentes |
| 4. Experimentos acadêmicos — 2 min | Etapas 0–4: calibração histórica 1:1, classificadores e protocolos 1:N/clustering | “Só a Etapa 1 registra métricas faciais reais, em verificação 1:1 no LFW. As Etapas 2–4 foram testadas sinteticamente.” | FAR/FRR não são FPIR/FNIR; holdout já consultado; sem avaliação real autorizada posterior |
| 5. Demonstração offline — 5 min | Seleção de testes sintéticos, CLI do benchmark, smoke e leitura de JSON histórico | “Vamos verificar contratos sem câmera, banco, modelo ou dados faciais. O smoke não é uma avaliação biométrica.” | Comandos, observações e alternativa estão em [docs/apresentacao.md](apresentacao.md) |
| 6. Evidências da tarefa 004 — 2 min | Três medições sequenciais, equivalência, latência e memória | “Cada execução comparou 240 consultas sintéticas sem divergências. Os tempos medem matching isolado; tracemalloc não é RSS.” | Sem FPS, inferência DeepFace, acurácia ou garantia de generalização; ver [relatório 004](../tasks/004-benchmark-matching/RESULTADO.md) |
| 7. Pendências e conclusão — 1 min | Autorização, avaliação biométrica 1:N representativa, anti-spoofing e múltiplas referências | “O software está verificável; desempenho em sala ainda não foi medido. O próximo passo depende de governança e dados autorizados.” | Não mudar o limiar por métricas sintéticas; ver [estado atual](ESTADO-ATUAL-E-EVIDENCIAS.md) |

**Soma:** 1 + 2 + 2 + 2 + 5 + 2 + 1 = **15 minutos**.

## Fala curta para os números históricos da Etapa 1

“A Etapa 1 avaliou verificação 1:1 no LFW, com identidades separadas entre
treino, validação e teste. No teste histórico, o baseline 0,30 teve FAR de
0,0018% e FRR de 38,03%. O candidato escolhido na validação para FAR de até
0,1% foi aproximadamente 0,42818; no teste histórico, teve FAR de 0,063% e
FRR de 16,39%. Isso mostra um trade-off naquele conjunto, sem anti-spoofing;
não mede identificação 1:N na sala e não alterou o limiar operacional.”

## Fechamento

“As tarefas 001–003 acrescentam controles optativos e testados com dados
sintéticos. A tarefa 004 mede equivalência e custo computacional do matching
com vetores artificiais. Nenhuma delas demonstra acurácia facial. Para avaliar
o uso em sala, precisamos de fonte e finalidade autorizadas, revisão
institucional e protocolo 1:N representativo, sem reutilizar o holdout
histórico como se fosse independente.”
