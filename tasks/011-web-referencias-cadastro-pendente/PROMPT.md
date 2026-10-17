# Prompt de execução — 011 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório
`projeto_reconhecimento_facial`.

**Execute somente a task 011 — Três referências, cadastro pendente e versionamento biométrico. O desenho e o plano estão
definidos. Apenas execute o escopo autorizado, teste e documente; não reabra
brainstorming, não delegue e não avance automaticamente para outra task.**

## Leitura obrigatória

1. `AGENTS.md`, `CLAUDE.md`, instruções relevantes e arquitetura atual.
2. `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`.
3. `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`.
4. `tasks/WEB-CONTRATO-EXECUCAO.md` e `tasks/WEB-MIGRACOES.md`.
5. `tasks/011-web-referencias-cadastro-pendente/DESENHO.md` e `tasks/011-web-referencias-cadastro-pendente/PLANO.md`, integralmente.
6. Resultados reais das dependências: **010**.

Use Superpowers executing-plans quando disponível; aprove internamente escolhas
rotineiras, sem pedir confirmações de decisões já definidas. Isso não amplia
permissões de banco, dados reais, contratação ou publicação.

## Entrega específica

Criar solicitação separada do aluno ativo, conjunto versionado e três referências de ordinais 1–3. Cada referência possui recorte privado relativo, embedding float32 normalizado, modelo/dimensão, versão e consentimento. Conjunto pode pertencer a solicitação pendente ou aluno aprovado, com integridade explícita; somente um conjunto ativo por aluno. Não replicar uma foto antiga três vezes.

Estados: em_coleta, em_validacao, pendente_aprovacao, aprovada, rejeitada, cancelada, expirada. Receber três preparações técnicas não aprova identidade nem vínculo. Aprovação requer método de conferência independente, professor responsável, consentimento e revalidação atômica de matrícula UK global/turma.

Matrícula existente nunca tem nome, foto ou embedding sobrescrito pelo link. Aprovação gera só vínculo após identidade verificada, preservando N:N. Em corrida de aprovações, a segunda solicitação deve ser reavaliada como vínculo existente. Não reservar matrícula indefinidamente por solicitação pública.

Troca de biometria: professor responsável/admin solicita, titular autoriza nova coleta e admin aprova novo conjunto com auditoria. Referências antigas não entram em novas verificações. Revogar/inutilizar trabalhos pendentes que dependiam do conjunto substituído. Dados provisórios rejeitados/expirados são removidos por limpeza rastreável; falha de arquivo não vira sucesso silencioso.

### Contratos que você deve respeitar

SolicitarCadastroWeb.criar(dados, contexto_convite, consentimento) -> Solicitacao.
AnexarReferencias.executar(solicitacao_id, preparacoes[3], contexto_job) -> estado.
AprovarCadastroWeb.executar(ator, solicitacao_id, metodo_identidade, justificativa) -> ResultadoAprovacao.
SolicitarAtualizacaoBiometrica e AprovarAtualizacaoBiometrica são operações distintas.
DTOs de professor não contêm imagem, embedding, caminho ou URL biométrica; preparação pode usar provider fake até012/013.

### Provas mínimas

- Duas referências não ativam; ordinal duplicado ou modelos incompatíveis recusam.
- Matrícula existente e corrida de aprovações não sobrescrevem cadastro global.
- Professor não lê biometria; tentativa de aprovar turma alheia falha.
- Falha SQL remove somente arquivos da própria solicitação; conjunto antigo permanece em falha de troca.

## Limites e conclusão

**Não criar interface, páginas, templates ou fluxo de câmera no navegador.** Use testes/cliente HTTP para provar a funcionalidade. UI fica exclusivamente na020.

Não executar migration, acessar banco operacional, conectar Google Drive,
provisionar VPS, realizar deploy ou usar rostos reais sem autorização específica
vigente. Preparar código/migration/testes não significa autorização para aplicá-los.
Não desabilitar antispoofing ou alterar threshold0,30 para fazer testes passarem.
Não interpretar matrícula informada como autenticação.

Modelo e casos de uso de cadastro pendente completos com fakes, sem formulário/câmera e sem alunos reais. Ativação exige três referências e aprovação independente.

Ao terminar, criar `tasks/011-web-referencias-cadastro-pendente/RESULTADO.md`, atualizar índice e relatar comandos
efetivos, contratos, pendências e estado dos gates. **Não fazer commit/push por
autorização herdada de tasks001–008.** A restrição da consolidação atual prevalece;
se o usuário autorizar explicitamente publicação nesta execução, fazer commit
em PT-BR e push na main conforme procedimento do contrato comum. Não contratar
ou implantar como consequência do push.
