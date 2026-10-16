# Migração e resultado — 008

## Autorização e estado

No planejamento original, a migration e os testes destrutivos ficaram pendentes por falta de autorização explícita. Em 16/10/2026, o usuário autorizou a migration no banco do projeto e informou que ele ainda não está em uso. A autorização foi usada apenas para `upgrade head`; os testes que executam `TRUNCATE` continuam reservados a bancos descartáveis identificados.

## Resultado da aplicação

- Alvo configurado pelo `.env`: banco `escola`, PostgreSQL 18.6 em `localhost:5433`.
- Estado confirmado antes: revisão Alembic `0003`; tabela `presencas` com 0 linhas.
- Executado: `python -m alembic upgrade head` no ambiente `.venv-app`.
- Resultado: upgrade `0003 -> 0004` concluído; `alembic current` retornou `0004 (head)`.
- `alembic check`: `No new upgrade operations detected.`
- Verificação estrutural: tabelas `turmas` e `aluno_turma`, coluna anulável `presencas.turma_id`, constraints e índices criados.
- `presencas` permaneceu com 0 linhas. Nenhum dado foi excluído, `TRUNCATE` ou downgrade foi executado.
- Testes de integração/BDD não executados; eles exigem bancos descartáveis separados e incluem operações de limpeza.

Nenhuma dependência nova. Reutilizar SQLAlchemy, Alembic e PostgreSQL atuais. Não instalar/subir servidor, Docker ou ambiente adicional nesta task.

## Leitores e gravadores afetados

| Consumidor | Adaptação |
|---|---|
| Cadastro manual/automático | Aluno+vínculo na mesma transação SQL; turma obrigatória na UI |
| Vinculação | Reutilizar matrícula global; não salvar imagem/embedding |
| Reconhecimento | Galeria e mapa de IDs por turma ativa |
| Registro de presença | Verificar turma/vínculo ativos na transação; conflito por turma/aluno/dia |
| Consultas | Separar turma, turmas excluídas e legado sem turma |
| Importador SQLite | Escrever turma_id NULL e ON CONFLICT por índice parcial legado |
| Expurgo e exclusão global | Continuar abrangendo todas as turmas e registros legados |
| Fixtures/BDD | Incluir novas tabelas, constraints e ordem de limpeza; não executar neste estágio |

## Upgrade proposto

Uma revisão Alembic após 0003, sob transação PostgreSQL:

1. Criar turmas, vínculos e constraints/índices determinísticos.
2. Adicionar presencas.turma_id nullable, FKs simples/composta e índice por turma/data.
3. Criar UK turma/aluno/dia e UNIQUE parcial legado aluno/dia WHERE turma_id IS NULL.
4. Remover `uq_presencas_aluno_dia` apenas quando as substitutas já existirem. Alunos.matricula mantém sua UK original.
5. Sem UPDATE de dados para atribuir turmas, sem nova biometria, sem turma fictícia.

Compatibilidade: **a versão antiga do app/importador usa o nome da UK removida e não pode continuar escrevendo após o upgrade**. Não prometer operação simultânea entre versões. O banco local configurado já avançou para `0004`; em outros ambientes, parar escritores antigos e coordenar a atualização de schema e código.

Nenhuma migration no boot. Erro de schema incompatível deve orientar aplicação da versão correta pelo operador, sem auto-migrar.

## Rollback sem perda silenciosa

Downgrade automático permitido somente se não existir nenhuma turma, vínculo ou presença com turma_id preenchido. Se houver qualquer dado novo, abortar explicitamente antes de DDL destrutivo. Não achatar presenças de duas turmas em uma, não apagar turmas com histórico para “fazer downgrade funcionar”.

Quando vazio, recriar UK global antiga, remover FKs/índices novos e coluna/tabelas na ordem correta. Testar que dados legados sobrevivem e que a recusa de downgrade mantém schema/dados intactos. Rollback após uso real exige plano explícito de exportação/restauração e decisão do operador; backup antigo pode perder registros posteriores e não deve ser tratado como reversão sem perda.

## Evidências a preparar

Testes unitários de metadados/compilação SQL ajudam a revisar constraints, mas não substituem execução PostgreSQL. Criar testes de integração usando somente dados sintéticos para:

- 0003 com alunos/presenças sintéticos → upgrade → comparar IDs, matrículas, embeddings sintéticos, consentimentos e datas; turma_id permanece NULL.
- Matrícula duplicada em turmas diferentes viola UK global; vínculo repetido não duplica.
- Presença sem vínculo viola FK; presença com vínculo inativo é recusada pelo repositório; NULL só em caminho legado explícito.
- Mesma pessoa/dia em duas turmas é permitida; duplicação na mesma turma e duplicação legada são impedidas, inclusive concorrentes.
- Desvinculação e exclusão lógica preservam histórico; exclusão global remove vínculos/presenças; turma física referenciada não pode ser apagada.
- Cadastro e vínculo são atômicos em falhas; rollback não deixa aluno sem vínculo após tentativa nova.
- Concorrência entre presença e desvinculação/exclusão segue ordem de locks; testar com duas conexões, não só mocks.
- Importação legada repetida continua idempotente; expurgo cobre registros com/sem turma.
- Downgrade em banco apenas legado preserva tudo; com dados novos recusa sem alterações parciais.

Não reutilizar cegamente a fixture que executa downgrade base na entrada. Preparar fixture específica para migração em banco descartável; impedir execução se não houver sinalização explícita de ambiente de teste. Nunca considerar só nome de variável/URL diferente como prova de que o banco pode ser destruído.

RESULTADO.md deve separar: revisão estática; unitários efetivamente executados; migration aplicada ao banco local; integração/BDD ainda não executada. Não chamar skips de testes aprovados.
