# Demonstração acadêmica offline

Roteiro de aproximadamente **5 minutos** para mostrar as melhorias 001–004
sem câmera, banco, modelo carregado, imagem facial ou arquivo de ambiente. Os
testes usam arrays sintéticos e doubles; o benchmark de smoke também gera
embeddings sintéticos. A apresentação geral de 13–15 minutos está em
[ML-ROTEIRO-APRESENTACAO.md](ML-ROTEIRO-APRESENTACAO.md), e o estado atual com
fontes e limites está em [ESTADO-ATUAL-E-EVIDENCIAS.md](ESTADO-ATUAL-E-EVIDENCIAS.md).

## Preparação

- Abra o PowerShell na raiz do repositório.
- Use o ambiente existente .venv-ml; não instale dependências nesta
  demonstração.
- Não execute python -m src.main, Docker, Alembic ou testes sem seleção.
  Eles não fazem parte do roteiro offline.
- A saída das medições longas da tarefa 004 já está nos três JSONs agregados;
  o smoke abaixo não sobrescreve nem cria JSON.

## Roteiro de cinco minutos

| Tempo | Ação | O que explicar |
|---|---|---|
| 0:00–0:40 | Abra o registro atual e apresente o fluxo 1:N. | O operador confirma antes do registro. O modelo é pré-treinado; o limiar 0,30 permanece sem nova calibração biométrica. |
| 0:40–2:10 | Execute a seleção unitária abaixo. | Qualidade, tempo e margem são contratos de software exercitados com dados sintéticos; não são taxas de reconhecimento. |
| 2:10–2:35 | Mostre a interface de linha de comando do benchmark. | O CLI aceita dimensões, rodadas, aquecimento e saída JSON; não depende de inferência facial. |
| 2:35–3:25 | Execute o smoke curto. | A validação compara 12 consultas sintéticas antes da medição. Observe status e divergências; ignore o tempo como previsão de operação. |
| 3:25–4:25 | Leia o resumo de execucao-1.json e o relatório 004. | As três execuções históricas compararam 240 consultas cada, sem divergências; tracemalloc não mede RSS. |
| 4:25–5:00 | Feche pelos limites e pendências. | Frames correlacionados, margens sem calibração e ausência de avaliação 1:N autorizada impedem alegações de acurácia em sala. |

### 1. Testes sintéticos focais

Use uma pasta temporária exclusiva fora do repositório:

~~~powershell
$task005Temp = Join-Path ([System.IO.Path]::GetTempPath()) ("rf-task005-" + [guid]::NewGuid().ToString("N"))
.\.venv-ml\Scripts\python.exe -m pytest tests/unit/test_qualidade_captura.py tests/unit/test_consistencia_temporal.py tests/unit/test_matcher_ambiguidade.py tests/unit/test_benchmark_matcher.py -q -p no:cacheprovider --basetemp $task005Temp
~~~

O resultado esperado é código 0 e todos os testes selecionados aprovados. A
quantidade desta seleção está registrada em tasks/005-consolidacao-demonstracao/RESULTADO.md;
ela não é a suíte inteira. Os testes de qualidade usam recortes sintéticos,
o confirmador temporal usa relógio controlado, o matcher usa embeddings
sintéticos e os testes do benchmark não carregam DeepFace. O conftest.py da
raiz apenas define fixtures de PostgreSQL para testes que as solicitam; estas
quatro seleções não usam essas fixtures.

### 2. CLI e smoke do benchmark

~~~powershell
.\.venv-ml\Scripts\python.exe -m scripts.benchmark_matcher --help
.\.venv-ml\Scripts\python.exe -m scripts.benchmark_matcher --tamanhos 10 --consultas-por-cenario 2 --rodadas 2 --aquecimento 1
~~~

No primeiro comando, mostre os argumentos. No segundo, confirme saída normal,
12 comparações validadas, status sem divergência e ausência de arquivo JSON.
O smoke demonstra execução do protocolo em miniatura; seus tempos não são
comparáveis às execuções padrão e não são latência da aplicação.

### 3. Consulta das evidências históricas

~~~powershell
$run = Get-Content tasks/004-benchmark-matching/evidencias/execucao-1.json -Raw | ConvertFrom-Json
$run.validacao | Format-List status, comparacoes, divergencias_status_id, divergencias_numericas, erro_maximo_absoluto, tolerancia_absoluta
$run.montagem | Format-Table n, payload_embeddings_bytes, montagem_pico_rastreado_bytes
~~~

Abra também tasks/004-benchmark-matching/RESULTADO.md para comparar as três
execuções e ver p50/p95 por cenário. Os JSONs são artefatos sintéticos
agregados já versionados; não execute o benchmark padrão durante esta
apresentação nem interprete a amostra como resultado biométrico.

## Interpretação dos controles

- **Qualidade:** tamanho, luminância e nitidez podem pedir nova captura quando
  a flag está ativa; os limites são heurísticas. Orientação facial explícita
  não é verificada e qualidade não substitui anti-spoofing.
- **Temporal:** três identificações iguais são exigidas por padrão quando a
  opção é ativada, mas quadros próximos são correlacionados. A sequência não
  comprova uma identidade correta.
- **Ambiguidade:** a margem compara a primeira e a segunda identidade após o
  melhor candidato passar pelo limiar. Margem zero rejeita empate exato;
  margem positiva não está calibrada.
- **Benchmark:** mede matching sintético isolado. A referência executa um
  NumPy dot por embedding; não simula DeepFace.verify() nem a inferência
  FaceNet512.

Se .venv-ml ou os comandos não estiverem disponíveis, não instale pacotes no
meio da apresentação. Mostre os relatórios e rotule os resultados como
históricos. Em nenhuma variante abra câmera, banco, arquivo de ambiente,
modelos, storage/ ou avaliacao/.
