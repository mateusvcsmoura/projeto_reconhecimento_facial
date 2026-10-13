# 001 — Desenho técnico: qualidade de captura

Data: 2026-10-13. Estado: desenho aprovado internamente para execução; implementação pendente.

## Objetivo e fronteiras

Recusar capturas inadequadas por dimensão, iluminação ou nitidez, antes de gerar o embedding, e orientar uma nova captura no cadastro e no reconhecimento. Reutilizar a rejeição existente de múltiplos rostos. Evidência esperada: comportamento funcional com imagens artificiais e dublês, sem alegar aumento da precisão facial.

Esta entrega não inclui estimativa de pose/orientação, decisão temporal, margem entre candidatos, múltiplas referências, benchmark do matcher, novos datasets, treinamento, migrações, Neon ou API. Orientação da face requer uma decisão própria sobre landmarks e confiabilidade; não criar um substituto improvisado baseado no formato do retângulo.

Preservar `FACE_THRESHOLD=0.30`, modelo, detector, confirmação manual e antispoofing. Não ler imagens, embeddings ou cadastros reais. Não adicionar bibliotecas. Domínio e aplicação continuam sem imports de OpenCV/DeepFace.

## Evidências do código inspecionado

- `DeepFaceAdapter._detectar_rosto_unico` centraliza detecção, alinhamento, múltiplos rostos e antispoofing.
- `gerar_embedding` usa o recorte validado com `detector_backend="skip"`.
- `CadastrarAluno.executar` extrai a face e depois chama `gerar_embedding(face)`, provocando uma segunda detecção sobre o recorte. A nova preparação de cadastro deve obter imagem e embedding da mesma detecção.
- `ReconhecerAluno.identificar` converte ausência/múltiplos rostos em `None`; falhas do modelo propagam.
- `MenuCLI` compara a cada oito frames e permite Enter quando existe candidato. Uma recusa por qualidade deve limpar esse candidato imediatamente naquele ciclo.
- `JanelaDeVideo.mostrar` desenha texto no próprio frame. Como o cadastro devolve esse frame depois da exibição, o desenho precisa passar a ocorrer numa cópia.
- Os testes usam módulos falsos em `sys.modules`, sem carregar modelos ou webcam.

## Decisões

### 1. Política optativa para preservar o baseline

As regras serão implementadas e integradas, mas desativadas por padrão com `FACE_QUALITY_ENABLED=false`. A ativação é explícita por ambiente; não editar o `.env` real. A flag desativa somente as três novas heurísticas, jamais o antispoofing ou a exigência de face única.

Defaults de engenharia para a política quando ativada:

| Ambiente / campo em Settings | Default | Restrição |
|---|---:|---|
| `FACE_QUALITY_ENABLED` / `face_quality_enabled` | false | booleano |
| `FACE_QUALITY_MIN_FACE_PX` / `face_quality_min_face_px` | 80 | inteiro >= 3 |
| `FACE_QUALITY_MIN_BRIGHTNESS` / `face_quality_min_brightness` | 40.0 | finito, entre 0 e 255 |
| `FACE_QUALITY_MAX_BRIGHTNESS` / `face_quality_max_brightness` | 215.0 | finito, entre 0 e 255 e maior que o mínimo |
| `FACE_QUALITY_MIN_SHARPNESS` / `face_quality_min_sharpness` | 100.0 | finito e >= 0 |

Esses números não foram calibrados com rostos. Devem aparecer como heurísticas iniciais nos documentos e no exemplo de configuração. Não otimizar valores usando dados reais nesta tarefa. O modo desligado preserva a política de aceitação anterior, embora a preparação do cadastro passe a evitar a detecção duplicada.

### 2. Avaliação pura com NumPy

Criar `src/domain/services/qualidade_captura.py` com:

- `ParametrosQualidade`: dataclass congelada, campos `min_face_px: int = 80`, `min_brightness: float = 40.0`, `max_brightness: float = 215.0`, `min_sharpness: float = 100.0`. Validar as restrições também na construção direta.
- `MedidasQualidade`: dataclass congelada com `largura_face: int`, `altura_face: int`, `luminosidade: float`, `nitidez: float`.
- `avaliar_qualidade(recorte_bgr: np.ndarray, largura_face: int, altura_face: int, parametros: ParametrosQualidade) -> MedidasQualidade`. Retorna medidas quando aprovado; lança o erro de qualidade correspondente quando recusado; entradas inválidas lançam `ValueError`.

Entrada: recorte BGR `uint8`, H x W x 3, pelo menos 3 x 3, e largura/altura originais positivas. Não aceitar NaN, arrays vazios, canais/dtype inesperados nem dimensões booleanas. Não modificar arrays recebidos.

Algoritmo fixado:

1. Validar a entrada e os parâmetros.
2. Exigir `min(largura_face, altura_face) >= min_face_px`. Usar `facial_area.w/h` do detector, antes de qualquer redimensionamento; não usar resolução da câmera nem dimensões de imagem ampliada como substituto.
3. Converter recorte em cinza float64: `0.114*B + 0.587*G + 0.299*R`, escala 0–255.
4. Iluminação: média dos pixels; aceitar o intervalo fechado `[min_brightness, max_brightness]`.
5. Nitidez: Laplaciano discreto no interior, sem padding: soma dos vizinhos acima/abaixo/esquerda/direita menos quatro vezes o pixel central. Calcular `np.var` com `ddof=0`; aceitar valor >= `min_sharpness`. Não redimensionar o recorte.

Ordem determinística de recusa: tamanho, escuro, claro, nitidez. A média não caracteriza toda condição de contraluz; ruído pode elevar nitidez. Documentar essas limitações.

### 3. Erros e mensagens

Em `src/domain/errors.py`, criar `QualidadeCapturaInsuficiente(ErroDeDominio)` e subclasses sem argumentos obrigatórios: `RostoMuitoPequeno`, `IluminacaoInsuficiente`, `IluminacaoExcessiva`, `RostoSemNitidez`.

Mapear subclasses antes da base no mecanismo existente de mensagens. A base também deve ter orientação, respeitando os testes que enumeram erros. Mensagens sem acentos na janela OpenCV, seguindo a interface atual:

| Erro | Problema + ação |
|---|---|
| RostoMuitoPequeno | Rosto muito pequeno. Aproxime-se da camera e tente novamente. |
| IluminacaoInsuficiente | Rosto escuro. Melhore a iluminacao frontal e tente novamente. |
| IluminacaoExcessiva | Rosto muito claro. Reduza a luz direta e tente novamente. |
| RostoSemNitidez | Rosto sem nitidez. Fique parado, ajuste o foco e tente novamente. |
| QualidadeCapturaInsuficiente | Captura inadequada. Ajuste o enquadramento e tente novamente. |

Não gravar imagens/embeddings de recusas, nomes ou matrículas nos logs. Não recomendar desligar antispoofing; remover a orientação existente `Persistindo, use FACE_ANTI_SPOOFING=false.` da mensagem de fraude, mantendo a orientação de iluminação e nova tentativa.

### 4. Adaptador e preparação do cadastro

Acrescentar ao construtor de `DeepFaceAdapter` o argumento opcional `qualidade: ParametrosQualidade | None = None`. Em `main.montar_menu`, construir a política a partir de Settings somente quando habilitada.

Depois da face única e do antispoofing existentes, converter o recorte para BGR uint8 e aplicar a política, antes de `DeepFace.represent`. Métodos públicos devem compartilhar esse caminho privado; nenhuma chamada pública pode ignorar a qualidade quando ativada.

Com a política ligada, `facial_area.w/h` ausentes ou inválidos são resposta incompatível do provider: lançar `ModeloIndisponivel` com detalhe sanitizado, sem inferência. Não inventar tamanho nem tratar erro estrutural como rosto desconhecido. Com a política desligada, não exigir metadados novos dos consumidores antigos.

Em `src/domain/services/face_recognition.py`, adicionar dataclass congelada `FacePreparada` com `imagem: Any` e `embedding: FaceEmbedding`, e método `preparar_cadastro(self, imagem: Any) -> FacePreparada` ao Protocol.

Implementar `DeepFaceAdapter.preparar_cadastro`: uma extração com prova de vida, uma avaliação de qualidade quando ligada e uma representação do recorte. Reutilizar a rotina privada de representação em `gerar_embedding`, mantendo as assinaturas públicas antigas para os demais consumidores.

Alterar `CadastrarAluno.executar` para usar `preparar_cadastro(imagem)`. Manter consentimento e validação de identificação antes de processar a imagem, e salvar/persistir somente após preparação aprovada. Adaptar todos os fakes/implementadores locais do Protocol identificados por busca. Nenhuma migração de schema.

### 5. Fluxos da CLI

Cadastro: manter nome, matrícula e consentimento da tentativa; capturar; executar cadastro. Se ocorrer um dos novos erros de qualidade, exibir `para_operador`, permitir outra captura sem refazer os prompts de identificação/consentimento, e permitir ESC cancelar. Não salvar a tentativa recusada. Não mudar tratamento dos demais erros nesta tarefa.

Reconhecimento: deixar os novos erros propagarem de `ReconhecerAluno.identificar`; capturá-los especificamente no laço da CLI. Definir `reconhecido=None`, exibir orientação em amarelo e continuar câmera aberta. Enter no ciclo recusado não grava presença. O próximo ciclo válido volta ao comportamento existente. Não englobar falhas de modelo num `except` genérico nem implementar votação/TTL temporal.

Viewer: desenhar overlays numa cópia do array e enviar essa cópia a `imshow`; preservar pixels do frame original para análise e armazenamento. Adaptar os testes que usavam sentinelas sem `.copy()` para imagens artificiais.

## Aceite

1. Política ligada recusa cada condição ruim antes de representar/persistir; política desligada mantém as decisões anteriores.
2. Face única, prova de vida, limiar 0.30 e confirmação manual preservados.
3. Cadastro usa uma detecção/uma representação por tentativa aprovada e permite recaptura.
4. Recusa no reconhecimento remove o candidato anterior e não encerra a câmera.
5. Pixels da captura não recebem overlays.
6. Testes determinísticos sem rostos, modelos, rede, webcam ou banco real; lint/tipos aprovados.
7. Documentação explica ativação, defaults e ausência de calibração biométrica.
8. Relatório registra resultados realmente executados; commit e push da tarefa na main concluídos ou impedimento concreto declarado.
