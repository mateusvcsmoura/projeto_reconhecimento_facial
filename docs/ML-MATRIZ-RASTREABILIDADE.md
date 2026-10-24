# Matriz de rastreabilidade acadêmica de Machine Learning

**Auditoria documental original:** 10/10/2026. A tabela acima preserva o
snapshot daquela data; a atualização das tarefas 001–004 de 13/10/2026 está
abaixo e o estado completo tem fontes em
[`ESTADO-ATUAL-E-EVIDENCIAS.md`](ESTADO-ATUAL-E-EVIDENCIAS.md).

## Conceitos, código e evidências

| Conceito | Implementação encontrada | Arquivo principal | Etapa / tarefa | Evidência | Estado |
|---|---|---|---:|---|---|
| Visão computacional / detecção facial | Detecção, alinhamento e exigência de exatamente um rosto | `src/infrastructure/face_recognition/deepface_adapter.py` | Base | Inspeção de código; testes unitários `tests/unit/test_deepface_adapter.py` | Implementado; desempenho do detector não medido nesta consolidação |
| Deep Learning / inferência | FaceNet512 pré-treinado gera vetor de 512 dimensões | `src/infrastructure/face_recognition/deepface_adapter.py`; `src/config/settings.py` | Base | Configuração operacional e adaptador | Inferência implementada; pesos não foram treinados pelo projeto |
| Embeddings normalizados | Validação finita, norma não nula e normalização L2 | `src/domain/entities/face_embedding.py` | Base | `tests/unit/test_face_embedding.py` | Implementado e coberto por testes |
| Distância cosseno e matcher | `1 − produto escalar`; menor distância compatível vence | `src/domain/services/matcher.py` | Base | `tests/unit/test_matcher.py` e `docs/ML-ETAPA-1-RESULTADO.md` | Implementado; limiar operacional segue 0,30 |
| Anti-spoofing | Parâmetro `anti_spoofing` passado à detecção; recusa de provável apresentação | `src/infrastructure/face_recognition/deepface_adapter.py`; `src/config/settings.py` | Base | Código e `docs/lgpd.md` | Implementado e habilitado por padrão; eficácia contra ataques não medida |
| Proteção e divisão experimental | Inventário, divisão de identidades, assinatura e teste de abertura única | `scripts/divisao_por_identidade.py`; `scripts/evaluate_model.py` | 0 | `docs/ML-ETAPA-0-RESULTADO.md`; testes em `tests/unit/test_divisao_por_identidade.py` | Implementado e testado com fixtures sintéticas |
| Métricas de verificação | FAR, FRR, ROC, AUC, EER e matriz de confusão | `scripts/metricas.py` | 0–1 | `tests/unit/test_metricas.py`; relatório da Etapa 1 | Implementado; Etapa 1 contém uma avaliação histórica real 1:1 |
| Calibração supervisionada de limiar | Seleção de τ na validação conforme teto de FAR | `scripts/calibrar_limiar.py` | 1 | `docs/ML-ETAPA-1-RESULTADO.md` | Executada historicamente no LFW; candidato não promovido a produção |
| Gráficos de verificação | Distâncias, ROC, FAR/FRR e matrizes de confusão | `scripts/graficos_calibracao.py` | 1 | `docs/ML-ETAPA-1-RESULTADO.md` | Gráficos históricos gerados; não foram refeitos na Etapa 5 |
| Regressão logística | Classificador binário com distância cosseno como característica escalar | `scripts/classificadores_binarios.py` | 2 | `tests/unit/test_classificadores_binarios.py`; `docs/ML-ETAPA-2-RESULTADO.md` | Implementado; treino biométrico real pendente |
| Gaussian Naive Bayes | Classificador binário sobre distância cosseno | `scripts/classificadores_binarios.py` | 2 | Testes de classificadores e relatório da Etapa 2 | Implementado; treino biométrico real pendente |
| Árvore de decisão | Stump e profundidades pequenas | `scripts/classificadores_binarios.py` | 2 | Testes de classificadores e relatório da Etapa 2 | Implementado; treino biométrico real pendente |
| Seleção e avaliação supervisionada | Congelamento, seleção na validação, teste reservado e métricas | `scripts/experimento_classificacao_binaria.py`; `scripts/avaliacao_classificadores.py` | 2 | `tests/unit/test_experimento_classificacao_binaria.py`; relatório da Etapa 2 | Infraestrutura implementada; sem desempenho real de M2–M4 |
| Identificação aberta 1:N | Galeria, consultas conhecidas/desconhecidas, limiar e rejeição | `scripts/identificacao_aberta.py`; `scripts/experimento_identificacao_aberta.py` | 3 | Testes em `tests/unit/test_identificacao_aberta.py` e `test_experimento_identificacao_aberta.py` | Implementado e testado sinteticamente; biometria real pendente |
| Métricas de open-set | FPIR, FNIR, rank 1, rejeição, trocas, falhas e intervalos agrupados | `scripts/identificacao_aberta.py` | 3 | Relatório da Etapa 3 e testes unitários | Implementadas; nenhuma métrica biométrica real medida |
| DBSCAN | Agrupamento por densidade com ruído e seleção sem rótulos | `scripts/agrupamento_embeddings.py`; `scripts/experimento_agrupamento.py` | 4 | `tests/unit/test_agrupamento_embeddings.py`; relatório da Etapa 4 | Implementado; biometria real pendente |
| K-Means | Baseline com `n_clusters` escolhido por critério interno | `scripts/agrupamento_embeddings.py` | 4 | Testes de agrupamento e relatório da Etapa 4 | Implementado; biometria real pendente |
| Métricas de clustering | ARI, NMI, homogeneity, completeness, V-measure e métricas internas | `scripts/agrupamento_embeddings.py` | 4 | Testes sintéticos de agrupamento | Implementadas; nenhum valor de identidade real medido |
| Rastreabilidade/reprodutibilidade | Scripts, seeds, versões, caches e artefatos isolados | `scripts/experimento_*.py`; `requirements-ml.txt`; `.gitignore` | 0–4 | Relatórios das Etapas 0–4 e testes unitários atuais | Implementado; depende de autorização e proveniência para dados reais |
| Registro de presença | Persistência após confirmação do operador | `src/application/use_cases/registrar_presenca.py`; repositórios PostgreSQL | Base | `tests/unit/test_registrar_presenca.py`; integração histórica | Operacional; não foi acessado na Etapa 5 |
| Qualidade de captura | Checagem optativa de tamanho, luminância e nitidez antes do embedding | `src/domain/services/qualidade_captura.py`; adaptador DeepFace | Tarefa 001 | `tests/unit/test_qualidade_captura.py`; relatório | Implementada; heurísticas sintéticas, orientação facial explícita não verificada |
| Consistência temporal | Sequência optativa de IDs iguais e revalidação em nova captura antes de registrar | `src/domain/services/consistencia_temporal.py`; `src/presentation/cli/menu.py` | Tarefa 002 | `tests/unit/test_consistencia_temporal.py`; relatório | Implementada; frames correlacionados, sem alegação de melhora biométrica |
| Rejeição por ambiguidade | Gap entre as duas menores distâncias de identidades distintas após o limiar | `src/domain/services/matcher.py` | Tarefa 003 | `tests/unit/test_matcher_ambiguidade.py`; relatório | Opt-in; margem positiva sem calibração biométrica |
| Benchmark vetorizado | Comparação com laço Python e `NumPy dot` sobre vetores sintéticos 512D | `scripts/benchmark_matcher.py` | Tarefa 004 | `tests/unit/test_benchmark_matcher.py`; relatório e JSONs agregados | Três execuções sem divergência; custo computacional local, não acurácia ou inferência |

Os arquivos de teste existem e os casos unitários usam dados sintéticos/fakes. Os relatórios das Etapas 2–4 documentam que não abriram embeddings biométricos nem produziram métricas faciais reais.

## Evidência da Etapa 5 histórica — 10/10/2026

- **Etapa 5, naquele snapshot:** `pytest tests/unit --basetemp "$env:TEMP\pytest-stage5-unit-20261010"` — 518 aprovados.
- **Etapa 5, naquele snapshot:** `ruff check src scripts tests` — aprovado.
- **Etapa 5, naquele snapshot:** `mypy` — aprovado, 67 arquivos.
- **Etapa 4, execução histórica registrada:** 22 testes focais e 597 na suíte completa. A suíte completa não foi repetida na Etapa 5 porque inclui testes de integração que usam PostgreSQL.
- Esses números verificam o software e não estimam a qualidade biométrica. São históricos e não substituem as verificações registradas nas tarefas posteriores.

## Verificação focal da tarefa 005 — 13/10/2026

A tarefa 005 executou os quatro módulos de teste das melhorias 001–004 e um
smoke curto do benchmark, sem executar a suíte inteira, integração/BDD,
câmera, banco, modelo ou dados faciais. O comando exato, total aprovado,
códigos de saída e interpretação estão no
`resultado da tarefa 005`.
Essa seleção confirma contratos funcionais locais; não constitui teste
biométrico nem reavalia todos os módulos da matriz.

## Conceitos estudados, não implementados

- **Aprendizado por reforço:** não há agente, política, ambiente, recompensa ou ciclo de exploração implementados.
- **Treinamento/fine-tuning do FaceNet512:** não realizado; o modelo é usado como extrator pré-treinado.
- **Treinamento biométrico real de M2–M4:** pendente de fonte autorizada, aprovação institucional e execução válida.
- **Medição biométrica real 1:N e clustering:** pendente.
- **Avaliação de ataques do anti-spoofing com APCER/BPCER:** sem protocolo/dataset de ataques aprovado e sem medição.

## Limite da matriz

“Implementado” significa que há código identificável e testes de software correspondentes, quando indicado. Não significa que haja precisão comprovada, adequação operacional, equidade, segurança contra ataques ou autorização para usar dados. O único resultado facial real registrado nas Etapas 0–4 é a verificação 1:1 histórica da Etapa 1, com as limitações descritas em [`ML-ETAPA-1-RESULTADO.md`](ML-ETAPA-1-RESULTADO.md).
