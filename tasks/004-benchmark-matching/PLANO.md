# Benchmark de matching — plano de implementação

> Executor Luna 6 High: usar `superpowers:executing-plans`, se disponível, executar no próprio agente sem delegação ou novo brainstorming.

**Objetivo:** produzir medições sintéticas reproduzíveis e equivalência verificável do matcher atual.

**Arquitetura:** ampliar `scripts/benchmark_matcher.py`; referência sequencial independente, validação antes da medição, fases separadas de latência/montagem/memória e JSON agregado.

**Stack:** Python/NumPy/Pytest e biblioteca padrão existentes.

**Especificação:** [DESENHO.md](DESENHO.md), fonte normativa para dados, opções, métodos e limites de evidência.

## Restrições globais

- Não editar `src/`, dependências, CI, `.env.example`, configuração real, schema ou políticas operacionais.
- Nenhum dataset/rosto/embedding real, câmera, DeepFace, banco, instalação ou migração.
- Dimensão 512, float32 operacional, seed 1234, limiar 0.30 local; modos padrão None e margem zero.
- Testes verificam comportamento; não assertar vencedor, limite de milissegundos ou speedup em CI.
- Execuções reais somente depois dos testes; três runs sequenciais com mesmo protocolo. Não confundir smoke/unitários com medição de engenharia.
- Não editar históricos em tasks/001–003. Somente pacote 004/índice e documentação de performance pertinente.

## Pontos de revisão

| Risco | Prova prevista |
|---|---|
| Oráculo chama matcher ou aceita divergência de ID dentro da tolerância | Tarefa 1: referência independente e discrepância induzida |
| Média de bloco apresentada como p95 de chamadas | Tarefa 2: relógio falso e lista de durações conhecidas |
| Warm-up/RNG/tracing entram no timer | Tarefa 2: ordem de eventos e timers instrumentados |
| Pico rastreado apresentado como RSS ou buffer como processo inteiro | Tarefas 2–3: nomes/unidades/limites nos artefatos |
| Script sobrescreve evidências ou exporta vetores/segredos | Tarefa 3: saída exclusiva e schema limitado |

## 0. Inspeção e baseline

- [x] Ler instruções do repositório, DESENHO.md, relatório da 003, script, matcher, FaceEmbedding, testes, configuração de ferramentas e docs de performance.
- [x] Registrar status/branch/HEAD e verificar remoto conforme PROMPT.md. Preservar trabalho alheio e temporários. Baseline da preparação: `main` em `d8b6816`; verificar novamente.
- [x] Identificar ambiente de testes existente, sem instalar pacotes. Inspecionar fixtures e executar baseline `tests/unit` sem banco. O número 776 é histórico.
- [x] Confirmar consumidores do script por `rg`; preservar comando de módulo e evitar execução no import. Não executar benchmark antigo e chamar sua estimativa de medição.

## 1. Corpus, comparador e equivalência

Alterar `scripts/benchmark_matcher.py`; criar `tests/unit/test_benchmark_matcher.py`. Manter helpers no script; não criar um framework/serviço em src.

Produz `comparar_sequencial(...)` e `validar_equivalencia(...)` com assinaturas do desenho, corpus determinístico e wrapper de status comum. Usar tipos explícitos/pequenas dataclasses locais para o corpus se úteis; não persistir objetos.

- [x] Escrever testes falhando antes da implementação: corpus igual para seed/N iguais e independente da ordem dos tamanhos, vetores finitos L2-normalizados 512D, IDs 1..N, duplicata entre 1/2, consulta ortogonal e Q por cenário.
- [x] Cobrir referência clara, ortogonal, empate com políticas None/zero/positiva. Referência sequencial nunca chama `melhor_candidato` nem usa sua regra como função comum.
- [x] Provar precedência do limiar, concorrente de ID distinto, galeria vazia/única, IDs repetidos, empate/permutação e margem de fronteira exata com vetores de base. Reutilizar conceitos dos testes da 003 sem modificar seus arquivos.
- [x] Implementar gerador e comparador com um dot por referência e regra equivalente. Construir corpus antes de medir; normalizar via FaceEmbedding.
- [x] Implementar validação completa, `rtol=0`, `atol=1e-5`. Testar erro numérico acima do limite, status/ID diferente com distância próxima, NaN, exceção inesperada e igualdade correta.
- [x] Induzir discrepância via monkeypatch do método vetorizado e provar que a execução para antes de medir performance e retorna status/exit de falha. Não reduzir tolerância/excluir caso para esconder diferença.
- [x] Rodar testes focais até aprovação; nenhuma medida real de velocidade é critério.

## 2. Medição de tempo e memória

Mesmo script e testes. Produz `resumir_tempos(...)`, rotinas de latência por chamada, montagem e memória separadas.

- [x] Testar estatísticas usando durações ns `[1000, 2000, 3000, 4000]`: média/mediana 2.5 us, p95 3.85 us, mínimo 1 us, máximo 4 us, 400000 chamadas/s. Lista vazia, duração zero/negativa devem falhar.
- [x] Instrumentar relógio/callables falsos: warm-up não contribui, RNG/validação fora de timer, cada chamada gera uma amostra, ordem de métodos alterna por rodada, ambos percorrem mesmas consultas, número de amostras = Q*rodadas.
- [x] Implementar `perf_counter_ns`, estatísticas e razões sem arredondar dados de JSON (arredondamento só na tabela). Recusas por exceção usam wrapper igual nos dois métodos.
- [x] Medir montagem uma vez por N como fase independente: aquecimento, rodadas e descarte fora do timer. Testar que corpus não é reconstruído em cada amostra e que matching usa matriz pronta.
- [x] Implementar memória: soma `nbytes` efetiva, payload teórico e picos tracemalloc separados de tempos. Testar `N*512*4` para buffer teórico; não exigir pico exato dependente de allocator.
- [x] Testar limpeza de tracing em sucesso/erro, recusa quando tracing já ativo, nenhum profiling dentro da latência e descarte de resultados no passe de memória. Não interromper tracing iniciado externamente.
- [x] Rodar testes focais; não adicionar psutil/threadpoolctl nem alterar BLAS/GC.

## 3. CLI e artefato agregado

Mesmo script e testes. Interface `main(argv=None) -> int`, opções/defaults e JSON schema_version=1 do desenho.

- [x] Testar parsing, tamanhos duplicados/<3, contagens inválidas, seed negativo, margem zero/negativa/NaN/inf/>2 fornecida, opções omitidas e positiva explícita. Default inclui somente None/zero; terceiro modo exige valor >0.
- [x] Implementar CLI e remover constante/coluna `CUSTO_INFERENCIA_MS`. Manter `python -m scripts.benchmark_matcher` funcional e não ler Settings/env de produção.
- [x] Testar JSON com tmp_path: UTF-8 válido, allow_nan=False, campos/unidades, nenhum array/embedding serializado, somente metadados autorizados, arquivo existente preservado e criação exclusiva em corrida. Sem saída solicitada, nenhuma gravação.
- [x] Testar metadados com env falso contendo segredo: exportar apenas as três variáveis de threads permitidas, sem hostname/path/URL. Nome de CPU indisponível não bloqueia medição; registrar limitação de BLAS desconhecido.
- [x] Testar tabela com todos os cenários/modos/métodos, razão inclusive <1, artefato de validação falha sem performance válida e exit codes 0/1/2.
- [x] Executar smoke real curto em processo, por exemplo N=10, Q=2, rodadas=2, aquecimento=1, sem salvar vetores. Validar saída, sem usar esse smoke como evidência final de performance.

## 4. Verificação e medições reais

- [x] Executar suíte e ferramentas com ambiente existente:

```powershell
.\.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider
.\.venv-ml\Scripts\python.exe -m ruff check src scripts tests
.\.venv-ml\Scripts\python.exe -m mypy
.\.venv-ml\Scripts\python.exe -m ruff format --check scripts/benchmark_matcher.py tests/unit/test_benchmark_matcher.py
git diff --check
```

- [x] Não rodar integração/BDD/migrations com banco. Se precisar `--basetemp`, usar diretório novo exclusivo em `$env:TEMP`, sem remover os temporários existentes.
- [x] Depois das verificações, rodar sequencialmente três execuções reais, preservando arquivos se já existirem e escolhendo novos nomes nesse caso:

```powershell
.\.venv-ml\Scripts\python.exe -m scripts.benchmark_matcher --saida-json tasks/004-benchmark-matching/evidencias/execucao-1.json
.\.venv-ml\Scripts\python.exe -m scripts.benchmark_matcher --saida-json tasks/004-benchmark-matching/evidencias/execucao-2.json
.\.venv-ml\Scripts\python.exe -m scripts.benchmark_matcher --saida-json tasks/004-benchmark-matching/evidencias/execucao-3.json
```

- [x] Inspecionar JSONs: mesmo protocolo, validação aprovada em todos, unidades/dados agregados, sem vetores/PII, tempos positivos e memória descrita corretamente. Se houver divergência, reportar e não publicar benchmark como aprovado.
- [x] Criar RESULTADO.md com comandos efetivos, máquina/versões, três runs e faixas de medianas/p95 por combinação, razões inclusive desfavoráveis, memória e limitações. Não selecionar melhor execução nem impor piso de speedup.
- [x] Atualizar README/ARCHITECTURE e acrescentar nota ao ADR-002 conforme desenho: números novos rastreáveis, anteriores históricos; laço com NumPy por vetor, não protótipo de inferência, não comparação ANN/pgvector.
- [x] Conferir novamente diff/check se documentos mudaram. Nenhuma alteração em src, dados ou env. Marcar caixas realmente executadas e atualizar índice, sem declarar push antes de confirmá-lo.
- [ ] Commit e push conforme PROMPT.md, incluindo somente JSONs sintéticos agregados inspecionados. Responder com hash e evidência remota ou impedimento concreto.
