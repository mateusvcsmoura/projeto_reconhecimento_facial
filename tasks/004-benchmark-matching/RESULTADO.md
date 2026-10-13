# Resultado — tarefa 004: benchmark sintético de matching

## Implementação

O script `scripts/benchmark_matcher.py` gera galerias sintéticas determinísticas
de 512 dimensões, compara o matcher vetorizado com uma referência independente
que executa `NumPy dot` por embedding e valida todas as decisões antes de
qualquer medição. O CLI preserva `python -m scripts.benchmark_matcher` e oferece
tamanhos, consultas, rodadas, aquecimento, seed, margem opcional e saída JSON.
Ele não lê `.env` nem variáveis `FACE_*`. A estimativa antiga `2N × 80 ms` foi
removida.

A latência é amostrada chamada a chamada; montagem da matriz e passes de memória
ocorrem em fases separadas. O JSON é opcional, agregado, usa `allow_nan=False` e
destino exclusivo. Se a validação divergir, o processo retorna 1 antes dos
timers e grava apenas o diagnóstico de validação.

Nenhum arquivo em `src/`, configuração operacional, limiar, dependência, CI,
banco, imagem, embedding real ou histórico de tasks/001–003 foi alterado.

## Testes e verificações

O teste novo `tests/unit/test_benchmark_matcher.py` foi escrito antes da
implementação e observado falhando pela ausência dos contratos; depois passou.
Ele cobre corpus e normalização, desempates e margens, oráculo independente,
divergência de status/ID, erro numérico e NaN, estatísticas, relógio
instrumentado, ordem e aquecimento, separação entre validação/medição/memória,
limpeza do `tracemalloc`, metadados, CLI, destino exclusivo e JSON agregado.

```text
.venv-ml/Scripts/python.exe -m pytest tests/unit -p no:cacheprovider --basetemp <diretório temporário exclusivo>
812 passed in 8.14s

.venv-ml/Scripts/python.exe -m ruff check src scripts tests
All checks passed!

.venv-ml/Scripts/python.exe -m mypy
Success: no issues found in 69 source files

.venv-ml/Scripts/python.exe -m ruff format --check scripts/benchmark_matcher.py tests/unit/test_benchmark_matcher.py
2 files already formatted

git diff --check
exit 0
```

O baseline unitário antes da implementação foi `776 passed in 7.50s`. Não foi
executada suíte de integração/BDD nem qualquer teste que use banco.

O smoke curto real (`--tamanhos 10 --consultas-por-cenario 2 --rodadas 2
--aquecimento 1`) terminou com exit 0, 12 comparações, nenhuma divergência e
erro absoluto máximo `1.1920928955078125e-07`. Ele valida a entrada e a saída do
programa; os resultados abaixo vêm das três execuções padrão.

## Três execuções padrão

Os comandos foram executados **sequencialmente**, sem paralelismo, após a suíte
e as verificações:

```powershell
.\.venv-ml\Scripts\python.exe -m scripts.benchmark_matcher --saida-json tasks/004-benchmark-matching/evidencias/execucao-1.json
exit 0; status ok
```

```powershell
.\.venv-ml\Scripts\python.exe -m scripts.benchmark_matcher --saida-json tasks/004-benchmark-matching/evidencias/execucao-2.json
exit 0; status ok
```

```powershell
.\.venv-ml\Scripts\python.exe -m scripts.benchmark_matcher --saida-json tasks/004-benchmark-matching/evidencias/execucao-3.json
exit 0; status ok
```

Cada execução usou a mesma configuração: `N = [10, 50, 200, 1000]`, `Q = 10`
consultas por cenário, 10 rodadas, 3 chamadas de aquecimento, seed 1234,
dimensão 512, `<f4`, rótulo `Facenet512`, limiar local 0.30, política desligada
e margem zero. Os cenários artificiais foram `referencia`, `ortogonal` e
`empate`. A margem positiva não foi usada nestes três runs; sua opção foi
exercitada em teste. Cada JSON contém 48 linhas de matching e 4 de montagem.

Em cada execução, as 240 consultas combinadas tiveram 0 divergências de
status/ID, 0 divergências numéricas, 0 distâncias não finitas e erro absoluto
máximo de `1.1920928955078125e-07`, abaixo de `1e-5`. Para ambos os métodos, as
contagens agregadas foram 120 aceitos, 80 desconhecidos e 40 ambíguos. São
contagens de caminhos sintéticos validados; **não** são acurácia, FAR, FRR,
FPIR ou FNIR.

Contexto registrado: Windows 11, Python 3.14.3, NumPy 2.5.3, 12 CPUs lógicas e
relógio `QueryPerformanceCounter()` com resolução declarada de `1e-7 s`. Nome
do processador e arquitetura não estavam disponíveis. `OMP_NUM_THREADS`,
`OPENBLAS_NUM_THREADS` e `MKL_NUM_THREADS` estavam `nao_definido`; isso não
identifica por completo o BLAS nem prova suas threads efetivas.

### Latência e picos rastreados por combinação

A tabela mostra, para cada combinação, a faixa mínimo–máximo observada entre os
três runs para p50, p95 e pico rastreado de matching. Os tempos estão em
microssegundos. A razão é `mediana sequencial / mediana vetorizada` por run e
mostra a faixa entre as três execuções. Razão abaixo de 1 significa que o laço
foi mais rápido naquela combinação; não é critério de aprovação.

| N | Cenário | Modo | Sequencial p50 / p95 (µs) | Vetorizado p50 / p95 (µs) | Razão mediana | Pico tracemalloc (B), sequencial / vetorizado |
|---:|---|---|---:|---:|---:|---:|
| 10 | referencia | sem_politica | 11.800–12.100 / 13.330–22.340 | 5.900–5.900 / 6.830–17.535 | 2.000–2.051 | 292–292 / 960–960 |
| 10 | referencia | empate | 13.000–13.400 / 15.300–21.310 | 11.700–12.000 / 13.915–14.850 | 1.083–1.136 | 560–560 / 1006–1006 |
| 10 | ortogonal | sem_politica | 11.300–18.550 / 12.705–22.035 | 5.300–8.500 / 6.720–11.510 | 2.132–2.182 | 292–292 / 896–896 |
| 10 | ortogonal | empate | 11.200–19.100 / 12.405–20.800 | 5.200–8.600 / 6.300–11.645 | 2.154–2.221 | 292–292 / 896–896 |
| 10 | empate | sem_politica | 11.900–19.900 / 12.405–21.210 | 5.800–9.500 / 6.230–12.445 | 2.052–2.095 | 292–292 / 896–896 |
| 10 | empate | empate | 12.700–13.100 / 15.640–22.405 | 11.900–12.000 / 14.290–20.505 | 1.058–1.101 | 1280–1280 / 1466–1466 |
| 50 | referencia | sem_politica | 51.600–54.400 / 57.905–65.455 | 6.900–7.000 / 10.520–20.620 | 7.478–7.771 | 868–868 / 1056–1056 |
| 50 | referencia | empate | 54.900–57.600 / 62.425–71.675 | 15.000–15.500 / 21.010–22.205 | 3.574–3.765 | 1136–1136 / 1366–1366 |
| 50 | ortogonal | sem_politica | 51.200–53.350 / 56.875–93.555 | 6.200–6.600 / 8.660–13.125 | 7.758–8.468 | 868–868 / 1056–1056 |
| 50 | ortogonal | empate | 51.200–54.200 / 59.640–63.110 | 6.200–6.500 / 7.475–15.735 | 8.063–8.338 | 868–868 / 1056–1056 |
| 50 | empate | sem_politica | 51.700–53.300 / 56.210–83.220 | 6.800–7.000 / 8.070–11.605 | 7.386–7.838 | 868–868 / 1056–1056 |
| 50 | empate | empate | 54.400–57.200 / 61.935–68.720 | 15.200–15.300 / 20.035–45.480 | 3.556–3.763 | 1616–1616 / 1666–1666 |
| 200 | referencia | sem_politica | 204.200–216.300 / 214.255–371.885 | 11.100–14.400 / 15.830–58.920 | 14.576–19.486 | 6540–6540 / 2236–2236 |
| 200 | referencia | empate | 216.400–226.550 / 240.670–379.070 | 27.800–28.650 / 35.845–79.695 | 7.668–8.149 | 6832–6832 / 2716–2716 |
| 200 | ortogonal | sem_politica | 203.700–213.000 / 236.015–354.390 | 10.400–10.600 / 14.920–16.805 | 19.241–20.481 | 6540–6540 / 2236–2236 |
| 200 | ortogonal | empate | 203.600–215.000 / 213.340–363.350 | 10.600–11.150 / 17.035–25.250 | 18.377–20.283 | 6540–6540 / 2236–2236 |
| 200 | empate | sem_politica | 204.050–213.950 / 234.445–270.340 | 10.950–11.150 / 15.505–15.830 | 18.413–19.275 | 6540–6540 / 2236–2236 |
| 200 | empate | empate | 215.350–223.650 / 224.165–263.250 | 27.500–28.050 / 35.915–48.400 | 7.734–8.074 | 7336–7336 / 2716–2716 |
| 1000 | referencia | sem_politica | 1031.200–1625.500 / 1204.110–2552.245 | 93.900–138.550 / 173.770–241.685 | 10.517–11.732 | 32940–32940 / 8636–8636 |
| 1000 | referencia | empate | 1197.850–1506.250 / 1844.750–2552.055 | 181.650–214.750 / 321.630–411.020 | 6.409–7.712 | 33232–33232 / 9916–9916 |
| 1000 | ortogonal | sem_politica | 1125.250–1491.700 / 1754.440–2298.980 | 118.600–129.500 / 207.595–221.070 | 9.488–11.519 | 32940–32940 / 8636–8636 |
| 1000 | ortogonal | empate | 1083.650–1237.500 / 1553.055–2217.695 | 96.650–121.400 / 146.045–209.605 | 10.194–11.212 | 32940–32940 / 8636–8636 |
| 1000 | empate | sem_politica | 1023.600–1099.550 / 1436.755–1659.435 | 91.000–115.700 / 168.920–215.700 | 9.136–11.248 | 32940–32940 / 8636–8636 |
| 1000 | empate | empate | 1066.650–1170.450 / 1273.680–1586.995 | 161.100–173.650 / 236.510–278.145 | 6.422–6.740 | 33736–33736 / 9916–9916 |

### Montagem e payload

`payload_embeddings_bytes` é a soma de `nbytes` efetiva; `payload_matriz_teorico_bytes`
é apenas `N × 512 × 4`, não memória total. `montagem_pico_rastreado_bytes`
registra somente o pico observado durante a construção com `tracemalloc`.

| N | Payload embeddings / matriz teórica (B) | Montagem p50 / p95 entre runs (µs) | Pico de montagem rastreado (B) |
|---:|---:|---:|---:|
| 10 | 20480 / 20480 | 15.800–20.050 / 20.410–27.340 | 42096–42096 |
| 50 | 102400 / 102400 | 42.250–113.650 / 47.685–138.750 | 206192–206192 |
| 200 | 409600 / 409600 | 246.900–267.050 / 256.335–506.540 | 821776–821776 |
| 1000 | 2048000 / 2048000 | 1272.450–1498.250 / 1331.265–2109.340 | 4105776–4105776 |

Os picos de matching por método e combinação estão na tabela anterior e nos
JSONs. São valores observados pelo `tracemalloc`, não RSS, e não cobrem
necessariamente memória nativa/BLAS. Payload e pico rastreado não devem ser
somados como se fossem um pico global. Os resultados não estabelecem benefício
de memória: as medições têm escopos diferentes.

## Limites da evidência

Os embeddings seguem distribuição normal sintética em 511 componentes, com a
última componente zero; IDs 1 e 2 compartilham artificialmente um vetor.
Consultas são cópias/ortogonalidade artificiais e algumas se repetem
deliberadamente. Portanto, elas não são amostras independentes de uma
população, e os resultados medem somente comportamento funcional e custo
computacional deste protocolo local.

A referência sequencial usa um laço Python com um `NumPy dot` por embedding;
não reconstrói `DeepFace.verify()` nem 512 multiplicações Python por
referência. Os resultados não medem captura, inferência, anti-spoofing,
aplicação completa, biometria ou acurácia, e não calibram `FACE_THRESHOLD` nem
margem positiva. A tarefa não compara `pgvector`/ANN nem revisita alegações
históricas sobre eles. Os tempos locais variam com ruído, cache, ordem e BLAS;
três execuções não dão garantia estatística de generalização.

## Artefatos e estado antes da publicação

Os JSONs foram inspecionados: mesma configuração nos três; `status=ok`; tempos
e taxas positivos; campos agregados/unidades presentes; nenhum vetor, embedding,
hostname, usuário, caminho pessoal, URL ou segredo. Veja [execução 1](evidencias/execucao-1.json),
[execução 2](evidencias/execucao-2.json) e [execução 3](evidencias/execucao-3.json).

Imediatamente antes do commit, o checkout estava na branch `main`, base
`d8b6816b5aaecbb466c3b17ff141ae85aafc8c49`, sincronizada com `origin/main`; não
havia commits locais desconhecidos. O commit e o push ainda não tinham sido
executados quando este relatório foi fechado. A confirmação remota posterior
e o hash publicado são informados na resposta final, conforme a instrução
para não criar outro commit apenas para registrar o próprio hash.
