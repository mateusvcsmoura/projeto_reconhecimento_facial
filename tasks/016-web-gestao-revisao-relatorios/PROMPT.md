# Prompt de execução — 016 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório
`projeto_reconhecimento_facial`.

**Execute somente a task 016 — CRUD autorizado, revisão manual, auditoria e CSV. O desenho e o plano estão
definidos. Apenas execute o escopo autorizado, teste e documente; não reabra
brainstorming, não delegue e não avance automaticamente para outra task.**

## Leitura obrigatória

1. `AGENTS.md`, `CLAUDE.md`, instruções relevantes e arquitetura atual.
2. `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`.
3. `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`.
4. `tasks/WEB-CONTRATO-EXECUCAO.md` e `tasks/WEB-MIGRACOES.md`.
5. `tasks/016-web-gestao-revisao-relatorios/DESENHO.md` e `tasks/016-web-gestao-revisao-relatorios/PLANO.md`, integralmente.
6. Resultados reais das dependências: **015**.

Use Superpowers executing-plans quando disponível; aprove internamente escolhas
rotineiras, sem pedir confirmações de decisões já definidas. Isso não amplia
permissões de banco, dados reais, contratação ou publicação.

## Entrega específica

Completar endpoints de CRUD sem UI. Turma exige matéria/período e um responsável; não adicionar nome obrigatório nem substituir diurno por vespertino. Professor gerencia suas turmas e vínculos; exclusão global/alterações globais que afetem outras turmas passam por admin, com confirmação e justificativa. Exclusão lógica de turma/desvínculo preservam histórico; exclusão global elimina dados conforme política revisada, com auditoria mínima que não guarde biometria.

Após três tentativas, aluno pode pedir revisão com justificativa; caminho acessível pode antecipar pedido. Professor verifica identidade por procedimento independente e registra presente manualmente ou anula, sempre com justificativa e auditoria antes/depois. Falha biométrica nunca aprova presença. Requisição de revisão não revela dados de terceiros; limitar uma revisão aberta por aluno/sessão.

Controle de versão/locks impede worker tardio de sobrescrever correção. Pedido de reativação de quota exige evento auditado, sem criar retry ilimitado silencioso. Sucesso de mutação depende do commit conjunto da auditoria.

CSV UTF8 por turma/dia/intervalo inclusivo/mês em America/Sao_Paulo: turma, matéria, período, sessão, data, horário rotulado, matrícula, nome, status e indicação manual. Não fotos, tokens, embeddings, scores ou justificativas sensíveis. Escape/neutralização de fórmulas; gerar sob demanda. Não deduzir faltas sem roster histórico.

Endpoint agregado do painel será usado no polling15s da020; aqui testar API e autorização, não criar painel.

### Contratos que você deve respeitar

RevisarPresenca.executar(ator,revisao_id,decisao,justificativa,versao_esperada) -> Presenca.
POST /api/v1/revisoes; GET /api/v1/turmas/{id}/revisoes; POST /api/v1/revisoes/{id}/decidir.
GET/POST/PATCH/DELETE /api/v1/turmas e /turmas/{id}; vínculos via /turmas/{id}/alunos.
GET /api/v1/turmas/{id}/painel -> estados mínimos e atualizado_em.
GET /api/v1/turmas/{id}/presencas.csv?inicio=...&fim=...; cabeçalhos explícitos, autorização por dono.

### Provas mínimas

- Justificativa vazia ou professor alheio não corrige; revisão não aprova automaticamente.
- Worker tardio não altera revisão; conflito de versão devolve erro explícito.
- Desvincular não apaga outras turmas; globaldelete é administrativo e audita sem biometria.
- CSV não vaza outra turma/biometria; trata fórmula, Unicode, vírgula e meia-noite/filtros.

## Limites e conclusão

**Não criar interface, páginas, templates ou fluxo de câmera no navegador.** Use testes/cliente HTTP para provar a funcionalidade. UI fica exclusivamente na020.

Não executar migration, acessar banco operacional, conectar Google Drive,
provisionar VPS, realizar deploy ou usar rostos reais sem autorização específica
vigente. Preparar código/migration/testes não significa autorização para aplicá-los.
Não desabilitar antispoofing ou alterar threshold0,30 para fazer testes passarem.
Não interpretar matrícula informada como autenticação.

Todas as funcionalidades de gestão, presença e relatório disponíveis por API e cobertas por testes, sem interface visual.

Ao terminar, criar `tasks/016-web-gestao-revisao-relatorios/RESULTADO.md`, atualizar índice e relatar comandos
efetivos, contratos, pendências e estado dos gates. **Não fazer commit/push por
autorização herdada de tasks001–008.** A restrição da consolidação atual prevalece;
se o usuário autorizar explicitamente publicação nesta execução, fazer commit
em PT-BR e push na main conforme procedimento do contrato comum. Não contratar
ou implantar como consequência do push.
