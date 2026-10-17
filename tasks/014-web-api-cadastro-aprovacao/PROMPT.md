# Prompt de execução — 014 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório
`projeto_reconhecimento_facial`.

**Execute somente a task 014 — API de cadastro por link e aprovação. O desenho e o plano estão
definidos. Apenas execute o escopo autorizado, teste e documente; não reabra
brainstorming, não delegue e não avance automaticamente para outra task.**

## Leitura obrigatória

1. `AGENTS.md`, `CLAUDE.md`, instruções relevantes e arquitetura atual.
2. `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`.
3. `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`.
4. `tasks/WEB-CONTRATO-EXECUCAO.md` e `tasks/WEB-MIGRACOES.md`.
5. `tasks/014-web-api-cadastro-aprovacao/DESENHO.md` e `tasks/014-web-api-cadastro-aprovacao/PLANO.md`, integralmente.
6. Resultados reais das dependências: **010–013**.

Use Superpowers executing-plans quando disponível; aprove internamente escolhas
rotineiras, sem pedir confirmações de decisões já definidas. Isso não amplia
permissões de banco, dados reais, contratação ou publicação.

## Entrega específica

Expor API completa de cadastro, sem páginas, CSS, JavaScript ou câmera no navegador. Cliente HTTP de teste representa aluno e professor. Link compartilhado de cadastro tem 256 bits aleatórios, hash no banco, escopo turma, finalidade, validade7dias e revogação. Trocar token por credencial efêmera, não registrar URL/segredo em logs.

Nome/matrícula e aviso versionado/consentimento antecedem upload. O backend solicita três capturas guiadas via protocolo013, processa pelo worker012 e deixa solicitação pendente. Professor confirma identidade por procedimento independente e aprova com método/justificativa; matrícula existente gera só vínculo autorizado.

Endpoint público não enumera nomes/vínculos ou informa se matrícula global existe. Retorno de status exige credencial da solicitação. Expiração natural do convite bloqueia novas submissões; pendência recebida tem próprio prazo min(7dias da submissão, fim da finalidade). Revogação cancela coletas e pendências vinculadas conforme recomendação consolidada, auditando efeito. Não efetivar cadastro após revogação concorrente.

Atualização de referência tem endpoints administrativos separados e autorização de solicitação pelo professor responsável; reutiliza casos011 sem acesso visual à biometria. Não tratar pedido de atualização como permissão de substituir imediatamente.

### Contratos que você deve respeitar

POST /api/v1/turmas/{id}/links-cadastro -> link opaco (professor responsável).
POST /api/v1/acessos-link -> credencial efêmera e finalidade; POST /api/v1/cadastros -> solicitacao_id/estado.
POST /api/v1/cadastros/{id}/capturas aceita protocolo de013 e reserva012.
GET /api/v1/cadastros/{id}; POST /api/v1/cadastros/{id}/aprovar ou /rejeitar.
POST /api/v1/links/{id}/revogar; atualização biométrica usa /solicitacoes-biometria, com aprovação admin.
Todas as respostas derivam estado persistido, sem blobs biométricos.

### Provas mínimas

- Cadastro pendente não permite presença; matrícula existente nunca sobrescreve dados.
- Convite expirado/revogado ou de outra finalidade rejeita; revogação durante processamento impede aprovação.
- Três capturas necessárias; recusa de consentimento não grava biometria.
- Professor alheio não aprova nem consulta; professor legítimo não recebe fotos/embedding/caminho.

## Limites e conclusão

**Não criar interface, páginas, templates ou fluxo de câmera no navegador.** Use testes/cliente HTTP para provar a funcionalidade. UI fica exclusivamente na020.

Não executar migration, acessar banco operacional, conectar Google Drive,
provisionar VPS, realizar deploy ou usar rostos reais sem autorização específica
vigente. Preparar código/migration/testes não significa autorização para aplicá-los.
Não desabilitar antispoofing ou alterar threshold0,30 para fazer testes passarem.
Não interpretar matrícula informada como autenticação.

Cadastro integral e aprovação exercitáveis por API/testes, incluindo matrícula existente, sem interface de usuário.

Ao terminar, criar `tasks/014-web-api-cadastro-aprovacao/RESULTADO.md`, atualizar índice e relatar comandos
efetivos, contratos, pendências e estado dos gates. **Não fazer commit/push por
autorização herdada de tasks001–008.** A restrição da consolidação atual prevalece;
se o usuário autorizar explicitamente publicação nesta execução, fazer commit
em PT-BR e push na main conforme procedimento do contrato comum. Não contratar
ou implantar como consequência do push.
