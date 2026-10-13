# Prompt de execução — tarefa 004 / Luna 6 High

Você é o executor **Luna 6, esforço High**, no repositório `projeto_reconhecimento_facial`.

**Execute a tarefa 004: aprofundar o benchmark de matching vetorizado. Desenho e plano já estão definidos: implemente o benchmark, teste, execute medições sintéticas, documente e publique. Não reabra brainstorming, não delegue nem peça aprovação de decisões rotineiras.** Esta numeração segue o roteiro da conversa: não é a frente de múltiplas referências do item 4 do AGENTS.md.

## Leia e execute

1. AGENTS.md, CLAUDE.md, instructions/ pertinentes e ARCHITECTURE.md.
2. `tasks/003-rejeicao-ambiguidade/RESULTADO.md`, somente como histórico.
3. `tasks/004-benchmark-matching/DESENHO.md`, contratos/protocolo/aceite.
4. `tasks/004-benchmark-matching/PLANO.md`, tarefas em ordem.

Use `superpowers:executing-plans`, TDD e verificação antes da conclusão quando disponíveis. Planos rotineiros podem ser aprovados internamente conforme AGENTS.md. Execute no próprio agente, em main do checkout atual, sem worktree/branch alternativa. Inspecione e adapte apenas divergências pequenas, justificando no relatório; impedimentos reais devem ser reportados.

## Escopo fechado

- Ampliar `scripts/benchmark_matcher.py` e criar testes unitários. **Não alterar src/** ou otimizar matcher durante esta tarefa.
- Comparar matcher real vetorizado com referência independente em laço Python/NumPy dot, sobre mesmos embeddings sintéticos 512D.
- Verificar equivalência de status/ID/distâncias antes de performance; discrepância bloqueia medições/publicação como benchmark válido.
- Medir latência por chamada, montagem e memória separadamente. Tracemalloc não é RSS; payload de array não é memória total. Não misturar profiling de memória com tempos.
- Modos padrão sem política e margem zero, cenários artificiais de referência/ortogonal/empate; margem positiva somente opcional explícita sem recomendação/calibração.
- Remover comparação estimada `2N*80ms`; não chamar a referência sequencial de protótipo DeepFace. Nenhuma inferência real neste benchmark.
- Fazer três execuções reais sequenciais do protocolo padrão depois dos testes, salvando apenas JSONs agregados novos no diretório de evidências da 004.

Não abrir dados/embeddings reais, `.env`, avaliacao/, storage/, câmera, modelo ou banco; não baixar pesos/datasets, instalar pacotes, executar migrations, mudar CI/configuração/dependências. Não implementar múltiplas referências, API/Neon, threads, gráficos ou outras melhorias. Não exigir speedup mínimo nem alegar acurácia. Testes de software e resultados de tempo são evidências distintas.

## Commit + push na main

Permanece a instrução do usuário para estes pacotes: **fazer commit e push das alterações na main quando terminar**. Após implementar, testar, medir e documentar esta tarefa, publique sem nova confirmação rotineira. Essa autorização específica permite commits da tarefa; permissões obrigatórias do ambiente continuam valendo.

1. Registre status, branch e HEAD antes de editar. Na preparação, HEAD era `d8b6816`; verificar novamente. Preserve trabalhos alheios/temporários e arquivos históricos de tasks/001–003. O pacote preparado 004 e sua entrada no índice integram a entrega.
2. Confira remoto sem expor credenciais, faça `git fetch origin` e inspecione divergência/commits locais. Não criar remoto por suposição nem publicar commits preexistentes desconhecidos.
3. Se somente atrás e sem conflito com trabalho local, atualizar por fast-forward antes de implementar. Se não puder integrar preservando trabalho alheio, reporte; não usar reset destrutivo, force push, stash indiscriminado ou limpar diretórios.
4. Revise diff e adicione caminhos explícitos: script/testes, README/ARCHITECTURE/nota ADR-002, tasks/README.md e pacote 004. Inspecione JSONs agregados antes do staging. Não versionar arrays, caches ou `.env`. Não usar `git add .`, `git add -A`, `git commit -a`.
5. Confira conteúdo staged, `git diff --cached --stat` e `git diff --cached --check`. RESULTADO.md deve conter resultados efetivos e estado honesto anterior à publicação. Commit sugerido: `perf: amplia benchmark sintetico de matching`.
6. Execute `git push origin main`, sem force, sem desligar hooks ou contornar proteção. Se remoto avançar, inspecione e só integre preservando trabalho alheio; caso contrário, reporte bloqueio.
7. Confirme com `git rev-parse HEAD` e `git ls-remote origin refs/heads/main`. Se houver atualização concorrente, fetch e verificação de ancestralidade antes de alegar publicação. Informe hash/resultado na resposta final; não criar outro commit apenas para inserir seu próprio hash.

Falha relevante de teste/validação bloqueia publicação da tarefa como concluída. Corrija problemas do benchmark. Se surgir divergência real do matcher, falta de ambiente ou permissão, declare entrega parcial e evidência; não altere produção para mascarar resultado. Tempos desfavoráveis não são falha: reportá-los honestamente. Não implantar aplicação ou tocar dados após o push.

## Resposta final

Informar: benchmark implementado, comandos/testes e resultados reais, resumo das três medições, equivalência e limites de memória, links de RESULTADO.md/evidências, hash e confirmação de push ou bloqueio concreto.

Comece pela inspeção e execute até a entrega. Não responda somente com intenção/plano.
