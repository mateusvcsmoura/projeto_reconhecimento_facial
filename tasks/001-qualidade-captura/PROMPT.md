# Prompt de execução — Luna 6 High

Você é o agente executor **Luna 6, esforço High**, trabalhando no repositório `projeto_reconhecimento_facial`.

**Execute integralmente a tarefa 001 de qualidade de captura. O desenho e o plano já estão definidos. Sua função é implementar, testar, documentar e entregar; não elaborar outro plano, propor alternativas ou pedir aprovação de decisões rotineiras.** Não iniciar as melhorias 2–5. Não chamar outros agentes. Se houver divergência pequena entre o plano e os nomes atuais, adapte o mínimo necessário e registre a razão. Se uma incompatibilidade real impedir a execução segura, reporte-a com evidência.

## Leitura obrigatória

1. `AGENTS.md`, `CLAUDE.md`, instruções pertinentes de `instructions/` e `ARCHITECTURE.md`.
2. `tasks/001-qualidade-captura/DESENHO.md` — contratos, comportamento, parâmetros e limites.
3. `tasks/001-qualidade-captura/PLANO.md` — ordem, testes e critérios de conclusão.

Use `superpowers:executing-plans`, TDD e verificação antes da conclusão quando disponíveis. O usuário autorizou aprovação interna de planos/especificações rotineiros. Não reabrir brainstorming nem interromper a execução para pedir confirmação do desenho. Trabalhe no checkout atual em `main`; não criar worktree/branch alternativa para esta tarefa.

## Escopo autorizado

Implementar somente nitidez, iluminação e dimensão da face, reutilizar rejeição de múltiplos rostos, integrar recaptura/mensagens e evitar detecção duplicada e overlays na imagem analisada, conforme desenho. A política nova é optativa (`FACE_QUALITY_ENABLED=false` por padrão); fornecer ativação explícita documentada. Isso preserva o baseline enquanto os valores heurísticos não têm calibração biométrica.

Não alterar `FACE_THRESHOLD=0.30`, não desligar antispoofing, não usar rostos reais/datasets externos, não acessar PostgreSQL operacional, não executar migrations, não treinar modelos e não implementar orientação/pose, votação temporal, margem de ambiguidade ou múltiplas referências. Não alegar ganho de acurácia com testes sintéticos.

## Autorização explícita de commit e push

O usuário solicitou: **“adicione no prompt que ele deve fazer commit + push das alteracoes na main quando terminar”.** Portanto, ao terminar implementação, testes e documentação, **faça commit e push das alterações desta tarefa na branch `main`**, sem pedir uma segunda confirmação rotineira. Esta autorização específica supera a proibição genérica de commits automáticos sem instrução em AGENTS.md; não supera permissões obrigatórias do ambiente.

Procedimento:

1. Antes de editar, registre branch, HEAD e alterações preexistentes. Confirme `main`. Não sobrescreva ou inclua trabalho alheio. `AGENTS.md` já estava não rastreado na preparação; não o adicionar por conveniência. Os temporários `.pytest-stage4-*` também não pertencem à tarefa.
2. Verifique o remoto configurado e faça `git fetch origin` para conhecer `origin/main`, sem exibir credenciais. Se não houver `origin`, acesso ou main remota, reporte o bloqueio; não crie remoto por suposição.
3. Inspecione divergências e commits locais anteriores antes de publicar. A autorização cobre esta tarefa, não commits preexistentes desconhecidos. Se estiver apenas atrás e a atualização não conflitar com trabalho local, atualize por fast-forward antes de implementar. Se houver divergência ou conflito com trabalho alheio, não use reset, force push, stash indiscriminado ou rebase destrutivo; reporte o impedimento.
4. Conclua as verificações do plano e revise o diff. Não use `git add .`, `git add -A` nem `git commit -a`. Adicione apenas caminhos explicitamente revisados de código, testes, `.env.example`, documentação e `tasks/` desta entrega. Confira `git diff --cached --stat` e `git diff --cached --check`; revise o conteúdo staged.
5. Registre em RESULTADO.md os testes e o estado anterior à publicação, sem antecipar sucesso do push. Crie o commit com mensagem `feat: adiciona validacao de qualidade de captura`.
6. Execute `git push origin main`, sem `--force`, sem contornar proteção de branch e sem desativar hooks. Se o remoto avançar durante o trabalho, não force; inspecione e reporte a necessidade de integração se não puder resolvê-la sem afetar trabalho alheio.
7. Confirme o hash publicado com `git rev-parse HEAD` e `git ls-remote origin refs/heads/main`. Se o remoto coincidir com HEAD, reporte ambos. Se houver atualização concorrente, confirme a inclusão do commit pela ancestralidade após fetch antes de afirmar publicação. Não é necessário criar outro commit só para inserir o próprio hash no relatório.

Falha de teste relevante bloqueia conclusão e publicação. Corrija problemas da tarefa. Se existir falha preexistente impeditiva ou barreira real de acesso, declare a entrega parcial e os comandos efetivamente executados; nunca afirme commit/push aprovado sem evidência. Não implante aplicação nem altere dados após o push.

## Resposta final obrigatória

Informe, de forma breve: comportamento implementado, como habilitar a qualidade, testes/comandos e resultados, limitações não biométricas, caminho de RESULTADO.md, hash do commit e confirmação de push na main (ou motivo concreto do bloqueio).

Comece pela inspeção e execute o plano até a entrega. Não responda apenas com intenção de implementar.
