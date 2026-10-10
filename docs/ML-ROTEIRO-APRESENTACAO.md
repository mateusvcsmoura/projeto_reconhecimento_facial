# Roteiro de apresentação acadêmica — Machine Learning

**Duração estimada:** 13–15 minutos, mais perguntas.
**Regra de apresentação:** não converter teste de software em taxa de acerto biométrico. O único resultado real documentado é a calibração histórica 1:1 da Etapa 1 no LFW.

| Parte / tempo | Conteúdo principal | Explicação oral sugerida | Conceitos a destacar | Pergunta provável |
|---|---|---|---|---|
| 1. Problema e motivação — 1 min | Apoio ao controle de presença, com confirmação do operador | “O trabalho investiga como comparar uma captura facial com referências cadastradas. A aplicação só grava presença após confirmação do operador.” | Finalidade delimitada; decisão humana | “O sistema registra automaticamente?” |
| 2. Objetivo — 45 s | Aplicação e evolução experimental em cinco etapas | “Além da aplicação, criamos protocolos para avaliar o modelo sem mudar seu comportamento.” | Objetivo acadêmico versus produção | “O projeto pretende substituir o operador?” |
| 3. Arquitetura — 1 min 15 s | Webcam, detecção, anti-spoofing, embedding, matcher, decisão, banco | “A infraestrutura de visão fica em adaptadores; a regra de comparação é um serviço puro. O operador confirma antes da persistência.” | Camadas; separação de responsabilidades | “O que ocorre se houver dois rostos?” |
| 4. FaceNet512 — 1 min 15 s | Rede pré-treinada e vetor de 512 dimensões | “O FaceNet não foi treinado pelo grupo. Ele converte o recorte do rosto em um vetor; o projeto normaliza esse vetor para comparar direções.” | Treinamento versus inferência; embedding | “Vocês ajustaram os pesos?” |
| 5. Distância e decisão operacional — 1 min | Distância `1 − similaridade cosseno`; threshold 0,30 | “O matcher calcula a distância para todos os vetores e escolhe o menor; o candidato só passa se estiver abaixo do limiar.” | Normalização L2; limiar não é probabilidade | “Por que o valor é 0,30?” |
| 6. Calibração supervisionada — 1 min 30 s | Pares genuínos/impostores, divisão por identidade, FAR/FRR | “Na Etapa 1, um limiar foi escolhido na validação segundo um teto de FAR e medido uma vez no teste separado por identidade.” | Verificação 1:1; FAR/FRR; vazamento | “Qual foi o efeito do limiar calibrado?” |
| 7. Resultado histórico — 1 min | Comparação LFW 1:1 | “No teste histórico, o candidato reduziu o FRR e elevou o FAR frente a 0,30. Isso mostra um trade-off no LFW, não desempenho de sala.” | População e domínio; intervalo de confiança | “Isso é a precisão do sistema em sala?” |
| 8. Classificadores supervisionados — 1 min | Regressão logística, GaussianNB, árvore | “Implementamos baselines sobre a distância escalar e testes sintéticos. Não treinamos esses classificadores com faces reais, então não há comparação biométrica.” | Classe desbalanceada; calibração | “Qual classificador venceu?” |
| 9. Identificação open-set — 1 min 15 s | Galeria, conhecidos, desconhecidos, FPIR/FNIR | “Em 1:N, pode ocorrer troca de identidade ou aceitação de um desconhecido. O protocolo separa identidades e calibra limiar na validação.” | Open-set; rank 1; tamanho da galeria | “Qual é a taxa de falsa identificação?” |
| 10. Clustering — 1 min | DBSCAN e K-Means | “DBSCAN pode marcar ruído e não exige K; K-Means exige K. A seleção usa métricas internas sem rótulos; ainda não há resultado facial real.” | Não supervisionado; ruído; ARI/NMI | “O algoritmo identifica pessoas?” |
| 11. Testes e evidências — 1 min | 518 unitários atuais; lint e type check | “Esses testes verificam as regras do software com dados sintéticos. Eles não comprovam precisão facial. O full suite anterior é histórico e não foi repetido aqui por incluir banco.” | Evidência de engenharia versus biometria | “Os testes incluem dados reais?” |
| 12. Limitações, privacidade e conclusão — 1 min 30 s | LFW, gate, domínio, anti-spoofing, LGPD, trabalhos futuros | “Somente a Etapa 1 tem métricas reais e seu escopo é limitado. Precisamos de fonte autorizada e piloto representativo antes de afirmar desempenho ou considerar integração.” | Dado sensível; autorização; próximos passos | “Por que não avaliaram mais?” |

## Fala para apresentar os números históricos

“A Etapa 1 avaliou verificação 1:1 no LFW, com identidades separadas entre treino, validação e teste. O baseline 0,30 teve FAR reportado de 0,0018% e FRR de 38,03%. O limiar escolhido na validação para FAR de até 0,1% foi aproximadamente 0,42818; no teste histórico o FAR foi 0,063% e o FRR 16,39%. Esses números pertencem ao LFW, sem anti-spoofing, e não medem a identificação 1:N da aplicação em sala. O candidato não substituiu o valor operacional.”

## Fechamento sugerido

“O resultado principal das etapas não é declarar um classificador vencedor. É deixar a decisão mensurável e o processo reproduzível, mantendo o sistema operacional isolado. Temos implementação e testes de software para os protocolos 1:1, 1:N e clustering; para as Etapas 2–4, a avaliação biométrica aguarda autorização e dados adequados. O passo seguinte é uma avaliação controlada em domínio relevante, com revisão institucional, sem reutilizar o holdout já observado.”
