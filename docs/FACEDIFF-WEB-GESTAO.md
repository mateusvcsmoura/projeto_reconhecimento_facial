# Gestão web, revisão de presença e relatórios

Estado: backend da tarefa 016 implementado, validado em PostgreSQL e migration
`0011` aplicada ao banco local de desenvolvimento `escola`. Não há interface
visual; ela continua reservada à tarefa 020.

## API disponível

Todas as rotas usam `/api/v1` e dependem da autenticação e da autorização por
papel/turma já estabelecidas na tarefa 010. Professor pode administrar somente
turmas sob sua responsabilidade; operações que alteram dados globais ou afetam
outras turmas exigem administrador, confirmação explícita e justificativa.

| Método e rota | Acesso e efeito |
|---|---|
| `GET /turmas` | Lista turmas autorizadas; admin vê todas as ativas. |
| `POST /turmas` | Cria turma com matéria, período e responsável. Transferência global exige confirmação e justificativa. |
| `PATCH /turmas/{id}` | Atualiza turma autorizada; transferência de responsável usa confirmação e justificativa. |
| `DELETE /turmas/{id}` | Exclusão lógica; preserva vínculos e histórico de presença. |
| `GET /turmas/{id}/alunos` | Lista vínculos ativos da turma autorizada. |
| `POST /turmas/{id}/alunos` | Cria vínculo usando matrícula existente, sem criar/alterar cadastro global. |
| `DELETE /turmas/{id}/alunos/{aluno_id}` | Desvincula somente da turma informada; outras matrículas N:N permanecem. |
| `DELETE /alunos/{aluno_id}` | Admin; exige confirmação explícita vinculada ao ID do aluno e justificativa; exclui dados globais relacionados. |
| `POST /revisoes` | Bearer de link ativo de presença; recebe sessão, matrícula, justificativa e opção de acessibilidade. Resposta contém somente protocolo e estado. |
| `GET /turmas/{id}/revisoes` | Professor responsável ou admin lista revisões da turma, filtradas por estado. |
| `POST /revisoes/{id}/decidir` | Professor responsável decide presente/anulada, com justificativa, versão esperada e confirmação explícita de verificação independente de identidade. |
| `GET /turmas/{id}/painel` | Retorna contagens agregadas e `atualizado_em` para polling; não calcula faltas. |
| `GET /turmas/{id}/presencas.csv` | Exporta período inclusivo por `inicio`+`fim` ou `mes=AAAA-MM`, no fuso configurado (`America/Sao_Paulo` por padrão). |
| `POST /turmas/{id}/sessoes/{sessao_id}/alunos/{aluno_id}/reativar-quota` | Exclusivo de admin; confirmação e justificativa registradas em auditoria. |

O pedido de revisão é autorizado pela credencial efêmera associada ao link e à
sessão. A matrícula não autentica. A opção `via_acessivel` permite solicitar
revisão antes do esgotamento das três tentativas. Um índice parcial garante no
máximo uma revisão aberta por aluno/sessão. A API não revela dados de outros
alunos no fluxo público.

Decisão manual “presente” não é inferida de falha biométrica. Ela exige a
declaração do operador de que conferiu a identidade por procedimento
independente; registra ator, instante, justificativa, versão anterior/nova e
auditoria na mesma transação. Controle de versão recusa decisão obsoleta e os
locks compartilhados com o worker impedem que um resultado tardio substitua a
revisão. Isso é um controle operacional auditável, não validação biométrica.

## Relatório e dados

O CSV inclui turma, matéria, período, sessão, data local, horário local rotulado,
matrícula, nome, status e indicação de origem manual. Inclui somente presenças
registradas e anulamentos: não infere ausências a partir da lista atual de
alunos. Não inclui imagem, caminho privado, embedding, token, score ou
justificativas. Valores de texto iniciados por caracteres de fórmula são
neutralizados; a resposta é UTF-8 e marcada `nosniff`.

O painel expõe totais mínimos de sessões, presenças e revisões, mais o instante
da consulta. Os filtros e totais respeitam a autorização da turma. CSV é gerado
sob demanda e não é armazenado pelo servidor.

## Transição de banco e arquivos legados

A revisão `0011` (down revision `0010`) adiciona estado, origem, versão,
horário-evidência e metadados de correção às presenças; preserva a distinção das
presenças legadas e biométricas já existentes, permite presença manual de uma
sessão com correção auditada, aumenta o domínio do ordinal de tentativas para
reativações de quota e cria `revisoes_presenca_web` com unicidade parcial de
revisão aberta. O downgrade recusa eliminar dados de revisão/correção novos.
Depois de confirmar `escola` como banco local em `localhost:5433`, na revisão
`0005`, foram aplicadas as revisões pendentes `0006–0011`. A revisão terminou
em `0011` e `alembic check` retornou `No new upgrade operations detected`. No
banco descartável `task016_gestao_test_20261018`, a fixture aplicou `head`,
validou o schema e executou uma corrida real revisão/worker; limpou os dados
sintéticos e reverteu o banco descartável a `base`. Também confirmou que um
downgrade com revisão persistida é recusado sem apagar o registro. Antes de
habilitar a API em outro ambiente, revisar o alvo e seguir o procedimento de
backup do contrato de migrations.

A exclusão global tenta remover os arquivos temporários e a imagem legada após
o commit do banco. A API informa `limpeza_pendente=true` se algum armazenamento
não puder ser limpo. Como os caminhos são retirados do banco na transação, a
falha não tem retry automático persistido; exige procedimento operacional de
limpeza/reconciliação. A configuração `WEB_LEGACY_IMAGE_STORAGE_DIR` é opcional
e limita remoção ao diretório privado configurado.

## Evidências e limites remanescentes

Na validação final, a suíte completa reportou 1.209 aprovados, 80 ignorados e
cobertura total de 80,23%, acima do gate de 80%. Ruff, formatação e mypy
passaram. Os dois testes PostgreSQL da tarefa passaram: migration/schema e
concorrência real do worker com uma revisão confirmada. `alembic check` passou
no banco descartável e em `escola`; o downgrade protegido preservou a revisão.
Não houve teste com pessoas, imagens biométricas, webcam ou implantação. A
validação não substitui o gate integrado
do backend previsto na tarefa 019.

Consulte o [resultado da tarefa 016](../tasks/016-web-gestao-revisao-relatorios/RESULTADO.md)
e os [contratos de execução](../tasks/WEB-CONTRATO-EXECUCAO.md) e de
[migrations](../tasks/WEB-MIGRACOES.md).
