# Resultado — Task 019A: fechamento das pendências do backend

**Estado: implementação e gate de backend concluídos; atualização do índice de tasks pendente.** Em 19/10/2026, o
`GATE_BACKEND_PARA_INTERFACE: APROVADO` foi comprovado em Docker Compose Linux
local, PostgreSQL/rclone descartáveis e dados estritamente sintéticos.
`GATE_OPERACIONAL_DADOS_REAIS: PENDENTE`. A interface 020 não foi iniciada.

Esta continuação começou na branch `main`, HEAD `da4665b`, com mudanças
preexistentes em `tasks/README.md` e diretórios temporários de pytest. Os
diretórios temporários foram preservados. O auto-review rejeitou o staging de
`tasks/README.md` por ser uma alteração preexistente que poderia incluir trabalho
do usuário; mantive o arquivo no estado em que estava antes desta execução e fora
dos commits. Assim, o índice ainda mostra o status anterior da 019A; sua
publicação depende de aprovação explícita.

## Diagnóstico e correções

A tentativa inicial estava bloqueada porque o Docker Desktop negava acesso ao
daemon e as ferramentas PostgreSQL/rclone não estavam no PATH do shell Windows.
Com a autorização do solicitante para organizar infraestrutura descartável, as
provas foram executadas dentro do Docker Desktop Linux, sem alterar o banco
`escola`, Drive, VPS, volumes de outras tarefas ou dados reais.

O build e o primeiro boot reproduziram quatro problemas de runtime, corrigidos
com testes de regressão:

- O target PostgreSQL substituía o entrypoint da imagem-base sem declarar
  `CMD ["postgres"]`; o container encerrava em vez de iniciar o servidor.
- O bootstrap usava autenticação local peer, incompatível com o papel
  administrativo da aplicação executada pelo script. O Compose agora usa SCRAM
  local e por rede; o script usa a credencial administrativa efêmera via
  `PGPASSWORD` e limpa as cópias locais das variáveis no encerramento.
- O binário Caddy trazia capability de arquivo que falhava com
  `no-new-privileges` e remoção de capabilities; o target remove essa capability
  no build.
- O runtime HTTP importava o domínio que usa NumPy, mas
  `requirements-web.txt` não o declarava. Foi adicionado
  `numpy==2.5.3`, mantendo OpenCV/DeepFace/TensorFlow fora desse runtime.

## Evidências do backup e restore

Foi criado um projeto Compose isolado, com secrets temporários, bancos e volumes
marcados como descartáveis. O fluxo real da aplicação executou `pg_dump`,
criptografia `rclone crypt`, `cryptcheck` e restauração via `pg_restore`.

A geração válida continha 3 artefatos (dump e duas referências sintéticas),
revisão Alembic `0011` e 93.915 bytes. A inspeção de origem/destino confirmou:

- turma e segundo aluno sintético preservados; aluno excluído depois do snapshot
  removido do destino;
- embedding de teste de dimensão 512 e conteúdo/hash da referência restante
  preservados;
- credencial e sessões restauradas invalidadas;
- exclusão registrada depois do snapshot reaplicada ao banco e ao storage;
- marcador do destino mantido e staging em claro vazio após o restore.

As recusas também foram exercitadas no fluxo real: configuração com chave
incorreta, manifesto cifrado corrompido e destino sem marcador de descarte. Os
três casos falharam antes de alterar o destino; a sentinela do banco não
descartável permaneceu. Uma falha injetada depois de solicitar manutenção
liberou o gate e deixou os diretórios de staging vazios. Não houve conexão ao
Google Drive.

## Evidências do runtime Linux/Compose

Ambiente: Docker Desktop Engine `29.8.0`, Linux AMD64, Compose `5.5.1`.
Targets app, face-worker, migrate, backup, PostgreSQL e Caddy foram construídos.
Versões observadas nas imagens: Python `3.12.15`, PostgreSQL e ferramentas
`pg_dump/pg_restore/psql 16.15`, rclone `1.75.2` e Caddy `2.11.4`.
O PostgreSQL executou como UID 999.

O banco descartável inicializou e as migrations existentes chegaram a
`0011 (head)`. A execução explícita do serviço migrate passou;
`alembic current` confirmou `0011 (head)` e `alembic check` respondeu
`No new upgrade operations detected.` App e worker ficaram healthy, PostgreSQL
aceitou conexões, e `caddy validate` aprovou a configuração efetivamente usada.
Após recriar app, worker e Caddy sem remover volumes, os serviços voltaram a
healthy; uma consulta ao destino confirmou a revisão `0011`, 21 tabelas e 3
linhas sintéticas. O volume privado conservou seu marcador e um arquivo de
referência sintética.

App, worker e Caddy executaram como UID `10001:10001`, root filesystem somente
leitura, `no-new-privileges` e capabilities removidas. As portas de teste
ficaram ligadas apenas a loopback. Verificações locais retornaram HTTPS health
`200`, caminho privado `404` e redirecionamento HTTP para HTTPS `308`.

O smoke pós-recriação carregou os pesos locais FaceNet512 e abriu o modelo
MediaPipe Tasks `0.10.35`; inferência em array sintético preto de 160×160
retornou zero faces e o detector foi fechado. A varredura de logs encontrou
zero valores Bearer, senhas ou cookies; encontrou uma menção textual isolada à
palavra `embedding`, sem valor, vetor, hex longo ou payload associado.

## Proteção pública e fluxo integrado

Os limites HMAC configuráveis nas rotas públicas de cadastro, solicitação,
captura e consulta continuam com defaults de 10 operações por minuto por
contexto, 60 consultas por credencial e teto agregado de 600 por origem. O
teste PostgreSQL confirmou concorrência e reset de janela; cabeçalhos
`X-Forwarded-For` arbitrários não alteram a origem.

O fluxo HTTP/PostgreSQL sintético foi executado até painel e CSV e verificou
ownership entre professores, correção manual com justificativa/auditoria,
atualização das leituras, escape de fórmulas e ausência de tokens/biometria no
CSV. As oito integrações direcionadas do fluxo completo e fila passaram
(2 testes de fluxo e 6 de fila); nenhuma delas foi ignorada. Não foram enviadas
imagens faciais reais.

## Arquivos alterados

| Arquivo | Mudança |
|---|---|
| `deploy/web/Dockerfile` | Comando do servidor PostgreSQL e remoção da capability incompatível do Caddy |
| `deploy/web/compose.yaml` | SCRAM também para autenticação local do PostgreSQL |
| `deploy/web/postgres-init/001-web-roles.sh` | Bootstrap dos papéis com credencial administrativa transitória |
| `requirements-web.txt` | NumPy fixado no runtime HTTP isolado |
| `tests/unit/test_web_deploy_config.py` | Regressões para os quatro defeitos encontrados |
| `tasks/019a-fechamento-backend/*` | Plano, desenho e este resultado atualizados |
| `tasks/017-web-backup-retencao/RESULTADO.md` | Adendo com o roundtrip comprovado |
| `tasks/018-web-infraestrutura-compose/RESULTADO.md` | Adendo com build e runtime local |
| `tasks/019-web-validacao-backend/RESULTADO.md` | Adendo corrigindo o status histórico do gate |
| `AGENTS.md`, `CLAUDE.md` | Estado atual e dependência da interface |
| `docs/ESTADO-ATUAL-E-EVIDENCIAS.md`, `docs/FACEDIFF-WEB-RUNTIME.md`, `docs/FACEDIFF-WEB-ROADMAP.md` | Dependências, evidências e estado dos gates |
| `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`, `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md` | Separação entre runtime local, deploy e operação real |

## Verificações executadas

| Comando/prova | Resultado |
|---|---|
| Build dos targets Docker app, face-worker, migrate, backup, postgres e caddy | Aprovado |
| `pip check` em app, worker, venv de landmarks, migrate e backup | `No broken requirements found` em todos |
| `bash -n deploy/web/postgres-init/001-web-roles.sh` | Aprovado |
| `caddy validate --config /etc/caddy/Caddyfile` na imagem efetiva | `Valid configuration` |
| `docker compose run --rm --no-deps migrate` | Aprovado; schema no head |
| `alembic current` e `alembic check` no serviço migrate | `0011 (head)`; nenhum upgrade pendente |
| Consulta read-only após recriação de serviços e verificação do volume privado | Destino em `0011`, 21 tabelas, 3 linhas sintéticas; marcador presente e 1 arquivo de referência |
| Integrações `test_web_fluxo_completo.py` e `test_fila_facial_postgresql.py` no Compose | 8 aprovadas |
| `tests/unit/test_web_deploy_config.py` | 14 aprovados |
| Suíte completa com cobertura | 1.277 aprovados, 84 ignorados, 0 falhas; cobertura 80,61% (mínimo 80%) |
| `ruff check .` | Aprovado; 3 avisos de acesso negado ao varrer temporários preexistentes |
| `ruff format --check tests/unit/test_web_deploy_config.py` | Arquivo já formatado |
| `python -m mypy src scripts` | Aprovado: 158 arquivos-fonte |
| `python -m pip check` no ambiente de desenvolvimento | `No broken requirements found` |
| `git diff --check` | Aprovado |
| Smoke local pós-recriação, sem webcam/rede | FaceNet512 carregado; MediaPipe inferiu 0 faces no array sintético |
| Caddy por loopback | HTTPS 200; caminho privado 404; HTTP→HTTPS 308 |

A suíte completa foi executada com:

```powershell
.venv-ml\Scripts\python.exe -m pytest --cov=src --cov=scripts.metricas --cov=scripts.divisao_por_identidade --cov=scripts.evaluate_model --cov=scripts.calibrar_limiar --cov-report=term:skip-covered --cov-fail-under=80 -p no:cacheprovider --basetemp "$env:TEMP\pytest-task019a-junit-20261019" --junitxml "$env:TEMP\task019a-junit-20261019.xml" -q --no-header
```

Os 84 skips são opt-ins de outras integrações/ambientes; as integrações
específicas de rate limit, fluxo, fila e restore deste gate foram executadas
diretamente. A cobertura reportada foi `80.60877350044763%`.

## Dependências, ativação e rollback

Antes: o runtime HTTP separado não declarava NumPy; o target PostgreSQL e o
bootstrap de papéis não iniciavam corretamente em uma instalação limpa; o
processo Caddy falhava com o conjunto de restrições de capabilities. Depois:
`numpy==2.5.3`, entrypoint PostgreSQL com `CMD ["postgres"]`, autenticação SCRAM
com bootstrap usando secret de arquivo e Caddy sem a capability conflitante.
Não foi adicionada migration; as migrations `0001–0011` foram aplicadas somente
ao banco PostgreSQL descartável deste ensaio.

Não houve deploy. Em uma instalação futura, construir as imagens e executar a
migration explicitamente conforme `deploy/web/README.md`; nunca depender de
migration no boot. Rollback do código por `git revert` dos commits desta tarefa.
O projeto Compose, bancos/volumes, containers e secrets sintéticos exclusivos
da validação foram removidos depois das provas. Nenhum container, imagem-base ou
volume de outro projeto foi removido.

## Limitações e decisão dos gates

- Não houve pessoa, webcam, captura ou embedding biométrico real. O smoke
  sintético prova apenas inicialização e chamada técnica do modelo.
- Não houve VPS, DNS/certificado público, firewall de hospedagem, Google Drive,
  OAuth, custódia operacional de chave, migração de banco operacional ou deploy.
- Limites públicos são guards iniciais, ainda não calibrados por tráfego real.
- Piloto com participantes, validação de segurança operacional, retenção do
  provedor e desempenho/capacidade KVM2 exigem ensaio separado e autorização.
- A interface 020 permanece não implementada e não foi iniciada por esta tarefa.

`GATE_BACKEND_PARA_INTERFACE: APROVADO`. As provas obrigatórias de restore real,
runtime Linux, abuso PostgreSQL e cadeia funcional passaram.
`GATE_OPERACIONAL_DADOS_REAIS: PENDENTE`; nenhum teste sintético é evidência de
acurácia biométrica ou prontidão de produção.
