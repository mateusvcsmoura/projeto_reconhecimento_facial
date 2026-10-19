# Resultado — task019: validação integrada do backend

Data da execução: 19/10/2026. Branch inicial: `main`, HEAD `012272c`; o
workspace não tinha alterações rastreadas no início. Os diretórios temporários
`.pytest-*` preexistentes foram preservados. Nenhum commit alheio foi incluído.

**Estado da tarefa: parcial.** A validação funcional sintética e as provas em
PostgreSQL descartável foram executadas. Não foi possível concluir o restore
cifrado real porque o executável `rclone` não está instalado neste ambiente.

GATE_BACKEND_PARA_INTERFACE: BLOQUEADO_POR_AMBIENTE

GATE_OPERACIONAL_DADOS_REAIS: PENDENTE

## Diagnóstico e decisão

A inspeção confirmou implementações das tasks009–018 e testes existentes para
autenticação/ownership, cadastro e referências, fila, sessões, presenças,
revisão manual, CSV, backup e artefatos Compose. As provas foram reutilizadas
onde já cobriam o contrato; acrescentei um fluxo HTTP integrado contra a
composição real da API e PostgreSQL local, com apenas a verificação facial
substituída por evidência sintética.

As integrações antigas de autenticação e referências afirmavam que a revisão
Alembic deveria permanecer em `0005`/`0006`, embora suas fixtures atualizem o
schema até o head atual `0011`. A execução PostgreSQL reproduziu essas
expectativas desatualizadas. Os testes agora consultam o head Alembic efetivo;
as integrações voltaram a passar sem reduzir a revisão do schema.

O bloqueio restante é ambiental: `pg_dump` e `pg_restore` 18.3 estão
disponíveis, mas `rclone` não está no PATH. Os testes de backup com fakes
passaram, porém não substituem o roundtrip local PostgreSQL + arquivos cifrados
exigido para aprovar o gate. Não introduzi um cifrador alternativo, pois isso
não provaria o transporte e restore usados pela aplicação. O Docker Compose
está instalado e sua configuração estática foi validada, mas o Docker Engine
nega acesso ao named pipe local; nenhum container foi iniciado.

## Implementação

- `scripts/benchmark_web.py`: benchmark agregado com fila e processador fake,
  cargas 1/2/5/10/excesso, tempos frio/quente, taxa de chegada, falhas injetadas,
  CPU, RAM, RSS e PSS quando disponível. Só usa bytes sintéticos temporários e
  identifica o resultado como fake; não tenta inferir capacidade de produção.
- `tests/unit/test_benchmark_web.py`: valida cargas, limite da fila, erro fake,
  métricas e ausência de dados pessoais no JSON.
- `tests/integration/test_web_fluxo_completo.py`: usa TestClient, composição
  `create_web_app`, repositórios PostgreSQL, fila persistida e três capturas
  sintéticas. Prova contas Professor A/B, ownership, cadastro aprovado com três
  referências sintéticas, recusa de matrícula existente sem conjunto aprovado,
  sessão/link, desafio de três etapas e gravação de uma presença pelo worker
  fake. O teste não processa nem armazena imagens faciais reais.
- `tests/integration/test_web_auth_postgresql.py` e
  `tests/integration/test_referencias_web_postgresql.py`: expectativas de
  revisão corrigidas para verificar o head Alembic atual.
- Nenhuma dependência, migration, threshold, pipeline de reconhecimento,
  configuração de produção ou interface foi alterada.

## Verificações executadas

Ambiente: `.venv-ml`, Python 3.14.3, Windows 11 AMD64. O PostgreSQL foi
conectado somente por nomes locais e bancos marcados como descartáveis; o banco
`escola` não foi acessado.

| Prova | Resultado observado |
|---|---|
| `pytest tests/unit -p no:cacheprovider --basetemp <tmp> -o addopts= -q -ra` | 1228 passaram; 1 aviso de depreciação do adaptador datetime do SQLite; 17,40 s |
| Testes HTTP, backup, autenticação, runtime, Compose e benchmark focados | 83 passaram; 1 aviso de depreciação do adaptador datetime do SQLite; 5,85 s |
| `tests/integration/test_web_fluxo_completo.py` | 1 passou em PostgreSQL local descartável task019 |
| `tests/integration/test_web_auth_postgresql.py` | 3 passaram em PostgreSQL descartável task010 |
| `tests/integration/test_referencias_web_postgresql.py` | 3 passaram em PostgreSQL descartável task011 |
| `tests/integration/test_fila_facial_postgresql.py` | 5 passaram em PostgreSQL descartável task012 |
| `tests/integration/test_cadastro_web_api.py` | 1 passou em PostgreSQL descartável task014 |
| `tests/integration/test_presenca_sessao_postgresql.py` | 5 passaram em PostgreSQL descartável task015 |
| `tests/integration/test_revisao_csv_web.py` | 2 passaram em PostgreSQL descartável task016 |
| Total das integrações PostgreSQL acima | 20 passaram; dados sintéticos; fixtures reverteram os schemas para `base` |
| `alembic upgrade head`, `alembic check`, `alembic downgrade base` no banco task019 | Upgrade e check aprovados na revisão `0011`; downgrade executado; banco ficou em `base` com a tabela `alembic_version` vazia |
| `tests/unit/test_web_deploy_config.py` | 10 passaram |
| `docker compose --env-file deploy/web/.env.example -f deploy/web/compose.yaml config --quiet` | Configuração estática passou; nenhum serviço foi iniciado |
| `ruff check` nos cinco arquivos Python alterados | Aprovado |
| `ruff format --check` nos cinco arquivos Python alterados | Aprovado |
| `mypy src scripts` | Aprovado: 156 arquivos fonte, sem erros |
| `git diff --check` | Aprovado; Git avisou apenas que normalizará LF para CRLF nos dois testes de integração alterados |

Os testes de PostgreSQL foram iniciados por wrapper local que leu a URL já
configurada sem imprimi-la, mudou somente o nome para cada banco dedicado e
forneceu os opt-ins esperados pelas fixtures. Cada fixture verificou nome,
comentário de descarte e servidor local antes de aplicar migrations; executou
`alembic check` quando previsto e limpou/reverteu seu banco ao final.

## Benchmark e limites

O comando executado foi:

```powershell
python -m scripts.benchmark_web --atraso-frio-ms 15 --atraso-quente-ms 3 --chegada-por-segundo 50 --falha-falsa-a-cada 0
```

O JSON agregado está em
[`evidencias/benchmark-fake-20261019.json`](evidencias/benchmark-fake-20261019.json).
Na máquina Windows, o benchmark registrou 12 CPUs lógicas, RSS de 34,1 MB no
início e 38,8 MB no fim; PSS ficou `null`, pois o contador disponível na
implementação depende de `/proc`. Nas cargas testadas, a fila fake aceitou
1/1, 2/2, 5/5, 10/10 e 10/11 jobs. A última carga recusou o job excedente. Os
tempos frios/quentes, p50/p95 de worker, CPU e memória estão no artefato.

Esses números descrevem somente a execução fake em Windows/Python 3.14.3.
Não medem FaceNet, MediaPipe, inferência real, PostgreSQL sob carga ou a VPS;
não aprovam concorrência, limites ou timeouts de produção. O ensaio na KVM2
continua sujeito a autorização própria.

## Critérios ainda pendentes

- **Restore cifrado local real:** não executado por falta do `rclone`; os testes
  unitários de upload falho, chave ausente, exclusões e restore sintético com
  doubles passaram, mas não provam `pg_dump`/`pg_restore` e transporte cifrado
  integrados.
- **Runtime dos containers e Caddy:** configuração Compose e testes estáticos
  passaram; build e execução não foram possíveis porque o daemon Docker negou
  acesso a `npipe:////./pipe/docker_engine`.
- **PSS:** indisponível nesta execução Windows e registrado como `null`.
- **Operação real:** não houve VPS, Drive, pessoas, webcam ou dispositivos
  reais. Não houve validação biométrica nem avaliação de capacidade.

O gate do backend permanece bloqueado até o restore cifrado local ser executado
e todos os artefatos obrigatórios serem confirmados. A task020 não deve começar
com este status. O gate operacional permanece pendente até ensaio separado,
com consentimento, ambiente e dispositivos autorizados.

## Ativação, reversão e arquivos

O benchmark é opcional e manual; nenhum serviço ou configuração o ativa. Para
gerar outro relatório agregado, execute `python -m scripts.benchmark_web` com
os parâmetros documentados em `docs/FACEDIFF-WEB-RUNTIME.md`. A alteração não
cria schema: a reversão funcional consiste em reverter os commits da task019;
o banco descartável usado para esta validação já voltou à revisão `base`.
O arquivo JSON é evidência da execução e pode ser removido junto da pasta
`evidencias` se for necessário regenerá-lo.

Arquivos atualizados: `DESENHO.md`, `PLANO.md`, este `RESULTADO.md`,
`tasks/README.md`, `docs/FACEDIFF-WEB-RUNTIME.md`,
`docs/FACEDIFF-WEB-ROADMAP.md` e `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`.
Arquivos de implementação/teste e o artefato de benchmark estão listados acima.

## Adendo — fechamento 019A (19/10/2026)

A task019A acrescentou proteção de frequência ao cadastro público e preparou
provas HTTP integradas para painel, CSV seguro, ownership e correção auditada.
Na primeira etapa, o ambiente ainda bloqueava o restore cifrado e o runtime
Linux. Na continuação autorizada, as provas foram concluídas em containers,
bancos e volumes descartáveis. O gate atual é
`GATE_BACKEND_PARA_INTERFACE: APROVADO`; o gate operacional segue pendente.
Consulte o [resultado final 019A](../019a-fechamento-backend/RESULTADO.md). A
tabela e as conclusões acima continuam descrevendo somente os testes executados
na task019.
