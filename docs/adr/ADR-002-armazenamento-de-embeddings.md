# ADR-002 — Armazenamento e comparação de embeddings faciais

- **Status:** aceito
- **Data:** 2026-09-07
- **Fase:** 4/5 (`REFACTORING_PLAN.md`)

---

## Problema

O protótipo comparava o frame com cada aluno chamando `DeepFace.verify()`
em laço. Cada chamada recalculava **dois** embeddings do zero: o do frame e
o da foto de referência. Com N alunos, até **2N inferências Facenet512 por
ciclo de comparação** — e as N inferências de referência eram desperdício
puro, já que as fotos não mudam (problema A5).

Três consequências:

1. o laço de vídeo congelava enquanto a varredura rodava, porque a
   inferência é síncrona na thread da interface;
2. o custo crescia linearmente com o número de alunos, tornando o sistema
   inviável acima de poucas dezenas;
3. `verify()` devolve apenas `verified: bool` na prática usada, então o
   código aceitava o **primeiro** aluno que passasse no limiar, e não o mais
   parecido — atribuindo a presença ao aluno errado sempre que dois
   candidatos ficassem próximos (problema A18).

Agravante: a foto de referência era o frame inteiro, não o rosto recortado,
o que forçava uma redetecção a cada comparação e guardava mais dado
biométrico do que o necessário (problema A14).

## Alternativas consideradas

### Onde guardar o vetor

| Opção | A favor | Contra |
|---|---|---|
| Recalcular sempre (protótipo) | Nada a persistir | É o problema |
| Arquivo `.npy` ao lado da foto | Simples de escrever | Segunda fonte de verdade fora do banco; complica exclusão, backup e transação |
| `REAL[]` (array do PostgreSQL) | Legível em SQL puro | ~4× maior em disco, sem ganho prático |
| **`BYTEA` (float32 little-endian)** | ~2 KB por aluno; `np.frombuffer` converte sem cópia; entra na mesma transação do cadastro | Não é inspecionável direto no `psql` |
| `pgvector` + índice HNSW | Correto para milhões de vetores | Extensão adicional no pré-requisito de infraestrutura; para centenas de alunos o índice **aproximado** é mais lento que a varredura exata, e ainda troca exatidão por velocidade que não é necessária |

### Como comparar

| Opção | Avaliação |
|---|---|
| `DeepFace.verify()` por aluno | Mantém o problema |
| Laço Python sobre os vetores | Sem inferência redundante, mas ~N×512 operações interpretadas por ciclo |
| **Produto matriz-vetor em NumPy** | Uma multiplicação para todos os candidatos; medido em microssegundos |

## Decisão

1. **`BYTEA` com float32 little-endian**, em `alunos.embedding`, acompanhado
   de `embedding_modelo` e `embedding_dim`, sob um `CHECK` que exige os três
   preenchidos ou os três nulos.
2. **Embedding calculado uma vez, no cadastro.** Custo por ciclo de
   reconhecimento: **uma** inferência, independente de N.
3. **Comparação vetorizada em NumPy**, em `domain/services/matcher.py`.
   Ambos os lados L2-normalizados, então a distância cosseno é
   `1 - produto_escalar`.
4. **Escolha do menor** entre os candidatos abaixo do limiar, e não do
   primeiro (fecha A18). A distância passa a ser exibida ao operador.
5. **Limiar externo** (`FACE_THRESHOLD`, padrão 0.30), em vez do limiar
   implícito da biblioteca.
6. **Armazena-se o rosto recortado e alinhado**, não o frame inteiro
   (fecha A14).
7. **Vetores de modelos diferentes nunca são comparados.** O modelo viaja
   junto do vetor; divergência levanta erro explícito.

## Justificativa

O ganho não é de tuning, é de desenho: o embedding de referência é
imutável, e recalculá-lo a cada comparação era trabalho que nunca precisou
existir.

Medição histórica do script anterior (`python -m scripts.benchmark_matcher`,
vetores de 512 dimensões, 2000 repetições por tamanho):

| Alunos | Comparação | Ciclos/s |
|---:|---:|---:|
| 10 | 0,0051 ms | 197.566 |
| 50 | 0,0064 ms | 155.409 |
| 200 | 0,0142 ms | 70.628 |
| 1000 | 0,1378 ms | 7.259 |

Esses tempos são referências históricas de uma execução do matcher
vetorizado; não vieram do protocolo atual e não incluem distribuição de
latência ou gate de equivalência.

Para 200 alunos, aquela execução reportou 0,0142 ms. O desenho anterior foi
descrito como até 400 inferências por ciclo no mesmo cenário. O custo por
ciclo hoje é **uma inferência mais o matching**, mas os tempos históricos
acima não medem a inferência.

Sobre o `pgvector`: dizer *por que não* adotá-lo, com o número na mão, vale
academicamente mais do que adotá-lo sem necessidade. A varredura exata sobre
centenas de vetores é mais rápida e mais simples que um índice aproximado.

### Nota de evidência — tarefa 004

O benchmark atual e seu protocolo estão registrados em
`tasks/004-benchmark-matching/RESULTADO.md`.
Ele compara a matriz vetorizada com um laço Python que executa `NumPy dot` por
embedding, usando somente vetores sintéticos. Esse laço não reconstrói o
protótipo de `DeepFace.verify()` nem mede inferência. A nova medição não
compara `pgvector`, não avalia índices ANN e não confirma as afirmações
históricas sobre a velocidade relativa de varredura exata e ANN. Os números
históricos acima permanecem registrados como contexto, não como resultado
reproduzido pela tarefa 004.

## Trade-offs aceitos

| Ganho | Custo |
|---|---|
| Uma inferência por ciclo, independente de N | Trocar `FACE_MODEL` invalida todos os embeddings gravados; exige backfill |
| Comparação exata, sem índice aproximado | A varredura é O(N); acima de ~100 mil alunos exigiria `pgvector` |
| Menos dado biométrico armazenado (só o recorte) | A imagem original do enquadramento se perde |
| Melhor candidato, com distância visível | Um limiar mal calibrado agora erra de forma mais visível — a Fase 7 o calibra com FAR/FRR |
| `numpy` como dependência do domínio | Aceita: é biblioteca numérica, não infraestrutura; não amarra o sistema a webcam, modelo ou banco |

## Consequências

- `alunos.foto_arquivo` continua existindo, agora com o recorte. A Fase 6
  decide se a imagem deve ser descartada de vez, mantendo só o vetor.
- Alunos cadastrados antes desta fase ficam invisíveis ao reconhecimento até
  `scripts/backfill_embeddings.py` rodar.
- O `matcher` é código puro: testável sem modelo de IA, sem webcam e sem
  banco. Onze testes cobrem empate, limiar, modelo divergente, dimensão
  divergente e equivalência com o cálculo ingênuo.
