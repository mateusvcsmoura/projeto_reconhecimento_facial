# Prompt de execução — 007 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório `projeto_reconhecimento_facial`.

**Execute a task 007: automatizar captura de cadastro e confirmação de presença, sem ESPAÇO/ENTER no fluxo padrão. Desenho e plano estão definidos e aprovados internamente. Apenas execute, teste, documente e faça commit + push na main ao terminar. Não reabra brainstorming, não delegue nem solicite aprovação rotineira.**

Leia AGENTS.md atualizado, CLAUDE.md, instructions/, `tasks/006-facial-landmarks/RESULTADO.md` e integralmente:

1. `tasks/007-captura-automatica/DESENHO.md`
2. `tasks/007-captura-automatica/PLANO.md`

Use Superpowers executing-plans e testes/verificação apropriados. A aprovação interna é autorizada pelo AGENTS.md; permissões obrigatórias do ambiente continuam valendo.

## Comportamento fechado

- Câmera aberta inicia busca automaticamente. Cadastro continua pedindo nome/matrícula e consentimento antes de abrir câmera.
- Uma operação por sessão: cadastrar OU registrar presença; depois fechar câmera e retornar ao menu. Se presença já existir hoje, informar e encerrar. Não criar modo de fila contínua.
- Esperar 5 segundos configuráveis de sequência válida e pelo menos três observações distintas; sample0.5s, idade/gap máximo2s. Os detalhes de timestamps e validade estão no desenho. Não capturar apenas por timer.
- Cadastro sonda com validação existente sem gerar embeddings/gravar; ao atingir critérios, nova captura final gera FacePreparada e só então persiste, após verificar idade e cancelamento. Separar preparação/conclusão no caso de uso mantendo executar compatível.
- Reconhecimento mantém a mesma identidade e revalida um frame novo antes de registrar. None, rejeição, troca de identidade ou expiração reiniciam. Temporal habilitado acrescenta requisitos atuais; desabilitado não remove mínimo3 automático.
- ESC cancela antes de persistir; SPACE/ENTER não antecipam ação. Após inferência final, processar ESC e frescor antes de gravar. Falhas técnicas encerram com erro explícito, sem retry de gravação.
- Flag `FACE_AUTO_CAPTURE_ENABLED=true` por padrão conforme solicitação; false conserva fluxo manual. Não mudar defaults das políticas existentes.
- Landmarks são visuais: não usar desenho ou resultado do worker como aprovação para salvar. Preservar processo isolado e pixels brutos; conferir idade depois de renderizar, pois o viewer pode demorar.

## Escopo e dependências

Nenhuma biblioteca nova, instalação, atualização de ambiente ou download. Reutilizar serviços, NumPy, relógio monotônico, casos de uso e fixtures. Código novo concentrado no controlador puro e orquestração; evitar reescrita dos fluxos manuais.

Não abrir `.env`, câmera, banco ou dados reais. Não executar migrations, app principal, integração/BDD dependente de banco ou experimentos biométricos. Não armazenar foto na verificação, alterar threshold0.30/antispoofing, processar a foto da conversa, reimplementar worker006 ou modificar resultados históricos. Não inferir que cadastro permite pesquisa. Testes usam arrays e serviços dublados; roteiro visual manual fica para o usuário e deve ser declarado pendente quando não executado.

Entregar implementação, testes pertinentes, `.env.example`, documentação indicada no plano, `tasks/007-captura-automatica/RESULTADO.md` e índice atualizado. Relatar resultados reais; não usar contagens históricas como se fossem desta execução. Não alegar melhora de acurácia por contagem ou tempo.

## Commit + push na main

Permanece a autorização explícita do usuário para estes pacotes: **fazer commit e push das alterações na main quando terminar**.

1. Registrar status/branch/HEAD; base preparada `f4763c7`, main. Preservar alterações alheias, memórias e temporários. Executar no checkout main atual, sem branch/worktree alternativa.
2. Conferir remoto sem expor credenciais, executar git fetch origin e inspecionar divergência/commits locais. Não publicar commits desconhecidos. Se somente atrás, fast-forward quando preservar trabalho; impedimento real deve ser reportado.
3. Concluir testes unitários pertinentes, Ruff/mypy, formato, revisão dos contratos e git diff --check. Falha obrigatória impede declarar/publicar tarefa concluída; não contornar testes.
4. Criar RESULTADO.md antes do commit, com resultados e estado honesto. Fazer staging por caminhos explícitos só da task, incluindo pacote preparado. Não usar git add . / -A / commit -a.
5. Inspecionar git diff --cached --stat, --check e conteúdo staged. Commit **em PT-BR**, sugerido `feat: automatiza captura de cadastro e registro de presença`. **Sem Co-Authored-By; usar apenas identidade e credenciais Git já configuradas do solicitante, sem alterá-las.**
6. git push origin main, sem force, resets destrutivos, stash indiscriminado, limpeza de diretórios ou contorno de hooks/proteções. Se remoto avançar, integrar apenas preservando trabalho; caso contrário, reportar bloqueio.
7. Confirmar git rev-parse HEAD e git ls-remote origin refs/heads/main. Se houver atualização concorrente, fetch e verificação de ancestralidade antes de afirmar publicação. Informar hash na resposta final sem commit extra apenas para registrar o próprio hash.

Resposta final: fluxos automatizados, configurações, comandos/resultados, link de RESULTADO.md, limitações e publicação confirmada ou bloqueio concreto. Execute até a entrega; não responda apenas com novo plano.

## Regra obrigatória de commit e push

Antes de qualquer commit ou push, leia ou releia o arquivo AGENTS.md na raiz do repositório e siga suas instruções vigentes. A autorização desta tarefa pode limitar ou proibir a publicação; esta regra não amplia autorizações.

- Mensagens de commit sempre em PT-BR. Não se identifique como Co Author nem adicione Co-authored-by; use somente a identidade e as credenciais Git já configuradas do solicitante, sem reconfigurar autoria.
- Se a entrega envolver muitos arquivos ou unidades lógicas distintas, divida-a em commits separados e organizados por escopo; não agrupe mudanças independentes em um commit monolítico.
- Adicione ao staging apenas caminhos explícitos e revise git diff --cached --stat, git diff --cached --check e o conteúdo staged antes de cada commit. Faça push somente para o branch/remoto autorizado e sem force.
