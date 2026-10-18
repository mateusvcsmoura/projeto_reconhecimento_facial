# Prompt de execução — 020 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório
`projeto_reconhecimento_facial`.

**Execute somente a task 020 — Interface web responsiva e validação ponta a ponta. O desenho e o plano estão
definidos. Apenas execute o escopo autorizado, teste e documente; não reabra
brainstorming, não delegue e não avance automaticamente para outra task.**

## Leitura obrigatória

1. `AGENTS.md`, `CLAUDE.md`, instruções relevantes e arquitetura atual.
2. `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`.
3. `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`.
4. `tasks/WEB-CONTRATO-EXECUCAO.md` e `tasks/WEB-MIGRACOES.md`.
5. `tasks/020-web-interface-final/DESENHO.md` e `tasks/020-web-interface-final/PLANO.md`, integralmente.
6. Resultados reais das dependências: **019 com GATE_BACKEND_PARA_INTERFACE=APROVADO; todas as funcionalidades009–018 prontas e testadas**.

Use Superpowers executing-plans quando disponível; aprove internamente escolhas
rotineiras, sem pedir confirmações de decisões já definidas. Isso não amplia
permissões de banco, dados reais, contratação ou publicação.

## Entrega específica

Única task de interface do pacote, deliberadamente por último. Consumir APIs já validadas, sem criar regras de negócio em JavaScript nem resolver funcionalidades faltantes escondidas naUI. Se um backend não cumprir contrato, registrar regressão, corrigir na camada responsável e repetir gate019 antes da aceitação. Não iniciar020 em status 'testes preparados'.

Frontend simples mesma origem, responsivo, sem necessidade de React/SPA/build adicional. Telas: login/troca de senha; painel/CRUD turmas e vínculos; convites; solicitações/aprovação sem biometria; sessão/presenças/revisões; CSV; administração segura. Professor vê estado e metadados necessários, nunca fotografia/embedding. Polling15s sem sobreposição, último horário e erro de atualização.

Aluno cadastro: link, explicação/consentimento, nome/matrícula, permissão de câmera, três capturas guiadas, processamento, pendência e resultado. Aluno presença: matrícula, câmera, desafio orientado013, captura automática, feedback fila/validação e confirmação só após persistência. A captura deve respeitar etapas backend; não basta temporizador no cliente. Evitar esconder controles de acessibilidade; oferecer revisão quando movimento não for possível.

Usar getUserMedia em HTTPS, tratar câmera negada/ocupada/ausente, orientação/espelhamento e troca de dispositivo; parar tracks no fim/cancelamento. Texto/indicador acessíveis, teclado, foco, contraste e leitor de tela. Não exibir score como probabilidade de identidade ou promessa de segurança. Não salvar frames no storage do navegador nem enviar analytics.

Testes browser sintéticos primeiro, com câmera fake, e ensaio nos celulares/notebooks reais somente com autorização. Configurar staging/HTTPS ou VPS permanece ação separadamente autorizada, não implícita por existir task020. Finalizar roteiro de apresentação/contingência e encerramento sem executar eliminação real.

### Contratos que você deve respeitar

Consumir OpenAPI/DTOs009–019, sem chamadas diretas ao banco/modelos.
Cliente de câmera implementa upload limitado e ordens do desafio; não decide horário/vida/identidade.
Painel usa GET /api/v1/turmas/{id}/painel a cada15s; status de operação usa endpoint próprio com backoff.
CSV usa endpoint autorizado, sem regenerar relatório biométrico no browser.
Estado final 'presença confirmada' depende de resultado persistido daAPI, nunca de sucesso local da câmera.

### Provas mínimas

- Fluxo completo no navegador com backend testado; matrícula existente não permite assumir identidade.
- Professor não acessa fotos/embeddings; usuário de outra turma negado mesmo alterandoURL.
- Captura automática após permissão e condições, três referências no cadastro, replay/erro nunca exibem sucesso.
- Polling15s sem duplicar requests; reload consulta tentativa em vez de consumir quota; CSV correto.
- Android/Chrome, iOS/Safari e notebook planejados/ensaiados com evidência; falhas de câmera/rede e revisão acessível cobertas.

## Limites e conclusão

**É a última task. Não começar sem GATE_BACKEND_PARA_INTERFACE=APROVADO na019.** E2E móvel acontece aqui; gates de dados reais/deploy continuam independentes.

Não executar migration, acessar banco operacional, conectar Google Drive,
provisionar VPS, realizar deploy ou usar rostos reais sem autorização específica
vigente. Preparar código/migration/testes não significa autorização para aplicá-los.
Não desabilitar antispoofing ou alterar threshold0,30 para fazer testes passarem.
Não interpretar matrícula informada como autenticação.

Interface completa sobre funcionalidades comprovadas, E2E aprovado com evidências; nenhuma decisão biométrica no cliente. Prontidão para dados reais/deploy só se gates operacionais adicionais forem efetivamente cumpridos.

Ao terminar, criar `tasks/020-web-interface-final/RESULTADO.md`, atualizar índice e relatar comandos
efetivos, contratos, pendências e estado dos gates. **Não fazer commit/push por
autorização herdada de tasks001–008.** A restrição da consolidação atual prevalece;
se o usuário autorizar explicitamente publicação nesta execução, fazer commit
em PT-BR e push na main conforme procedimento do contrato comum. Não contratar
ou implantar como consequência do push.

## Regra obrigatória de commit e push

Antes de qualquer commit ou push, leia ou releia o arquivo AGENTS.md na raiz do repositório e siga suas instruções vigentes. A autorização desta tarefa pode limitar ou proibir a publicação; esta regra não amplia autorizações.

- Mensagens de commit sempre em PT-BR. Não se identifique como Co Author nem adicione Co-authored-by; use somente a identidade e as credenciais Git já configuradas do solicitante, sem reconfigurar autoria.
- Se a entrega envolver muitos arquivos ou unidades lógicas distintas, divida-a em commits separados e organizados por escopo; não agrupe mudanças independentes em um commit monolítico.
- Adicione ao staging apenas caminhos explícitos e revise git diff --cached --stat, git diff --cached --check e o conteúdo staged antes de cada commit. Faça push somente para o branch/remoto autorizado e sem force.
