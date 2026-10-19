# Resultado — task 015: Sessões, tentativas e presença por API

**Estado: concluída e publicada na `main` em 18/10/2026.** A entrega conecta
sessões por turma, links de finalidade `presenca`, tentativas limitadas e o
worker 1:1 já existente. Não cria interface e não afirma validação biométrica
com pessoas.

## Baseline e implementação

- Branch inicial: `main`, HEAD `c3d4f6fc5068d244ff0a0016ffbefd94ae166e12`.
- Foram preservados os diretórios temporários da task014 já presentes no
workspace. A migration inicial inspecionada era `0009`; a task adicionou `0010`.
- Não foi necessário instalar dependências novas.

A API cria e revoga sessões autorizadas por turma, emite links vinculados à
sessão, inicia tentativas com `Idempotency-Key`, recebe as três etapas do
desafio e consulta o estado com credencial de captura. A matrícula localiza o
aluno, mas o início exige vínculo ativo e conjunto biométrico aprovado com três
referências. Horários são avaliados pelo servidor; timestamps do cliente são
rejeitados.

A revisão `0010` adiciona sessões, tentativas/ordinais, hash da chave de
idempotência, hash de payload por etapa e buckets de rate limit. A presença web
fica vinculada à sessão e à tentativa, com unicidade por aluno/sessão. Índices
parciais preservam o escritor diário da CLI. A captura recebida dentro do prazo
pode terminar seu processamento depois dele; o worker só confirma sucesso após
uma transação que revalida sessão, vínculo, referências, desafio e lease. A
revogação impede um commit tardio. Reenvio idêntico é idempotente; payload
diferente para a mesma etapa é recusado.

Os frames transitam pelo armazenamento temporário local e não são gravados no
banco. O banco guarda somente o hash do conteúdo para idempotência; não há
persistência de coordenadas. A feature reutiliza a fila, o desafio e o pipeline
1:1 existentes, sem mudar FaceNet512, MiniFASNet, threshold `0.30` ou as regras
do reconhecimento legado.

## Validação executada

| Verificação | Resultado |
| --- | --- |
| `pytest tests/unit --disable-warnings --tb=short -p no:cacheprovider --basetemp .pytest-task015-unit-count-final-20261018` | 1.160 aprovados em 20,22 s |
| Comando de cobertura do CI (`pytest --cov=src --cov=scripts.metricas --cov=scripts.divisao_por_identidade --cov=scripts.evaluate_model --cov=scripts.calibrar_limiar --cov-report=term-missing --cov-fail-under=80`) | 1.185 aprovados, 78 ignorados; cobertura total 80,09% |
| Testes HTTP de presença | 11 testes na suíte de contrato; incluem timestamps recusados, quota/fila, rate limit, expiração, repetição e limpeza pendente |
| `tests/integration/test_presenca_sessao_postgresql.py` em banco local descartável marcado para task015 | 5 aprovados: migration/índices, escritor CLI, reserva concorrente/quota, revogação durante processamento e recebimento tempestivo com duas sessões no mesmo dia |
| Migration `0010` e `alembic check` | Upgrade até `head` e check aprovados; fixture limpou os dados sintéticos e retornou o banco descartável a `base` |
| `ruff check src scripts tests` | Aprovado |
| `ruff format --check` nos 32 arquivos Python alterados | Aprovado |
| `mypy src scripts` | Aprovado: 135 arquivos-fonte |
| `pip check` no ambiente `.venv-ml` | `No broken requirements found.` |
| `compileall` em `src`, `scripts`, `tests` e `migrations/versions`; `git diff --check` | Aprovados |

Uma tentativa adicional de `ruff format --check src scripts tests` apontou 15
arquivos preexistentes e não alterados fora do formato. Não os reformatei para
manter o escopo; todos os 32 arquivos Python tocados pela task passaram na
verificação específica.

O banco usado na integração foi o local descartável
`task015_presenca_test_20261018`, com comentário marcador validado pela fixture.
O banco `escola` não recebeu `0010` nem foi alterado. Nenhuma webcam, imagem
biométrica real ou banco de produção foi acessado.

## Arquivos e limites

As mudanças principais estão na revisão `0010`, nas entidades e casos de uso de
sessão/tentativa, no repositório PostgreSQL, nas rotas `presencas.py` e na
integração com `WorkerFacial`, `DesafioCaptura` e os links da task014. Os testes
adicionados cobrem regras de domínio, HTTP, integração PostgreSQL concorrente,
compatibilidade do escritor CLI e a persistência transacional do worker. A
documentação atualizada inclui o runtime web, arquitetura/operação, planejamento,
contratos/migrations e índice das tasks.

Continuam pendentes interface de câmera (task020), deploy, configuração de
storage temporário de produção, medição na VPS e validação visual/biométrica com
pessoas autorizadas. Os testes usam somente payloads e identidades sintéticos;
80,09% é cobertura de código, não métrica de acurácia facial.

## Ativação e rollback

Para uma instalação futura, configure as variáveis `WEB_*` obrigatórias do
runtime, inclusive origem HTTPS, limites e política de encerramento. O processo
HTTP e o worker devem compartilhar o armazenamento temporário local e a raiz
privada de referências; o worker também precisa do modelo local e do
interpretador MediaPipe isolado. A revisão do banco deve ser aplicada de forma
coordenada, com backup e validação no ambiente de destino, por meio de
`alembic upgrade head`. Este registro não significa que a feature foi implantada
ou que a revisão foi aplicada a `escola`.

O downgrade de `0010` só é permitido sem sessões, tentativas, links de presença
ou presenças por sessão; a migration verifica esses dados e recusa a remoção se
existirem. Em caso de rollback de código, reverta os commits da task em ordem
inversa com `git revert`; não use reset/force push. Para dados já criados, pare
as escritas, faça backup e avalie a migração/reconciliação antes de qualquer
downgrade.

Os commits foram organizados entre implementação/testes e documentação, em
português, e enviados para `origin/main` sem force push.
