# Contrato de execução — FaceDiff web, tasks 009–020

Data: 17/10/2026. **Todos os pacotes estão planejados, não implementados.**
Executor previsto: Luna 6, esforço High, execução inline sem delegação.
O usuário solicitou a geração dos pacotes; esta preparação não implementa nem
publica a aplicação. Executar cada pacote somente quando enviado/autorizado.

## 1. Ordem e interface por último

Decisão mais recente: **primeiro todas as funcionalidades e testes do backend;
interface somente na020**. API, schemas HTTP, worker e testes de cliente não
são interface visual. Não criar templates, CSS, JavaScript de câmera, páginas
de login/painel ou protótipos de produto nas009–019. Documentação de endpoints
é permitida; não usar um frontend temporário para substituir testes.

A019 emite GATE_BACKEND_PARA_INTERFACE. Sem aprovação real, não iniciar020.
Testes de câmera/permissão, acessibilidade e E2E em navegador ficam na020 e são
necessariamente posteriores à construção da interface. Medição real da VPS,
restore real do Drive e biometria autorizada são gates operacionais separados;
ausência de autorização não pode ser escondida como teste aprovado.

## 2. Fontes obrigatórias e precedência

- [Planejamento consolidado](../docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md).
- [Arquitetura e operação](../docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md).
- [Roadmap atualizado](../docs/FACEDIFF-WEB-ROADMAP.md).
- [Transição de schema](WEB-MIGRACOES.md).
- AGENTS.md, CLAUDE.md, instructions relevantes, desenho/plano da task e
  RESULTADO das dependências; conferir código real, não só documentação.

A ordem009–020 substitui a ordenação W01–W12 anterior que intercalava interface
com funcionalidades. Não substitui requisitos de produto. Diretórios/nomes
propostos podem ser ajustados para reutilizar código existente, registrando o
mapeamento; não deixar contratos diferentes entre tarefas dependentes.

## 3. Requisitos transversais

| Requisito | Valor/contrato |
|---|---|
| Hospedagem | Hostinger KVM2, 2vCPU/8GB/100GB, Ubuntu24.04, Compose, Caddy, PostgreSQL local |
| Estrutura | FastAPI recomendado como nova apresentação; domínio/application sem dependência de HTTP, câmera ou SQL concreto |
| Professor | Usuário/senha, um responsável/turma; admin inicial seguro, reset administrativo sem e-mail |
| Turmas/alunos | Matéria e período obrigatórios; matutino/diurno/noturno; matrícula globalUK, N:N |
| Cadastro | Link7dias revogável; consentimento antes de upload; três capturas; aprovação independente; professor sem acesso à biometria |
| Existente | Matrícula não autentica, não sobrescrever referências/nome por link; novo vínculo autorizado |
| Verificação | Matrícula informada,1:1, FaceNet512,0,30, antispoofing obrigatório, desafio curto backend |
| Presença | Única por aluno/sessão, link compartilhado; nenhuma confirmação antes do commit |
| Prazo | Início dentro da janela; envio completo em prazo curto do servidor, teto fim+120s; processamento pode terminar depois |
| Tentativas | Três emissões por aluno/sessão, uma ativa; revisão manual auditada; alternativa acessível |
| Fila | Uma inferência ativa, dez aguardando como limite inicial incluindo reservas; banco/lease/idempotência |
| Gestão | CRUD autorizado, correção justificada, auditoria, CSV por turma/período sem biometria |
| Interface020 | Polling15s, responsiva, câmera explícita com captura automática, sem videoconferência/localização |
| Dados | EmbeddingsPG, fotos privadas persistentes, captura de presença transitória e fora do backup |
| Backup | Local+Drive cifrados, diário/manual, restauração comprovada; não contratar extra Hostinger |
| Finalidade | Demonstração~10dias, integrantes autorizados, sem reutilização para pesquisa; eliminação/encerramento documentados |

As recomendações da consolidação (mediana de três distâncias, TTL de tentativa,
fila SQL, três gerações de backup) são escolhas de engenharia para executar,
não evidência biométrica. Qualquer mudança deve ser documentada e testada,
sem alterar threshold/segurança por conveniência. Timeout de produção e capacidade
dependem da medição019 e do gate operacional.

## 4. Convenções de integração

- Composition root web separado; API não importa pesos de ML nem abre webcam.
  Serviços são construídos por injeção, com fakes em testes.
- Rotas sob `/api/v1`, mesma origem. UTC aware no banco, America/Sao_Paulo na
  apresentação/CSV. Relógio injetável; cliente não define horário autorizativo.
- Erros públicos tipados com request_id, sem traceback/segredo. Não expor nome,
  estado global de matrícula ou dados de outra turma para clientes anônimos.
- Sessão de autenticação é distinta de sessão de presença. Link tem finalidade
  validada; credencial efêmera identifica o acesso à tentativa, não autentica
  identidade biométrica. UUID/ID aleatório não substitui autorização.
- Uma transação para mutação+auditoria; arquivos requerem compensação/reconciliação.
  Idempotência e constraints SQL resolvem concorrência, não check-then-insert
  isolado. Resultado tardio revalida estado/versão/lease.
- Atualizar OpenAPI/DTOs e este contrato quando necessário, antes de tarefa
  consumidora. Não renomear endpoint silenciosamente na interface020.
- Testes podem usar fakes paraML; não usar mocks para alegar prova de constraint,
  lock ou migrationPostgreSQL. Dados sintéticos não provam acurácia.

## 5. Permissões para futuras execuções

Ao receber uma task para executar, implementar somente seu código/testes/docs.
Instalar dependências apenas em ambiente isolado do trabalho autorizado;
respeitar permissões do ambiente e não modificar ambientes pessoais/produção.

**Não há autorização implícita** para banco operacional, migrations online,
provisionamento/contratação, deploy, GoogleDrive, imagens reais, cadastro de
participantes, troca de limiar, desligamento de antispoofing ou publicaçãoGit.
Preparar os artefatos, indicar bloqueio específico e concluir o que independe
dele. Integração que cria/migra/limpa banco exige autorização explícita de
ambiente descartável; nunca ler `.env` real como fallback.

Nenhum teste deve coletar webcam, buscar datasets ou baixar biometria da internet.
Pesos de modelos não são autorização para usar imagens de terceiros; registrar
origem/licença e download separado quando necessário. Nenhuma imagem da conversa
deve ser incorporada às fixtures.

## 6. Resultado e publicação

Criar RESULTADO.md somente após executar: HEAD/branch, escopo, comandos completos,
ambiente, testes aprovados/falhos/não executados, migrations só preparadas ou
aplicadas com autorização, riscos e condição de parada. Nenhum número de teste
histórico vira evidência da entrega atual. Não marcar skips como aprovação.

**Commit e push não estão automaticamente autorizados nos novos pacotes.**
A restrição explícita da consolidação recente substitui a autorização herdada
dos prompts001–008. Se o usuário instruir commit+push na execução da task:

1. Usar apenas identidade/credenciaisGit já configuradas; mensagem PT-BR, sem
   Co-Authored-By, separar commits por escopo quando houver muitos arquivos.
2. Conferir branch/status/remoto/divergência e commits locais; publicar na main
   somente o trabalho autorizado. Não publicar commits desconhecidos.
3. Stage por caminhos explícitos, revisar diff e `git diff --cached --check`;
   sem `git add .`, `-A`, `commit -a`, dados, modelos ou segredos.
4. Push sem force/reset destrutivo e sem contornar hooks; confirmar hash/estado
   remoto. Push não é deploy nem autorização de migration.

## 7. Condição de parada

Finalizar só a task recebida. Preenchimento de checklist não substitui evidência.
Reportar o estado real, inclusive gates impedidos por falta de ambiente. Não
avançar à020 por pressão para concluir se019 não aprovou o backend.
