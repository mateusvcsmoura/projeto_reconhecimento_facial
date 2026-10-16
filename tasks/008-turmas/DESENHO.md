# Desenho — 008: turmas, vínculos de alunos e presença por turma

**Executor: Luna 6 High. Estado: planejamento; implementação pendente.** Desenho aprovado internamente conforme AGENTS.md. Base inspecionada em 16/10/2026: main, `6d56409`; tarefa007 implementada. Nesta preparação não foram executados testes, migrations ou acesso a dados reais.

## Requisitos e decisões

O usuário solicita CRUD de Turma, com `periodo` e `materia` obrigatórios, e cadastro, reconhecimento, exclusão e consulta de presenças de alunos no contexto de uma turma. Confirmou explicitamente que **um aluno pode participar de várias turmas**.

- Aluno continua global: uma matrícula, um cadastro facial, uma identidade e consentimento registrado. Preservar `uq_alunos_matricula` e sua semântica atual; não substituir por unicidade composta com turma, nem mudar normalização/case da matrícula nesta tarefa.
- Turma e Aluno têm relação N:N, por tabela de vínculo. Vincular aluno existente não recaptura biometria nem cria outro Aluno.
- Presença passa a ser única por **turma + aluno + dia**, no APP_TIMEZONE atual. O mesmo aluno pode ter presença em duas turmas no mesmo dia. Não introduzir sessões/aulas/horários nesta entrega.
- Período aceita exatamente `matutino`, `diurno` ou `noturno`. Não trocar diurno por vespertino. Matéria é texto obrigatório, espaços normalizados, 1–120 caracteres. Não criar entidade Matéria nem exigir nome/código extra para a turma. Identificar na UI por ID + matéria + período.
- Não impor unicidade matéria/período: podem existir turmas distintas da mesma matéria e período. O ID as distingue.
- “Remover aluno da turma” desativa apenas o vínculo e mantém histórico, biometria e outros vínculos. “Excluir aluno do sistema” continua como operação global explícita, com confirmação informando alcance; preserva a remoção de imagem/embedding/presenças existente.
- Exclusão de turma é lógica (`excluida_em`): sai das operações ativas, mas histórico permanece consultável. Não apaga alunos nem suas presenças. A UI deve explicar isso antes da confirmação. Não adicionar restauração nesta entrega.

## Estado atual e impacto

`models.py` tem apenas alunos e presencas; a UK de presenças é `uq_presencas_aluno_dia`. Repositórios/listagens/reconhecimento são globais. A referência de matching é carregada ao iniciar a câmera e cacheada em ReconhecerAluno. Cadastro007 separa validar/preparar/concluir e é automático por padrão. A006 usa worker MediaPipe isolado; preservá-lo.

O importador `scripts/import_legacy_sqlite.py` usa ON CONFLICT com o nome da UK atual; precisa adaptação junto da migration. O expurgo de presenças é global por data e deve continuar cobrindo turmas excluídas e histórico legado. Fixtures de integração fazem downgrade/upgrade e TRUNCATE: não executá-las inadvertidamente no ambiente atual.

## Modelo persistente

| Tabela | Campos e regras |
|---|---|
| `turmas` (nova) | id bigint identity PK; materia varchar(120) NOT NULL, CHECK trim não vazio; periodo varchar(10) NOT NULL com CHECK IN dos três valores; criado_em/atualizado_em timestamptz NOT NULL; excluida_em timestamptz NULL |
| `aluno_turma` (nova) | turma_id + aluno_id PK composta; FKs para turmas (RESTRICT físico) e alunos (CASCADE); ativo boolean NOT NULL default true; vinculado_em timestamptz NOT NULL; desvinculado_em NULL; CHECK coerência ativo/data de desvínculo; índice por aluno_id para consultas reversas |
| `alunos` | Preservar PK, UK global da matrícula, biometria e consentimento |
| `presencas` | Acrescentar turma_id nullable para histórico legado; FK turma RESTRICT físico; FK composta (turma_id, aluno_id) para vínculo, ON DELETE CASCADE, MATCH SIMPLE; preservar FK aluno CASCADE; nova UK (turma_id, aluno_id, data_referencia); índice (turma_id, data_referencia) |

Com turma_id NULL, a FK composta não exige vínculo (somente legado). Para evitar duplicatas legadas, criar também índice UNIQUE parcial `(aluno_id, data_referencia) WHERE turma_id IS NULL`. Nome sugerido `uq_presencas_legado_aluno_dia`. Para registros novos, UK `uq_presencas_turma_aluno_dia`.

Não manter a UK global antiga, pois bloquearia duas turmas no mesmo dia. Nenhuma tabela extra para embeddings por turma. Na remoção de vínculo, atualizar ativo/desvinculado_em; não deletar a linha, pois ela ancora histórico. Reativar a mesma linha em nova vinculação, com data de vínculo renovada e desvinculado_em NULL. Não prometer auditoria completa de todos os intervalos de participação.

Exclusão global de Aluno continua removendo seus vínculos e presenças por cascata, incluindo legado; testar as FKs e cascatas reais. Exclusão lógica de turma não altera vínculos fisicamente: consultas de ativos exigem turma não excluída e vínculo ativo. Histórico de presença não filtra vínculo ativo.

## Navegação

Menu principal: criar turma; listar/selecionar turma; consultar turmas excluídas (somente leitura/histórico); administração de alunos/histórico legado; sair.

Dentro da turma ativa, cabeçalho permanente com ID/matéria/período e ações:

1. Cadastrar novo aluno nesta turma — coleta dados/consentimento e usa captura007.
2. Vincular aluno existente por matrícula — mostra identidade e confirmação; sem câmera, sem editar cadastro global. Se já ativo, informar idempotentemente. Cadastro sem consentimento registrado não pode ser habilitado para reconhecimento por essa ação: bloquear com orientação, sem inventar consentimento.
3. Listar alunos vinculados ativos e situação do embedding.
4. Reconhecer/registrar presença nesta turma — automático007 ou manual configurado.
5. Consultar presenças da turma por dia (hoje por padrão), incluindo pessoas posteriormente desvinculadas.
6. Remover aluno da turma — confirmação explícita, sem apagar cadastro global/histórico.
7. Atualizar matéria/período — validações idênticas à criação, sem alterar vínculos/presenças.
8. Excluir turma — explicar preservação do histórico; confirmação negativa por padrão; voltar ao menu principal após sucesso.
9. Voltar/trocar turma.

Administração global é caminho separado para localizar/excluir aluno integralmente (inclusive aluno sem turma) e consultar presenças antigas “Sem turma — legado”. Não oferecer reconhecimento global pelo fluxo operacional novo. Não criar cadastros novos sem turma pela UI.

Ao tentar cadastrar matrícula existente, não capturar foto nem sobrescrever dados; orientar a ação “Vincular aluno existente”. Vinculação operacional não autoriza uso experimental. Mensagens de exclusão nunca devem confundir desvinculação, exclusão lógica de turma e eliminação global do aluno.

## Escopo de reconhecimento e transações

Todos os casos de uso operacionais recebem `turma_id` explicitamente (keyword-only recomendado). Não usar variável global ou último ID implícito. A ausência de turma nunca deve cair silenciosamente em consulta global. Métodos administrativos/legados têm nomes separados.

`listar_referencias(modelo, *, turma_id)` filtra no SQL turma ativa e vínculo ativo, preserva filtro de modelo e não carrega embeddings de outras turmas. ReconhecerAluno limpa seu mapa ao carregar outra turma; matriz e sessão pertencem a um único turma_id. Não reutilizar candidato, contador temporal ou sequência automática na troca de turma. Captura007 retorna ao menu da turma após concluir.

Filtrar galeria altera a população comparada; não implica acurácia melhor e não permite reconhecer como pertencente à turma alguém que não pertence. Testar especialmente candidatos de fora e troca de turma.

Antes de cadastrar/vincular/remover/atualizar/excluir, validar turma existente/ativa. Validação deve ocorrer novamente no limite da transação, e não só ao mostrar menu. Para novo aluno, INSERT do aluno e INSERT do vínculo precisam de **uma transação SQL**, nunca duas chamadas com commits independentes. Estender repositório de cadastro para realizar essa unidade atomicamente; não abrir transação no domínio/UI.

Storage não participa da transação SQL. Evitar sobrescrever foto existente em corrida de matrícula: gerar nome de arquivo exclusivo por tentativa de novo cadastro. Se transação falhar, remover somente arquivo criado pela tentativa, nunca imagem de cadastro preexistente. Falha de limpeza é reportada; não mascarar a causa principal nem declarar rollback integral de filesystem/banco. Não regravar imagem ao vincular aluno existente.

Registrar presença exige turma ativa e vínculo ativo **na mesma transação do INSERT**, mesmo se o aluno foi reconhecido segundos antes. Serializar alterações concorrentes com locks de turma e vínculo em ordem única (turma primeiro, vínculo depois), usada por exclusão de turma/desvinculação/registro. Isso define uma ordem válida entre presença e desvinculação; se remoção vence primeiro, registro é recusado. Manter ON CONFLICT para deduplicar; False significa somente presença já existente, não turma inválida ou aluno desvinculado. Traduzir violações de contexto em erros de domínio distintos.

## Contratos e arquivos

- Criar `src/domain/entities/turma.py` com Turma/Periodo, validações puras e vínculo/DTO se necessário. Domínio sem SQLAlchemy.
- Criar `src/domain/repositories/turma_repository.py`, `src/infrastructure/repositories/postgres_turma_repository.py` e `src/application/use_cases/gerenciar_turmas.py` (CRUD e vínculo/desvínculo).
- Alterar models.py e repositórios de Aluno/Presenca: escopo explícito, atomicidade, índices/FKs, consultas administrativas separadas. DTO de presença deve identificar turma ou legado; não perder nome/matrícula/instante.
- Alterar cadastrar_aluno.py, reconhecer_aluno.py, registrar_presenca.py e consultar.py para contexto de turma; preservar validar/preparar/concluir007 e imagem original. ExcluirAluno global continua distinto de remover vínculo.
- Criar `src/presentation/cli/turmas.py` para navegação/CRUD; adaptar menu.py, orquestração automática existente e main.py. Não duplicar loops de câmera por turma.
- Atualizar erros/mensagens, fakes, testes e scripts consumidores afetados; inspecionar chamadas com rg antes de mudar assinaturas.
- Não mudar worker006, matching, limiar0.30, antispoofing, configurações temporais/automáticas ou dependências.

## Migração e compatibilidade

Criar `migrations/versions/0004_turmas.py`, revisando head real antes. Não editar 0001–0003. **Preparar o arquivo não autoriza executá-lo em banco algum nesta task.** Procedimento e gates em [MIGRACAO.md](MIGRACAO.md).

Dados existentes: alunos permanecem globais sem vínculo até seleção explícita do operador; presenças existentes mantêm IDs, datas, aluno_id e turma_id NULL. Não criar turma fictícia com período/matéria inventados nem inferir atribuição histórica. Importador legado preserva NULL e usa índice parcial correspondente para idempotência.

Atualização de matéria/período afeta o rótulo exibido no histórico da turma; não há versionamento desses atributos nesta entrega. Documentar. Retenção/expurgo existentes continuam globais; exclusão lógica não significa retenção ilimitada.

## Aceite

CRUD e menus funcionais; N:N sem duplicar aluno/biometria; UK matrícula preservada; consulta/matching/presença limitados à turma; duas turmas permitem duas presenças no mesmo dia; repetição na mesma turma é idempotente; remoção/exclusão não perde dados de outras turmas; legado preservado; captura007 e worker006 não regridem.

Provar com testes sintéticos e, quando explicitamente autorizado em etapa separada, PostgreSQL descartável. Sem executar migrations, declarar validação de integração pendente e não anunciar sistema pronto para uso no banco atual. Commit/push de código/documentos não são deploy nem autorização para migrar.
