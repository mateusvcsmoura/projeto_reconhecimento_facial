# 004 — Desenho técnico: benchmark de matching

Estado: aprovado internamente para execução; implementação e medições pendentes.

Executor: Luna 6 High. Dependência: tarefa 003 concluída.

## 1. Análise e numeração

Este pacote segue a sequência proposta na conversa: qualidade, temporalidade, ambiguidade e **benchmark de matching**. O item 4 da lista geral de AGENTS.md é múltiplas referências; essa frente continua adiada. A tarefa 004 não altera cadastro nem quantidade de referências operacionais.

Inspeção em `main`, HEAD `d8b6816`, após `3472423` (ambiguidade) e `d8b6816` (registro de publicação). Status inicial sem alterações listadas, com avisos de acesso negado aos temporários antigos do pytest. Não houve consulta ao remoto nesta preparação.

O relatório da 003 registra 776 testes unitários, Ruff, mypy e verificação de formato aprovados. São evidências históricas; não foram reexecutadas nesta análise. O código confirma:

- Matcher mantém produto matriz-vetor único e, com ambiguidade ligada, reduz distâncias de IDs distintos usando máscara; nenhum novo embedding é calculado.
- `ReconhecerAluno` recebe a política e repassa ao matcher; a CLI trata a recusa nos três pontos de identificação e interrompe a sequência temporal.
- `scripts/benchmark_matcher.py` já existe: vetores sintéticos 512D, tamanhos 10/50/200/1000, seed 1234, uma consulta e 2000 repetições. Mede tempo médio e ciclos/s.
- A coluna antiga de custo usa `2*N*80 ms`, uma **estimativa**, não medição da implementação anterior.
- Ainda não há distribuição de latência, comparação cronometrada com referência em laço, equivalência verificada no próprio benchmark, custo separado de montagem, memória ou artefato estruturado.
- README/ARCHITECTURE e ADR-002 contêm informações históricas de performance. Não substituir números antigos por resultados não executados nem confundir matching com inferência.

## 2. Objetivo e escopo

Ampliar o script existente para produzir evidência reproduzível de engenharia sobre o matcher atual: equivalência de decisões, diferenças numéricas, latência por chamada, montagem da matriz e memória rastreável.

Comparar **matcher operacional vetorizado** com **laço Python que chama NumPy dot por referência**, ambos sobre os mesmos embeddings normalizados. A segunda implementação é uma referência experimental; não é reconstrução do protótipo de `DeepFace.verify` e não executa 512 multiplicações em Python por vetor.

Código permitido: script de benchmark, testes unitários novos, documentação e pacote tasks. **Não alterar `src/`**, dependências, CI, configuração operacional, thresholds, policies, schema ou dados. Se surgir discrepância real do matcher, reportá-la; não corrigir produção disfarçadamente neste benchmark.

Sem imagens, DeepFace, OpenCV, câmera, banco, cache de embeddings real ou rede para executar medições. Sem otimização, threads/workers, pgvector, gráficos ou novo framework de benchmark.

## 3. Comando e configuração

Preservar `python -m scripts.benchmark_matcher` como entrada funcional. Atualizar `main(argv: list[str] | None = None) -> int` com argparse:

| Opção | Default | Validação |
|---|---|---|
| `--tamanhos` | 10 50 200 1000 | um ou mais inteiros únicos >= 3; preservar ordem |
| `--consultas-por-cenario` | 10 | inteiro >= 1 |
| `--rodadas` | 10 | inteiro >= 1 |
| `--aquecimento` | 3 | inteiro >= 1 |
| `--seed` | 1234 | inteiro >= 0 |
| `--margem-ambiguidade` | ausente | opcional, finito em (0,2], para um terceiro modo sintético |
| `--saida-json` | ausente | arquivo novo; nunca sobrescrever existente |

Dimensão fixa 512, dtype operacional `<f4`, modelo como rótulo `Facenet512`, limiar local fixo 0.30. Não ler Settings, `.env` ou variáveis FACE_* para determinar o experimento.

Modos padrão: `sem_politica` (None) e `empate` (PoliticaAmbiguidade(0.0)). Se uma margem positiva for explicitamente fornecida, acrescentar `margem_explicita`, sem substituir os dois modos. O valor serve para comparar custo de uma política, não para calibrá-la; não declarar recomendação operacional.

Argparse inválido/erro de caminho: exit 2. Divergência de equivalência: exit 1. Medição/validação concluída: exit 0. Não executar nada no import. Remover a coluna e constante de inferência estimada do novo benchmark.

## 4. Corpus exclusivamente sintético

Para cada N, gerar uma galeria determinística com `np.random.default_rng(np.random.SeedSequence([seed, N]))`. IDs 1..N, uma referência por ID. Gerar vetores com distribuição normal nos primeiros 511 componentes e último componente zero; normalizar com `FaceEmbedding.de_valores`. Não usar `rng.random` somente positivo como substituto de distribuição facial.

Duplicar o vetor do ID 1 no ID 2, mantendo IDs distintos. É uma construção artificial para exercer empate. Não representa pessoas reais.

Criar três listas de Q consultas pré-construídas, rotacionando IDs quando aplicável:

| Cenário | Consulta | Intenção do caminho |
|---|---|---|
| `referencia` | cópia dos vetores de IDs 3..N em rodízio | vencedor claro no corpus padrão |
| `ortogonal` | vetor unitário na componente 512 | todas as distâncias 1: desconhecido pelo limiar |
| `empate` | cópia do vetor compartilhado por IDs 1 e 2 | sem política escolhe ID 1; com política recusa |

As três listas têm Q elementos. Repetições de vetores são deliberadas para medir caminhos, não amostras estatisticamente independentes de uma população. Rotular os nomes como cenários sintéticos; não apresentar contagens como top-1 accuracy/FAR/FPIR.

Com margem positiva muito alta, o cenário `referencia` também pode ser recusado. Registrar a decisão observada; não forçar aprovação nem alterar o corpus para obter resultado melhor. O cenário desconhecido permanece fora do limiar antes da margem.

Preparar todos os dados antes dos intervalos cronometrados. Nunca salvar arrays/vetores, dumps de objetos ou consultas no JSON; somente parâmetros e agregados. N determina sua própria seed derivada, independente da posição em `--tamanhos`.

## 5. Referência em laço e equivalência

Definir no script interfaces locais:

- `comparar_sequencial(pares: list[tuple[int, FaceEmbedding]], consulta: FaceEmbedding, limiar: float, ambiguidade: PoliticaAmbiguidade | None) -> Identificacao | None`.
- `validar_equivalencia(pares, referencia, consultas, limiar, ambiguidade) -> dict[str, object]`, com anotações completas na implementação; `consultas` é lista de `FaceEmbedding`, `referencia` é `MatrizDeReferencia`.
- `resumir_tempos(amostras_ns: list[int]) -> dict[str, float | int]`.
- `main(argv: list[str] | None = None) -> int`.

A referência em laço calcula uma distância por par com `consulta.distancia_cosseno(embedding)`, mantém primeiro mínimo, aplica limiar inclusivo e só então compara com o menor valor de ID distinto. Reproduz a semântica de `PoliticaAmbiguidade` e lança `IdentificacaoAmbigua`. Não chamar `melhor_candidato` por dentro da referência nem reutilizar sua função decisória como oráculo.

Usar wrapper comum de resultado para os dois métodos: `aceito` (ID/distância), `desconhecido`, `ambiguo`. Capturar somente `IdentificacaoAmbigua`. Outras exceções não são resultado válido. Esse wrapper também estará dentro da medição para ambos, contabilizando o custo real da exceção na recusa.

Antes de medir, validar **cada consulta** de cada cenário/modo/tamanho:

1. Mesmo status e mesmo ID aceito entre os dois métodos.
2. Distância aceita dentro de tolerância absoluta `1e-5`, `rtol=0`.
3. Fora dos timers, calcular distâncias matriciais com a mesma expressão/dtype de produção e compará-las com as distâncias em laço para registrar maior erro absoluto do vetor inteiro. Não acessar atributos privados do matcher. Essa checagem numérica é complementar; a checagem de decisões deve chamar o matcher real.
4. Distâncias finitas; erro máximo <= 1e-5. Tolerância serve somente à auditoria numérica, nunca para mudar decisão operacional, arredondar empates ou relaxar limiar/margem.

Qualquer status/ID diferente é divergência mesmo quando numericamente próximo. Interromper medições da execução inteira, retornar 1 e, se houver saída solicitada, gravar artefato `validacao_falhou` com diagnóstico agregado, sem tabela de performance parcial apresentada como válida. Não modificar produção para fazer o benchmark passar.

Também testar funcionalmente fixtures pequenas e bordas: galeria vazia, ID único, IDs repetidos, empate/permutação, desconhecido, segundo acima do limiar e igualdade de margem exatamente representável. Essas fixtures são testes, não necessariamente cenários cronometrados.

## 6. Protocolo de latência e montagem

Relógio: `time.perf_counter_ns`, injetável/monkeypatchável para testes. Não usar datetime ou sleeps. Uma observação de latência é **uma chamada**, não média de um bloco rotulada como p95 de chamadas.

- Aquecer cada combinação tamanho/cenário/modo/método por `aquecimento` chamadas não registradas, percorrendo consultas disponíveis.
- Em cada rodada executar Q chamadas por método para cada cenário/modo; alternar ordem dos métodos entre rodadas pares e ímpares. Mesmas consultas, mesma ordem para ambos. Não intercalar geração, validação, impressão, profiling ou IO nos timers.
- Cada chamada mede wrapper + matching sobre galeria pronta. Não incluir construção, cópia de corpus, geração ou normalização.
- Guardar durações inteiras em nanossegundos na memória. Duração não positiva é erro de medição; não inventar 1 ns nem dividir por zero. Os testes simulam relógio com resolução controlada.
- Resumo: quantidade, mínimo, média, mediana/p50, p95 por `np.percentile(..., 95, method="linear")`, máximo em microssegundos; `chamadas_por_segundo = quantidade * 1e9 / soma_ns`.
- Chamar a taxa de throughput dos trechos de matching medidos: não é FPS da câmera nem vazão da aplicação; exclui intervalos externos entre chamadas.
- Razão `mediana_sequencial / mediana_vetorizado`, para mesma combinação, sem prometer que será >1. É comparação com laço sobre embeddings, não ganho sobre DeepFace/protótipo.

Medir montagem `MatrizDeReferencia.de_embeddings(pares)` separadamente: aquecer uma vez e fazer `rodadas` construções a partir dos mesmos embeddings prontos, liberando cada instância fora do intervalo. Informar estatísticas de tempo; não incluir RNG/normalização. A galeria usada no matching é construída fora dos timers de chamadas.

Não alterar GC, afinidade, prioridade, BLAS threads ou ambiente automaticamente. Não criar limite de speedup para aprovação no CI. São tempos locais dependentes da máquina; ruído, cache e ordem influenciam a execução.

## 7. Memória com escopo explícito

Separar a coleta de memória da coleta de latência. Usar biblioteca padrão `tracemalloc`, sem instalar psutil ou medir RSS por estimativa.

Campos por N:

- `payload_embeddings_bytes`: soma efetiva de `embedding.vetor.nbytes` dos pares (N referências do corpus).
- `payload_matriz_teorico_bytes`: N * 512 * `np.dtype(DTYPE).itemsize`, explicitamente tamanho teórico do buffer da matriz, não memória total do processo.
- `montagem_pico_rastreado_bytes`: iniciar tracing com corpus já pronto, construir uma matriz, obter pico, encerrar tracing em finally. O pico inclui somente alocações observadas pelo tracemalloc durante essa construção, não o corpus anterior nem toda memória nativa.

Por combinação cenário/modo/método: `matching_pico_rastreado_bytes` para um passe separado das Q consultas, com corpus/matriz já prontos e resultados descartados por chamada. Iniciar/encerrar tracing especificamente para esse passe, limpar referências de resultados para não medir retenção de uma lista artificial.

Se tracemalloc já estiver ativo, falhar explicitamente em vez de reiniciar/interromper tracing de outro consumidor. Garantir desligamento do tracing iniciado pelo benchmark até em erro. Não somar picos de fases para inventar um pico global e não afirmar captura integral das alocações NumPy/BLAS. Não reportar ganho de memória baseado apenas em `nbytes`.

## 8. Saída e reprodutibilidade

Console com tabelas: validação; montagem/memória por N; matching por N/cenário/modo/método; razões pareadas. Descrever unidades e limites. Não imprimir vetores ou tabelas por pessoa.

JSON UTF-8, `allow_nan=False`, schema_version=1, campos:

- `status`: `ok` ou `validacao_falhou`;
- `config`: tamanhos, Q, rodadas, warm-up, seed, dimensão, dtype, limiar, modos/margens e distribuição artificial;
- `ambiente`: Python, NumPy, SO/release/arquitetura, processador textual quando disponível, contagem lógica de CPUs, resolução/implementação do relógio; `nao_disponivel` quando não houver nome de CPU;
- `threads_configuradas`: somente OMP_NUM_THREADS, OPENBLAS_NUM_THREADS e MKL_NUM_THREADS, com valor ou `nao_definido`. São configuração declarada, não prova de threads efetivas; nunca exportar todo o ambiente;
- `validacao`: quantidade de comparações, divergências de status/ID, erro máximo absoluto e tolerância;
- `montagem`: lista por N, estatísticas de tempo e memória da seção 7;
- `matching`: lista por N/cenário/modo/método com estatísticas, pico rastreado e contagens de status durante validação;
- `comparacoes`: razões de medianas para cada par e parâmetros completos;
- `limitacoes`: matching isolado, dados sintéticos, memória parcial, ruído e ausência de biometria.

Não registrar hostname, username, diretórios pessoais, variáveis de banco, URLs, arrays ou caches. Não capturar `np.show_config` integral com caminhos locais; versão NumPy e variáveis de threads não identificam completamente o BLAS, e essa limitação deve ser declarada.

JSON só quando solicitado. Criar diretório pai se necessário, abrir arquivo em modo exclusivo (`x`); falhar antes de medir se o destino já existir. Nunca sobrescrever mesmo se houver corrida. Não produzir CSV/gráfico nesta entrega.

## 9. Execuções e documentação exigidas

Após testes, executar três vezes o protocolo padrão, com mesmo seed/config, salvando novos arquivos agregados em `tasks/004-benchmark-matching/evidencias/execucao-1.json`, `execucao-2.json`, `execucao-3.json`. Se já existirem, preservar e usar nomes livres. Não executar runs em paralelo. Somente esses JSONs sintéticos agregados pertencem ao commit; nunca corpus/arrays.

Opcional de execução desta tarefa: um smoke com margem positiva explícita e N=10 para demonstrar a opção (sem transformá-la em recomendação). Sua lógica deve ser coberta nos testes mesmo se não houver esse run adicional.

RESULTADO.md deve comparar as três execuções sem selecionar apenas a mais rápida, registrar comandos, contexto de máquina, faixas de medianas e p95 por combinação, memória e validação. Não inventar intervalos de confiança ou ganhos biométricos. Três repetições não são garantia estatística de generalização.

Atualizar README e seção de performance de ARCHITECTURE com protocolo e links para evidências novas. Preservar os números antigos como históricos, rotulando-os. Em ADR-002, acrescentar nota de evidência atual: novo comparador é laço Python com NumPy por vetor; o benchmark não compara pgvector nem prova afirmações históricas sobre ANN. Não reescrever decisões antigas como se tivessem sido novamente medidas.

## 10. Aceite

Entrada antiga continua funcional; default mede dois modos e três cenários. Equivalência é gate antes de performance. Latência, construção e memória separadas. Artefatos não contêm dados de rosto ou segredos. Tests não dependem de velocidade real. Três execuções reais documentadas, sem exigir vitória do vetorizado. Nenhum arquivo operacional alterado. Commit/push conforme prompt.
