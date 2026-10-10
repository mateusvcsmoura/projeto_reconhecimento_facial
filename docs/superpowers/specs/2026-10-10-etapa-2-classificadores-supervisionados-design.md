# Etapa 2 — Desenho de classificadores supervisionados

**Estado:** desenho aprovado em conversa; aguardando revisão desta especificação.

**Escopo:** experimento acadêmico de verificação facial binária 1:1, isolado da aplicação operacional.

## Objetivo e limites

Comparar regras e classificadores sobre a distância cosseno entre embeddings FaceNet512 já extraídos. Cada par recebe rótulo 1 (mesma identidade) ou 0 (identidades diferentes). O resultado mede verificação 1:1 e não equivale ao desempenho da identificação 1:N usada no controle de presença.

O FaceNet512 não será treinado ou ajustado. Nenhuma imagem/embedding de aluno será usado. Não haverá conexão ou alteração no PostgreSQL. Nenhum modelo será ligado à aplicação.

## Decisão do gate de dados

A auditoria local encontrou a cópia experimental LFW e os artefatos da Etapa 1. O arquivo do dataset confere com o SHA-256 documentado; os pares da Etapa 1 usam seed 42, identidades separadas entre subconjuntos e não registram sobreposição de identidade/imagem. O cache contém 5.663 embeddings de 512 dimensões. A extração anterior contabilizou 757 falhas (162 sem face e 595 com múltiplas faces), e o relatório anterior registra zero quase duplicatas segundo seu critério.

O gate de treino real, contudo, **não está liberado por esta auditoria**: a documentação de procedência consultada não registra licença formal nem consentimento dos retratados para este uso. A existência de uma cópia pública e a etapa anterior não demonstram autorização suficiente. Assim, esta etapa pode implementar o fluxo e testar os componentes somente com dados sintéticos. Treino, seleção e avaliação com LFW permanecem pendentes de confirmação documentada de que o uso proposto é autorizado e apropriado. Não serão usados dados dos alunos como alternativa.

O conjunto de teste da Etapa 1 já foi aberto e seus resultados estão publicados no relatório da etapa. A Etapa 2 não usará teste para ajuste e o fluxo bloqueará a leitura do teste até o congelamento dos modelos; ainda assim, a avaliação não será descrita como teste externo intocado. O reuso e a exposição histórica serão declarados no relatório final.

## Dados e prevenção de vazamento

O experimento reutilizará somente o cache de embeddings e o artefato de pares versionados pela infraestrutura da Etapa 1, validando modelo/configuração, dimensão, seed e assinatura do split antes do uso. Não executará novamente o FaceNet512 para cada par.

Os splits existentes são por identidade, com seed 42 e assinatura `4c7ddc45f322ec3c`:

| Subconjunto | Identidades | Imagens | Pares | Mesma identidade | Identidades diferentes |
|---|---:|---:|---:|---:|---:|
| Treino | 999 | 3.502 | 1.007.319 | 7.319 | 1.000.000 |
| Validação | 333 | 1.062 | 563.391 | 2.052 | 561.339 |
| Teste | 336 | 1.099 | 603.351 | 2.001 | 601.350 |

Não se regeneram pares cruzando subconjuntos. A quantidade e o balanceamento, incluindo o forte desbalanceamento da validação e teste, serão informados. Qualquer mudança no split exige novo identificador de dados e nova auditoria. Serão verificadas a integridade e a compatibilidade dos artefatos antes do treino.

## Organização proposta

Toda lógica nova permanece em `scripts/`, sem mudanças em `src/` ou no fluxo operacional. Reaproveita os leitores, geradores, métricas e bootstrap existentes quando compatíveis, sem duplicar a infraestrutura da Etapa 1.

- `scripts/classificadores_binarios.py`: preparação de características escalares, ajuste de candidatos, seleção de parâmetros e limiar na validação, e predição.
- `scripts/experimento_classificacao_binaria.py`: validação de metadados/dados, execução em duas fases e persistência/carregamento dos parâmetros congelados.
- `scripts/graficos_classificacao.py`: visualizações a partir de resultados medidos.
- Testes unitários em `tests/` usando somente fixtures sintéticas.
- Dependências experimentais isoladas em arquivo próprio e ambiente `.venv-ml`; não alterar `requirements.txt` operacional nem instalar pacotes no ambiente de execução da aplicação.
- Relatório obrigatório `docs/ML-ETAPA-2-RESULTADO.md`.

Os arquivos de execução, modelos e gráficos ficam em `avaliacao/resultados/etapa2/`, que é ignorado pelo Git. Metadados agregados e sem identificadores individuais podem constar no relatório. Logs não contêm imagens, embeddings, nomes ou identidades.

## Modelos e seleção

Todos os modelos usam inicialmente uma característica: `X = [[distância_cosseno]]`, `y = [0 ou 1]`.

| Código | Método | Seleção permitida |
|---|---|---|
| M0 | Regra histórica `distância <= 0.30` | Sem ajuste |
| M1 | Limiar válido da Etapa 1: `0.4282` | Sem recalibração |
| M2 | `LogisticRegression` | `C ∈ {0.1, 1, 10}` × `class_weight ∈ {None, "balanced"}` |
| M3 | `GaussianNB` | Parâmetros padrão; documentar a hipótese gaussiana e a sobreposição entre classes |
| M4 | `DecisionTreeClassifier` | `max_depth ∈ {1, 2, 3}`; registrar folhas, profundidade e limiares |

SVM fica fora: em uma distância escalar acrescentaria pouca informação. Uma SVM sobre diferenças absolutas de embeddings seria outra representação e outro experimento.

Para regressão logística serão gravados coeficiente, intercepto e probabilidades estimadas; a probabilidade será tratada como escore sob a amostragem e ponderação dos pares, não como probabilidade real de identidade. A árvore registrará profundidade observada, quantidade de folhas e limiares aprendidos.

Transformações, se necessárias, são ajustadas somente no treino. Cada configuração elegível gera escores de validação. Para cada método/configuração, seleciona-se na validação o limiar que minimiza FRR sujeito à estimativa pontual de FAR ≤ 0,001 (0,1%), teto reportado na Etapa 1. Empates são resolvidos primeiro pelo menor FAR pontual e depois pelo limiar mais estrito, com regra determinística. Se os escores forem inválidos ou nenhuma decisão puder satisfazer o teto, a configuração falha e não se relaxa o teto após observar teste. A estimativa pontual serve à seleção; ela, por si só, não sustenta uma afirmação estatística de que o método atende ao teto. Na avaliação final, só se afirmará atendimento quando a estimativa pontual e o limite superior do IC agrupado de 95% forem ambos ≤ 0,1%; caso contrário, o relatório marcará atendimento como não demonstrado. A configuração final e o limiar ficam congelados antes da avaliação final.

M1 não será recalibrado. Para M0/M1, a regra é aplicada à distância e não requer treino. Para M2–M4, a orientação do escore é definida como maior escore = classe positiva; o limiar selecionado na validação define a decisão binária.

## Execução em duas fases

1. **Preparar e congelar:** carrega somente metadados e partições treino/validação; valida proveniência e rótulos; treina candidatos; seleciona hiperparâmetros e limiares; grava parâmetros, seed, versões, assinatura do split, hash dos artefatos de entrada e resultados de validação. Esta fase não abre matrizes/arrays do teste.
2. **Avaliação final:** carrega o congelamento e valida sua integridade antes de abrir a partição de teste. Calcula uma única avaliação final dos modelos congelados. Não há retorno à fase de seleção em resposta aos resultados do teste.

A auditoria de integridade detecta identidade/imagem em mais de uma partição e inconsistências entre metadados, pares e cache. O protocolo não altera os dados originais.

## Avaliação e interpretação

M0, M1 e todos os modelos elegíveis recebem a mesma avaliação final. Serão calculados TP/TN/FP/FN, FAR, FRR, acurácia, precisão, recall, F1, ROC/AUC, EER, latência de inferência; tempo de treino para modelos treináveis. Para modelos probabilísticos, também Brier, curva e distribuição de calibração. Escores/probabilidades são sinais de decisão sob o desenho de amostragem dos pares, não probabilidades reais de identidade.

AUC da regressão logística univariada deve ser igual à ordenação induzida pela distância, salvo empates/implementação; não se alegará ganho de representação. `class_weight="balanced"` modifica o ajuste e não garante calibração. Para GNB serão reportadas a compatibilidade limitada entre distribuição observada e hipótese do modelo e as consequências para o escore. Árvores pequenas serão avaliadas por complexidade e risco de overfitting.

Intervalos de confiança para FAR/FRR usarão reamostragem agrupada por identidade, com seed fixa, preservando a dependência entre pares da mesma identidade. O relatório não tratará os milhões de pares como observações independentes. O número efetivo de identidades e a resolução estatística do FAR serão explícitos. Se os dados não sustentarem o teto de 0,1%, o resultado será “não demonstrado”, mesmo que o FAR pontual esteja abaixo dele.

Os gráficos reais previstos são: matrizes de confusão, ROC comparativa, FAR versus FRR, comparação de métricas, distribuições de distâncias, calibração da regressão logística, árvore e tempo de inferência. Relatórios de resultados sintéticos de teste de código não geram gráficos biométricos nem são apresentados como avaliação.

## Reprodutibilidade, privacidade e dependências

A execução registra seed 42 e versões de Python/scikit-learn/NumPy, FaceNet512, DeepFace, detector, pré-processamento, normalização, dimensão e configuração de inferência herdadas dos metadados experimentais. Só dependências necessárias ao experimento entram no ambiente isolado.

Artefatos com pares/embeddings/modelos permanecem locais e ignorados pelo Git. O relatório agrega métricas sem IDs, imagens, nomes ou scores por indivíduo. A condição de uso do dataset e risco de sobreposição entre LFW e dados de treino do FaceNet512 serão discutidos; sem evidência, não se afirmará independência do pré-treino.

## Testes e comandos previstos

Testes sintéticos cobrirão construção de características e rótulos, separação e validação de identidades, reprodutibilidade, treino dos três classificadores, seleção de configuração/limiar sem acesso a teste, métricas, ausência de classes, insuficiência de dados, persistência/carregamento e compatibilidade com artefatos da Etapa 1. Nenhum teste dependerá de webcam, PostgreSQL, rede, download, DeepFace ou dados biométricos.

Os comandos definitivos serão escritos após conferir a interface e a disponibilidade das dependências na implementação. A execução de qualquer comando sobre LFW fica condicionada à liberação documentada do gate de dados. Sem essa liberação, o relatório deve dizer “implementação concluída, avaliação experimental pendente”.

## Compatibilidade operacional e aceite

Não modificar webcam, anti-spoofing, adaptador FaceNet512, matcher, limiar/configuração `FACE_THRESHOLD`, cadastro, identificação 1:N, banco/esquema/migrations ou interface. Nenhum artefato experimental é carregado pela aplicação.

A conclusão desta etapa pode ser registrada como implementação e testes sintéticos concluídos enquanto o gate de autorização de dados estiver pendente. Não será declarada validação experimental completa sem execução permitida, avaliação congelada, relatório baseado em métricas reais e verificações aprovadas. Recomendações para Etapa 3 ficarão limitadas ao que os dados autorizados e a análise estatística efetivamente sustentarem; a Etapa 3 não será iniciada.
