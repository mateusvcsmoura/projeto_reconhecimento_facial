# Prompt de execução — 015 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório
`projeto_reconhecimento_facial`.

**Execute somente a task 015 — Sessões, tentativas e presença por API. O desenho e o plano estão
definidos. Apenas execute o escopo autorizado, teste e documente; não reabra
brainstorming, não delegue e não avance automaticamente para outra task.**

## Leitura obrigatória

1. `AGENTS.md`, `CLAUDE.md`, instruções relevantes e arquitetura atual.
2. `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`.
3. `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`.
4. `tasks/WEB-CONTRATO-EXECUCAO.md` e `tasks/WEB-MIGRACOES.md`.
5. `tasks/015-web-api-sessoes-presencas/DESENHO.md` e `tasks/015-web-api-sessoes-presencas/PLANO.md`, integralmente.
6. Resultados reais das dependências: **014**.

Use Superpowers executing-plans quando disponível; aprove internamente escolhas
rotineiras, sem pedir confirmações de decisões já definidas. Isso não amplia
permissões de banco, dados reais, contratação ou publicação.

## Entrega específica

Criar sessão com turma/professor responsável, início/fim awareUTC, título, revogação e versão. Link compartilhado por turma/sessão reutiliza serviço014 com finalidade presença. Matrícula informada determina única identidade; cadastro deve estar aprovado e vínculo ativo.

Início de tentativa: inicio<=agora<fim. Prazo recomendado do plano: min(iniciada_em+120s, fim+120s); tratar como validade curta explícita, mantendo teto autorizado após encerramento. Horário de recepção é corpo integral recebido pelo servidor; cliente/EXIF não autorizam prazo. A tentativa tem estados iniciada, recebida, enfileirada, processando, concluída, expirada, rejeitada; motivo técnico separado. Processamento tempestivamente recebido pode terminar depois do prazo, sob timeout próprio medido019.

Reservar ordinal1–3 atomically por aluno/sessão, uma tentativa ativa. Cancelar/abandonar/falha biométrica/expirar consomem emissão; câmera recusada antes de emissão e sobrecarga antes de reserva não consomem. Falha técnica posterior não devolve quota automaticamente; revisão/admin auditado controla restauração. Rate limits mitigam consumo malicioso de quota por matrícula alheia, sem fingir que matrícula autentica.

Commit final revalida dono/escopo, sessão não revogada, turma/vínculo, conjunto ativo, lease e terminalidade. UNIQUE(aluno_id,sessao_id), resultado idempotente e persistência antes de sucesso. Não sobrescrever presença/correção existente. Preparar migração com sessao_id e índices parciais preservando legado diário; atualizar on_conflict nos caminhos afetados, importador e testes sem executar importação.

Não inventar sessão para registros antigos nem desativar CLI; web exige sessão, ramo legado explícito mantém semântica anterior. Downgrade recusa perda de dados novos; documentar coordenação de versões e escritores.

### Contratos que você deve respeitar

CriarSessao.executar(ator,turma_id,inicio,fim,titulo) -> Sessao.
IniciarTentativa.executar(acesso_link,matricula,chave_idempotente,agora) -> Tentativa/desafio.
ReceberCaptura.executar(tentativa_id,credencial,payload,recebida_em_servidor) -> Job.
ConcluirPresenca.executar(job,decisao,agora) -> ResultadoPersistido; única entrada de persistência biométrica.
POST /api/v1/turmas/{id}/sessoes; POST /api/v1/sessoes/{id}/tentativas; POST /api/v1/tentativas/{id}/capturas; GET /api/v1/tentativas/{id}; revogação por professor.

### Provas mínimas

- Início exato aceita; fim exato não cria tentativa; corpo recebido no prazo aceita e1ms depois rejeita.
- Envio no prazo pode concluir depois; revogação impede commit tardio.
- Duas sessões no dia geram duas presenças; mesmo aluno/sessão duplica só retorno, não linha.
- Duas emissões simultâneas não criam tentativa4; upload repetido com payload diferente não passa.
- Falha banco não retorna sucesso; fallback1:N e timestamp cliente nunca autorizam.

## Limites e conclusão

**Não criar interface, páginas, templates ou fluxo de câmera no navegador.** Use testes/cliente HTTP para provar a funcionalidade. UI fica exclusivamente na020.

Não executar migration, acessar banco operacional, conectar Google Drive,
provisionar VPS, realizar deploy ou usar rostos reais sem autorização específica
vigente. Preparar código/migration/testes não significa autorização para aplicá-los.
Não desabilitar antispoofing ou alterar threshold0,30 para fazer testes passarem.
Não interpretar matrícula informada como autenticação.

Fluxo de presença completo por API/testes e persistência preparada, com schema legado preservado e integração concorrente registrada ou bloqueada por autorização.

Ao terminar, criar `tasks/015-web-api-sessoes-presencas/RESULTADO.md`, atualizar índice e relatar comandos
efetivos, contratos, pendências e estado dos gates. **Não fazer commit/push por
autorização herdada de tasks001–008.** A restrição da consolidação atual prevalece;
se o usuário autorizar explicitamente publicação nesta execução, fazer commit
em PT-BR e push na main conforme procedimento do contrato comum. Não contratar
ou implantar como consequência do push.
