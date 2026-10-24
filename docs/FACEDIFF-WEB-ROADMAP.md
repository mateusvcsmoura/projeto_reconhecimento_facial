# FaceDiff web — roadmap e plano de validação

Data: 20/10/2026. **Tarefas 009–019A implementadas; gate do backend aprovado em ambiente local descartável. A interface 020 está parcialmente implementada.**
O runtime HTTP e a instalação/importação da stack ML foram provados em Ubuntu
24.04/Python 3.12; inferência com pesos e validação integrada continuam gates
futuros, conforme o resultado 009.
Tarefa 010 foi implementada, validada e publicada: 984 testes unitários,
3 testes PostgreSQL em banco descartável, revisão `0005` aplicada ao banco local
e `alembic check` aprovado. Deploy e validação operacional continuam pendentes; veja o
resultado 010.
Especificação: [planejamento principal](PLANEJAMENTO-FUTURO-PRESENCA-WEB.md).
Arquitetura: [operação KVM2](FACEDIFF-WEB-ARQUITETURA-OPERACAO.md).

## 1. Atualização de ordem solicitada pelo usuário

**Todas as funcionalidades e seus testes de backend vêm antes da interface.**
A antiga divisão W01–W12 foi reorganizada nos pacotes009–020. Não executar
os passos antigos que intercalavam telas com API. A020 é a última task de
desenvolvimento e inclui login, painel, câmera/cadastro, presença, aprovação,
revisão, CRUD e relatórios visuais.

Até019, usar API, clientes HTTP automatizados, doubles de ML e ambientes
descartáveis autorizados. Não criar frontend provisório para provar backend.
Após aUI, testar navegação/permissões/câmeras e E2E; esses testes dependem da
interface e não poderiam honestamente ser declarados aprovados antes dela.

## 2. Pacotes executáveis

Cada pasta contém desenho, plano e prompt para **Luna 6 High**.
O contrato comum e o
contrato de migrations são leitura obrigatória.

| Task | Escopo | Dependência | Prompt |
|---|---|---|---|
| 009 | Fundação web e compatibilidade Linux | 008 como referência histórica; planejamento consolidado | Executar 009 |
| 010 | Contas, autenticação, professor responsável e auditoria | 009 | Executar 010 |
| 011 | Três referências, cadastro pendente e versionamento biométrico | 010 | Executar 011 |
| 012 | Worker facial único, fila limitada e temporários | 011 e runtime009 validado para a parte executada | Executar 012 |
| 013 | Desafio facial no servidor e verificação 1:1 | 012 | Executar 013 |
| 014 | API de cadastro por link e aprovação | 010–013 | Executar 014 |
| 015 | Sessões, tentativas e presença por API | 014 | Executar 015 |
| 016 | CRUD autorizado, revisão manual, auditoria e CSV | 015 | Executar 016 |
| 017 | Backup cifrado, retenção e restauração | 016 | Executar 017 |
| 018 | Artefatos de implantação Ubuntu, Compose e Caddy | 017 | Resultado parcial |
| 019 | Validação integrada do backend e gate para a interface | 009–018 implementadas; não basta existirem seus documentos | Executar 019 |
| 019A | Fechamento do restore, runtime Compose, proteção pública e fluxo integrado | 019; gate backend aprovado com PostgreSQL/rclone crypt e Compose Linux descartáveis | Resultado 019A |
| 020 | Interface web responsiva e validação ponta a ponta | Backend aprovado; implementação parcial; browser/E2E visual ainda pendente | Resultado 020 |

A sequência recomendada é linear009→020, embora os contratos descrevam
dependências mais específicas. Não paralelizar alterações de schema/contratos
por iniciativa própria. Cada execução atualiza o RESULTADO.md com evidências reais.

A task018 possui artefatos Compose, Dockerfiles, Caddy, preflight, healthcheck
do worker e runbook. Em 19/10/2026, a task019A construiu e executou localmente os
targets Linux com secrets/volumes descartáveis, validou Caddy, healthchecks,
permissões e persistência após recriação. Isso não representa deploy nem medição
na VPS; consulte o resultado 018
e o resultado 019A.

## 3. Cobertura do planejamento anterior

| Tema anterior | Pacote responsável atual |
|---|---|
| W01 runtime/decisão web |009|
| W02 contas/professor |010|
| W03 três referências |011|
| W04 worker/desafio |012 e013|
| W05 cadastro web |014 API,020 interface|
| W06 sessões/tentativas |015|
| W07 experiência móvel/polling |020 exclusivamente|
| W08 revisão/CRUD/CSV |016 API,020 interface|
| W09 backup/retencão |017|
| W10 empacotamento |018 artefatos, sem deploy automático|
| W11 benchmark/ensaio |019 backend;020 browser/roteiro; ensaio real só autorizado|
| W12 encerramento |Ferramentas017 e runbook018; execução após demonstração autorizada|

Encerramento e deploy são operações do ciclo de vida, não funcionalidades a
serem implementadas depois daUI. Seus artefatos serão preparados antes dela;
sua execução real exige autorização e momento apropriado.

## 4. Gates: não confundir testes preparados com aprovados

### Gate de backend para iniciar020

A019 deve registrar **GATE_BACKEND_PARA_INTERFACE: APROVADO** e apontar:

- unitários e regressões afetadas;
- fluxo completo por HTTP com dados sintéticos e ML fake;
- integração real em PostgreSQL descartável autorizado, incluindo migrations,
  constraints, transações, quota, idempotência e concorrência;
- segurança de autenticação/ownership/CSRF/tokens/logs/CSV;
- fila, leases, falhas, limpeza e backup cifrado com restauração local sintética;
- validação dos artefatos de implantação e contratos completos de API.

Falha implica REPROVADO; ausência de ambiente/autorização necessária implica
BLOQUEADO_POR_AMBIENTE. Ambos impedem começar020. Suíte apenas escrita, skip,
mock de SQL ou relato histórico não aprova o gate.

**Estado verificado em 19/10/2026:** a task019 passou nos testes unitários,
HTTP sintéticos e integrações PostgreSQL descartáveis. A task019A executou o
roundtrip PostgreSQL/rclone crypt, runtime Compose/Linux, rate limit concorrente
e fluxo completo até painel/CSV. `GATE_BACKEND_PARA_INTERFACE: APROVADO`; veja
os resultados 019 e
019A. O gate de dados reais
permanece `PENDENTE`; a interface 020 está parcialmente implementada e ainda
aguarda inspeção visual e E2E em navegador, conforme seu resultado.

### Gate operacional para dados reais e apresentação

Separado do gate acima, exige:

- prova de runtime/modelos e desafio com material legitimamente autorizado;
- medição de CPU/RAM/inferência/fila/cold start na KVM2 e timeouts fundamentados;
- aviso, responsáveis e autorizações do grupo, confirmação independente de
  identidade, alternativa acessível e regras de eliminação;
- domínio/HTTPS/contratação/localização e política de snapshots confirmados;
- OAuthDrive autorizado, custódia de chaves e restauração da cópia externa;
- interface020 testada, ensaio móvel nos dispositivos reais, backup manual e
  contingência.

Não bloquear desenvolvimento sintético de009–018 por esses gates futuros.
Não declarar prontidão operacional se algum deles estiver pendente. Nenhuma
tarefa autoriza contratar ou configurar conta pessoal para superar bloqueio.

## 5. Matriz de testes futura

| Área | Prova mínima | Task |
|---|---|---|
| Runtime | API isolada; worker/fila e smoke com pesos locais passaram em Windows; tmpfs Linux, handlers e validação da VPS pendem |009/012/019|
| Auth | ProfessorA não acessaB, conta inativa, expiração/reset/CSRF, admin seguro |010|
| Referências | Três ordinais, versão, matrículaUK, corrida de aprovação, compensação de arquivo |011|
| Fila | Um ativo, dez aguardando/reservados, lease/restart/timeout, resposta tardia |012|
| Identidade/desafio | Mediana/limiar0,30, incompatibilidade, replay/nonce/ordem/movimento, cliente forjado |013|
| Cadastro |7dias, revogação, consentimento, pendência, aprovação, matrícula existente |014|
| Sessões | Início/fim exatos, recepção completa, teto120s, quota3 e duplicidade aluno/sessão |015|
| Revisão/gestão | Justificativa, correção versus worker, CRUD autorizado, CSV seguro/fuso |016|
| Backup | Consistência SQL/fotos, cifra, hash, falha de upload, restore/exclusões/prazo final |017|
| Infraestrutura | Só80/443 públicos, rede privada, persistência, sem biometria em proxy, sem migration no boot |018|
| Integração | FluxoAPI completo, concorrênciaPostgreSQL, segurança e benchmark agregado |019|
| Interface | Câmera/permissão,3capturas, polling15s, espera, acessibilidade, reload, E2E móvel |020|

Fixtures e conftest devem ser inspecionados antes de execução; integração usa
banco descartável identificado e autorizado. Ensaios não podem apontar ao banco
local operacional. Testes funcionais não são avaliação de acurácia biométrica.

## 6. Permissões, conclusão e evidências

A execução da tarefa009 criou código e dependências web isoladas e executou
testes com dados sintéticos em container descartável. Banco real, infraestrutura,
modelos e dados pessoais permaneceram intocados. Não há commit/push automático;
os prompts novos respeitam a restrição recente, mesmo que os prompts001–008
tenham autorização histórica diferente.

Verificação da preparação: formato DESENHO/PLANO/PROMPT, dependências e ordem,
links locais, consistência de gates e diff documental. Os resultados de testes
da aplicação só serão registrados pelos executores nas respectivas tasks.

Não há decisão de produto adicional bloqueando009. A interface está
intencionalmente condicionada ao gate019. Caso a integração necessite
autorização de ambiente, o executor deve concluir preparativos independentes e
pedir somente o acesso/ação concreta necessária, sem reabrir decisões aprovadas.
