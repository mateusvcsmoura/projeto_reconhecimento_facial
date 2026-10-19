# Resultado — tarefa 016: gestão, revisão manual e CSV

Estado: **concluída**. Implementação, gates locais e validação PostgreSQL
descartável foram concluídos. A migration `0011` também foi aplicada ao banco
local de desenvolvimento `escola`; isso não representa deploy.

## Diagnóstico e solução

O repositório já continha autorização, turmas, vínculos, sessões, tentativas,
presenças biométricas e auditoria das tarefas anteriores. Faltavam operações
de gestão web, correção transacional de presença, fluxo de revisão, painel
agregado, exportação CSV e estado versionado persistente. A migration `0011`
é necessária para esses estados. A solução estende os contratos existentes,
reutiliza a autenticação da tarefa 010 e conecta novas rotas/use cases ao
composition root. A consulta existente `GET /api/v1/turmas/{id}` foi mantida
em seu endpoint original e delegada ao novo repositório quando configurado,
evitando uma rota duplicada.

## Implementação

- CRUD autorizado de turmas e vínculos N:N; exclusão lógica preserva o histórico.
- Exclusão global de aluno somente para admin, com confirmação, justificativa
  e auditoria mínima. Limpeza de arquivos acontece após o commit; falha é
  exposta como `limpeza_pendente`.
- Revisão pública exige bearer de link ativo associado à turma/sessão; só
  retorna protocolo e estado. Revisão acessível pode ocorrer antes do limite;
  há no máximo uma solicitação aberta por aluno/sessão.
- Decisão de professor exige identidade conferida independentemente,
  justificativa e versão esperada. Presença manual, decisão, incremento de
  versão e auditoria são transacionais. A falha biométrica não gera presença.
- Locks e revalidação de estado protegem contra resultado tardio do worker;
  reativação da quota é exclusiva de admin e auditada.
- Painel agregado respeita autorização e fornece `atualizado_em`. CSV UTF-8
  aplica intervalo inclusivo no fuso local, neutraliza fórmulas e não inclui
  biometria, tokens, score, justificativas ou faltas inferidas.
- Migration `0011_gestao_revisao_presencas.py` amplia os metadados de presença,
  registra estado biométrico preexistente, cria revisões versionadas e permite
  registrar reativações de quota. Downgrade protege contra perda de dados novos.
- O PostgreSQL confirmou a estrutura da revisão; numa corrida real, o worker
  aguardou o lock da sessão e não persistiu presença depois que a revisão aberta
  foi confirmada. O downgrade `0011 -> 0010` foi recusado com a revisão existente,
  e o teste confirmou que a linha e a revisão Alembic permaneceram intactas.

Não houve alteração dos embeddings FaceNet512, do MiniFASNet, do threshold
operacional `0.30` nem das decisões biométricas. O operador confirmar a
identidade é uma afirmação auditada para correção manual, não uma validação
biométrica. Nenhuma interface visual foi criada.

## Arquivos alterados

Código de domínio, use cases, repositório e rotas de gestão; composição da
aplicação; modelo de presença/revisão; checagens do worker; migration `0011`;
testes unitários e PostgreSQL de rotas, repositório, concorrência e limpeza
protegida de arquivos. Os contratos e a documentação estão em
[FACEDIFF-WEB-GESTAO.md](../../docs/FACEDIFF-WEB-GESTAO.md).

## Validação executada

- Suíte completa com cobertura: **1.209 passed, 80 skipped**, cobertura total
  **80,23%** (limite: 80%).
- Ruff nos arquivos alterados: aprovado.
- Ruff format check nos arquivos alterados: aprovado.
- Mypy em `src` e `scripts`: aprovado, sem problemas em 142 arquivos.
- `git diff --check`: aprovado.
- PostgreSQL descartável `task016_gestao_test_20261018`: **2 testes passaram**;
  a fixture aplicou a cadeia até `0011`, executou `alembic check`, conferiu o
  schema e o lock/concorrência do worker, comprovou a recusa segura de downgrade
  com revisão aberta, limpou os dados sintéticos e reverteu o schema a `base`.
- Banco local `escola`: estava em `0005`; `alembic upgrade head` aplicou `0006`
  a `0011`. A conferência posterior confirmou a revisão `0011` e tabela de
  revisões presente; `alembic check` retornou `No new upgrade operations detected`.
- Os diretórios `__pycache__` sob `tests` foram removidos porque bytecode pytest
  compilado no caminho antigo `C:\Users\User\Documents\...` fazia o plugin BDD
  procurar `.feature` fora do workspace `D:`. Os fontes e os arquivos `.feature`
  não foram alterados.

Comando da suíte completa:

```powershell
.venv-ml\Scripts\python.exe -m pytest --cov=src --cov=scripts.metricas --cov=scripts.divisao_por_identidade --cov=scripts.evaluate_model --cov=scripts.calibrar_limiar --cov-report=term-missing --cov-fail-under=80 -p no:cacheprovider --basetemp "$env:TEMP\pytest-task016-full-final-20261019"
```

O teste PostgreSQL focado foi executado com as variáveis de opt-in da fixture;
a URL foi derivada em memória de `.env` e direcionada ao banco descartável com
nome e comentário verificados, sem exibir credenciais. A suíte geral não abriu
conexão de banco nem executou esses testes opt-in. Não houve webcam, imagens ou
biometria de pessoas.

Comando focado (as duas variáveis da fixture foram preparadas em memória para o
banco descartável):

```powershell
.venv-ml\Scripts\python.exe -m pytest tests/integration/test_revisao_csv_web.py -p no:cacheprovider --basetemp "$env:TEMP\pytest-task016-pg-final-20261019"
```

Para o banco local, `alembic upgrade head` foi executado com
`ALEMBIC_DATABASE_URL` derivada em memória de `DATABASE_URL` do `.env`, depois
de confirmar `localhost:5433`, banco `escola` e revisão `0005`. Em seguida,
`alembic check` foi executado contra o mesmo alvo.

## Dependências, limitações e operação

Nenhuma dependência Python nova. `0011` está aplicada ao banco de desenvolvimento
local `escola`, junto das revisões pendentes `0006–0010`, e validada no banco
descartável da tarefa. Outros ambientes ainda precisam de migração própria e
`alembic check`; não houve deploy ou alteração de banco remoto/compartilhado.

A remoção de imagem legada/temporários ocorre após commit. Se o armazenamento
falhar, o endpoint informa `limpeza_pendente=true`; não há fila durável de retry
para esses caminhos, então a limpeza precisa de reconciliação operacional. A
validação visual de interfaces e operação na VPS não faz parte desta tarefa.

Ativação: configurar banco web já migrado até `0011`, autenticação, raízes
privadas e `WEB_LEGACY_IMAGE_STORAGE_DIR` quando houver imagens legadas no
storage configurado. Rollback de código exige primeiro confirmar ausência de
revisões, correções, presenças manuais e reativações novas; o downgrade recusa
remover esses dados. Não executar rollback destrutivo automático.

## Publicação

Os commits anteriores de implementação e documentação já estão em `main`. Esta
validação atualiza os testes de integração e os registros de status; não houve
deploy.
