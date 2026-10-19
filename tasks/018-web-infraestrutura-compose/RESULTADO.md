# Resultado — tarefa 018: artefatos Compose e Caddy

**Estado: parcial.** Os artefatos de implantação e testes foram implementados; a
configuração Compose estática, a suíte unitária e as verificações Python
passaram. O Docker CLI existe, mas o daemon local negou acesso ao named pipe.
Não foi possível construir as imagens, validar o Caddy no container ou testar
volumes em recriação. Nenhum serviço, banco ou volume foi iniciado nesta tarefa.

## Baseline e escopo

- Branch inicial: `main`.
- HEAD inicial: `72434fede3b7aece4a8f23e74c1a9f7ef3fca5e8`.
- Os arquivos rastreados estavam limpos no início. Diretórios `.pytest-task014*`,
  `.pytest-task015*` e `.pytest-task016*` já existiam como untracked; foram
  preservados e não serão adicionados ao commit.
- O resultado da task017 continua parcial; roundtrip PostgreSQL/rclone e Drive
  seguem pendentes. A task018 não trata isso como backup validado.
- Sem alterações de schema, requisitos Python ou limiar biométrico. Nenhuma
  imagem facial real foi aberta.

## Implementação

- `deploy/web/compose.yaml` define Caddy, API, worker facial único, PostgreSQL,
  migração administrativa one-shot e backup one-shot. Só TCP 80/443 é publicado;
  app e PostgreSQL não recebem portas no host. Redes `web` e `data` são
  internas; worker não tem saída externa; backup tem rede de saída separada.
- `deploy/web/Dockerfile` fixa as imagens-base por digest e separa app sem ML,
  worker ML, migração, backup, PostgreSQL e Caddy. O worker mantém MediaPipe em
  ambiente virtual separado. Dependências transitivas de APT ainda não são
  snapshotadas; esse reprodutibilidade adicional fica para a task019.
- `deploy/web/Caddyfile` é a única entrada HTTP, usa TLS automático e remove URI,
  cookies, Authorization e `Set-Cookie` dos access/runtime logs. Não monta
  arquivos biométricos. A validação do parser Caddy depende do build/engine e
  permanece pendente.
- Secrets são arquivos concedidos explicitamente a cada serviço. O entrypoint
  Python lê segredos para a configuração de processo; o entrypoint do
  PostgreSQL copia credenciais de inicialização para seu tmpfs.
- Migrations são uma ação manual via perfil `admin`; o boot da API não chama
  Alembic. O backup roda apenas sob perfil `ops`, e o exemplo systemd chama
  Compose no host sem montar `docker.sock` no container.
- Capturas app/worker compartilham o mesmo bind em tmpfs do host. Modelos são
  somente leitura no worker; referências persistem em volume privado e Caddy
  não as monta. `scripts/web_worker_preflight.py` exige os modelos locais sem
  download automático.
- O worker publica um marcador somente depois do aquecimento. O healthcheck
  executa pelo mesmo entrypoint que carrega secrets, verifica o marcador, acesso
  ao PostgreSQL e existência do lock advisory exclusivo, liberando o lock caso a
  sonda o adquira. O marcador é removido na saída do processo. Os estágios
  Python do Dockerfile executam `pip check` durante o build.
- `deploy/web/README.md` documenta preparação manual do host, secrets, volumes,
  modelos, DNS/TLS, migração explícita, timer de backup, limites, rollback e
  encerramento. O domínio e a tarifa Hostinger são registrados como consulta
  histórica, sem contratação.
- `.dockerignore` exclui diretórios de teste e documentação, ambientes locais,
  modelos, mídia e artefatos sensíveis do contexto de build.

## Arquivos afetados

- Novos: `.dockerignore`, `deploy/web/` (Compose, Dockerfile, Caddyfile,
  runbook, exemplos de tmpfs/systemd, entrypoints e criação inicial de papéis),
  `scripts/web_worker_preflight.py`,
  `src/infrastructure/workers/web_worker_healthcheck.py`, testes de deploy,
  healthcheck, entrypoint e preflight.
- Alterados: `src/face_worker_main.py`,
  `tests/unit/test_composicao_worker_task014.py`,
  `ops/systemd/facediff-web-backup.service.example`, documentação do roadmap,
  arquitetura, contrato comum, índice de tarefas e documentos da task018.

## Verificações executadas

Ambiente: Windows AMD64, Python 3.14.3 em `.venv-ml`.

| Verificação | Resultado |
|---|---|
| `.venv-ml\Scripts\python.exe -m pytest tests/unit/test_web_deploy_config.py tests/unit/test_web_worker_healthcheck.py tests/unit/test_web_deploy_entrypoint.py tests/unit/test_web_worker_preflight.py tests/unit/test_composicao_worker_task014.py -p no:cacheprovider -q` | 24 aprovados; configuração Compose resolvida com todos os perfis e secrets sintéticos |
| `.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider --basetemp "$env:TEMP\pytest-task018-unit-final-20261019" -q` | Suíte unitária completa aprovada; um aviso conhecido do adapter datetime SQLite |
| `ruff check` nos módulos e testes alterados | Aprovado após correção de ordenação/variável de loop |
| `ruff format --check` nos módulos e testes alterados | Aprovado |
| `mypy src scripts` | Aprovado: 155 arquivos-fonte |
| `git diff --check` | Aprovado; Git emitiu avisos de normalização LF/CRLF do Windows |
| `docker compose version` | CLI Compose v5.5.1 disponível |
| `docker compose config --format json`, executado pelo teste estrutural | Aprovado, usando arquivos de segredo sintéticos fora do repositório |
| `docker info` / acesso ao daemon | Falhou por acesso negado ao named pipe do Docker Desktop |
| `bash -n` nos dois scripts de inicialização PostgreSQL | Não validado: o `bash.exe` local não pôde ser executado pelo sistema |

As duas linhas de teste pytest foram executadas em `.venv-ml`; diretório
temporário usado pela suíte completa: `$env:TEMP\pytest-task018-unit-final-20261019`.
O primeiro passe da suíte detectou vazamento de variável sintética de um teste;
o teste foi isolado e a suíte completa foi repetida com sucesso.

## Não executado e motivo

- `docker compose build`, `caddy validate`, inicialização de serviços, testes de
  healthcheck reais e recriação/inspeção de volumes: o daemon Docker Desktop
  retornou acesso negado. A validação Compose foi apenas estática.
- Nenhum comando `up`, migração, banco, backup, DNS, domínio, firewall, Drive ou
  deploy foi executado. A task autoriza preparar artefatos, não iniciar
  infraestrutura.
- Os limites de CPU/RAM são guardas iniciais de engenharia, não medições da KVM2.
  O ensaio integrado e revisão de capacidade ficam para a task019.
- As redes Compose isolam serviços, mas não filtram egress por protocolo. O host
  ainda precisa restringir e verificar a saída do backup a HTTPS/destino aprovado
  e confirmar as regras Docker/firewall efetivas.

## Ativação e rollback

O procedimento está em [`deploy/web/README.md`](../../deploy/web/README.md).
Antes de qualquer ensaio operacional, instale Docker Engine/Compose em host
autorizado, valide os oito arquivos de segredo fora do checkout, confirme DNS,
CIDR e firewall, forneça modelos locais aprovados e execute a sequência manual
documentada. Comece por validar e construir imagens; faça backup/restauração
descartável comprovados antes de migrations. O serviço de migração e o backup
são comandos explícitos, não parte do boot automático.

Rollback de código: interromper tráfego, preservar todos os volumes, reverter
para imagem de commit anterior e conferir compatibilidade com o schema. Não usar
`docker compose down -v` nem downgrade destrutivo. O rollback operacional e a
recuperação só devem ser tratados como comprovados após ensaio real de backup e
restore, pendente desde task017.

## Limitações e conclusão

Os testes comprovam contratos de configuração e comportamento com doubles; não
provam build de imagem, parser/runtime Caddy, permissões efetivas do host,
persistência de volumes, desempenho ML em Linux ou recuperação de backup. A
validação visual/biométrica com pessoas não foi feita nem é requisito desta
tarefa. A entrega fica **parcial** até o build e ensaio integrado em ambiente
Linux autorizado; nenhum deploy ou recurso foi contratado.

## Adendo — fechamento 019A (19/10/2026)

O `docker compose version` estava disponível (CLI 5.5.1), mas naquela etapa
`docker info` foi negado pelo named pipe local do Docker Desktop
(`npipe:////./pipe/docker_engine`). A configuração estática era apenas
evidência de sintaxe; build e runtime ficaram pendentes até a autorização e
execução da task019A. Veja o [resultado 019A](../019a-fechamento-backend/RESULTADO.md).

## Adendo — runtime local comprovado na task 019A (19/10/2026)

A task019A construiu e executou app, worker, migrator, backup, PostgreSQL e
Caddy em um projeto Compose Linux isolado. Foram verificados SCRAM/bootstrap de
papéis, migrations até `0011`, healthchecks, Caddy, loopback HTTPS, proteção de
caminho privado, permissões/hardening, smoke sintético dos modelos locais e
persistência de registros/referências após recriar app, worker e Caddy. Os
defeitos de inicialização encontrados foram corrigidos com regressões. Isso
comprova runtime local descartável, não deploy, DNS, firewall, KVM2 ou operação
com dados reais; ver [resultado 019A](../019a-fechamento-backend/RESULTADO.md).
