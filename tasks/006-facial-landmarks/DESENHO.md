# Desenho — 006: landmarks faciais no cadastro

**Executor: Luna 6 High. Estado: correção técnica concluída no workspace; validação visual manual pendente.** A implementação e suas evidências estão em [RESULTADO.md](RESULTADO.md). A integração de dependências precisou trocar a execução in-process por worker local isolado, documentado em [PLANO-CORRECAO.md](PLANO-CORRECAO.md); os contratos visuais e biométricos deste desenho permanecem vigentes. Base inspecionada: main, `f116a95`, tarefa 005 concluída. A imagem fornecida foi usada como referência da interface; não foi copiada para o repositório nem processada como dado biométrico.

## Objetivo e decisão

Adicionar pontos e contornos faciais acompanhando o rosto na janela **Cadastro facial** mostrada pelo usuário. A primeira entrega cobre a prévia do cadastro. A visualização não decide identidade, qualidade, prova de vida ou autorização para registrar presença. As janelas de reconhecimento mantêm o caminho atual, evitando acrescentar inferência ao controle temporal nesta tarefa.

Escolha original: **MediaPipe Tasks Face Landmarker 0.10.31**, CPU, modelo local `face_landmarker.task`, integrado como recurso visual optativo. A wheel Windows dessa versão tinha uma tag interna Linux inválida; a correção executa a Tasks API com **MediaPipe 0.10.35 em worker local isolado**. O modelo estima 478 landmarks; desenhar os pontos e conexões dos contornos principais, sem malha triangular densa. Desativar blendshapes e matrizes de transformação; não inferir emoções, idade, gênero, orientação em graus ou prova de vida.

Alternativas consideradas: landmarks esparsos do detector existente não oferecem a visualização densa pretendida; dlib exigiria outra cadeia de dependências/modelo; versões recentes do MediaPipe corrigem a tag Windows, mas declaram `opencv-contrib-python`, incompatível com uma instalação conjunta com DeepFace e `opencv-python`. O isolamento em processo mantém um único fornecedor de `cv2` em cada ambiente; a compatibilidade está registrada em [DEPENDENCIAS.md](DEPENDENCIAS.md).

## Modelo de integração

O ponto de entrada existente é `MenuCLI._capturar_rosto()` em `src/presentation/cli/menu.py`: lê o frame, chama `janela.mostrar(frame, instrucoes)` e retorna o frame quando ESPAÇO é pressionado. `JanelaDeVideo.mostrar()` já desenha em `frame.copy()`. Preservar esse contrato e a assinatura pública de `mostrar`.

| Componente | Responsabilidade proposta |
|---|---|
| `src/domain/services/facial_landmarks.py` (novo) | DTOs imutáveis e Protocol do provider, sem importar MediaPipe/OpenCV |
| `src/infrastructure/face_recognition/mediapipe_landmarks.py` (novo) | Conversão BGR/RGB, resize proporcional, Tasks API, resultado normalizado, liberação do detector |
| `src/presentation/cli/landmarks_overlay.py` (novo) | Transformar coordenadas normalizadas em pixels e desenhar pontos/contornos com OpenCV sobre a cópia de exibição |
| `src/presentation/cli/viewer.py` | Provider opcional por factory, uma instância por janela; desenhar landmarks antes dos textos e manter teclas |
| `src/main.py` | Injetar factory apenas para o título existente `Cadastro facial`, quando habilitado; demais janelas sem provider |
| `src/config/settings.py` e `.env.example` | Duas configurações descritas abaixo |

Contratos fechados: `PontoFacial(x: float, y: float, z: float)`; `ResultadoLandmarks(rostos: tuple[tuple[PontoFacial, ...], ...], conexoes: tuple[tuple[int, int], ...])`; Protocol `LandmarksProvider.detectar(frame: Any, timestamp_ms: int) -> ResultadoLandmarks` e `fechar() -> None`. DTOs só contêm números, nunca objetos MediaPipe ou imagens. As conexões vêm das constantes de contornos da Tasks API instalada; confirmar os nomes na versão fixada, sem usar `mp.solutions` legado ou copiar listas enormes sem fonte.

Adicionar argumento opcional keyword-only `criar_landmarks` ao construtor do viewer, default `None`, mantendo largura/altura existentes. Factory só é chamada no início da janela de cadastro. `main` fornece a implementação concreta; o viewer não importa o adaptador. Import do MediaPipe ocorre somente ao criar o provider habilitado. Testes e inicialização com flag false funcionam sem MediaPipe/modelo.

## Ciclo de um frame

1. Câmera entrega o BGR original. Viewer obtém timestamp monotônico em milissegundos; usar `max(ultimo + 1, monotonic_ns() // 1_000_000)` para garantir crescimento estrito, inclusive no mesmo milissegundo. Relógio injetável para testes.
2. Provider recebe o original somente para leitura, reduz proporcionalmente até largura máxima 640 sem ampliar e produz array RGB contíguo próprio. Não espelhar, recortar ou esticar a imagem.
3. Executar `detect_for_video` em modo VIDEO síncrono, CPU, `num_faces=2`, confidências internas `0.5`, blendshapes/matrizes false. Duas faces permitem aviso visual; isso não substitui a validação de múltiplas faces do cadastro. Não há smoothing nativo de uma face com esse limite; documentar essa escolha.
4. Resultado vale somente para esse frame. Não guardar/desenhar resultado anterior quando não detectar rosto ou ocorrer erro. Sem callbacks, threads ou fila de imagens nesta entrega.
5. Viewer cria cópia do frame original, desenha overlay nela e desenha instruções por último. Converter x/y usando dimensões reais do frame de exibição, não o tamanho solicitado à webcam nem a janela redimensionada. Rejeitar coordenadas não finitas; pular pontos fora de [0,1] e conexões com pontas inválidas. `x=1`/`y=1` mapeiam ao último pixel, nunca fora do array.
6. ESPAÇO retorna exatamente o frame original do menu. Armazenamento, qualidade, antispoofing e embedding recebem pixels sem overlay. ESC e falha da câmera preservam comportamento e liberam recursos.

O modo síncrono simplifica a correspondência entre frame e pontos, mas acrescenta latência ao cadastro. Uma inferência por frame exibido; criar modelo uma vez por janela, nunca uma vez por frame. Não prometer FPS, não alterar resolução da câmera e não introduzir otimização assíncrona sem medição.

## Aparência e estados

- Pontos pequenos, raio 1, ciano BGR `(255,255,0)`; contornos finos, espessura 1, para olhos, sobrancelhas, lábios e oval facial. Usar conexões fornecidas pela API, mantendo pontos discretos no restante do rosto.
- Preservar `ESPACO = capturar | ESC = cancelar` no topo, desenhado por último. Acrescentar linha curta de estado abaixo.
- Um rosto: `Pontos faciais ativos` em ciano. Não mostrar “identificado”, porcentagem ou “qualidade aprovada”.
- Zero rostos: não desenhar pontos; `Posicione o rosto na camera` em amarelo.
- Dois rostos: não desenhar malha; `Mantenha apenas uma pessoa na camera` em amarelo. O limite de duas detecções não conta todas as pessoas da cena.
- Falha de inicialização/inferência: `Pontos faciais indisponiveis` em amarelo; registrar aviso técnico uma vez por sessão, desabilitar overlay até fechar a janela e continuar cadastro normal. Não repetir tentativas caras a cada frame.

Tratar falhas conhecidas da integração (import, arquivo ausente/corrompido, erro nativo reportado como Exception) na fronteira do recurso opcional. Não capturar `BaseException`, não esconder erros de câmera/teclado e não tratar uma falha nativa fatal do processo como recuperável.

## Configuração e recursos

`FACE_LANDMARKS_ENABLED=false` e `FACE_LANDMARKS_MODEL_PATH=<raiz>/models/face_landmarker.task`. Resolver caminho relativo contra PROJECT_ROOT, e não cwd. Desligado: sem verificar existência do modelo, importar MediaPipe ou fazer download. Ligado com modelo ausente: fallback visível acima, sem impedir as funções atuais.

Um provider por sessão; fechar ao sair normalmente, ESC, captura, falha da câmera ou exceção. Se `__enter__` falhar após alocar algum recurso, liberar o que foi criado. Em `__exit__`, usar finally para também fechar janela se `fechar()` falhar. `fechar()` idempotente. Não persistir coordenadas, capturas ou resultados, nem colocá-los em logs.

Instalação e download são etapas futuras do executor, documentadas em DEPENDENCIAS.md; nenhum pacote/modelo foi instalado/baixado nesta preparação. Não usar a imagem enviada como fixture. Não baixar datasets ou abrir webcam/banco para validar automaticamente.

## Aceite

- Feature optativa funcional no cadastro, sem contaminar os pixels de captura e sem alterar contratos de reconhecimento.
- Flag false não importa nem instancia MediaPipe; ausência/falha do recurso tem fallback legível.
- Testes sintéticos cobrem geometria, estados, timestamps, pixels originais, fechamento e regressões.
- Dependências resolvidas sem trocar NumPy/TensorFlow/OpenCV e sem duplicar provedores de `cv2`; smoke real do modelo sobre array sintético, sem webcam.
- Validação visual com pessoa fica como roteiro manual para o usuário; marcar honestamente se não executada. Smoke sintético não comprova qualidade dos landmarks em rostos.
- Documentação, resultado e publicação conforme prompt. Não mudar limiar 0.30, antispoofing, banco, embeddings existentes ou políticas 001–003.

Fontes do modelo/API e decisões de dependências estão em [DEPENDENCIAS.md](DEPENDENCIAS.md).
