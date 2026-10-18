# FaceDiff web — contrato de transição de schema

Planejamento complementar às tasks 009–020. **Nenhuma migration será executada
na geração dos pacotes.** Escrever revision/testes é diferente de executar SQL.

## Autorização explícita vigente

Em 18/10/2026, o usuário autorizou executar migrations e testes que escrevam em
bancos de desenvolvimento/teste do projeto, inclusive reset e seed sintético
quando necessário. O projeto ainda não está em uso e não há dados importantes.
Esta autorização cobre a validação das migrations `0005` da task 010, `0006` da
task 011 e `0007` da task 012 em bancos descartáveis. Antes de cada escrita,
confirmar host, nome e marcador do destino; preferir banco
descartável para testes. Ela não abrange produção, banco remoto/compartilhado
ou uso de imagens biométricas reais. O `DATABASE_URL` local existente pode ser
usado apenas para identificar/conectar ao banco de desenvolvimento após
confirmar host e nome; não usá-lo como fallback para variáveis `WEB_*` nem
exibir credenciais.

## Estado confirmado por inspeção

O repositório contém as revisões 0001–0007. A revisão `0005` da task 010 foi
compilada offline e aplicada ao banco local `escola` em 18/10/2026; `alembic
check` não detectou drift. O módulo de integração PostgreSQL passou 3 testes no
banco descartável `task010_web_auth_test_20261018`; a fixture limpou os dados e
reverteu o schema a `base`. A revisão `0006` da task 011 foi aplicada, validada
com `alembic check` e revertida pela fixture no banco descartável
`task011_web_references_test_20261018`; 3 testes PostgreSQL passaram. O banco
local `escola` não recebeu a revisão `0006`. `models.py` mantém alunos com embedding único,
turmas, vínculos N:N e presença única turma/aluno/dia. `AGENTS.md` e
`ARCHITECTURE.md` registravam a revisão 0004 antes desta execução.
`0005` acrescenta contas/perfis, sessões, rate limit, auditoria e responsável
nullable por turma legada; consulte `docs/FACEDIFF-WEB-AUTH.md`.
CLAUDE contém trechos históricos divergentes; não presumir estado de outro banco.

A revisão `0007` da task 012 foi migrada até `head`, verificada com `alembic
check` e revertida a `base` pela fixture PostgreSQL no banco descartável local
`task012_web_worker_test_20261018`, identificado pelo comentário
`projeto_reconhecimento_facial: task 012 disposable worker database`. Quatro
testes PostgreSQL passaram. O banco `escola` não recebeu `0006` nem `0007`.

## Donos das expansões

| Task | Expansão esperada |
|---|---|
| 010 | Conta/professor, sessão de autenticação, auditoria e responsável por turma |
| 011 | Solicitação, conjunto/referências versionadas e consentimento/estado web (`0006`, validada em banco descartável) |
| 012 | Jobs/reservas/leases da fila, índices de admissão e idempotência |
| 013 | Estado persistente de desafio quando não coberto por job/solicitação |
| 014 | Link/credencial efêmera e associação de solicitações ao convite |
| 015 | Sessão de presença, tentativa/quota e novo ramo de presença por sessão |
| 016 | Revisão/correção/status/versão de presença, se não criados antes |

Inspecionar head real a cada execução; não criar números fixos conflitantes nem
uma segunda tabela para entidade já entregue. Não modificar silenciosamente
revisão já aplicada. Documentar relacionamento de campos criados em fases
anteriores que só ganham FK/validação completa depois.

## Preservação e compatibilidade

- Matrícula UK global permanece; aluno/turma N:N e períodos atuais preservados.
  Matrícula continua string com zeros à esquerda; não converter para inteiro.
- Responsável de turma pode ser nulo só no legado em transição. Novas turmas
  web exigem responsável; legado sem dono não aparece ao professor. Nenhum
  professor fictício criado por migration.
- Manter foto/embedding legado para CLI enquanto existir esse consumidor;
  novo conjunto de três referências pertence à web. Não triplicar referência
  única nem recalcular dados reais durante upgrade. Schema expandido primeiro,
  limpeza de colunas somente em tarefa futura expressa.
- Solicitação pública não reserva matrícula; a aprovação revalida unicidade e,
  se o aluno já existe, preserva nome, foto e embedding globais e cria apenas o
  vínculo autorizado. O conjunto novo só fica ativo para aluno recém-cadastrado.
- Cada conjunto contém exatamente três ordinais e metadados de modelo/consentimento;
  o índice parcial admite no máximo um conjunto ativo por aluno. Troca aprovada
  desativa a versão anterior atomicamente. A limpeza provisória é auditada e
  repetível após falha de remoção de arquivo.
- `presencas.sessao_id` nulo representa legado; web exige sessão. Remover UK
  diária global do ramo web e substituir por índices parciais adequados:
  `(turma_id,aluno_id,data_referencia)` somente `sessao_id IS NULL AND turma_id
  IS NOT NULL`; legado sem turma mantém `(aluno_id,data_referencia)` somente
  `sessao_id IS NULL AND turma_id IS NULL`; ramo web exige UK aluno/sessão.
- Reavaliar FK composta: presença web deve referenciar sessão da mesma turma e
  vínculo aluno/turma; checagem de vínculo ativo é transacional. Se manter
  turma_id redundante, garantir consistência via FK/constraint, não só UI.
- `on_conflict` diário atual referencia constraint por nome. Migrar código e
  índice parcial em conjunto; atualizar caminho da CLI/importador e testes. Não
  prometer que versões antigas continuam escrevendo com constraint removida.
- Não fabricar sessões para histórico. Não misturar faltas inferidas, registros
  manuais e confirmações biométricas. Auditoria não deve ser apagada por cascata
  acidental nem reter biometria excluída; prever minimização por política.

## Testes e execução

1. Testes unitários de metadados/SQL e guardas podem rodar sem conexão.
2. Preparar banco descartável identificado, credenciais exclusivas e autorização
   explícita. Proibir uso de DATABASE_URL operacional e destinos não marcados.
3. Só nessa etapa autorizada: upgrades em banco vazio e com fixtures sintéticas
   legadas, integridade, rollback protegido e concorrência de transações.
4. Validar CLI/repositórios atuais contra schema expandido e comportamento web
   contra novas constraints. Mock de session não prova lock real.
5. Downgrade deve recusar antes de perder sessões/referências/auditoria novas;
   documentar restauração de backup e rollback de aplicação quando reversão SQL
   sem perda não for possível. Nunca remover dados apenas para permitir downgrade.

## Implantação futura

Base nova de demonstração é recomendada, sem importar banco local/biometria.
Implantação exige backup consistente, parada coordenada de escritores, migration
explícita, verificação e troca de versão. Nada de `create_all`/upgrade no boot.
Não executar este procedimento porque uma task contém a palavra migration.
