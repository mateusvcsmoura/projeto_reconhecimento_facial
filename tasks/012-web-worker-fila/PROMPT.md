# Prompt de execução — 012 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório
`projeto_reconhecimento_facial`.

**Execute somente a task 012 — Worker facial único, fila limitada e temporários. O desenho e o plano estão
definidos. Apenas execute o escopo autorizado, teste e documente; não reabra
brainstorming, não delegue e não avance automaticamente para outra task.**

## Leitura obrigatória

1. `AGENTS.md`, `CLAUDE.md`, instruções relevantes e arquitetura atual.
2. `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`.
3. `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`.
4. `tasks/WEB-CONTRATO-EXECUCAO.md` e `tasks/WEB-MIGRACOES.md`.
5. `tasks/012-web-worker-fila/DESENHO.md` e `tasks/012-web-worker-fila/PLANO.md`, integralmente.
6. Resultados reais das dependências: **011 e runtime009 validado para a parte executada**.

Use Superpowers executing-plans quando disponível; aprove internamente escolhas
rotineiras, sem pedir confirmações de decisões já definidas. Isso não amplia
permissões de banco, dados reais, contratação ou publicação.

## Entrega específica

API não carrega modelos. Um processo worker, mesma base de código e VPS, aquece FaceNet512 e MiniFASNet e executa um trabalho facial por vez. Job guarda ID, proprietário/tipo, estado, lease, prazos, referência de mídia temporária; não embedding/frame em logs. Cadastro processa suas três capturas sequencialmente num job limitado.

Fila PostgreSQL FIFO, até dez aguardando incluindo reservas de upload; um ativo adicional. Limite verificado atomicamente por lock apropriado, não SELECT count fora de transação. Um job ativo permanece contabilizado até término efetivo do modelo; timeout do request não autoriza segunda inferência. Watchdog invalida lease antes de aceitar trabalho substituto e impede resultado tardio. Não implementar Redis/Celery.

Temporários privados em memória compartilhada app/worker com quota; limpeza em sucesso/falha/cancelamento/expiração e órfãos. Não backup nem rota pública. Reinício sem mídia produz falha técnica registrada, não confirmação nem replay automático. Propor parâmetros iniciais de limite de bytes/frames como configuração de laboratório, registrar que limites de produção dependem019.

Corrigir para o caminho web ausência de is_real/resultado esperado como falha fechada e sanitizar erros do adaptador. Preservar comportamento CLI por contrato documentado e regressões; qualquer endurecimento comum deve ser testado e relatado, sem desligar proteção.

### Contratos que você deve respeitar

FilaFacial.reservar(tipo, dono_id, idempotencia, prazo) -> Reserva | FilaCheia.
FilaFacial.submeter(reserva_id, manifesto_temporario) -> Job; claim/heartbeat/finalizar exigem lease.
GET /api/v1/operacoes/{id} exige credencial opaca do proprietário ou ator autorizado.
503 + Retry-After para capacidade; 429 para abuso; estados recebida/enfileirada/processando/concluida/rejeitada.
Worker despacha tipos conhecidos; cadastro/presença serão ligados em014/015, sem aceitar código arbitrário.

### Provas mínimas

- Uma execução ativa e no máximo dez aguardando/reservadas sob corrida.
- Timeout/restart/resultado tardio não duplicam inferência válida nem persistência.
- Job de proprietário alheio não é consultável; payload excessivo falha antes de decodificar.
- Arquivo ausente, modelo indisponível ou is_real ausente falham fechado; temporários removidos.

## Limites e conclusão

**Não criar interface, páginas, templates ou fluxo de câmera no navegador.** Use testes/cliente HTTP para provar a funcionalidade. UI fica exclusivamente na020.

Não executar migration, acessar banco operacional, conectar Google Drive,
provisionar VPS, realizar deploy ou usar rostos reais sem autorização específica
vigente. Preparar código/migration/testes não significa autorização para aplicá-los.
Não desabilitar antispoofing ou alterar threshold0,30 para fazer testes passarem.
Não interpretar matrícula informada como autenticação.

Fila/worker/temporários funcionais com testes de lógica e integração preparada; limites e estados públicos definidos. Sem UI e sem falsa prova de capacidade da VPS.

Ao terminar, criar `tasks/012-web-worker-fila/RESULTADO.md`, atualizar índice e relatar comandos
efetivos, contratos, pendências e estado dos gates. **Não fazer commit/push por
autorização herdada de tasks001–008.** A restrição da consolidação atual prevalece;
se o usuário autorizar explicitamente publicação nesta execução, fazer commit
em PT-BR e push na main conforme procedimento do contrato comum. Não contratar
ou implantar como consequência do push.
