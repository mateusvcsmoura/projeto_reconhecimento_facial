# Prompt de execução — tarefa 003 / Luna 6 High

Você é o executor **Luna 6, esforço High**, no repositório `projeto_reconhecimento_facial`.

**Execute a melhoria 3: rejeição por ambiguidade entre identidades candidatas. O desenho e o plano estão definidos: implemente, teste, documente e publique. Não reabra brainstorming, não proponha outro plano, não delegue e não peça confirmação para decisões rotineiras.** Inspecione o código para preservar as tarefas 001 e 002; adapte somente divergências pequenas com justificativa. Reporte impedimentos reais que não possam ser resolvidos dentro do escopo.

## Leitura e execução

1. `AGENTS.md`, `CLAUDE.md`, instruções pertinentes de `instructions/`, `ARCHITECTURE.md`.
2. `tasks/002-consistencia-temporal/RESULTADO.md`, como evidência histórica; não repetir essa implementação.
3. `tasks/003-rejeicao-ambiguidade/DESENHO.md`, contratos e critérios normativos.
4. `tasks/003-rejeicao-ambiguidade/PLANO.md`, execução e testes em ordem.

Use `superpowers:executing-plans`, TDD e verificação antes da conclusão quando disponíveis. O projeto autoriza aprovação interna de decisões rotineiras. Execute no próprio agente e no checkout atual em `main`, sem worktree/branch alternativa.

## Escopo fechado

- `FACE_AMBIGUITY_ENABLED=false` por padrão e margem None. Ao habilitar, exigir margem explícita finita em [0,2]. **Não inventar default positivo.** Zero recusa apenas empates exatos; positivo recusa também gaps menores, sem alegar calibração.
- Política no matcher, usando uma única multiplicação matriz-vetor. d1 deve atender ao limiar antes de examinar d2. Concorrente é outra identidade, mesmo se sua distância exceder o limiar. Uma só identidade não é ambiguidade.
- Rejeitar empate e `d2-d1 < margem`; aceitar igualdade positiva à margem. Política desligada mantém o baseline, inclusive empate decidido pela primeira linha.
- Propagar `IdentificacaoAmbigua` pelo caso de uso e tratar especificamente nos três caminhos da CLI: sem temporal, temporal normal e confirmação no Enter. Limpar candidato/sequência e manter orientação, sem registrar nem fechar câmera por essa recusa.
- Preservar `FACE_THRESHOLD=0.30`, antispoofing, qualidade, temporalidade, frequência de comparação e confirmação manual. Não adicionar inferência para top-2 ou alterar cadastro/banco.

Não implementar múltiplas referências operacionais, pose, tracking, novos modelos, treinamento, benchmarks, API/Neon ou outras melhorias. Não abrir `.env` real, datasets, imagens/embeddings reais, webcam ou banco operacional. Não baixar pesos, instalar dependências ou executar migrations. Testes usam embeddings sintéticos, fakes e relógio manual; sem sleeps e sem alegar precisão facial.

## Commit e push ao concluir

Mantém-se a instrução do usuário para os pacotes: **fazer commit + push das alterações na `main` quando terminar**. Depois de implementar, validar e documentar a 003, publique sem pedir nova confirmação rotineira. A autorização específica supera a proibição genérica de commits sem instrução em AGENTS.md, mas não permissões obrigatórias do ambiente.

1. Registre status, branch e HEAD antes de editar. Na preparação, HEAD era `0e17c12`; confira novamente. Preserve trabalho alheio, temporários e documentos das tarefas 001/002. Os arquivos preparados em `tasks/003-*` e sua entrada no índice pertencem a esta entrega.
2. Confira o remoto existente sem expor credenciais e faça `git fetch origin`. Inspecione divergência/commits locais antes de publicar. Não criar remoto por suposição nem empurrar commits preexistentes desconhecidos junto com a tarefa.
3. Se estiver apenas atrás e sem conflito com trabalho local, atualizar por fast-forward antes de implementar. Em divergência que exija afetar trabalho alheio, reporte o impedimento; não usar reset destrutivo, force push, stash indiscriminado ou limpeza de diretórios.
4. Com testes aprovados, revise diff e adicione apenas caminhos explícitos de código/testes/documentação da tarefa, `.env.example`, `tasks/README.md` e `tasks/003-rejeicao-ambiguidade/`. Não usar `git add .`, `git add -A` ou `git commit -a`.
5. Confira `git diff --cached --stat`, `git diff --cached --check` e conteúdo staged. RESULTADO.md deve registrar comandos/resultados reais, sem antecipar push. Commit sugerido: `feat: rejeita identificacoes ambiguas por margem`.
6. Execute `git push origin main`, sem `--force`, sem desativar hooks ou contornar proteção de branch. Se o remoto avançar, inspecione e integre apenas se puder preservar trabalho alheio; caso contrário, reporte o bloqueio.
7. Confirme publicação com `git rev-parse HEAD` e `git ls-remote origin refs/heads/main`. Se houver atualização concorrente, faça fetch e verifique ancestralidade antes de alegar sucesso. Informar hash/resultado na resposta final; não criar outro commit apenas para inserir o próprio hash no relatório.

Falha relevante de teste bloqueia publicação. Corrija regressões da tarefa. Se ambiente/permissão/falha preexistente impedir conclusão, declare entrega parcial e evidência, sem inventar sucesso. Não implante aplicação ou altere dados depois do push.

## Resposta final

Informar: comportamento implementado, como habilitar e distinção entre margem zero/positiva, testes/resultados reais, limitações, caminho do RESULTADO.md, hash e confirmação do push (ou impedimento concreto).

Comece pela inspeção e prossiga até a entrega. Não responda apenas com intenção/plano.
