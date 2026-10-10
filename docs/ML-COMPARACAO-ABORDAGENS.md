# Comparação de abordagens de decisão e agrupamento facial

Este documento compara o propósito e as limitações metodológicas dos métodos presentes nas Etapas 0–4. Não declara um vencedor: fora da calibração histórica 1:1 da Etapa 1, não houve avaliação biométrica real comparativa.

## Verificação 1:1 — mesma pessoa ou pessoas diferentes

| Abordagem | Como funciona | Pontos fortes | Limitações e estado |
|---|---|---|---|
| Limiar cosseno | Aceita o par quando `distância ≤ τ` | Regra simples, barata e interpretável; explicita a fronteira de decisão | Depende de calibração representativa. `0.30` segue operacional; `0.42817932706540435` é apenas candidato histórico 1:1 |
| Regressão logística | Aprende a probabilidade de classe 1 a partir da distância escalar | Coeficiente/intercepto interpretáveis; decisão monotônica para um preditor | Não adiciona informação à distância; classe balanceada muda a prevalência efetiva; score não é automaticamente probabilidade calibrada. Código implementado, sem treino real |
| Gaussian Naive Bayes | Estima distribuições gaussianas condicionais para as classes | Ajuste e inferência leves; baseline probabilístico simples | Pressupõe forma/dispersão das distribuições por classe; calibração precisa ser avaliada; código implementado, sem treino real |
| Árvore de decisão | Divide a distância em intervalos por limiares | Regras legíveis; profundidade 1 equivale a uma regra de corte simples | Árvores mais profundas ajustam flutuações e podem sobreajustar; desempenho depende da validação. Código implementado, sem treino real |

Na Etapa 2, os métodos supervisionados recebem apenas a distância cosseno entre embeddings FaceNet512, uma característica escalar. A documentação alerta que uma regressão logística monotônica não deve superar de modo sistemático a ordenação/AUC da distância; mudanças de orientação ou empates podem mudar os resultados em casos pontuais. Não foram publicados FAR, FRR, ROC/AUC, F1, Brier ou tempos biométricos para M2–M4.

## Identificação open-set 1:N

O pipeline da Etapa 3 não é simplesmente uma classificação de pares: para cada consulta ele compara uma galeria, seleciona o rank 1 e pode devolver uma pessoa errada, rejeitar uma pessoa conhecida ou aceitar um desconhecido. FPIR/FNIR e a variação com o tamanho da galeria respondem a perguntas diferentes de FAR/FRR 1:1.

T0 é `0.30`; T1 é `0.42817932706540435` obtido na validação 1:1 da Etapa 1; T2 seria calibrado somente na validação 1:N. T1 é uma referência histórica, não um limiar 1:N aprovado. A Etapa 3 implementa estratégias de galeria e métricas, mas nenhum cenário real foi executado; assim, não há comparação empírica entre T0, T1 e T2.

## Agrupamento não supervisionado

| Abordagem | Geometria/objetivo | Pontos fortes | Limitações e estado |
|---|---|---|---|
| DBSCAN | Região densa definida por `eps` e `min_samples`; amostras sem densidade suficiente podem ser ruído | Não exige fixar número de clusters; explicita amostras não agrupadas | Sensível à escala/densidade e aos parâmetros; pode não funcionar bem quando clusters têm densidades diferentes; escalabilidade e silhouette podem ser custosas |
| K-Means | Minimiza distâncias quadráticas a `K` centroides | Simples, reproduzível com seed e útil como baseline | Exige `K`, depende de inicialização, não modela ruído e favorece grupos aproximadamente convexos/esféricos |

Para DBSCAN, o protocolo escolhe `eps` e `min_samples` usando somente diagnósticos internos no desenvolvimento; para K-Means, `K` vem de uma grade interna predefinida. Não se usa o número verdadeiro de identidades para selecionar a configuração. ARI/NMI e demais métricas externas só podem ser calculadas depois do ajuste, com rótulos autorizados. Silhouette de DBSCAN é calculada sobre pontos cobertos e deve sempre ser interpretada junto à cobertura e ao ruído.

Ambos são tratados como agrupadores transdutivos neste protocolo. Ajustar um agrupamento a um novo conjunto não é o mesmo que usar um classificador indutivo para prever a identidade de uma amostra futura.

## Evidência disponível

- A Etapa 1 mediu um trade-off entre dois limiares em teste LFW 1:1: o candidato de 0,4282 teve FRR menor e FAR maior que 0,30. O resultado e os intervalos estão em [`ML-ETAPA-1-RESULTADO.md`](ML-ETAPA-1-RESULTADO.md).
- M2–M4, 1:N, DBSCAN e K-Means foram exercitados em testes sintéticos. Não existe comparação biométrica real para afirmar que algum deles supera outro.
- A decisão operacional continua sendo o matcher atual com `FACE_THRESHOLD=0.30`. Qualquer mudança depende de avaliação 1:N representativa, governança apropriada e autorização separada.
