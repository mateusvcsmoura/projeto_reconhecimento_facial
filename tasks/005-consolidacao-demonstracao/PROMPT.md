# Prompt de execução — tarefa 005 / Luna 6 High

Você é o executor **Luna 6, esforço High**, no repositório `projeto_reconhecimento_facial`.

**Execute a tarefa 005: reconciliar documentação/memórias e organizar a demonstração acadêmica offline das melhorias 001–004. Desenho e plano estão definidos e aprovados internamente. Apenas execute, verifique, documente e faça commit + push na main quando terminar. Não reabra brainstorming, não delegue nem peça aprovação para decisões rotineiras.**

A numeração segue a conversa. Esta tarefa é distinta da Etapa 5 histórica de ML e do benchmark da prioridade 5 do AGENTS.md, já aprofundado na tarefa 004.

## Leitura e execução

1. Leia `AGENTS.md`, `CLAUDE.md` e instruções adicionais aplicáveis.
2. Leia integralmente `tasks/005-consolidacao-demonstracao/DESENHO.md` e `PLANO.md`.
3. Confira resultados 001–004, fontes no código e documentos indicados.
4. Execute o plano em ordem no checkout atual da main. Use Superpowers executing-plans e verification-before-completion se disponíveis. Esta entrega documental não requer TDD nem novos testes. Não criar branch/worktree alternativa.

Adapte somente divergências pequenas de nomes/caminhos, justificando no relatório. Lacunas de implementação descobertas ficam registradas como pendências; não ampliar escopo.

## Entrega fechada

- Criar `docs/ESTADO-ATUAL-E-EVIDENCIAS.md` com rastreabilidade e limites.
- Reconciliar `AGENTS.md`, `CLAUDE.md`, `REFACTORING_PLAN.md`, `README.md` e `ARCHITECTURE.md`.
- Atualizar em `docs/`: `apresentacao.md`, `ML-CONSOLIDACAO-ACADEMICA.md`, `ML-MATRIZ-RASTREABILIDADE.md`, `ML-GUIA-REPRODUTIBILIDADE.md`, `ML-ROTEIRO-APRESENTACAO.md` e `ML-PERGUNTAS-BANCA.md`.
- Executar seleção unitária e smoke offline previstos no plano; conferir links e diff.
- Criar `tasks/005-consolidacao-demonstracao/RESULTADO.md` e atualizar `tasks/README.md`.

Qualidade, temporal e ambiguidade são optativas e desligadas por padrão. Limiar operacional permanece `0.30`; margem positiva não está calibrada. A 004 registra 812 testes unitários e três medições: evidência histórica consultada, separada dos comandos desta execução. Benchmark sintético não mede acurácia facial, inferência DeepFace ou latência do pipeline completo. Tracemalloc não é RSS. Projeto de disciplina de IA, não TCC.

Não alterar código, scripts, testes, configuração, dependências, CI ou ADRs. Preservar `ML-ETAPA-*-RESULTADO.md`, baseline de arquitetura, pacotes 001–004 e JSONs. Não abrir `.env`, dados/embeddings reais, `storage/`, `avaliacao/`, câmera, modelo ou banco. Não baixar pesos/datasets, instalar pacotes, executar migrations ou desabilitar antispoofing. Não criar slides, gráficos, ferramentas ou aplicação de demonstração. Não editar/versionar memórias ignoradas.

## Commit + push na main — autorizado pelo usuário

Permanece a instrução explícita do usuário: **fazer commit e push das alterações na main quando terminar**. Publique após concluir e verificar esta tarefa, sem nova confirmação rotineira. Permissões obrigatórias do ambiente continuam valendo.

1. Confira status/branch/HEAD antes de editar. Base da preparação: `e5cc961` em main. Preserve alterações alheias e temporários. O pacote preparado da 005 e sua entrada no índice integram a entrega.
2. Confira remoto sem expor credenciais; execute `git fetch origin` e inspecione divergência/commits locais. Não presumir remoto nem publicar commits desconhecidos.
3. Se somente atrás, atualizar por fast-forward quando preservar trabalho local. Se integração segura não for possível, reporte. Não usar reset destrutivo, force push, limpeza recursiva ou stash indiscriminado.
4. Revise diff completo e faça staging somente dos caminhos explícitos da entrega e do pacote 005. Não usar `git add .`, `git add -A` ou `git commit -a`; não incluir trabalho alheio.
5. Confira `git diff --cached --stat`, `git diff --cached --check` e conteúdo staged. RESULTADO.md deve conter evidências reais e estado honesto anterior à publicação. Commit sugerido: `docs: consolida evidencias e demonstracao academica`.
6. Execute `git push origin main`, sem force ou contorno de hooks/proteções. Se o remoto avançar, inspecione e integre apenas preservando trabalho alheio; caso contrário, reporte bloqueio.
7. Confirme com `git rev-parse HEAD` e `git ls-remote origin refs/heads/main`. Havendo atualização concorrente, faça fetch e verifique ancestralidade antes de afirmar publicação. Informe hash/resultado na resposta final, sem commit adicional apenas para inserir seu próprio hash.

Falha de verificação obrigatória ou ausência de ambiente impede publicar/declarar a tarefa como concluída. Corrija problemas documentais; falhas de implementação ou permissões devem ser relatadas sem ampliar escopo. Não realizar deploy ou tocar dados após o push.

## Resposta final

Informar documentos consolidados, divergências corrigidas, comandos/resultados reais, links de roteiro/demonstração e RESULTADO.md, limitações e hash/confirmação de push ou bloqueio concreto.

Comece pela inspeção e execute até a entrega. Não responda apenas com outro plano.

## Regra obrigatória de commit e push

Antes de qualquer commit ou push, leia ou releia o arquivo AGENTS.md na raiz do repositório e siga suas instruções vigentes. A autorização desta tarefa pode limitar ou proibir a publicação; esta regra não amplia autorizações.

- Mensagens de commit sempre em PT-BR. Não se identifique como Co Author nem adicione Co-authored-by; use somente a identidade e as credenciais Git já configuradas do solicitante, sem reconfigurar autoria.
- Se a entrega envolver muitos arquivos ou unidades lógicas distintas, divida-a em commits separados e organizados por escopo; não agrupe mudanças independentes em um commit monolítico.
- Adicione ao staging apenas caminhos explícitos e revise git diff --cached --stat, git diff --cached --check e o conteúdo staged antes de cada commit. Faça push somente para o branch/remoto autorizado e sem force.
