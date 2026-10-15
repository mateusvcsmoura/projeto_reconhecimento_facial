# Arquitetura

Projeto acadêmico da disciplina de Inteligência Artificial da Fatec:
reconhecimento facial para controle de presença de alunos.

| | |
|---|---|
| **Estado** | Fases 1–9 da refatoração registradas como executadas; tarefas 001–007 implementadas no workspace; inspeção visual manual das tarefas 006–007 pendente |
| **Entrada** | `python -m src.main` |
| **Código** | ~2.400 linhas e 30 módulos no snapshot pré-006; novos módulos da tarefa 006 estão no diff local |
| **Testes** | Tarefa 007: 911 testes unitários, Ruff, mypy e formato aprovados; `pip check` dos ambientes app/worker registrado na [tarefa 006](tasks/006-facial-landmarks/RESULTADO.md); ver [resultado 007](tasks/007-captura-automatica/RESULTADO.md) |
| **Ponto de partida** | [`docs/baseline-arquitetura.md`](docs/baseline-arquitetura.md) — o protótipo de 364 linhas num arquivo só |

Decisões e trade-offs em [`docs/adr/`](docs/adr/). Plano e histórico da
refatoração em [`REFACTORING_PLAN.md`](REFACTORING_PLAN.md). O snapshot com
fontes, verificações e limitações das tarefas 001–007 está em
[`docs/ESTADO-ATUAL-E-EVIDENCIAS.md`](docs/ESTADO-ATUAL-E-EVIDENCIAS.md).

---

## 1. Visão geral

O sistema cadastra alunos a partir do rosto e registra presença
reconhecendo-os pela webcam. É uma aplicação CLI local, monousuário, com
PostgreSQL como banco oficial.

O que ele faz, em uma frase por operação:

| Operação | O que acontece |
|---|---|
| **Cadastrar** | Colhe consentimento; por padrão, valida uma sequência e persiste a preparação de um novo frame final |
| **Reconhecer** | Por padrão, exige sequência da mesma identidade e reidentifica um frame novo antes da presença |
| **Registrar presença** | `INSERT ... ON CONFLICT DO NOTHING` — a regra "uma por dia" é do banco |
| **Listar / consultar** | Alunos com situação de embedding; presenças do dia com horário de chegada |
| **Excluir** | Remove linha, embedding, imagem e presenças (cascade) |

---

## 2. Camadas

Quatro camadas, dependências apontando sempre para dentro.

```mermaid
graph TD
    P["<b>Presentation</b><br/>menu · prompts · viewer · overlays"]
    A["<b>Application</b><br/>casos de uso"]
    D["<b>Domain</b><br/>entidades · contratos · matcher · erros"]
    I["<b>Infrastructure</b><br/>PostgreSQL · OpenCV · DeepFace · worker MediaPipe local opcional"]
    M["<b>src/main.py</b><br/>composition root"]

    P --> A
    A --> D
    I -.implementa os contratos.-> D
    M -.injeta.-> P
    M -.injeta.-> I
```

`src/main.py` é o **único** módulo que conhece implementações concretas.
Todo o resto conversa por `Protocol`s — e os testes unitários rodam sem
webcam, sem OpenCV e sem TensorFlow instalados. A suíte completa inclui
testes de integração/BDD dependentes do PostgreSQL; os totais por execução,
datas e escopos estão no registro atual de evidências.

### Invariantes, verificáveis por comando

```bash
# o domínio e a aplicação não conhecem bibliotecas de infraestrutura
grep -rn "import cv2\|from deepface\|sqlalchemy" src/domain/ src/application/   # vazio

# DeepFace vive num arquivo só
grep -rln "from deepface" src/                           # 1 arquivo

# a aplicação não usa SQLite nem cria schema
grep -rn "sqlite3\|CREATE TABLE" src/                    # vazio

# print() é para falar com o operador, não para diagnosticar
grep -rn "^\s*print(" src/ | grep -v presentation | grep -v main.py   # vazio
```

---

## 3. Estrutura

```text
src/
├── main.py                      composition root e entrada
│
├── config/
│   ├── settings.py              pydantic-settings; falha no boot sem DATABASE_URL
│   └── logging.py               logging estruturado, sem PII
│
├── domain/                      núcleo puro — regras e contratos
│   ├── entities/
│   │   ├── aluno.py             dataclass
│   │   └── face_embedding.py    vetor L2-normalizado + modelo + dimensão
│   ├── repositories/            contratos de persistência
│   ├── services/
│   │   ├── matcher.py           escolha do melhor candidato (regra pura)
│   │   ├── consistencia_temporal.py IDs/timestamps para confirmação vigente
│   │   ├── captura_automatica.py regra temporal pura, sem IO nem imagens
│   │   ├── face_recognition.py  contrato do reconhecimento
│   │   ├── facial_landmarks.py  DTOs numéricos e contrato visual opcional
│   │   ├── camera_provider.py   contrato da fonte de imagem
│   │   └── image_storage.py     contrato do armazenamento
│   └── errors.py                erros nomeados do domínio
│
├── application/use_cases/
│   ├── cadastrar_aluno.py       consentimento → rosto → embedding → persistência
│   ├── reconhecer_aluno.py      1 inferência + comparação vetorizada
│   ├── registrar_presenca.py    delega a unicidade ao banco
│   ├── excluir_aluno.py         direito à eliminação
│   ├── expurgar_presencas.py    política de retenção
│   └── consultar.py             listagens para o operador
│
├── presentation/cli/
│   ├── menu.py                  laço do menu e laços de vídeo
│   ├── captura_automatica.py    orquestra cadastro e presença automáticos
│   ├── prompts.py               entrada do operador (leitor injetável)
│   ├── viewer.py                janela OpenCV
│   ├── landmarks_overlay.py    desenho transitório sobre cópia da prévia
│   ├── confianca.py             distância → porcentagem legível
│   ├── mensagens.py             erro de domínio → orientação acionável
│   └── teclas.py                constantes, sem cv2
│
└── infrastructure/
    ├── database/                engine, sessão transacional, modelos ORM
    ├── repositories/            PostgreSQL — todo o SQL do sistema
    ├── camera/opencv_camera.py  captura (cv2)
    ├── storage/                 imagens em disco (cv2)
    └── face_recognition/
        ├── deepface_adapter.py  único importador de deepface
        ├── mediapipe_landmarks.py provider visual carregado sob demanda
        ├── mediapipe_landmarks_protocol.py framing local por pipes binários
        └── mediapipe_landmarks_worker.py Tasks executadas em processo auxiliar
```

---

## 4. Fluxo de reconhecimento

O ganho central da refatoração está aqui: o embedding de referência é
calculado **uma vez, no cadastro**.

```mermaid
sequenceDiagram
    participant Op as Operador
    participant Menu as MenuCLI
    participant UC as ReconhecerAluno
    participant Cam as OpenCVCamera
    participant DF as DeepFaceAdapter
    participant Mat as matcher
    participant DB as PostgreSQL

    Op->>Menu: opção 2
    Menu->>UC: carregar_referencias()
    UC->>DB: SELECT embeddings do modelo em uso
    DB-->>UC: N vetores
    UC-->>Menu: matriz N×512

    loop a cada 8 frames
        Menu->>Cam: ler_frame()
        Cam-->>Menu: frame
        Menu->>UC: identificar(frame, referências)
        UC->>DF: gerar_embedding(frame)
        Note over DF: 1 deteccao + anti-spoofing<br/>qualidade opcional antes de 1 representacao Facenet512
        DF-->>UC: vetor normalizado
        UC->>Mat: melhor_candidato(vetor, limiar, política opcional)
        Note over Mat: um produto matriz-vetor<br/>menor distância vence; top-2 opcional
        Mat-->>UC: aluno + distância
        UC-->>Menu: Reconhecimento
    end

    Op->>Menu: ENTER
    Menu->>DB: INSERT ... ON CONFLICT DO NOTHING
```

Com `FACE_QUALITY_ENABLED=true`, as medidas de tamanho, iluminação e
nitidez são avaliadas depois da face única e do anti-spoofing, antes da
representação. No cadastro, `preparar_cadastro` usa o mesmo recorte para
gravar a imagem e gerar o embedding, evitando uma segunda detecção. Uma
recusa não persiste imagem ou embedding e permite outra captura sem repetir
identificação e consentimento. No reconhecimento, a recusa limpa o candidato
imediatamente; a câmera continua aberta e ENTER não registra presença nesse
ciclo.

Com `FACE_AMBIGUITY_ENABLED=true`, o matcher primeiro exige que `d1` satisfaça
`FACE_THRESHOLD`; somente então compara `d2 - d1`, em que `d2` é a menor
distância de outra identidade. A segunda distância conta mesmo acima do
limiar. A operação reutiliza o único vetor de distâncias já calculado e não
acrescenta inferência. Identidades empatadas são recusadas; gap positivo
menor que `FACE_AMBIGUITY_MIN_MARGIN` também é recusado, e igualdade positiva
com a margem é aceita. Referências duplicadas com o mesmo ID não concorrem
entre si. Com a política desligada, o resultado anterior permanece, inclusive
o desempate pela primeira linha.

Ambiguidade é distinta de desconhecido (nenhum candidato passa pelo limiar) e
de múltiplos rostos (a captura contém mais de uma face). A recusa limpa a
identificação atual e, no modo temporal, interrompe a sequência usando uma
observação ausente com timestamp. `FACE_AMBIGUITY_MIN_MARGIN` não tem valor
positivo calibrado: a flag ligada exige escolha explícita entre 0 e 2. Margem
zero recusa apenas empates exatos calculados; uma margem positiva pode aumentar
as recusas, e um gap grande não garante identidade correta.

Com `FACE_TEMPORAL_ENABLED=true`, `MenuCLI` injeta o instante de um relógio
monotônico imediatamente antes de cada leitura da câmera. O serviço puro
`ConfirmadorTemporal` recebe somente o ID reconhecido e esse timestamp; ele
mantém no máximo N timestamps (3 por padrão), interrompe a sequência para
outro ID ou ausência e aplica a janela de 5 s e a validade de 2 s. O menu
observa apenas os ciclos de inferência já existentes (um a cada oito
frames), consulta a validade em cada frame e ao receber ENTER, e mostra o
progresso como contagem sem exibir o nome enquanto a identidade está parcial.

ENTER elegível causa uma leitura e identificação adicionais, com a mesma
qualidade, anti-spoofing e limiar atuais. O registro usa somente a identificação
nova quando o ID permanece igual e a sequência segue confirmada. Após um
registro normal, inclusive duplicado, a sequência é consumida; ao sair, o
estado local da sessão é descartado. A flag desligada preserva o laço anterior.
Essa política adiciona uma inferência apenas no ENTER elegível.

Os três resultados usam frames correlacionados, então consistência temporal
não demonstra ganho de acurácia e pode repetir uma decisão errada. O marco
anterior à leitura inclui o tempo de espera da câmera, mas a leitura seguinte
não garante frescor físico do sensor: dispositivos podem bufferizar frames.
Não há rastreamento contínuo nem calibração biométrica desses limites.

### Captura automática padrão

`FACE_AUTO_CAPTURE_ENABLED=true` encaminha cadastro e reconhecimento para
`CapturaAutomaticaCLI`, mantendo o modo manual quando a flag é `false`. O
serviço puro `ConfirmadorCapturaAutomatica` armazena somente a chave atual,
timestamps e contagem; não recebe frames nem persiste resultados. A sequência
exige pelo menos três observações em timestamps distintos, intervalo válido e
tempo mínimo de 5 s. Por padrão, as análises são separadas por ao menos 0,5 s,
e uma observação vence quando fica mais velha que 2 s ou o gap excede esse
limite. As análises são agendadas pelo relógio monotônico desde o fim da
inferência anterior; a interface segue mostrando frames e verificando ESC.

No cadastro, `validar_captura` faz sondagem sem embedding nem persistência.
Quando a sequência está pronta, o menu lê um frame novo, prepara uma única
`FacePreparada`, exibe a confirmação e só persiste se a sequência e a captura
continuarem atuais. No reconhecimento, o ID precisa permanecer igual e um
frame novo precisa identificar a mesma pessoa. Se `FACE_TEMPORAL_ENABLED` também
estiver ativo, o `ConfirmadorTemporal` atual precisa estar confirmado para esse
mesmo ID. Uma sessão registra no máximo uma presença, inclusive quando ela já
existia naquele dia, e então fecha a câmera. SPACE e ENTER não antecipam ação;
ESC continua cancelando antes da persistência.

O marco do relógio ocorre antes da leitura da câmera, que não garante frescor
físico do sensor se houver buffer. O worker de landmarks continua sendo apenas
visual; o desenho usa uma cópia e não participa da decisão. O menu revalida o
prazo após exibir o frame, pois o overlay pode atrasar a apresentação. Tempo e
observações correlacionadas demonstram comportamento funcional, não melhoram
nem medem acurácia biométrica. Configuração e roteiro manual estão em
[`docs/CAPTURA-AUTOMATICA.md`](docs/CAPTURA-AUTOMATICA.md).

### Evidência histórica e benchmark atual

Os valores abaixo são **históricos**, produzidos pelo script anterior com
uma consulta e 2000 repetições. Eles mediam somente o matcher vetorizado e
incluíam uma estimativa separada de inferência que não era medição. Não são
resultados das execuções atuais.

| Alunos | Comparação histórica | Ciclos/s históricos |
|---:|---:|---:|
| 10 | 0,0051 ms | 197.566 |
| 50 | 0,0064 ms | 155.409 |
| 200 | 0,0142 ms | 70.628 |
| 1000 | 0,1378 ms | 7.259 |

O protótipo anterior foi descrito como fazendo até `2N` inferências por
ciclo; com 200 alunos, isso correspondia a até 400 inferências no desenho
antigo. Essa comparação pertence ao histórico arquitetural e não é medida
pelo benchmark novo.

O protocolo atual preserva `python -m scripts.benchmark_matcher` e usa
embeddings sintéticos 512D, seed por tamanho, limiar local 0.30 e cenários
artificiais de referência, ortogonalidade e empate. Antes da medição, compara
o matcher real com uma referência independente em laço Python e `NumPy dot`
por embedding. Mede latência de cada chamada, montagem da matriz e memória em
fases separadas. A referência não é o protótipo de `DeepFace.verify()` e não
mede inferência facial.

As execuções padrão repetidas e seus limites estão em
[`tasks/004-benchmark-matching/RESULTADO.md`](tasks/004-benchmark-matching/RESULTADO.md):
[execução 1](tasks/004-benchmark-matching/evidencias/execucao-1.json),
[execução 2](tasks/004-benchmark-matching/evidencias/execucao-2.json) e
[execução 3](tasks/004-benchmark-matching/evidencias/execucao-3.json). O JSON
registra estatísticas por chamada, montagem e picos observados por
`tracemalloc`. Esses picos não são RSS nem incluem necessariamente toda
alocação nativa; `nbytes` é apenas o payload dos vetores. Os tempos medem
matching isolado, não FPS, vazão da aplicação ou desempenho biométrico.
O benchmark não compara `pgvector` e não verifica afirmações históricas sobre
índices ANN.

---

## 5. Modelo de dados

```mermaid
erDiagram
    ALUNOS ||--o{ PRESENCAS : "ON DELETE CASCADE"

    ALUNOS {
        bigint id PK "GENERATED ALWAYS AS IDENTITY"
        text matricula UK "chave de negocio"
        text nome "CHECK nao vazio"
        text foto_arquivo "relativo a STORAGE_DIR"
        bytea embedding "float32 LE, L2-normalizado"
        text embedding_modelo "impede comparar modelos diferentes"
        smallint embedding_dim
        timestamptz consentimento_em "LGPD art. 11"
        timestamptz criado_em
        timestamptz atualizado_em
    }

    PRESENCAS {
        bigint id PK "GENERATED ALWAYS AS IDENTITY"
        bigint aluno_id FK
        timestamptz registrado_em "instante exato"
        date data_referencia "UNIQUE com aluno_id"
    }
```

### As regras que viraram constraint

| Regra | Como é garantida |
|---|---|
| Uma presença por aluno por dia | `UNIQUE (aluno_id, data_referencia)` |
| Matrícula não se repete | `UNIQUE (matricula)` |
| Presença sempre tem aluno | `FOREIGN KEY` — sempre ativa no PostgreSQL |
| Excluir aluno leva as presenças | `ON DELETE CASCADE` |
| Nome e matrícula não vazios | `CHECK (length(btrim(...)) > 0)` |
| Embedding sem modelo é inutilizável | `CHECK` de coerência dos três campos |

Nenhuma dessas regras depende de a aplicação lembrar de aplicá-las. O
protótipo fazia `SELECT`-depois-`INSERT` para a regra do dia — sujeito a
corrida e, sobre os dados legados, **cego**: o formato de data gravado fazia
`date()` retornar `NULL` em 39 de 39 linhas.

### Por que `data_referencia` é coluna, e não expressão

`(registrado_em AT TIME ZONE 'America/Sao_Paulo')::date` é `STABLE`, não
`IMMUTABLE`. O PostgreSQL recusa isso em coluna gerada e em índice. O "dia"
é decidido pela aplicação, em `APP_TIMEZONE`, e persistido.

---

## 6. Stack

| Componente | Versão | Papel |
|---|---|---|
| Python | 3.12 / 3.13 | Piso: numpy 2.5.3. Teto: TensorFlow |
| PostgreSQL | 18 | Banco oficial |
| SQLAlchemy | 2.0.52 | ORM, confinado a `infrastructure/` |
| Alembic | 1.19.2 | Migrations versionadas |
| psycopg | 3.3.5 | Driver |
| pydantic-settings | 2.15.0 | Configuração validada |
| numpy | 2.5.3 | Comparação vetorizada (dependência do domínio) |
| DeepFace | 0.0.92 | Detecção, embedding e anti-spoofing |
| TensorFlow + tf-keras | 2.21.0 | Backend do Facenet512 |
| PyTorch | 2.14.0 | Backend do anti-spoofing (MiniFASNet) |
| OpenCV | 4.13.0.92 | Câmera e janela |
| MediaPipe Tasks | 0.10.35 em `.venv-landmarks` | Worker visual optativo por pipes locais; `pip check` limpo e sem fornecedor cv2 concorrente por ambiente |

O DeepFace declara só `tensorflow>=1.9.0` e não declara `torch`. Ambos são
fixados aqui: sem isso, cada máquina resolvia uma combinação diferente — e
foi assim que o `tf-keras` faltante só apareceu na primeira execução real.

---

## 7. Configuração

Tudo por ambiente. `DATABASE_URL` não tem default: a aplicação **falha no
boot** se ela faltar, em vez de apontar silenciosamente para o banco errado.

| Variável | Padrão | Observação |
|---|---|---|
| `DATABASE_URL` | — | Obrigatória |
| `APP_TIMEZONE` | `America/Sao_Paulo` | Define o "dia" da presença |
| `LOG_LEVEL` | `INFO` | |
| `CAMERA_INDEX` | `0` | |
| `CAMERA_LARGURA` / `CAMERA_ALTURA` | `1280` / `720` | Recorte maior melhora embedding e anti-spoofing |
| `CAMERA_BACKEND` | `auto` | DirectShow no Windows — **27 s → 0,8 s** |
| `FACE_MODEL` | `Facenet512` | Trocar exige backfill |
| `FACE_DETECTOR` | `opencv` | |
| `FACE_THRESHOLD` | `0.30` | Ainda não calibrado — ver ADR-004 |
| `FACE_ANTI_SPOOFING` | `true` | |
| `FACE_AUTO_CAPTURE_ENABLED` | `true` | Busca automática; `false` recupera ESPAÇO/ENTER |
| `FACE_AUTO_CAPTURE_WAIT_SECONDS` | `5.0` | Duração mínima da sequência válida |
| `FACE_AUTO_CAPTURE_SAMPLE_SECONDS` | `0.5` | Intervalo mínimo entre análises após cada inferência |
| `FACE_AUTO_CAPTURE_MAX_AGE_SECONDS` | `2.0` | Idade e gap máximos; precisa exceder o intervalo de análise |
| `FACE_LANDMARKS_ENABLED` | `false` | Overlay apenas em Cadastro facial; opt-in |
| `FACE_LANDMARKS_MODEL_PATH` | `models/face_landmarker.task` | Bundle local, resolvido a partir da raiz |
| `FACE_LANDMARKS_PYTHON_PATH` | `.venv-landmarks/Scripts/python.exe` | Worker MediaPipe isolado do ambiente principal |
| `FACE_QUALITY_ENABLED` | `false` | Opt-in; mantém a política de aceitação anterior por padrão |
| `FACE_QUALITY_MIN_FACE_PX` | `80` | Menor dimensão da face informada pelo detector |
| `FACE_QUALITY_MIN_BRIGHTNESS` / `FACE_QUALITY_MAX_BRIGHTNESS` | `40` / `215` | Faixa fechada da média de luminância, escala 0–255 |
| `FACE_QUALITY_MIN_SHARPNESS` | `100` | Variância mínima do Laplaciano discreto |
| `FACE_TEMPORAL_ENABLED` | `false` | Opt-in da consistência temporal |
| `FACE_TEMPORAL_MIN_OBSERVATIONS` | `3` | Observações analisadas consecutivas |
| `FACE_TEMPORAL_WINDOW_SECONDS` | `5.0` | Janela máxima de observações |
| `FACE_TEMPORAL_MAX_AGE_SECONDS` | `2.0` | Idade máxima da observação mais recente |
| `FACE_AMBIGUITY_ENABLED` | `false` | Opt-in da recusa entre identidades próximas |
| `FACE_AMBIGUITY_MIN_MARGIN` | `None` | Obrigatória quando habilitada; valor finito entre 0 e 2 |
| `STORAGE_DIR` | `./storage/faces` | Fora do Git |
| `RETENCAO_PRESENCAS_DIAS` | `1825` | 5 anos; `0` desliga |

Os limites de qualidade são heurísticas iniciais sem calibração biométrica.
A média de luminância não caracteriza toda contraluz, e ruído pode elevar a
medida de nitidez. A validação usa somente imagens sintéticas e demonstra
comportamento do software, sem medir acurácia em reconhecimento facial.
Os limites temporais são de engenharia, não calibrados. Qualidade,
temporalidade e ambiguidade são controles independentes; nenhum altera o
limiar 0.30 ou o anti-spoofing. Testes funcionais com embeddings sintéticos
não calibram margem, não medem acurácia facial e não comprovam redução de FAR
ou FPIR.

Os limites da captura automática também são valores de engenharia, não
calibrados com pessoas nem avaliados como política biométrica. O modo
automático não altera `FACE_THRESHOLD=0.30`, anti-spoofing, embeddings ou
regras de identidade. Frames correlacionados, cronômetro e um frame novo de
confirmação não comprovam identidade nem frescor físico da câmera.

---

## 8. Tratamento de erros

Cada falha tem nome próprio e mensagem que **diz o que fazer**.

```mermaid
graph LR
    L["Biblioteca<br/>DeepFace, cv2, SQLAlchemy"]
    T["Adaptador<br/>traduz"]
    E["Erro de dominio"]
    M["Orientacao<br/>ao operador"]

    L -->|excecao crua| T
    T -->|nomeia e registra| E
    E -->|problema + acao| M
```

| Erro | Mensagem |
|---|---|
| `NenhumRostoDetectado` | Aproxime-se, olhe para a lente, verifique a iluminação |
| `MultiplosRostosDetectados` | Peça que as outras pessoas saiam do enquadramento |
| `IdentificacaoAmbigua` | Olhe de frente para a câmera, ajuste a posição e tente novamente |
| `RostoMuitoPequeno` | Aproxime-se da câmera e tente novamente |
| `IluminacaoInsuficiente` | Melhore a iluminação frontal e tente novamente |
| `IluminacaoExcessiva` | Reduza a luz direta e tente novamente |
| `RostoSemNitidez` | Fique parado, ajuste o foco e tente novamente |
| `QualidadeCapturaInsuficiente` | Ajuste o enquadramento e tente novamente |
| `PossivelFraude` | Se está ao vivo, o modelo errou: melhore a iluminação e a resolução |
| `ModeloIndisponivel` | Verifique a instalação — **mais a causa original anexada** |
| `CameraIndisponivel` | Feche outros programas e ajuste `CAMERA_INDEX` |
| `AlunoJaCadastrado` / `AlunoNaoEncontrado` | Confira na listagem |

O protótipo transformava tudo isso em `except Exception: continue` e exibia
"Rosto nao reconhecido" — indistinguível de TensorFlow quebrado. Um teste
varre as subclasses de `ErroDeDominio` e falha se alguém adicionar um erro
sem mensagem.

---

## 9. Segurança e dados pessoais

Política completa em [`docs/lgpd.md`](docs/lgpd.md).

| Controle | Estado |
|---|---|
| Consentimento antes da câmera | Implementado; `consentiu` sem default no caso de uso |
| Exclusão completa | Linha + embedding + imagem + presenças |
| Retenção configurável | Script de expurgo, dry-run por padrão |
| Menor privilégio no banco | `escola_app` só DML; DDL exclusivo das migrations |
| Logs sem PII | Aluno por id interno; coberto por teste |
| Anti-spoofing | Implementado; **eficácia pendente de validação** |
| Criptografia em repouso | Não implementada — limite declarado |
| Autenticação de operador | Não implementada — sistema local monousuário |

---

## 10. Testes

```text
tests/
├── unit/          domínio, casos de uso, CLI, adaptadores — com dublês
├── integration/   PostgreSQL real: schema, constraints, repositories, ETL
└── features/      24 cenários BDD em Gherkin (pytest-bdd)
```

A suíte roda **sem OpenCV e sem TensorFlow**. Os módulos que dependem deles
são testados injetando dublês em `sys.modules` — o que cobre a lógica que é
nossa (liberar a câmera no `finally`, sanitizar nomes de arquivo, traduzir
erros) sem exigir hardware.

`requirements-dev.txt` não inclui essas bibliotecas de propósito: se um
teste passar a exigi-las, o CI quebra, e essa quebra é o aviso de que uma
fronteira vazou.

### CI

`.github/workflows/ci.yml`: lint → tipos → migrations sobem e descem →
`alembic check` → testes com piso de 80% de cobertura → verificação de que
nenhum arquivo sensível foi versionado.

---

## 11. O que não foi feito, e por quê

Declarado por honestidade. Nada aqui é omissão silenciosa.

| Item | Situação |
|---|---|
| **Calibração do `FACE_THRESHOLD`** | Calibração 1:1 medida no LFW (Etapa 1): candidato 0,4282 para FAR ≤ 0,1%. **Não adotado**: falta a avaliação 1:N e a validação na webcam da sala. O valor em uso continua 0,30. Ver [ADR-004](docs/adr/ADR-004-limiar-de-reconhecimento.md) e [`docs/ML-ETAPA-1-RESULTADO.md`](docs/ML-ETAPA-1-RESULTADO.md) |
| **Eficácia do anti-spoofing** | Recusou pessoa ao vivo em contraluz com 86–96% de confiança. Falta testar em iluminação frontal e contra foto impressa |
| **Comparação com `DeepFace.verify()`** | A equivalência de decisão sobre imagens reais não foi medida |
| **API HTTP** | Não há consumidor. As camadas permitem adicionar sem tocar nos casos de uso |
| **`pgvector`** | Desnecessário nesta escala — ver [ADR-002](docs/adr/ADR-002-armazenamento-de-embeddings.md) |
| **Threading da inferência** | No protótipo, o travamento era atribuído às até `2N` inferências, não à falta de paralelismo |
| **Criptografia, autenticação, auditoria** | Fora do escopo de um sistema local monousuário — ver `docs/lgpd.md` |

---

## 12. Decisões arquiteturais

| ADR | Assunto |
|---|---|
| [ADR-001](docs/adr/ADR-001-migracao-postgresql.md) | SQLite → PostgreSQL; SQLAlchemy + Alembic; redesenho do schema |
| [ADR-002](docs/adr/ADR-002-armazenamento-de-embeddings.md) | `BYTEA` + NumPy; por que **não** `pgvector` |
| [ADR-003](docs/adr/ADR-003-limpeza-do-historico.md) | Remoção do banco legado do histórico do Git |
| [ADR-004](docs/adr/ADR-004-limiar-de-reconhecimento.md) | Limiar por teto de FAR, e por que não EER |
