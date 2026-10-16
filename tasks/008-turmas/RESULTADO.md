# Resultado — tarefa 008: turmas

## Estado

**Código implementado e publicado na `main`; migration `0004` preparada, mas
não aplicada; validação PostgreSQL/BDD pendente.** O código desta revisão
requer o schema `0004` para abrir as operações de turma. Portanto, o push do
código não representa implantação nem autorização para conectá-lo ao banco
operacional.

## Diagnóstico e decisão

O modelo anterior vinculava uma presença diretamente ao aluno e impunha uma
única presença por aluno/dia. Isso não representava várias turmas por aluno e
impedia duas presenças legítimas em turmas diferentes no mesmo dia. A solução
mantém a matrícula globalmente única, adiciona vínculo N:N e leva o contexto
da turma até consulta, galeria, cadastro e transação que registra presença.

A revisão Alembic `0004` sucede `0003`. Ela cria `turmas` e `aluno_turma`,
adiciona `presencas.turma_id` anulável, mantém as presenças antigas sem
atribuir turmas fictícias e substitui a unicidade global por uma regra por
turma mais um índice parcial para o legado. O downgrade verifica dados de
turma antes de qualquer DDL destrutivo e recusa quando os encontra.

Não foi criada dependência nem escolhida biblioteca alternativa. A implementação
reutiliza os repositórios, casos de uso, captura automática 007 e worker visual
006 existentes. A integração com banco não foi executada porque o prompt desta
tarefa proibiu conexões e migrations nesta etapa.

## Comportamento entregue

- Menu principal para criar/listar/selecionar turmas, consultar histórico de
  turmas excluídas e acessar administração global separada.
- Menu de turma ativa com cadastro, vínculo por matrícula global, listagem,
  reconhecimento/presença, consulta, desvinculação, edição, exclusão lógica e
  retorno ao menu principal.
- Aluno pode participar de mais de uma turma; vínculo de aluno existente não
  recaptura nem modifica imagem, embedding, nome ou consentimento. Cadastro novo
  grava aluno e vínculo na mesma transação SQL e usa imagem temporária exclusiva
  por tentativa para compensação restrita.
- Galeria filtrada no PostgreSQL pela turma e pelos vínculos ativos; não há
  fallback para reconhecimento global. Trocar ou sair da turma limpa o
  contexto local de referências e confirmação.
- Presença nova valida turma e vínculo na transação e é única por turma/aluno/
  dia. Desvincular preserva aluno e histórico; excluir turma é lógico; excluir
  aluno global permanece uma operação separada.
- O importador legado grava `turma_id = NULL` e usa a regra de conflito parcial;
  expurgo e exclusão global seguem cobrindo registros de todas as turmas e o
  legado.
- Os erros da nova área têm mensagens ao operador. O fluxo preserva limiar
  `0.30`, embeddings, consentimento, anti-spoofing, captura automática e seu
  fallback manual; landmarks continuam apenas visuais.

## Arquivos modificados

- **Domínio e aplicação:** `src/domain/entities/turma.py`,
  `src/domain/repositories/turma_repository.py`, `src/domain/errors.py`,
  `src/application/use_cases/gerenciar_turmas.py` e casos de uso de aluno,
  consulta, reconhecimento e presença.
- **Persistência:** `src/infrastructure/database/models.py`, repositórios
  PostgreSQL de aluno/presença/turma, `migrations/versions/0004_turmas.py` e
  `scripts/import_legacy_sqlite.py`.
- **Interface e composição:** `src/presentation/cli/turmas.py`, `menu.py`,
  `captura_automatica.py`, `src/main.py` e mensagens do operador.
- **Testes:** fixtures/fakes, testes unitários de domínio, casos de uso,
  modelos, migration, importador, mensagens e menus; callsites dos testes
  PostgreSQL/BDD atualizados; novos testes preparados em
  `tests/integration/test_turmas_postgresql.py` e
  `tests/integration/test_migracao_turmas.py`.
- **Documentação/configuração:** `README.md`, `ARCHITECTURE.md`, `AGENTS.md`,
  `CLAUDE.md`, `.env.example`, `docs/ESTADO-ATUAL-E-EVIDENCIAS.md`,
  `docs/TURMAS.md` e `tasks/README.md`.

## Verificações executadas

Ambiente de testes: `.venv-ml`. Os testes usaram doubles e dados sintéticos.
Nenhum `.env`, conexão PostgreSQL, webcam, imagem biométrica real, migration
ou importador foi aberto/executado.

| Comando | Resultado |
|---|---|
| `.\.venv-ml\Scripts\python.exe -m pytest tests/unit/test_mensagens.py -q -p no:cacheprovider --basetemp <temp exclusivo>` | 54 passaram após adicionar orientações para os erros de turma/vínculo |
| `$bt = Join-Path $env:TEMP ("pytest-task008-unit-final-" + [guid]::NewGuid().ToString('N')); .\.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider --basetemp $bt` | **955 passaram** |
| `.\.venv-ml\Scripts\ruff.exe check src scripts tests migrations/versions/0004_turmas.py` | `All checks passed!` |
| `.\.venv-ml\Scripts\mypy.exe` | `Success: no issues found in 81 source files` |
| `ruff format --check` nos 49 arquivos Python alterados (paths selecionados do `git status --short`) | 49 arquivos já formatados |
| `.\.venv-ml\Scripts\python.exe -m compileall -q tests/integration tests/features` | Passou; compilação sintática somente, não executou testes |
| `git diff --check` | Passou; sem erros de whitespace |

A primeira execução completa encontrou um erro de cobertura de mensagens para
cinco novos erros de domínio (`944 passaram, 1 falhou`). As orientações foram
adicionadas e cobertas pela execução focada; a repetição final da suíte passou
com 955 testes.

## Não executado e limites

- `alembic upgrade`/`downgrade`, qualquer teste de `tests/integration` ou
  `tests/features`, `TRUNCATE` e qualquer conexão a banco: **não executados**.
- A compilação de arquivos de teste e os testes unitários não validam DDL,
  constraints, locks, isolamento transacional ou concorrência reais no
  PostgreSQL. Os skips causados pelos gates não foram contabilizados como
  testes aprovados.
- Não houve smoke com webcam, pessoas ou embeddings biométricos reais; esta
  tarefa muda organização e contexto de persistência, não mede reconhecimento.
- O código atual requer o schema `0004`; enquanto a revisão não for aplicada
  de forma autorizada e coordenada, não use esta versão com o banco operacional.
- A implantação exige backup validado, parada dos escritores antigos e
  atualização coordenada: o app/importador antigo nomeia a constraint global
  removida e não deve gravar depois do upgrade.

## Ativação e rollback futuros

1. Obter autorização específica para o schema e integração; identificar um
   PostgreSQL descartável e um segundo banco fisicamente separado para os
   testes de migration, conforme [`docs/TURMAS.md`](../../docs/TURMAS.md).
2. Validar backup e plano de restauração; parar escritores antigos; executar
   a suíte de integração protegida somente depois de configurar o opt-in e o
   marcador dos dois bancos descartáveis.
3. Revisar os resultados da migration em cópia autorizada e então combinar a
   aplicação do schema `0004` com a disponibilização deste código. Não há
   migration automática no boot.
4. Rollback sem dados novos pode usar downgrade. Com turmas, vínculos ou
   presenças contextualizadas, `downgrade()` recusa antes de DDL; rollback
   exige plano explícito de exportação/restauração, sem achatar presenças.

Documentação de regras e roteiro: [`docs/TURMAS.md`](../../docs/TURMAS.md).
