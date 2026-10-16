# Turmas, vínculos e presenças

## Estado da entrega

O código da tarefa 008 prepara a navegação por turma, o vínculo N:N, o
reconhecimento filtrado e a presença por turma. A revisão Alembic `0004` foi
criada depois de `0003`, mas **não foi aplicada** nesta etapa. A integração com
PostgreSQL também está pendente de autorização e de execução em banco
descartável identificado. O commit e o push do código não aplicam schema nem
liberam o sistema para uso no banco atual.

O aplicativo que está no workspace exige o schema `0004` quando acessa o menu
de turmas. Antes da aplicação autorizada da migration, não execute essa versão
contra o banco operacional.

## Regras do modelo

- `Turma` tem matéria obrigatória, normalizada entre 1 e 120 caracteres, e
  período exatamente `matutino`, `diurno` ou `noturno`. O ID distingue turmas
  com a mesma matéria e período.
- `Aluno` continua global. Matrícula permanece única no sistema; biometria e
  consentimento ficam no cadastro global. Um aluno pode ter vínculos ativos em
  várias turmas.
- Vincular um aluno existente reutiliza a matrícula e não captura, grava ou
  altera imagem, embedding, nome ou consentimento. Sem consentimento registrado,
  o vínculo que habilitaria o reconhecimento é recusado.
- Remover um aluno de uma turma desativa apenas o vínculo. O aluno, a biometria,
  os outros vínculos e as presenças históricas permanecem. Excluir o aluno do
  sistema é uma ação global separada, com confirmação explícita.
- Excluir turma é lógico: a turma deixa de aceitar operações, mas alunos,
  vínculos e histórico ficam preservados para consulta.
- Uma presença nova é única por turma, aluno e dia no fuso `APP_TIMEZONE`.
  Presenças antigas ficam com `turma_id = NULL`, sem turma ou contexto
  inventados, e continuam consultáveis como legado.

## Navegação

O menu principal cria turma, lista e seleciona uma turma ativa, abre o histórico
de turmas excluídas, oferece administração global (exclusão global de aluno e
consulta de legado) e encerra o programa. Não há caminho operacional de
reconhecimento global.

Dentro de uma turma ativa, as opções cadastram um aluno novo, vinculam matrícula
existente, listam os vinculados, reconhecem e registram presença, consultam
presenças por dia, removem um vínculo, atualizam matéria/período, excluem a
turma logicamente ou retornam ao menu principal. O reconhecimento carrega a
galeria filtrada no SQL por turma e vínculo ativos; não usa fallback global.
Ao sair da turma, o mapa de referências é limpo. Cadastro automático 007,
fallback manual, worker local de landmarks 006, limiar `0.30` e anti-spoofing
continuam nos mesmos fluxos. A presença ainda revalida turma e vínculo dentro
da transação que grava.

## Schema legado e migration

A migration adiciona `turmas` e `aluno_turma`, acrescenta `presencas.turma_id`
nullable, cria a FK composta para o vínculo, a unicidade
`(turma_id, aluno_id, data_referencia)` e um índice único parcial para o legado
(`aluno_id, data_referencia WHERE turma_id IS NULL`). A UK global
`uq_alunos_matricula` permanece. Não há atualização de linhas antigas para
atribuir uma turma.

O importador SQLite grava `turma_id = NULL` e usa o índice parcial para manter
a idempotência. O expurgo segue global e inclui presenças de turmas ativas,
excluídas e legado.

O cadastro novo grava aluno e vínculo na mesma transação SQL. Cada tentativa
usa nome de arquivo exclusivo; se a transação falha, a compensação remove
somente o arquivo daquela tentativa. Essa compensação não transforma o
filesystem em parte da transação e não oculta a falha original.

## Aplicação futura e proteção dos testes

A aplicação da migration depende de autorização específica em etapa separada.
O procedimento futuro exige backup validado, parada dos escritores antigos,
aplicação coordenada do schema e disponibilização do novo código. O app e o
importador antigos nomeiam a constraint removida `uq_presencas_aluno_dia`; as
duas versões não podem gravar simultaneamente após o upgrade.

Os testes de integração existentes foram protegidos para não ler `.env` nem
destruir bancos por engano. Eles só obtêm uma URL por variáveis de ambiente,
exigem o opt-in literal abaixo e validam um `COMMENT ON DATABASE` antes de
qualquer migration ou `TRUNCATE`:

```powershell
$env:FACE_TURMAS_TEST_DB_AUTORIZACAO = "AUTORIZO_DESTRUIR_BANCO_DESCARTAVEL_TASK_008"
$env:FACE_TURMAS_TEST_DATABASE_URL = "postgresql+psycopg://.../escola_test"
```

O banco de integração deve ter este comentário, aplicado manualmente somente
depois de identificado como descartável:

```sql
COMMENT ON DATABASE escola_test IS
  'projeto_reconhecimento_facial: task 008 disposable test database';
```

Os testes da migração usam um segundo banco fisicamente separado:

```powershell
$env:FACE_TURMAS_MIGRATION_DATABASE_URL = "postgresql+psycopg://.../escola_migration_test"
```

O nome diferente da URL, isoladamente, não é uma confirmação de segurança: o
fixture confere o marcador do próprio banco e a identidade PostgreSQL dos dois
bancos antes de DDL. Sem essas variáveis, os testes ignoram a integração; esse
skip não conta como validação. Nenhuma dessas variáveis foi configurada nem
nenhuma conexão foi aberta nesta entrega.

Depois de autorização, a revisão deve incluir migração de snapshot `0003`,
preservação de IDs e linhas legadas, vínculos N:N, concorrência entre registro
e desvinculação, integridade por turma e a guarda do downgrade. O smoke
sintético e os testes unitários não substituem essa prova PostgreSQL nem uma
validação visual com pessoa real.

## Rollback

O downgrade automático restaura a constraint global antiga somente quando não
há turmas, vínculos ou presenças associadas a turma. Ao encontrar qualquer um
desses dados, ele recusa antes de executar DDL destrutivo. Depois que houver
dados de turma, rollback exige plano explícito de exportação e decisão do
operador; não se deve achatar presenças entre turmas nem remover histórico para
forçar o downgrade.
