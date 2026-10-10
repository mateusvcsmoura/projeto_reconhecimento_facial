# Etapa 4 — Aprendizado não supervisionado e agrupamento de embeddings

**Estado: implementação concluída; avaliação biométrica real pendente.** O pipeline e os testes usam vetores sintéticos. Nenhuma imagem, embedding, cache ou rótulo biométrico real foi aberto ou processado nesta etapa.

## 1. Resumo executivo

Foi implementada infraestrutura experimental para agrupamento não supervisionado de embeddings FaceNet512. O DBSCAN usa distância cosseno sobre vetores L2-normalizados; K-Means, em espaço euclidiano normalizado, serve como baseline. Os parâmetros são escolhidos exclusivamente por diagnósticos internos sobre desenvolvimento. A avaliação em teste é transdutiva, usa identidades reservadas e só calcula métricas externas depois do clustering.

O gate permaneceu fechado: não há autorização específica verificada para usar o LFW neste projeto, e o holdout da Etapa 1 já foi consultado historicamente. Não houve treinamento, extração biométrica, métrica real ou gráfico de desempenho. Os testes sintéticos verificam software e não constituem evidência de reconhecimento facial.

## 2. Objetivo acadêmico

Demonstrar como algoritmos não supervisionados podem agrupar embeddings faciais sem conhecer identidades durante o ajuste. Os rótulos verdadeiros ficam restritos à avaliação externa posterior. O experimento não cadastra nem identifica estudantes e não integra o fluxo operacional.

## 3. Estado das etapas anteriores

- **Etapa 0:** infraestrutura de separação de identidades, cache, falhas e proteção de artefatos implementada.
- **Etapa 1:** calibração 1:1 executada historicamente; o teste associado já foi consultado e não é tratado como holdout independente desta etapa.
- **Etapa 2:** código de classificadores implementado; treinamento/avaliação biométrica real pendente por falta de autorização.
- **Etapa 3:** pipeline open-set 1:N implementado; avaliação biométrica real pendente pela mesma restrição.

As Etapas 2 e 3 não são apresentadas como validações biométricas concluídas.

## 4. Gate de autorização

O LFW permanece somente candidato. A datasheet de origem registra ausência de licença formal e de aviso explícito/consentimento dos indivíduos, o que não comprova autorização para esta finalidade ou contexto institucional ([Datasheet do LFW, seção de licença e considerações legais](https://www.microsoft.com/en-us/research/wp-content/uploads/2019/01/1803.09010.pdf)). Não foi criado documento de consentimento ou licença.

O executor exige documento local não vazio e a opção explícita `--confirmar-revisao-autorizacao`; o sinalizador representa uma atestação do operador e **não valida juridicamente o documento nem substitui aprovações institucionais**. Como nenhuma autorização verificável foi fornecida, os comandos não foram executados contra qualquer dataset. O gate também precede inventário, hashing de imagens, abertura de cache e importação tardia do DeepFace.

## 5. Dataset e proveniência

**Dataset utilizado: nenhum.** Não foram consultados LFW, webcam, PostgreSQL, embeddings de alunos ou caches biométricos anteriores. O teste da Etapa 1 já foi observado, portanto não se afirma independência histórica em relação às mesmas identidades. Uma nova seed não resolveria essa limitação sem proveniência autorizada.

## 6. Preparação dos embeddings

O runner reutiliza inventário, deduplicação exata, divisão por identidade, cache versionado, extração e validação FaceNet512 das etapas anteriores. A configuração esperada é FaceNet512, detector OpenCV, alinhamento habilitado, anti-spoofing desabilitado para a avaliação de embeddings e normalização L2. A dimensão é validada como 512 e os vetores precisam ser finitos e não nulos.

Os caches da Etapa 4 são isolados por execução e partição (`desenvolvimento`, `validacao`, `teste`), evitando reabrir acidentalmente o holdout histórico. A API do cache existente ganhou `matriz()`, que entrega uma cópia dos vetores sem expor hashes de imagem.

Duplicatas exatas de arquivos são detectadas antes da divisão pela infraestrutura existente. Entre embeddings, conta-se o excedente de linhas idênticas e o número de amostras com vizinho cosseno abaixo do limite heurístico `1e-6`. Esse alerta não é detecção perceptual de imagens duplicadas.

## 7. Algoritmo DBSCAN

DBSCAN (`sklearn.cluster.DBSCAN`) é o método principal. Usa `metric="cosine"`, `eps` como raio local de densidade e `min_samples` como suporte mínimo. A matriz normalizada torna cosseno coerente com a geometria dos embeddings; distância cosseno e euclidiana não são intercambiáveis em todas as operações, então a escolha é registrada. O limiar operacional 1:1 `0.30` não é usado como regra para `eps`.

A implementação registra ruído (`-1`), número e tamanhos dos clusters, singletons, clusters pequenos, cobertura e estado diagnóstico: sem clusters, cluster único, ruído alto, muitos clusters pequenos ou clusters encontrados.

## 8. Algoritmo K-Means

K-Means (`sklearn.cluster.KMeans`) é baseline comparativo. Usa vetores L2-normalizados no espaço euclidiano, `n_init=10` e seed fixa. A grade de `n_clusters` é limitada por quantidade de amostras e escolhida sem a quantidade real de identidades. O método exige número de clusters, é sensível à inicialização, não modela ruído explicitamente e favorece partições aproximadamente convexas/esféricas.

## 9. Seleção de parâmetros

O seletor recebe somente a matriz de embeddings e a grade — não recebe vetor de identidade. No DBSCAN, usa `eps=(0.10, 0.20, 0.35, 0.50, 0.75)` e `min_samples=(2, 3, 5)`. Elegibilidade exige pelo menos dois clusters, silhouette válida e cobertura mínima predefinida de 50%. Entre candidatos elegíveis, maximiza silhouette cosseno; desempata por maior cobertura, menos ruído, menos clusters pequenos e ordem determinística dos parâmetros.

K-Means avalia `k=(2, 3, 5, 8, 13)` quando `k < n`, maximizando silhouette cosseno e desempata pelo menor `k`. A busca não conhece os rótulos verdadeiros nem usa o número real de identidades. Se nenhuma configuração for válida, o algoritmo fica indisponível.

A estabilidade é diagnosticada no desenvolvimento com cinco subamostras determinísticas de 80%, comparando partições por ARI sem rótulos externos. É um diagnóstico exploratório de instabilidade, não critério para ajustar em teste nem garantia de generalização.

## 10. Métricas internas

Silhouette cosseno, Davies–Bouldin e Calinski–Harabasz são calculadas apenas quando há ao menos dois clusters e menos clusters que amostras avaliadas. Para DBSCAN, as métricas internas são calculadas sobre amostras não classificadas como ruído; cobertura e percentual de ruído são mostrados junto. Para K-Means, todos os pontos entram. Davies–Bouldin e Calinski–Harabasz usam distância euclidiana sobre vetores normalizados.

Para diagnóstico de `eps`, as distâncias ao k-ésimo vizinho são calculadas por `NearestNeighbors` com armazenamento O(nk), sem materializar a matriz n×n.

## 11. Métricas externas

Depois do agrupamento, quando houver rótulos autorizados, o relatório calcula ARI, NMI, homogeneity, completeness e V-measure somente sobre pontos não-ruído e sempre reporta a cobertura. Como análise de sensibilidade, calcula também ARI em todos os pontos tratando `-1` como uma única classe de ruído; isso pode confundir ruído heterogêneo com um cluster real e não substitui os resultados com cobertura.

Nenhuma métrica externa foi medida nesta entrega.

## 12. Tratamento de ruído

O rótulo DBSCAN `-1` não é tratado como identidade válida nas métricas principais de silhouette ou métricas externas cobertas. Ruído permanece no denominador de cobertura e no cálculo de ARI secundário sobre todos os pontos, identificado explicitamente. K-Means não possui classe de ruído; todos os seus pontos são cobertos.

## 13. Visualizações

O gerador prevê PCA por cluster, PCA por identidade verdadeira codificada, distribuição de tamanhos, ruído por configuração, silhouette por configuração, comparação DBSCAN/K-Means, ARI/NMI e curva k-vizinhos. Figuras recebem somente dados em memória e não exibem nomes ou caminhos pessoais. PCA é apenas projeção visual e não comprova validade no espaço original.

**Gráficos produzidos nesta entrega: nenhum.** A avaliação real não foi autorizada/executada; os vetores sintéticos dos testes não são apresentados como resultados experimentais.

## 14. Escalabilidade

O relatório mede tempo de ajuste, número de amostras, dimensão e tamanho aproximado da matriz de entrada. O cache evita inferência FaceNet512 repetida para o mesmo conteúdo dentro da execução. DBSCAN pode exigir custo de tempo/memória elevado conforme densidade e implementação da busca de vizinhos; silhouette também pode ser O(n²). A busca k-vizinhos usa vizinhos sob demanda e não aloca matriz completa. Não há benchmark biométrico real nesta etapa.

## 15. Resultados reais

Não houve execução biométrica autorizada. Nenhum ARI, NMI, silhouette, tempo ou percentual de ruído real foi medido. Os valores candidatos de parâmetros são protocolo, não resultados.

| Método | Parâmetros | Métricas biométricas reais | Estado |
|---|---|---|---|
| DBSCAN | Seleção pendente | Pendente | Não executado |
| K-Means | Seleção pendente | Pendente | Não executado |

## 16. Testes automatizados

Os testes usam vetores sintéticos, fixtures e extrator falso; nenhum dado biométrico real foi aberto. Resultados executados em 10/10/2026:

- Testes focais da Etapa 4: **22 passaram**.
- Suíte completa: **597 passaram** (`597 passed in 16.56s`).
- `ruff check src scripts tests`: **aprovado**.
- `mypy`: **aprovado, 67 arquivos verificados**.
- `ruff format --check` nos seis arquivos alterados da Etapa 4: **aprovado**.
- Verificação de formatação adicional em todo `src/`, `scripts/` e `tests/`: **32 arquivos existentes precisam de reformat**, 73 já estão formatados. Os seis arquivos alterados nesta etapa passaram na verificação focada; o escopo não foi ampliado para reformatar arquivos alheios.

O primeiro `ruff check .` também retornou sucesso, com avisos de acesso negado ao percorrer diretórios temporários antigos do pytest. A verificação final foi executada diretamente em `src/`, `scripts/` e `tests/` e passou sem esses avisos. Testes sintéticos validam software, não biometria.

## 17. Segurança e privacidade

Não houve acesso a dados operacionais, PostgreSQL, Neon, webcam ou serviços externos. O cache, congelamento, métricas agregadas e gráficos são restritos a `avaliacao/`, já ignorado pelo Git junto com `*.npy` e imagens. O manifesto não contém nomes, caminhos, identificadores individuais nem embeddings; logs sanitizam falhas como categorias. Documento de autorização não é criado nem presume consentimento.

## 18. Limitações

- Sem dataset autorizado, não é possível afirmar que identidades formam clusters.
- DBSCAN e K-Means são transdutivos: na partição teste, cada algoritmo é ajustado novamente sem rótulos; isso não equivale a prever cluster de uma amostra futura.
- Silhouette em pontos cobertos pode favorecer configuração que omite casos difíceis; a cobertura é apresentada junto e restringe a elegibilidade DBSCAN.
- Bootstrap/intervalos por identidade não são reportados sem experimento. Consultas do mesmo indivíduo e partições/galerias de um dataset são dependentes.
- LFW tem diferenças de domínio em relação à webcam e pode sobrepor identidades já observadas ou dados de pré-treinamento FaceNet512.
- Thresholds de quase duplicata e de estabilidade são diagnósticos heurísticos, não decisões biométricas ou garantias.
- K-Means impõe `k`; a busca interna não pode demonstrar por si só que o número de clusters coincide com pessoas reais.

## 19. Conclusões

O pipeline experimental de DBSCAN/K-Means implementa seleção sem rótulos, ruído explícito, divisão por identidade, cache isolado e holdout reservado até congelamento. A evidência sustenta apenas o funcionamento do software em cenários sintéticos; não sustenta qualidade, segurança, equidade ou adequação de agrupamento facial real.

### Critérios de aceite da implementação

- [x] DBSCAN e K-Means implementados; seleção dos parâmetros não recebe rótulos verdadeiros.
- [x] Métricas externas/internas, cobertura e tratamento de ruído implementados.
- [x] Gate de autorização preservado e exercitado pelos testes sem acesso ao dataset.
- [x] Divisão/cache/holdout validados com fixtures sintéticas; holdout consumido uma vez.
- [x] Testes focais, suíte completa, Ruff, mypy e formato dos arquivos alterados aprovados.
- [x] Código operacional preservado: `git diff --exit-code -- src` passou; a única alteração em arquivo preexistente é o método matricial do cache experimental em `scripts/calibrar_limiar.py`.
- [x] Relatório e comandos reproduzíveis registrados.
- [ ] Avaliação biométrica real: pendente de fonte autorizada, revisão institucional e execução legítima.

## 20. Pendências

1. Obter fonte autorizada para finalidade de pesquisa e revisão institucional documentada; não usar alunos cadastrados.
2. Revisar termos/licenças e confirmar armazenamento, retenção e proteção local antes da execução.
3. Registrar proveniência, sobreposição histórica do teste Etapa 1 e possível sobreposição ao pré-treinamento FaceNet512.
4. Após autorização válida e revisão institucional, executar `preparar` para congelar parâmetros sem rótulos; somente depois executar `avaliar` no holdout uma vez.

### Impacto no sistema operacional

Nenhum arquivo de `src/` foi alterado. FaceNet512 operacional, MiniFASNet, matcher, `FACE_THRESHOLD`, webcam, cadastro, presenças, banco, schema, migrations e interface não mudaram. A única alteração a uma infraestrutura existente é um método de leitura matricial do cache experimental da Etapa 1; não modifica inferência, persistência ou uso operacional.

## 21. Preparação para a Etapa 5

Os testes e verificações de software estão concluídos. A implementação está pronta para consolidação acadêmica e planejamento da Etapa 5; isso não conclui a avaliação biométrica real. Não avancei para a Etapa 5 nem usei LFW. Antes de qualquer execução biométrica, ainda são necessárias autorização apropriada, revisão institucional e confirmação de proveniência. Interprete resultados futuros considerando densidade, estabilidade, cobertura, domínio e risco de reidentificação.

Use ambiente experimental isolado com dependências de `requirements-ml.txt` e seed 42. Somente após as aprovações externas apropriadas, os comandos de referência são:

```powershell
python -m scripts.experimento_agrupamento preparar `
  --dataset avaliacao/datasets/<dataset-autorizado> `
  --autorizacao-dataset <documento-local> `
  --confirmar-revisao-autorizacao `
  --seed 42

python -m scripts.experimento_agrupamento avaliar `
  --dataset avaliacao/datasets/<dataset-autorizado> `
  --autorizacao-dataset <mesmo-documento-local> `
  --confirmar-revisao-autorizacao
```

As versões de Python, NumPy, scikit-learn, DeepFace, OpenCV, TensorFlow e Matplotlib, a seed, as assinaturas de dataset/divisão, a configuração de extração e as contagens agregadas ficam no congelamento. O primeiro comando extrai desenvolvimento/validação e congela parâmetros; o segundo valida o congelamento, reserva o teste antes de inventariar/extrair a partição e só então calcula métricas externas. A Etapa 5 não foi iniciada.
