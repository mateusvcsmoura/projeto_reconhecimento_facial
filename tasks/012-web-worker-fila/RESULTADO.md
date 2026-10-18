# Resultado — task012: Worker facial único, fila limitada e temporários

**Estado: concluída no workspace em 18/10/2026.** A implementação está
validada localmente; não houve deploy nem ativação com participantes. O branch
inicial era `main`, no commit `02e38a1f121dfd174598d774b7d535782e306a03`, sem
alterações rastreadas preexistentes. Os diretórios pytest temporários criados
para esta tarefa foram removidos; diretórios preexistentes sem permissão de
leitura foram preservados.

## Causa e solução

A task012 precisava fornecer execução serial e recuperável para o futuro fluxo
web sem carregar modelos na API, sem introduzir Redis/Celery e sem colocar
capturas ou embeddings em logs. A solução reutiliza PostgreSQL e os contratos da
task011: migration `0007`, admissão transacional com advisory lock, idempotência,
limite de dez jobs aguardando/reservados e um ativo adicional, lease por job,
credencial opaca para consulta de status e mídia temporária privada.

O worker é um processo separado, com lock local e advisory session lock no
PostgreSQL. Ele não libera o slot até o executor retornar; lease vencido, prazo
excedido e resultado tardio não concluem o job. Após reinício, o próximo worker,
depois de adquirir os dois locks, marca os jobs interrompidos como falha e não
os reproduz. A recuperação ocorre antes do aquecimento ML para que uma falha de
peso/modelo não deixe jobs interrompidos sem estado terminal.

Cadastro exige três capturas; presença aceita até três. O limite inicial de
laboratório é 8 MiB por captura e quota temporária total de 300 MiB. Em produção,
o worker exige tmpfs Linux e espaço livre para a quota completa. Não foram
adicionadas dependências Python.

## Arquivos

- Fila/aplicação: `src/application/services/fila_facial.py` e
  `src/application/services/worker_facial.py`.
- Persistência: `src/infrastructure/database/models.py`,
  `src/infrastructure/repositories/postgres_job_repository.py` e
  `migrations/versions/0007_worker_fila_facial.py`.
- Worker e mídia transitória: `src/face_worker_main.py`,
  `src/infrastructure/workers/singleton_process_lock.py` e
  `src/infrastructure/storage/temporary_capture_storage.py`.
- API/configuração/provider: `src/presentation/web/routes/operations.py`,
  `src/presentation/web/app.py`, `src/presentation/web/schemas.py`,
  `src/web_main.py`, `src/config/web_settings.py` e
  `src/infrastructure/face_recognition/deepface_adapter.py`.
- Testes: novos testes unitários de fila, worker, storage e status HTTP, regressões
  do `DeepFaceAdapter` e `tests/integration/test_fila_facial_postgresql.py`.
- Documentação atualizada: `AGENTS.md`, documentos de runtime/arquitetura/
  planejamento web, contrato de execução, contrato de migrations, índice,
  desenho e plano da task012.

`requirements.txt`, `requirements-web.txt` e `requirements-dev.txt` não mudaram.

## Verificações executadas

Ambiente Windows AMD64. `.venv-app`: Python 3.12.0rc2, pip 26.2.1, DeepFace
0.0.92, TensorFlow/tf-keras 2.21.0, PyTorch 2.14.0, NumPy 2.5.3, OpenCV
4.13.0.92, SQLAlchemy 2.0.52 e psycopg 3.3.5. `.venv-ml`: Python 3.14.3 e pip
25.3; usado para a suíte unitária/coverage. `.venv-app` é um Python pré-release;
estes resultados não substituem validação em Python 3.12 estável/Linux, ainda
pendente da task019. Não alterei os interpretadores.

| Verificação | Resultado observado |
|---|---|
| Suíte completa com coverage em `.venv-ml` | `1066 passed, 71 skipped`; cobertura total 82,23%, acima do mínimo 80%; 13,50 s |
| Integração PostgreSQL task012 em `.venv-app` | `4 passed` no banco local descartável identificado abaixo |
| Ruff nos 22 arquivos Python afetados | `All checks passed`; 22 arquivos já formatados |
| Mypy | `Success: no issues found in 114 source files` |
| `pip check` em `.venv-app` | `No broken requirements found` |
| `pip check` em `.venv-ml` | `No broken requirements found` |
| Smoke do provider com pesos locais | FaceNet512 e MiniFASNet aquecidos; imagem sintética preta recusada como sem rosto; sem baixar pesos |

Verificações estáticas e de dependências:

```powershell
.venv-ml\Scripts\ruff.exe check <22-arquivos-python-afetados>
.venv-ml\Scripts\ruff.exe format --check <22-arquivos-python-afetados>
.venv-ml\Scripts\python.exe -m mypy src scripts
.venv-app\Scripts\python.exe -m pip check
.venv-ml\Scripts\python.exe -m pip check
```

Comando da suíte completa:

```powershell
.venv-ml\Scripts\python.exe -m pytest --cov=src --cov=scripts.metricas --cov=scripts.divisao_por_identidade --cov=scripts.evaluate_model --cov=scripts.calibrar_limiar --cov-report=term-missing --cov-fail-under=80 -p no:cacheprovider --basetemp <diretorio-temporario-exclusivo> --tb=short
```

Os testes PostgreSQL foram executados com
`.venv-app\Scripts\python.exe -m pytest tests/integration/test_fila_facial_postgresql.py -p no:cacheprovider --basetemp <diretorio-temporario-exclusivo> --tb=short -v`
contra
`localhost:5433/task012_web_worker_test_20261018`. A URL foi fornecida somente
no ambiente do processo de teste, sem imprimir credenciais. Antes de qualquer
DDL, a fixture confirmou o comentário
`projeto_reconhecimento_facial: task 012 disposable worker database` e endereço
de servidor local. O teste migrou `base` até `head`, executou `alembic check`,
validou concorrência, idempotência, lease, cancelamento, recuperação de restart
e lock único, então limpou jobs e reverteu a `base`. Uma consulta posterior
confirmou `version_num` vazio e ausência de `jobs_faciais_web`. A migration
`0007` **não** foi aplicada ao banco local `escola`.

Smoke CPU com o modelo local, executado em `.venv-app`:

```python
import numpy as np
from src.domain.errors import NenhumRostoDetectado
from src.infrastructure.face_recognition.deepface_adapter import DeepFaceAdapter

adapter = DeepFaceAdapter(
    modelo="Facenet512",
    detector="opencv",
    anti_spoofing=True,
    strict_resultado_antispoofing=True,
    sanitizar_erros=True,
)
adapter.preaquecer_para_web()
try:
    adapter.extrair_face_unica(np.zeros((224, 224, 3), dtype=np.uint8))
except NenhumRostoDetectado:
    print("Entrada sintética recusada como sem rosto.")
```

O resultado esperado para a imagem artificial foi `NenhumRostoDetectado`. Esse
smoke confirma carga dos pesos e recusa de uma entrada sem rosto; não é
validação visual, prova biométrica, avaliação de anti-spoofing com pessoas nem
medição de latência/capacidade.

## Contratos preservados e limites

- A API não importa nem aquece DeepFace; o modelo é carregado no worker. O
  caminho web exige `is_real` booleano quando anti-spoofing está ativo e
  converte exceções internas em mensagens sanitizadas. O modo padrão do adapter
  preserva o comportamento anterior da CLI.
- `GET /api/v1/operacoes/{id}` exige `Authorization: Bearer <credencial>`;
  credencial ausente/incorreta recebe 404 genérico e a resposta não é cacheada.
  Fila cheia retorna 503 e `Retry-After`.
- Payload acima do limite é rejeitado pelo storage antes de ser lido por um
  decoder. Os fluxos HTTP de reserva/upload/cancelamento, limites de requisições
  para submissão e handlers biométricos permanecem nas tasks 014/015. Até esses
  handlers existirem, o worker recusa com segurança jobs de tipo sem processador.
- Não há inferência operacional de cadastro/presença, resultado biométrico,
  persistência de embeddings ou gravação de presença nesta tarefa. Nenhuma
  imagem facial real foi usada.
- Os testes do worker usam fakes; o smoke dos modelos ocorreu em Windows. Não
  foi executado worker em Linux, tmpfs compartilhado, teste de carga, medição na
  VPS, deploy ou inspeção visual com pessoa real. A task019 continua responsável
  pela validação integrada/capacidade antes da interface.
- Não há supervisor/watchdog neste pacote para terminar automaticamente uma
  inferência nativa que fique bloqueada indefinidamente. O lease expirado impede
  aceitar resultado tardio e o job continua ocupando o slot; um reinício
  controlado invalida o job antes do próximo claim. Um watchdog operacional e
  sua política de reinício precisam ser validados na task019/018.
- O banco descartável foi preservado vazio e com marcador para testes futuros;
  `escola` permaneceu sem `0006` e `0007` nesta execução.

## Ativação e rollback

Para execução local, configure `WEB_*` com a mesma raiz privada em app/worker,
`WEB_CAPTURE_TEMP_DIR` e limites documentados em
[runtime web](../../docs/FACEDIFF-WEB-RUNTIME.md). Inicie a API com
`.venv-web/bin/uvicorn src.web_main:create_web_app --factory`, usando
`requirements-web.txt`; em processo separado, inicie o worker com
`.venv-worker/bin/python -m src.face_worker_main`, usando `requirements.txt`.
Em `production`, a raiz precisa ser
tmpfs Linux compartilhado, com quota suficiente, e os pesos devem estar
previamente presentes no cache local. O worker valida os pesos sem download
automático. Como não há handlers/rotas públicas nas tasks atuais, essa execução
apenas prepara o runtime e não habilita fluxo biométrico.

Para rollback de código, parar API e worker e reverter os commits da task012
individualmente. Se `0007` tiver sido aplicada deliberadamente em algum ambiente,
parar produtores/worker e verificar o destino antes de executar
`alembic downgrade 0006`; esse downgrade remove a tabela e os jobs. Nenhum
rollback foi executado contra `escola`.

## Estado final

Task012 concluída: implementação, testes unitários/HTTP/PostgreSQL, verificações
estáticas, compatibilidade de dependências e smoke sintético do modelo foram
validados. Não há validação de capacidade Linux/VPS, fluxo biométrico habilitado
ou deploy.
