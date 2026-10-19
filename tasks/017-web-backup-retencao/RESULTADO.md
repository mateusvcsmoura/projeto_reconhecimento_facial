# Resultado — Tarefa 017: backup cifrado, retenção e restauração

**Estado: parcial, publicada na `main`.** A implementação, testes unitários e
verificações estáticas passaram. O roundtrip com rclone e PostgreSQL não pôde ser executado neste
Windows porque `rclone`, `pg_dump`, `pg_restore` e `psql` não estão instalados;
o teste de integração opt-in permaneceu ignorado. Não houve acesso ao banco
`escola`, migration, Drive, arquivos biométricos ou deploy.

## Baseline e escopo

- Branch inicial: `main`.
- HEAD inicial: `66e5b5dade4f2968d05cdf42f5499c01cd753f21`.
- As alterações foram restritas à tarefa 017. Diretórios `.pytest-task014*`,
  `.pytest-task015*` e `.pytest-task016*` já estavam não rastreados e foram
  preservados, sem stage.
- Não foi criada migration nem dependência Python nova. `pip check` continuou
  limpo.

## Implementação

- `GerarBackup` pausa novas escritas HTTP, permite o worker drenar a fila,
  aguarda lock exclusivo e cria dump lógico PostgreSQL e snapshot das
  referências no mesmo ponto. Staging é privado, verificado com `cryptcheck`,
  limpo e a manutenção é liberada em blocos `finally`.
- O snapshot usa `rclone crypt` local. Referências são copiadas sob nomes
  aleatórios planos; seu caminho privado original permanece somente no
  manifesto cifrado. Essa escolha responde ao comportamento documentado do
  rclone: sem criptografia de nomes de diretório, a estrutura fica visível no
  backend raw. O remote ainda expõe geração opaca, contagem, tamanho aproximado
  e horários dos arquivos.
- Transporte opcional replica bytes já cifrados, verifica a cópia por download
  e amostra SHA-256. Erros tentam limpar o destino; se a limpeza falhar, um
  marcador permite a retenção localizar a tentativa incompleta. A expiração
  remove a cópia externa configurada antes da local.
- O ensaio de restore valida hashes e só aceita PostgreSQL local com comentário
  de descarte, confirmação exata e volume de referências vazio marcado.
  Reaplica exclusões append-only e invalida sessões/credenciais restauradas.
- Retenção tem dry-run por padrão, limite de três gerações completas, logs de
  três dias, limpeza de temporários e purga final quando a finalidade termina.
  Timer systemd e serviço de exemplo não contêm segredos.
- Runtime web bloqueia mutações no período de manutenção e responde 503; após
  `WEB_PURPOSE_END_AT`, bloqueia a API com 410 e encerra o worker. Exclusões
  globais registram estado pendente antes da transação para evitar ressuscitar
  dados após restauração.

## Arquivos afetados

- Novos módulos em `src/application/services/web_backup.py`,
  `src/infrastructure/backup/`,
  `src/infrastructure/workers/maintenance_gate.py` e scripts
  `scripts/web_backup.py`, `scripts/web_restore_check.py`,
  `scripts/web_retencao.py`.
- Integração com runtime e exclusão global em
  `src/config/web_settings.py`, `src/face_worker_main.py`,
  `src/presentation/web/app.py`, `src/presentation/web/routes/gestao.py` e
  `src/web_main.py`.
- Testes em `tests/unit/test_web_backup_retencao.py`, ajustes em
  `tests/unit/test_web_fundacao.py` e teste opt-in
  `tests/integration/test_web_restore_local.py`.
- Exemplos em `ops/systemd/` e atualização dos documentos de operação,
  planejamento, contrato comum e índice de tarefas.

## Verificações executadas

Ambiente: `.venv-ml`, Python 3.14.3, Windows AMD64.

| Comando | Resultado |
|---|---|
| `.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider --basetemp "$env:TEMP\pytest-task017-unit-20261019"` | 1209 aprovados; 1 aviso de adapter datetime do SQLite; 23,65 s |
| `.venv-ml\Scripts\python.exe -m pytest tests/unit/test_web_backup_retencao.py tests/unit/test_web_fundacao.py -p no:cacheprovider --basetemp "$env:TEMP\pytest-task017-focused-final4-20261019"` | 41 aprovados; 1 aviso SQLite |
| `.venv-ml\Scripts\ruff.exe check src/config/web_settings.py src/face_worker_main.py src/presentation/web/app.py src/presentation/web/routes/gestao.py src/web_main.py src/application/services/web_backup.py src/infrastructure/backup src/infrastructure/workers/maintenance_gate.py scripts/web_backup.py scripts/web_restore_check.py scripts/web_retencao.py tests/unit/test_web_fundacao.py tests/unit/test_web_backup_retencao.py tests/integration/test_web_restore_local.py` | aprovado |
| `.venv-ml\Scripts\ruff.exe format --check src/config/web_settings.py src/face_worker_main.py src/presentation/web/app.py src/presentation/web/routes/gestao.py src/web_main.py src/application/services/web_backup.py src/infrastructure/backup src/infrastructure/workers/maintenance_gate.py scripts/web_backup.py scripts/web_restore_check.py scripts/web_retencao.py tests/unit/test_web_fundacao.py tests/unit/test_web_backup_retencao.py tests/integration/test_web_restore_local.py` | 19 arquivos formatados |
| `.venv-ml\Scripts\python.exe -m mypy src scripts` | aprovado, 153 arquivos-fonte |
| `.venv-ml\Scripts\python.exe -m pip check` | `No broken requirements found.` |
| `git diff --check` | aprovado |
| `.venv-ml\Scripts\python.exe -m pytest tests/integration/test_web_restore_local.py -p no:cacheprovider --basetemp "$env:TEMP\pytest-task017-restore-optin-20261019"` | 1 ignorado: opt-in de restore descartável não configurado |

Também foi confirmado que `rclone`, `pg_dump`, `pg_restore` e `psql` não estão
no PATH. A enumeração WSL foi negada pelo sistema (`E_ACCESSDENIED`). Não foi
possível fazer smoke real de cifra/restore nem validar locks PostgreSQL nesta
execução; os testes unitários usam SQLite em memória, fakes e dados sintéticos.

## Alternativa e dependências

Foi mantido o rclone crypt requerido no desenho, sem instalar dois fornecedores
de `cv2`, sem `--no-deps` e sem alterar metadados de pacotes. A investigação da
configuração de nomes está baseada na [documentação oficial do rclone crypt](https://rclone.org/crypt/).
Nenhum pacote Python foi adicionado; os requisitos CLI/ML não foram modificados.

## Ativação e rollback

Antes de operar, o administrador deve provisionar, fora do repositório, os
arquivos `pg_service` e `rclone.conf`, manter a custódia/recuperação da chave
separada da VPS e configurar caminhos absolutos privados e não sobrepostos nos
`WEB_*` descritos em `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`. Após instalar
`rclone` e ferramentas PostgreSQL compatíveis, executar primeiro backup manual
e restore em banco/volume marcados como descartáveis. O timer diário é apenas
um exemplo; sua instalação e a autorização OAuth/Drive são gates operacionais.
O dry-run de retenção deve ser revisado antes de qualquer `--apply`.

Rollback do código não exige migration: desativar o timer/serviço exemplo e
reverter os commits da tarefa. Não apagar arquivos de backup durante rollback;
preservar as chaves e arquivos até validar uma restauração independente.

## Limitações restantes

- Roundtrip local cifrado, `pg_dump`/`pg_restore`, validação de lock real e
  reaplicação de exclusões em PostgreSQL permanecem pendentes.
- Nenhuma conta/credencial Google foi conectada; cópia externa, OAuth e restore
  remoto não foram executados nem alegados.
- O backup local reside no mesmo host da aplicação e não protege contra perda
  total da VPS. A recuperação depende da custódia independente das chaves.
- Não houve validação visual, biométrica, com webcam ou rosto real.
- O estado é **parcial**, até executar a integração opt-in em ambiente
  PostgreSQL/rclone descartável e validar a restauração. A tarefa não autoriza
  implantação ou migração operacional.

## Adendo — fechamento 019A (19/10/2026)

A tentativa de fechamento revalidou o ambiente e confirmou que o roundtrip
cifrado continua sem execução: `rclone`, `pg_dump`, `pg_restore` e `psql` não
estão disponíveis no shell atual. O teste opt-in existente recebe uma geração
já preparada externamente e verifica o processo de restore; ainda não cria o
backup e compara conteúdo conhecido da origem e destino. Não houve alteração
no serviço de backup sem uma falha reproduzida. O critério de roundtrip real
permanece pendente; veja o [resultado 019A](../019a-fechamento-backend/RESULTADO.md).

## Adendo — roundtrip concluído na task 019A (19/10/2026)

Após autorização para usar containers e bancos descartáveis, a task019A executou
o fluxo real PostgreSQL/rclone crypt com dump, 2 referências sintéticas,
`cryptcheck`, restauração, hash de arquivo e comparação de registros conhecidos.
Exclusões posteriores ao snapshot foram reaplicadas; chaves/sessões restauradas
foram invalidadas. Chave incorreta, manifesto corrompido e destino sem marcador
foram recusados sem alterar dados/sentinela. A falha injetada liberou manutenção
e removeu staging em claro. O roundtrip local está comprovado; Google Drive,
OAuth, custódia operacional das chaves e dados reais continuam pendentes. Ver
[resultado final 019A](../019a-fechamento-backend/RESULTADO.md).
