# Resultado — Task 019A: fechamento das pendências do backend

**Estado: parcial; gates bloqueados por ambiente.** Execução em 19/10/2026,
inline, na `main`, com HEAD inicial `1e7c6081215699e98c88451441f013c216cbfd0f`.
Os documentos de definição desta task foram mantidos no escopo e atualizados.
A entrada 019A de `tasks/README.md` também está atualizada no workspace, mas
permanece fora desta publicação por ser uma alteração local preexistente
identificada pelo auto-review. Os diretórios temporários `.pytest-*`
preexistentes foram preservados e excluídos da entrega.

## Diagnóstico e ambiente

O bloqueio do fechamento não foi causado por falha reproduzida no serviço de
backup ou nos artefatos Compose: os componentes necessários para executar as
provas reais não estão disponíveis neste shell. O Docker Compose CLI responde
com versão 5.5.1, mas `docker info` não alcança o named pipe
`npipe:////./pipe/docker_engine` por acesso negado. `rclone`, `pg_dump`,
`pg_restore` e `psql` não estão no `PATH`. A sessão usa Windows AMD64; o Python
do PATH é 3.12.0rc2 e `.venv-ml` usa Python 3.14.3.

Não consultei `.env`, banco `escola`, VPS, Drive, rostos ou referências
biométricas. Nenhum serviço Compose foi iniciado, nenhuma migration foi
executada nesta tarefa e nenhuma ferramenta foi instalada. A indisponibilidade
das ferramentas impediu tanto o roundtrip cifrado com origem/destino
descartáveis quanto a execução do runtime Linux.

## Implementação

Foi adicionada limitação persistida de frequência às rotas públicas de troca
de link, solicitação de cadastro, envio de capturas/consentimento e consulta de
status. As chaves persistidas são HMAC; token e endereço não são gravados. Os
valores iniciais são configuráveis: 10 operações por minuto por contexto,
60 consultas por minuto por credencial e teto agregado de 600 requisições por
minuto por origem. O `X-Forwarded-For` só é considerado quando o peer pertence
a `WEB_TRUSTED_PROXY_CIDRS`; acesso direto e cabeçalhos forjados não alteram a
origem. Em produção, falta do limitador ou segredo resulta em 503 antes da
operação.

O fluxo integrado PostgreSQL foi ampliado para verificar painel e CSV antes e
depois de uma correção manual justificada, escape de fórmula CSV, ausência de
credencial/nonce/embedding, isolamento do professor sem ownership e evento de
auditoria. Foi acrescentada prova PostgreSQL concorrente para o contador e
reset da janela, além de uma regressão opt-in em que um worker recém-iniciado
processa um job que já estava enfileirado sem registrar presença em falha.
Essas duas provas PostgreSQL dependem dos respectivos opt-ins e não foram
executadas nesta máquina.

Nenhum defeito no backup ou Compose foi confirmado; não alterei esses
componentes sem evidência. O teste de restore existente continua recebendo uma
geração externa e validando o código de saída; ele ainda não cria por si só um
backup e compara dados conhecidos de origem/destino. A correção de abuse guard
é uma proteção inicial, não limite calibrado para carga real; alunos atrás do
mesmo NAT compartilham o teto agregado.

## Critérios e evidências

| Critério | Estado observado nesta execução |
|---|---|
| Diagnóstico do shell e preservação do workspace | Concluído; ferramentas ausentes, daemon Docker negou acesso; alterações e temporários alheios preservados |
| Backup/restore cifrado real, conteúdo conhecido, exclusões, chave incorreta/corrupção e manutenção após falha | Bloqueado: `rclone`, `pg_dump`, `pg_restore` e `psql` indisponíveis; nenhuma prova substitutiva foi tratada como real |
| Build/execução Linux Compose, healthchecks, Caddy, volumes e runtime | Bloqueado: daemon Docker negou acesso; teste estático da configuração não é execução do runtime |
| Proteção das rotas públicas e limites de origem confiável | Implementada; testes HTTP/unitários focados passaram |
| Concorrência e janela no rate limit PostgreSQL | Teste opt-in acrescentado; não executado por ausência do banco/ferramentas de integração nesta sessão |
| Fluxo sintético até painel/CSV, isolamento e correção auditada | Teste de integração ampliado; não executado sem opt-in PostgreSQL descartável |
| Reinício do worker com job já enfileirado | Teste PostgreSQL opt-in acrescentado; não executado nesta sessão |
| Operação com dados reais | Pendente separadamente; não autorizada nem executada |

## Verificações executadas

| Comando | Resultado |
|---|---|
| `.venv-ml\Scripts\python.exe -m pytest -o addopts= tests/unit/test_cadastro_web_rate_limit.py tests/unit/test_api_cadastro_web.py tests/unit/test_web_auth.py tests/unit/test_rotas_presenca_web.py tests/unit/test_web_fundacao.py tests/unit/test_web_deploy_config.py tests/integration/test_web_fluxo_completo.py tests/integration/test_web_restore_local.py tests/integration/test_fila_facial_postgresql.py -p no:cacheprovider --basetemp "$env:TEMP\pytest-task019a-focused-final-20261019" -q -ra` | 75 passaram, 9 ignorados: 2 fluxos task019, 6 integrações task012 e 1 restore task017 sem opt-ins |
| `.venv-ml\Scripts\python.exe -m pytest --cov=src --cov=scripts.metricas --cov=scripts.divisao_por_identidade --cov=scripts.evaluate_model --cov=scripts.calibrar_limiar --cov-report=term --cov-fail-under=80 -q` | 1273 passaram, 84 ignorados; 1 aviso de adapter datetime do SQLite; cobertura 80,61% (gate 80%) |
| `.venv-ml\Scripts\ruff.exe check .` | Aprovado; Ruff emitiu 3 avisos de acesso negado ao varrer diretórios temporários não relacionados |
| `.venv-ml\Scripts\ruff.exe format --check` nos 9 Python alterados | 9 arquivos já formatados; `ruff format --check src scripts tests` reportou 15 arquivos não alterados fora do escopo sem o formato atual |
| `.venv-ml\Scripts\python.exe -m mypy src scripts` | Aprovado: 158 arquivos-fonte |
| `.venv-ml\Scripts\python.exe -m pip check` | `No broken requirements found.` |
| `git diff --check` | Aprovado; Git emitiu avisos de normalização LF/CRLF no Windows |
| `docker info`; procura de `rclone`, `pg_dump`, `pg_restore`, `psql` | Docker negou acesso ao named pipe; quatro ferramentas ausentes |

Os testes unitários focados usam doubles HTTP para a proteção do cadastro.
As 84 marcações de skip da suíte completa incluem as integrações PostgreSQL e
restore sem opt-in. Elas não contam como evidência de concorrência real,
backup cifrado, runtime Linux nem acurácia biométrica.

## Dependências, ativação e rollback

Não foram adicionadas dependências Python nem migrations. Os limites são lidos
por `WebSettings` e expostos no Compose via
`WEB_PUBLIC_REGISTRATION_CONTEXT_LIMIT_PER_MINUTE` (10),
`WEB_PUBLIC_REGISTRATION_QUERY_LIMIT_PER_MINUTE` (60) e
`WEB_PUBLIC_REGISTRATION_ORIGIN_LIMIT_PER_MINUTE` (600). Os valores são
provisórios e devem ser medidos antes de operação; não reduzir proteções de
payload, fila, consentimento ou expiração.

Para rollback, desative as três configurações na implantação e reverta o
commit de proteção do cadastro; não é necessária migration. A limitação
compartilha o repositório persistente já usado pelo rate limit de presença.
Nenhum deploy foi executado.

## Gates

- **`GATE_BACKEND_PARA_INTERFACE: BLOQUEADO_POR_AMBIENTE`.** A proteção e os
  testes do fluxo foram preparados, mas faltam roundtrip cifrado real e runtime
  Linux/Compose. Também não foram executadas as integrações PostgreSQL novas
  nesta sessão. Os critérios obrigatórios do plano não podem ser aprovados com
  skips ou testes sintéticos.
- **`GATE_OPERACIONAL_DADOS_REAIS: PENDENTE`.** Exige autorização e ensaio
  separado para host, armazenamento externo, chaves, dispositivos e dados
  legítimos. Nenhum desses itens foi executado.

A task 020 continua bloqueada pelo gate do backend. Para retomar as provas
faltantes, disponibilizar neste workspace um daemon Docker autorizado e um
ambiente local descartável com `rclone`, `pg_dump`, `pg_restore` e `psql`,
incluindo configurações criptográficas temporárias e bancos/volumes com os
marcadores previstos nos testes. Não usar `escola`, Drive, VPS ou dados reais.
