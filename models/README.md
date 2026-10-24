# Modelo local Face Landmarker

O runtime opcional espera `face_landmarker.task` nesta pasta. O arquivo do
modelo é ignorado pelo Git (`/models/*.task`) e deve ser obtido somente durante
setup local explícito. A aplicação não faz download automático; o setup é
`python -m scripts.baixar_modelos`, que baixa da origem abaixo e confere o
SHA-256.

- Modelo: Face Landmarker, bundle `float16`, versão `1`.
- Origem oficial versionada:
  <https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task>
- Tamanho do arquivo presente nesta máquina: 3.758.596 bytes.
- SHA-256 calculado localmente: `64184E229B263107BC2B804C6625DB1341FF2BB731874B0BCC2FE6544E0BC9FF`.

O hash identifica o arquivo local; não foi publicado pelo fornecedor como
checksum autenticado. Para repor o modelo, baixe somente da origem oficial
acima e compare o hash com este registro. Não copie o `.task` para commits.

Consulte a [página do Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker?hl=en)
e os [model cards oficiais](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker#models)
para finalidade, componentes e termos, incluindo o [card Face Mesh V2](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf).
Os cards consultados declaram Apache
License 2.0 para os modelos componentes. O Face Mesh V2 é descrito como
estimador de landmarks para efeitos visuais; o card não o destina a
reconhecimento ou identificação facial. Esta integração usa apenas os pontos
para uma prévia transitória, sem inferir identidade, emoção, idade, gênero,
orientação em graus ou prova de vida.
