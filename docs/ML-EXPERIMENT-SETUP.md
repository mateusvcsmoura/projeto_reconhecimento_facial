# Preparação experimental de Machine Learning

Como montar, validar e descartar os dados de avaliação do reconhecimento
facial. Escrito na Etapa 0 (`docs/ML-ETAPA-0-RESULTADO.md`), a partir das
lacunas G4, G5, G6, G10 e G11 de `docs/ML-LEARNING-AUDIT.md`.

> **Regra que vem antes de tudo:** os rostos e embeddings dos **alunos
> cadastrados nunca entram em experimento**. O consentimento deles cobre
> apenas o controle de presença (`docs/lgpd.md` §2). Experimento usa dataset
> público com termos de uso verificados ou voluntários com consentimento
> **específico para pesquisa** (§7).

---

## 1. O que roda hoje e o que depende de implementação futura

| Avaliação | Comando | Estado |
|---|---|---|
| Validação da estrutura e da divisão por identidade | `--validar-divisao` | **Disponível.** Não precisa de DeepFace nem de banco |
| A — exploratória (todos os pares, sem divisão) | sem flag | **Disponível, com ressalva:** limiar e erro saem dos mesmos pares. Serve para olhar, **não** para calibrar |
| A — calibração do limiar com treino/validação/teste | — | **Etapa 1.** A infraestrutura de divisão já existe; falta a calibração |
| A — classificadores (regressão logística, etc.) | — | Etapa 2 (`ML-LEARNING-AUDIT.md` §11) |
| A — identificação 1:N (FPIR/FNIR) | — | Etapa 3 |
| B — anti-spoofing (APCER/BPCER) | — | **Sem data.** Depende de um dataset de ataques que o projeto não tem (§4) |

---

## 2. Estrutura de diretórios

Tudo o que é dado experimental fica sob `avaliacao/`, que o `.gitignore`
exclui por inteiro. Código, testes e documentação ficam onde já estão.

```text
avaliacao/                        ← IGNORADO pelo Git, inteiro
├── datasets/
│   └── <nome-do-dataset>/        ← um diretório por dataset
│       ├── <identidade-1>/       ← um diretório por pessoa
│       │   ├── 0001.jpg
│       │   └── 0002.jpg
│       └── <identidade-2>/
│           └── ...
├── cache/                        ← embeddings (.npy) — uso a partir da Etapa 1
└── resultados/                   ← saídas de execução, se forem salvas
```

### Formato esperado

| Regra | Detalhe |
|---|---|
| Identidade | O **nome do diretório** é o rótulo. Duas pastas = duas pessoas, mesmo que sejam a mesma pessoa por engano — revise antes |
| Imagens | `.jpg`, `.jpeg`, `.png` (extensão sem distinção de maiúsculas) |
| Um rosto por imagem | Imagem com 0 ou 2+ rostos é rejeitada e contada (§5) |
| Imagens por pessoa | Mínimo 2 para gerar par genuíno; recomendado 5+ |
| Tamanho mínimo do dataset | 6 identidades (2 por conjunto) — mínimo técnico, não estatístico. Útil a partir de dezenas |
| Arquivos fora do formato | Ignorados e **contados** no relatório (`Arquivos ignorados`) |
| Nomes com acento | Aceitos: a imagem é lida pelo próprio script, não pelo DeepFace, que exige caminho ASCII |

---

## 3. Comandos

```bash
# 1) Validar estrutura e divisão — qualquer ambiente, sem modelo e sem banco
python -m scripts.evaluate_model --dataset avaliacao/datasets/<nome> --validar-divisao
python -m scripts.evaluate_model --dataset avaliacao/datasets/<nome> --validar-divisao --seed 7

# 2) Avaliação A exploratória — Python 3.12/3.13 com DeepFace (.venv-app)
python -m scripts.evaluate_model --dataset avaliacao/datasets/<nome>

# 3) Testes automatizados da infraestrutura (sem DeepFace, sem imagens reais)
pytest tests/unit/test_divisao_por_identidade.py tests/unit/test_evaluate_model.py tests/unit/test_metricas.py
```

Saída do modo 1 sobre um dataset **sintético** de 12 identidades com 3
arquivos cada (execução real desta etapa):

```text
=== Divisao por identidade (seed 42) ===
  conjunto | ident. | imagens | genuinos | impostores
-------------------------------------------------------
    treino |      8 |      24 |       24 |        252
 validacao |      2 |       6 |        6 |          9
     teste |      2 |       6 |        6 |          9

Sobreposicao de identidades entre conjuntos: nenhuma (verificada)
Assinatura da divisao: 0d4d2b2afcffae69
```

---

## 4. Avaliação A × Avaliação B

As duas medem coisas diferentes e **não se misturam** num mesmo número.

| | **A — Reconhecimento facial** | **B — Anti-spoofing (prova de vida)** |
|---|---|---|
| Pergunta | "Estes dois rostos são da mesma pessoa?" | "Este rosto é de uma pessoa ao vivo?" |
| Pipeline | Detecção → embedding Facenet512 → distância cosseno | Detecção → MiniFASNet → real × ataque |
| Prova de vida | **Desligada** (`anti_spoofing=False`): o dataset é de fotografias, e recusá-las anularia a medição | É o objeto da medição |
| Dados | Fotos de pessoas, uma pasta por identidade | Capturas **ao vivo** e **ataques** (foto impressa, tela) das mesmas pessoas, nas condições da sala |
| Métricas | FAR, FRR, ROC/AUC, EER (ISO/IEC 19795-1) | APCER, BPCER (ISO/IEC 30107-3) |
| Estado | Exploratória disponível; calibração na Etapa 1 | **Não implementada.** Sem dataset adequado, qualquer número seria inventado |

**Limitação declarada da Avaliação A:** o FRR medido **não inclui** as
rejeições da prova de vida. Em produção, com `FACE_ANTI_SPOOFING=true`, o
FRR real tende a ser maior — já há falsa rejeição em contraluz registrada em
`docs/apresentacao.md` §6. A configuração operacional da prova de vida
**não foi alterada**.

**O que a Avaliação B exigiria** (fora do escopo atual): voluntários com
consentimento específico; capturas ao vivo e ataques com mídias variadas;
mesma câmera e iluminação da operação; relatório de APCER por tipo de ataque
e BPCER. Datasets públicos de ataque existem, mas têm licenças restritivas e
condições diferentes das da sala — verificar antes de qualquer uso.

---

## 5. Falhas de extração: como são contadas

Toda imagem recebida termina em **processada** ou **rejeitada com motivo**.
O resumo mostra os dois números e avisa quando a amostra avaliada é menor
que a recebida.

| Motivo no relatório | Origem | Causa típica |
|---|---|---|
| `erro de leitura` | `OSError`, `ImagemIlegivel` | Arquivo inexistente, sem permissão, vazio ou em formato não decodificável |
| `sem rosto detectado` | `NenhumRostoDetectado` | Rosto pequeno, de perfil, cortado; detector Haar falhou |
| `multiplos rostos` | `MultiplosRostosDetectados` | Mais de uma pessoa no enquadramento |
| `falha de inferencia` | `ModeloIndisponivel` | Erro do DeepFace/TensorFlow numa imagem específica |
| `embedding invalido` | `EmbeddingInvalido` | Vetor vazio, com NaN ou de norma zero |
| `recusada pela prova de vida` | `PossivelFraude` | Não ocorre na Avaliação A (prova de vida desligada); classificada por completude |

- A imagem é **lida e decodificada antes** do modelo (`ler_imagem`), para que
  um arquivo ruim não chegue ao DeepFace e volte disfarçado de falha de
  inferência.
- **Qualquer outra exceção aborta a avaliação**, com o caminho da imagem
  anexado ao erro. Erro de programação não vira estatística.
- Se o modelo não carregar (`preaquecer`), o script para antes de ler a
  primeira imagem.
- Pessoa com todas as imagens rejeitadas sai da avaliação e aparece em
  `Identidades avaliadas`.
- Sem 2 pessoas ou sem par genuíno, o script termina com código 2 e **não
  imprime nenhuma métrica**.

---

## 6. Divisão por identidade

Implementada em `scripts/divisao_por_identidade.py` (funções puras).

1. As identidades com 1+ imagem são **ordenadas** — a ordem do disco não muda
   o resultado — e embaralhadas com `random.Random(seed)`.
2. Corte em **60% treino / 20% validação / 20% teste**, com no mínimo 2
   identidades por conjunto (um par impostor exige duas pessoas).
3. A divisão acontece **antes de formar pares**: nenhuma pessoa aparece em
   dois conjuntos. O construtor de `Divisao` recusa sobreposição
   (`VazamentoDeIdentidade`).
4. Cada conjunto precisa de pares genuínos **e** impostores; senão,
   `DadosInsuficientes` — e nenhum número é reportado.
5. **O teste vem lacrado.** Treino e validação são acessíveis; as identidades
   de teste só saem por `abrir_teste(limiar_congelado)`, **uma vez**. Um
   segundo acesso levanta `UsoIndevidoDoTeste`. É proteção de API: torna o
   uso indevido explícito, não impossível.
6. `resumir()` conta identidades, imagens e pares de cada conjunto — inclusive
   do teste — **sem abri-lo**. Contar não é usar para decidir.
7. **Reprodução:** mesma seed + mesmo dataset → mesma divisão e mesma
   `Assinatura da divisao`. A garantia vale na mesma versão do Python; se a
   assinatura divergir entre máquinas, a divisão divergiu.

Uso previsto na Etapa 1:

```text
treino + validação  →  escolher o limiar (teto de FAR, ADR-004)  →  congelar
abrir_teste(limiar)  →  medir FAR/FRR UMA vez  →  reportar
```

A extração de embeddings roda sobre o dataset inteiro, antes da divisão:
ela não tem parâmetro ajustável, então não é fonte de vazamento. O vazamento
estaria em **decidir** olhando o teste — e é isso que o lacre impede.

---

## 7. Dados biométricos: fontes, armazenamento, acesso, retenção e descarte

### Fontes

| Fonte | Permitida? | Condição |
|---|---|---|
| Alunos cadastrados (`storage/`, tabela `alunos`) | **Não** | Finalidade consentida é só presença (`docs/lgpd.md` §2) |
| Dataset público (ex.: LFW) | Sim | **Ler e registrar os termos de uso no site oficial antes de baixar.** São dados biométricos de pessoas reais, mesmo que públicos |
| Voluntários locais | Sim | Consentimento **escrito e específico para pesquisa**, separado do termo de presença (ver abaixo) |
| Coleta automática (webcam, scraping) | **Não** | Fora do escopo desta preparação |

O consentimento de voluntário deve dizer, no mínimo: finalidade (avaliação
do modelo para trabalho acadêmico); quais dados (imagens e vetores
derivados); onde ficam e quem acessa; até quando (data de descarte); que o
consentimento é revogável a qualquer momento, com exclusão imediata; e que
os resultados publicados são agregados, sem identificação. **O termo de
consentimento da aplicação não foi alterado** — ampliar a finalidade dele
exige decisão explícita dos responsáveis.

### Armazenamento e acesso

- Somente sob `avaliacao/`, no disco local de quem conduz o experimento.
- **Não** em pastas sincronizadas com nuvem pessoal (no Windows, `Documentos`
  costuma estar no OneDrive — confira antes de criar `avaliacao/`).
- Acesso restrito aos integrantes do grupo; nada de envio por mensageiro ou
  e-mail.
- Relatórios e slides só com **números agregados**. Nenhuma imagem de
  pessoa, nenhum nome de identidade de voluntário.
- O relatório do console lista arquivos rejeitados pelo nome: trate a saída
  como dado do experimento, não a cole em issue ou PR.

### Retenção e descarte

- Retenção: até a apresentação/defesa do trabalho. Registre a data prevista
  de descarte no momento da coleta.
- Descarte: apagar `avaliacao/` **inteiro** — datasets, `cache/` (os
  embeddings também são dado biométrico) e `resultados/` — e esvaziar a
  lixeira. Em SSD, apagar não garante remoção física; para dados de
  voluntários, prefira manter `avaliacao/` num volume criptografado
  (BitLocker, por exemplo).
- Revogação de um voluntário: apagar a pasta da identidade e o cache; dividir
  e medir de novo.

### Proteção no Git

| Camada | O que faz |
|---|---|
| `.gitignore` | Exclui `/avaliacao/`, imagens (`*.jpg`, `*.jpeg`, `*.png`, `*.bmp`, `*.webp`, `*.heic`, `*.tif[f]`), vídeos (`*.mp4`, `*.avi`, `*.mov`) e vetores/caches (`*.npy`, `*.npz`, `*.pkl`, `*.pickle`), além de `/fotos/` e `/storage/` |
| CI ("Nenhum dado sensível versionado") | Reprova o build se qualquer desses padrões estiver rastreado — inclusive via `git add -f` |

Conferir antes de qualquer commit:

```bash
git check-ignore -v avaliacao/datasets/<nome>/<identidade>/0001.jpg   # deve imprimir a regra
git status --short                                                      # nada de avaliacao/
```

A extensão em maiúsculas (`.JPG`) depende de `core.ignorecase`: no Windows é
ignorada; no Linux, não pelo `.gitignore` — mas o CI a reprova (`grep -i`).

---

## 8. Testes automatizados

```bash
pytest tests/unit/test_divisao_por_identidade.py tests/unit/test_evaluate_model.py tests/unit/test_metricas.py
pytest                                   # suíte completa (integração exige o PostgreSQL de teste)
```

Os testes usam identidades e "imagens" sintéticas (bytes em `tmp_path`),
dublês do adaptador e do OpenCV: nenhum dado biométrico, nenhum download de
pesos, nenhuma câmera.
