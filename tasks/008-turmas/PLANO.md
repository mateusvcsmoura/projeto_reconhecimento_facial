# Plano executável — 008: turmas

> Executor **Luna 6 High**, com `superpowers:executing-plans` e princípios da skill migration. Executar no próprio agente, sem delegar ou reabrir desenho. Spec aprovada internamente: [DESENHO.md](DESENHO.md). Transição: [MIGRACAO.md](MIGRACAO.md).

**Objetivo:** CRUD de turmas, alunos N:N com matrícula global única, reconhecimento/presença no contexto selecionado e legado preservado.

**Stack:** existente; sem instalar dependências. Esta entrega produz código, migration, testes e documentação; aplicação do schema e testes que migram banco ficam pendentes de autorização explícita.

## 1. Baseline e contratos

- [ ] Ler AGENTS.md/CLAUDE.md/instructions/, arquitetura, resultados006–007 e pacote008. Registrar branch/HEAD/status; baseline preparado `6d56409`, main.
- [ ] Inspecionar referências de listar_referencias, cadastrar, registrar_se_ausente, listar_do_dia e uq_presencas_aluno_dia em src/scripts/tests. Mapear chamadas antes de alterar assinaturas.
- [ ] Conferir remoto/divergência conforme prompt, preservando trabalho alheio.
- [ ] Criar entidade pura `src/domain/entities/turma.py`, repositório Protocol `src/domain/repositories/turma_repository.py` e erros nomeados (turma inexistente/excluída, vínculo ausente/inativo). Testar período, matéria, identificadores e campos obrigatórios.

## 2. Schema e migration sem execução

- [ ] Alterar `src/infrastructure/database/models.py`; criar `migrations/versions/0004_turmas.py` após confirmar head. Implementar schema e guarda do downgrade especificados.
- [ ] Criar testes de metadados/SQL em `tests/unit/test_modelos_turmas.py`: PK/UK/FK/CHECK, índices parciais, nulabilidade apenas para legado, sem import do app ou conexão.
- [ ] Preparar `tests/integration/test_turmas_postgresql.py` e `tests/integration/test_migracao_turmas.py` com cenários de MIGRACAO.md. Não executá-los.
- [ ] Adaptar fixtures/BDD que dependem da constraint antiga e limpeza de tabelas; evitar SQL destrutivo automático em fixtures novas sem guardas explícitas de autorização.

## 3. Repositórios e atomicidade

- [ ] Criar PostgresTurmaRepository e casos de uso de CRUD/vínculo em `gerenciar_turmas.py`, com testes unitários usando fakes.
- [ ] Adaptar PostgresAlunoRepository: consultas por turma, lookup global explícito, cadastro de aluno+vínculo em uma transação; tratar corrida de matrícula via UK real.
- [ ] Adaptar PostgresPresencaRepository e DTO: turma_id explícito nas operações novas, consultas históricas sem filtro por vínculo ativo, deduplicação composta e transação de validação/INSERT.
- [ ] Usar ordem de locks consistente turma→vínculo para registro, exclusão lógica e desvinculação. Preparar testes reais concorrentes, sem alegar prova de concorrência com mocks.
- [ ] Manter métodos legados/admin explícitos, sem turma_id=None significando “todos” no caminho operacional.
- [ ] Adaptar import_legacy_sqlite para índice parcial e NULL; manter expurgo global. Atualizar testes do importador e schema afetados, sem executar importação real.

## 4. Casos de uso e proteção de biometria

- [ ] Cadastro exige turma ativa antes da câmera e novamente na transação final; preservar etapas validar/preparar/concluir007 e consentimento anterior à captura.
- [ ] Nome de imagem exclusivo por tentativa; falha do banco remove apenas arquivo dessa tentativa. Testar concorrência de matrícula sem sobrescrever/apagar imagem do aluno existente.
- [ ] Vincular matrícula existente não invoca storage/câmera/provider facial, não edita nome/embedding/consentimento e é idempotente. Registro sem consentimento não se torna reconhecível por vinculação silenciosa.
- [ ] Remover vínculo preserva aluno e presenças; reativar vínculo não duplica histórico. Excluir aluno global permanece ação distinta e preserva tratamento de falha na remoção do arquivo.
- [ ] ReconhecerAluno carrega apenas turma selecionada; limpa mapa/cache na troca. RegistrarPresenca recebe aluno_id + turma_id e revalida contexto no repositório.
- [ ] Testar dois alunos de turmas diferentes, um aluno em duas turmas, aluno removido durante captura e turma excluída durante captura; nenhum registro em contexto inválido.

## 5. CLI e composição

- [ ] Criar `src/presentation/cli/turmas.py`, adaptar menu.py/main.py e mensagens; implementar navegação do desenho com contexto explícito.
- [ ] Preservar captura automática007 e fallback manual: retorno vai ao menu da turma; troca de turma encerra sessão, limpa candidatos/contadores e recarrega referências.
- [ ] Turma sem referências informa antes de abrir câmera. Turma excluída permite somente histórico em tela própria.
- [ ] Confirmações negativas por padrão para desvincular/excluir turma/excluir aluno global, com efeitos descritos claramente. CRUD de matéria/período não requer câmera.
- [ ] Atualizar tests/fakes.py e testes de menus/composição/use cases: novos `test_turmas.py`, `test_menu_turmas.py`, `test_presenca_por_turma.py`, `test_reconhecimento_por_turma.py`, além de regressões001–007.

## 6. Verificação autorizada nesta etapa

- [ ] Executar testes unitários novos/afetados primeiro na `.venv-ml`, com `-p no:cacheprovider --basetemp` em diretório temporário exclusivo.
- [ ] Depois executar uma vez `.venv-ml/Scripts/python.exe -m pytest tests/unit` com mesmas opções e outro basetemp exclusivo.
- [ ] Executar Ruff em src/scripts/tests e migration nova, mypy, format --check nos arquivos Python alterados e git diff --check. Ajustar apenas problemas pertinentes.
- [ ] Inspecionar migration/SQL e links. Não executar Alembic online, testes de integração/BDD ou fixtures com banco. Não ler .env, subir serviços ou testar em dados reais.
- [ ] Se unitários dependerem indevidamente de banco, corrigir isolamento; não utilizar credenciais reais para fazê-los passar.
- [ ] Preparar roteiro de integração em PostgreSQL descartável para autorização posterior. Declarar explicitamente a ausência dessa prova; testes unitários não validam DDL/locks reais.

## 7. Documentar e publicar código preparado

- [ ] Criar `docs/TURMAS.md`: regras, menus, exclusão lógica, matrícula UK, vínculo N:N, dados legados, limites de período/matéria e autorização para migrar.
- [ ] Atualizar README.md/ARCHITECTURE.md, registro atual de evidências e AGENTS.md/CLAUDE.md somente no snapshot afetado; não marcar schema aplicado ou sistema operacionalmente validado.
- [ ] Criar `tasks/008-turmas/RESULTADO.md`: baseline, mudanças, testes executados, testes só preparados, migration não aplicada, riscos/pendências e estado de publicação. Atualizar índice para “código preparado; migração/integração pendentes” se esse for o estado real.
- [ ] Revisar staged por caminhos explícitos; commit PT-BR sugerido `feat: organiza alunos e presenças por turma`, sem Co-Authored-By, somente credenciais do solicitante. Push main conforme prompt.

Condição de parada desta etapa: código/migration/testes/documentos preparados e unitários/checks aprovados, publicação verificada, pendência de migração/integração declarada. **Não avançar para aplicação de banco ou declarar implantação concluída.**
