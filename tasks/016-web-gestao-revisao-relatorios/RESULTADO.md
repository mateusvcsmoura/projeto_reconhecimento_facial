# Resultado — tarefa 016: gestão, revisão manual e CSV

Estado: **parcial — implementação e gates locais concluídos; validação em
PostgreSQL descartável pendente**. A aplicação não deve receber a revisão
`0011` em ambiente operacional até esse gate ser executado.

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

Não houve alteração dos embeddings FaceNet512, do MiniFASNet, do threshold
operacional `0.30` nem das decisões biométricas. O operador confirmar a
identidade é uma afirmação auditada para correção manual, não uma validação
biométrica. Nenhuma interface visual foi criada.

## Arquivos alterados

Código de domínio, use cases, repositório e rotas de gestão; composição da
aplicação; modelo de presença/revisão; checagens do worker; migration `0011`;
testes unitários de rotas, repositório e limpeza protegida de arquivos. Os
contratos e a documentação estão em [FACEDIFF-WEB-GESTAO.md](../../docs/FACEDIFF-WEB-GESTAO.md).

## Validação executada

- Suíte completa com cobertura: **1.209 passed, 78 skipped**, cobertura total
  **80,23%** (limite: 80%).
- Ruff nos arquivos alterados: aprovado.
- Ruff format check nos arquivos alterados: aprovado (17 arquivos já formatados).
- Mypy em `src` e `scripts`: aprovado, sem problemas em 142 arquivos.
- `compileall` nos arquivos de fonte, migration e testes alterados: aprovado.
- `git diff --check`: aprovado; Git reportou apenas normalização LF/CRLF no
  Windows.
- Alembic `upgrade head --sql` com URL PostgreSQL offline: gerou a cadeia
  completa até `0011` sem conectar a banco.

Comando da suíte completa:

```powershell
.venv-ml\Scripts\python.exe -m pytest --cov=src --cov=scripts.metricas --cov=scripts.divisao_por_identidade --cov=scripts.evaluate_model --cov=scripts.calibrar_limiar --cov-report=term-missing --cov-fail-under=80 -p no:cacheprovider --basetemp .pytest-task016-full-rerun-20261018
```

As 78 marcações ignoradas incluem os testes de integração PostgreSQL protegidos
por opt-in. Não foram executados upgrade/downgrade em PostgreSQL, `alembic
check`, testes de lock/concorrência real nem BDD por não haver ambiente
descartável próprio da task016 configurado. SQLite e fakes não comprovam
constraints ou locks PostgreSQL. Também não houve acesso a `escola`, outro banco
operacional, webcam ou imagens/biometria de pessoas.

## Dependências, limitações e operação

Nenhuma dependência Python nova. A revisão `0011` está **somente preparada**;
as migrations `0006–0010` não foram alteradas. Antes de ativar o backend em um
banco, executar o gate PostgreSQL em banco descartável identificado, validar
`alembic check`, confirmar upgrade e downgrade sem perda e exercitar resultado
tardio concorrente com revisão. O banco operacional deve receber migration em
operação separada após backup e revisão explícita.

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

O commit de implementação `6c366bc` foi publicado em `main`. Este relatório e
os contratos foram organizados em commit documental separado, também em PT-BR
e sem `Co-authored-by`. Não foi feito deploy nem executada migration.
