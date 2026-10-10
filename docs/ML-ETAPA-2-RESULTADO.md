# Etapa 2 — Treinamento e comparação de classificadores supervisionados

**Estado: implementação concluída; avaliação experimental pendente.** O gate
de autorização para uso do LFW não está satisfeito. Nenhum array biométrico da
Etapa 1 foi aberto pela Etapa 2, nenhum modelo foi treinado com o LFW e nenhum
resultado ou gráfico biométrico foi produzido. Os modelos foram ajustados
somente sobre números sintéticos nos testes automatizados.

## 1. Resumo executivo

Foi implementado um fluxo experimental isolado para comparar M0–M4 em
verificação facial binária 1:1. A implementação reutiliza os pares, as métricas
e o bootstrap por identidade da Etapa 1, fixa os modelos e limiares antes de
liberar a leitura do teste e mantém os artefatos fora do Git.

A auditoria local encontrou os artefatos e metadados da Etapa 1, mas não
encontrou documento que autorize este uso do LFW. A aplicação bloqueia o treino
real sem um arquivo local de autorização, portanto os valores de FAR, FRR, AUC,
F1, tempo, erros e curvas da Etapa 2 permanecem pendentes. Esta entrega não é
uma validação biométrica nem uma comparação de desempenho.

## 2. Objetivo acadêmico

Comparar regras e classificadores supervisionados para decidir se duas imagens
pertencem à mesma pessoa, usando pares rotulados e a distância cosseno entre
embeddings FaceNet512 já extraídos. A classe positiva é “mesma identidade”; a
negativa é “identidades diferentes”.

O experimento mede verificação 1:1. Não mede o reconhecimento operacional 1:N
usado no controle de presença. O FaceNet512 não é treinado ou ajustado.

## 3. Pré-requisitos e estado das Etapas 0 e 1

| Gate | Estado observado |
|---|---|
| Infraestrutura da Etapa 0 | Validada no relatório da etapa; o resultado documenta 322 testes aprovados e divisão por identidade reproduzível. |
| Proteção dos dados | `avaliacao/` e padrões de imagens/vetores estão ignorados pelo Git. A Etapa 2 não persiste imagens, embeddings ou IDs em logs. |
| Dataset autorizado para este uso | **Pendente.** Não foi encontrado documento local de autorização/termos para o uso do LFW nesta etapa. |
| Divisão por identidade reproduzível | Confirmada nos metadados S1: seed 42, assinatura `4c7ddc45f322ec3c`; a auditoria S1 documenta identidades sem sobreposição. |
| Geração de pares após a divisão | Documentada na infraestrutura S1; a Etapa 2 lê cada split separadamente e não regenera pares entre splits. |
| Falhas de extração contabilizadas | Confirmadas nos metadados S1: 162 imagens sem rosto e 595 com múltiplos rostos. |
| Baseline e metodologia da Etapa 1 | Documentados; baseline histórico 0,30 e limiar de validação 0,42817932706540435 para FAR pontual de 0,001. |
| Vazamento entre splits | A auditoria S1 registra divisão por identidade; o novo fluxo verifica identidades, imagens, rótulos e contagens. |
| Teste preservado durante a Etapa 2 | **Sim durante esta implementação:** os arrays do teste não foram carregados. A Etapa 1, porém, já abriu e publicou seus próprios resultados de teste; por isso este teste não será descrito como um holdout historicamente intocado. |
| Dependências experimentais isoladas | Instaladas somente em `.venv-ml`; `.venv-app` não foi alterado. |

O gate de treino real permanece fechado por falta de autorização documentada.
Esta condição interrompeu a execução biométrica, mas não impediu a implementação
ou os testes sintéticos.

## 4. Dataset utilizado

**Nenhum dataset biométrico foi utilizado na Etapa 2.** O LFW local foi
considerado somente um candidato e seus metadados/checksum de origem foram
validados sem abrir os arrays de pares. A documentação da Etapa 1 descreve a
cópia como LFW original, com 13.233 imagens de 5.749 pessoas, publicado para
pesquisa em verificação facial e sem licença formal. A confirmação documentada
de que esse uso é autorizado e apropriado ainda não existe no workspace.

Também não foram utilizados imagens ou embeddings de alunos, dados do
PostgreSQL, webcam ou novos embeddings. O cache de embeddings FaceNet512 não
foi lido nem recalculado.

## 5. Distribuição dos dados

Os números abaixo são **proveniência da Etapa 1**, não observações ou
resultados da Etapa 2. Os arrays dos pares não foram carregados nesta etapa.

| Split S1 | Identidades | Imagens | Pares | Mesma identidade | Identidades diferentes |
|---|---:|---:|---:|---:|---:|
| Treino | 999 | 3.502 | 1.007.319 | 7.319 | 1.000.000 |
| Validação | 333 | 1.062 | 563.391 | 2.052 | 561.339 |
| Teste | 336 | 1.099 | 603.351 | 2.001 | 601.350 |

O desbalanceamento é intencional no artefato S1: todos os pares genuínos foram
mantidos e os impostores foram limitados/amostrados segundo a configuração
documentada. A auditoria S1 também registra duas duplicatas exatas entre
identidades removidas antes da divisão, zero duplicatas dentro da identidade,
zero quase duplicatas genuínas e 757 falhas de extração. Esses dados descrevem
a S1 e não constituem uma auditoria de imagens refeita pela S2.

## 6. Modelos implementados

| Código | Método | Situação na implementação |
|---|---|---|
| M0 | Regra histórica `distância <= 0.30` | Implementado como baseline sem treinamento. |
| M1 | Limiar da Etapa 1 (`0.42817932706540435`) | Implementado se a validação S1 for compatível; não é recalibrado. |
| M2 | Regressão logística | Implementada com `predict_proba` e grade reduzida. |
| M3 | Gaussian Naive Bayes | Implementado com `var_smoothing=1e-9` e diagnóstico das distribuições por classe. |
| M4 | Árvore de decisão | Implementada com profundidades máximas 1, 2 e 3. |
| M5 | SVM opcional | Não implementada: uma distância escalar não acrescentaria representação relevante; diferenças absolutas dos embeddings seriam outro experimento. |

Nenhum desses modelos foi ajustado a dados biométricos reais nesta etapa. M2,
M3 e M4 foram exercitados apenas em fixtures sintéticas dos testes.

## 7. Características de entrada

Os métodos M2–M4 recebem uma única característica por par:

```text
X = [[distância_cosseno]]  # shape (n, 1), float64
y = 1 se as identidades forem iguais; 0 caso contrário
```

O extrator valida vetor unidimensional não vazio e valores finitos. A
representação não inclui pixels, vetores FaceNet512 ou características
aprendidas com o conjunto completo. Nenhuma transformação é ajustada antes da
divisão.

## 8. Estratégia de treinamento

`preparar` exige um documento local de autorização não vazio antes de validar
ou carregar arrays de pares. Valida o checksum e a proveniência S1, abre apenas
treino e validação, confirma rótulos, contagens e ausência de sobreposição
entre esses splits, ajusta candidatos e grava um manifesto e modelos
congelados.

`avaliar` valida os hashes do manifesto, dos modelos e do arquivo de origem,
confere a proveniência e os baselines, e carrega treino e validação para
verificar as partições. Antes de abrir o split de teste, cria um marcador
exclusivo em `avaliacao/resultados/etapa2/.teste-consumido.json`; novas
tentativas são recusadas mesmo se indicarem outra pasta de saída, seed ou
congelamento. A preparação não indexa chaves `teste_*`; testes sintéticos
confirmam esses contratos.

Esse fluxo foi testado com arquivos sintéticos. Nenhuma das duas fases foi
executada sobre o LFW nesta entrega.

## 9. Seleção de hiperparâmetros

- Regressão logística: `solver="lbfgs"`, `max_iter=1000`, `random_state=seed`,
  seis combinações de `C ∈ {0.1, 1, 10}` e `class_weight ∈ {None, "balanced"}`.
- GaussianNB: `var_smoothing=1e-9`.
- Árvore: critério Gini, `random_state=seed` e `max_depth ∈ {1, 2, 3}`.

A seleção considera apenas treino e validação. Entre candidatos elegíveis,
minimiza FRR na validação sob FAR pontual máximo de 0,001; desempata por menor
FAR, limiar de score mais estrito e ordem estável da grade. A seleção do
limiar testa os valores observados de score por uma ordenação e soma acumulada
(`O(n log n)`), e recusa a configuração quando só é possível respeitar o teto
recusando todas as amostras genuínas. Candidatos sem limiar elegível são
registrados como indisponíveis. Nenhum hiperparâmetro foi selecionado com dados
biométricos nesta etapa.

## 10. Calibração e seleção de limiares

M0 conserva o limiar histórico 0,30. M1 conserva o limiar S1 de validação
0,42817932706540435 e não usa resultados de teste para recalibração. M2–M4
selecionam, na validação, um limiar no escore em que valores maiores favorecem
a classe positiva. A seleção é exata sobre os scores observados; minimiza FRR
sob o teto de FAR e desempata por FAR menor e threshold mais alto.

Os valores selecionados para M2–M4 no dataset real estão **pendentes**. As
probabilidades de classificadores são escores condicionados ao balanceamento e
à ponderação usados no treino; não são interpretadas automaticamente como
probabilidades reais de identidade. Não foi aplicado calibrador probabilístico
pós-ajuste.

## 11. Métricas no conjunto de teste

**Nenhuma métrica biométrica da Etapa 2 foi medida.** A tabela usa apenas
“Pendente”; não contém valores simulados.

| Modelo | FAR | FRR | AUC | F1 | Tempo de inferência |
|---|---|---|---|---|---|
| Limiar 0,30 (M0) | Pendente | Pendente | Pendente | Pendente | Pendente |
| Limiar calibrado S1 (M1) | Pendente | Pendente | Pendente | Pendente | Pendente |
| Regressão logística (M2) | Pendente | Pendente | Pendente | Pendente | Pendente |
| GaussianNB (M3) | Pendente | Pendente | Pendente | Pendente | Pendente |
| Árvore de decisão (M4) | Pendente | Pendente | Pendente | Pendente | Pendente |
| SVM (M5) | Fora do escopo | Fora do escopo | Fora do escopo | Fora do escopo | Fora do escopo |

O avaliador implementa TP/TN/FP/FN, FAR, FRR, acurácia, precisão, recall,
F1, ROC, AUC, EER interpolado, Brier Score para classificadores probabilísticos,
curva/distribuição de calibração e tempos. As estimativas de FAR/FRR usam
bootstrap agrupado por identidade; denominadores ausentes retornam `null`.
Nenhum resultado desses cálculos foi persistido para dados biométricos.

## 12. Comparação com os baselines

M0 e M1 estão prontos para comparação futura com os mesmos pares de teste e
escores orientados como `-distância`. A comparação de S2 com o teste S1 não foi
executada, pois o gate de autorização bloqueou o uso dos arrays. A existência
do limiar M1 é evidência de uma calibração anterior na validação; não é uma
métrica S2.

O relatório futuro apresentará diferenças pareadas de FAR e FRR contra M0,
usando as mesmas réplicas do bootstrap por identidade. AUC de regressão
logística univariada não deve ser interpretada como ganho de representação:
uma transformação monotônica da distância preserva a ordenação, salvo empates
ou problemas de ajuste.

## 13. Gráficos

O gerador está implementado para produzir oito SVGs com títulos, rótulos e
identificação do conjunto:

1. Matrizes de confusão por método.
2. Curvas ROC comparativas.
3. FAR versus FRR.
4. Comparação de métricas.
5. Distribuição de distâncias por classe.
6. Curva de calibração da regressão logística.
7. Visualização da árvore de decisão.
8. Tempo de inferência.

**Zero gráficos biométricos foram gerados** porque não houve avaliação real.
O salvamento exige uma confirmação explícita do orquestrador após validar os
dados. Os testes sintéticos interceptam `savefig` e confirmam que nenhum SVG
fictício fica em disco.

## 14. Análise de falsos positivos e falsos negativos

Pendente de dados autorizados e avaliação congelada. A implementação calcula
as contagens FP/FN e FAR/FRR sem exportar os IDs das imagens ou identidades.
Não existem casos biométricos de falso aceite ou rejeição analisados pela S2.

## 15. Análise de overfitting

Para o classificador selecionado, a implementação registra FAR/FRR de treino
com o limiar escolhido na validação, exclusivamente como diagnóstico. A
validação também seleciona hiperparâmetros e limiar; por isso seu resultado não
é uma estimativa final de generalização. Profundidade, folhas e limiares da
árvore são registrados para discutir sua complexidade. Comparações reais de
overfitting estão pendentes.

## 16. Limitações estatísticas

- Pares derivados das mesmas identidades/imagens são dependentes; milhões de
  pares não equivalem a milhões de observações independentes.
- O bootstrap reamostra identidades e as diferenças contra M0 são pareadas.
  Com zero falsos aceites, o relatório também apresenta a regra do três sobre
  pares distintos de identidades; atendimento a FAR ≤ 0,001 requer estimativa
  pontual e limite superior do IC de 95% dentro do teto.
- O conjunto S1 é fortemente desbalanceado; precisão, F1, Brier e calibração
  refletem a amostragem dos pares, não a prevalência operacional em sala.
- `class_weight="balanced"` altera o ajuste e não assegura calibração.
- GaussianNB pressupõe distribuições condicionais gaussianas. Assimetria,
  curtose e quantis empíricos versus gaussianos são diagnósticos, não prova de
  validade nem critério de seleção.
- Árvores podem sobreajustar, mesmo em profundidades pequenas.
- O teste S1 foi historicamente aberto na etapa anterior; seu reuso não é um
  teste externo totalmente inédito.
- LFW contém fotos de imprensa, com mudança de domínio em relação à webcam.
  Sobreposição de identidades com o pré-treino FaceNet512/VGGFace2 não foi
  verificada; não se afirma independência do pré-treino.
- A cobertura de grupos demográficos e a taxa de falha de extração limitam a
  generalização.

## 17. Privacidade e proteção de dados

Nenhuma imagem ou embedding de aluno foi usado; o PostgreSQL não foi acessado.
Nenhum dado individual ou score por identidade é escrito no relatório. Os
artefatos de experimento ficam sob `avaliacao/`, ignorado pelo Git; esta
execução não criou modelos, resultados ou gráficos biométricos. O manifesto
futuro guarda o hash da autorização, não seu conteúdo. Nenhum dado foi enviado
para fora do workspace e nenhum commit foi feito.

## 18. Testes automatizados

Os testes novos usam apenas arrays sintéticos e `tmp_path`; não dependem de
webcam, PostgreSQL, internet, downloads de pesos ou dataset biométrico. Cobrem
características, rótulos, grids e limiares, desempate conservador, separação,
gate de autorização, ausência de acesso precoce ao teste, consumo único do
teste, hashes/congelamento, persistência, métricas, bootstrap reprodutível por
identidade com escores próprios de cada método, varredura de 100.000 scores
únicos, regra do três, calibração, gráficos sem arquivos sintéticos e
argumentos da CLI.

Resultados da rodada final após revisão: **528 testes aprovados** (`pytest`,
13,99 s), Ruff (`ruff check .`) sem achados e mypy sem achados em 61 arquivos.
Os 53 testes focais da infraestrutura S1 também passaram após a pequena
correção de tipagem do histograma descrita abaixo. O primeiro baseline de pytest sem
`--basetemp` encontrou `PermissionError` ao enumerar a pasta temporária do
usuário; a mesma suíte passou quando o diretório temporário foi redirecionado
para dentro do workspace.

## 19. Reprodutibilidade

- Seed de divisão S1: 42; assinatura: `4c7ddc45f322ec3c`.
- Seed padrão dos classificadores e bootstrap: 42.
- Hash S1 de `pares.npz`: `BF40A75899A76334F2A2D11354C9D8DB6F8F5BAD74D7E9675B98D7DFDEA46058`.
- Stack experimental isolada: Python 3.14.3, NumPy 2.5.3, scikit-learn 1.9.1,
  Matplotlib 3.11.2, SciPy 1.18.1 e joblib 1.6.0; as outras versões ficam no
  manifesto de congelamento. A instalação foi feita somente em `.venv-ml`; o
  `.venv-app` não foi alterado.
- Configuração herdada S1: FaceNet512, detector OpenCV, alinhamento ligado,
  normalização L2 e prova de vida desligada. A Etapa 2 não executa esse modelo.

Instalação e testes sintéticos:

```powershell
& '.\.venv\Scripts\python.exe' -m venv .venv-ml
.\.venv-ml\Scripts\python.exe -m pip install -r requirements-ml.txt
.\.venv-ml\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=avaliacao/resultados/etapa2/pytest-temp
.\.venv-ml\Scripts\ruff.exe check .
.\.venv-ml\Scripts\mypy.exe
```

Depois de registrada a autorização apropriada, os comandos implementados são:

```powershell
.\.venv-ml\Scripts\python.exe -m scripts.experimento_classificacao_binaria preparar `
  --entrada avaliacao/resultados/etapa1 `
  --saida avaliacao/resultados/etapa2 `
  --autorizacao-dataset <documento-local-de-autorizacao> `
  --seed 42

.\.venv-ml\Scripts\python.exe -m scripts.experimento_classificacao_binaria avaliar `
  --entrada avaliacao/resultados/etapa1 `
  --congelamento avaliacao/resultados/etapa2/congelamento.json `
  --saida avaliacao/resultados/etapa2 `
  --seed 42 `
  --replicas 1000
```

Esses dois comandos **não foram executados** nesta entrega: o documento de
autorização não existe no workspace.

A instalação de Matplotlib no ambiente ML tornou visível uma incompatibilidade
de tipos na chamada de histograma já existente em `scripts/graficos_calibracao.py`.
As mesmas bordas são passadas como lista (`bordas.tolist()`), sem alterar os
valores; os 53 testes focais S1, Ruff e mypy passaram depois dessa correção.

## 20. Conclusões

O código de M0–M4, a preparação com gate, o congelamento antes do teste, as
métricas agrupadas, os gráficos e a CLI foram implementados e exercitados com
dados sintéticos. Nenhum desempenho biométrico de M0–M4 foi medido. A conclusão
correta desta etapa é **implementação concluída, avaliação experimental
pendente**.

## 21. Recomendações para a Etapa 3

Não avançar automaticamente. Antes de qualquer comparação real, obter e
registrar evidência local apropriada de autorização/termos do dataset ou
selecionar uma fonte autorizada, sem usar alunos. Se uma nova divisão for
necessária, separá-la por identidade antes de gerar pares e reservar teste que
não tenha sido usado em decisões anteriores. Só então executar a avaliação
congelada uma vez, reportar intervalos por identidade e analisar erros e
limitações de domínio. Uma decisão de integração futura exige uma etapa
operacional separada, aprovação explícita e avaliação 1:N/anti-spoofing própria.
