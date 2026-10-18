# Prompt de execução — tarefa 002 / Luna 6 High

Você é o executor **Luna 6, esforço High**, no repositório `projeto_reconhecimento_facial`.

**Execute a melhoria 2: consistência temporal. O desenho e o plano estão definidos; implemente, teste, documente e publique. Não reabra planejamento, não proponha alternativas, não delegue e não peça confirmação para decisões rotineiras.** Faça a inspeção necessária para preservar a tarefa 001 já concluída. Adapte divergências pequenas do código com justificativa no relatório; reporte impedimentos reais que não possam ser resolvidos no escopo.

## Leia e execute

1. `AGENTS.md`, `CLAUDE.md`, instruções pertinentes de `instructions/` e `ARCHITECTURE.md`.
2. `tasks/001-qualidade-captura/RESULTADO.md` para contexto histórico; não repetir a tarefa 001.
3. `tasks/002-consistencia-temporal/DESENHO.md` para contratos e critérios normativos.
4. `tasks/002-consistencia-temporal/PLANO.md` para sequência, testes e entrega.

Use `superpowers:executing-plans`, TDD e verificação antes da conclusão quando disponíveis. As decisões rotineiras do pacote foram aprovadas internamente conforme AGENTS.md. Trabalhe na `main` do checkout atual, sem worktree/branch alternativa e sem novos agentes.

## Escopo fechado

- Política optativa (`FACE_TEMPORAL_ENABLED=false`), 3 observações consecutivas, janela 5 s, validade 2 s, parâmetros configuráveis de engenharia.
- Domínio puro com IDs/timestamps; não guardar frames/embeddings. Um estado novo por sessão de reconhecimento.
- Interromper sequência em troca de identidade, desconhecido, ausência, múltiplos rostos ou recusa de qualidade. Expirar também entre inferências.
- Relógio monotônico injetado; marco anterior à leitura da câmera e nova consulta após inferência e ao receber Enter.
- Enter só elegível após sequência confirmada/fresca; ler um novo frame e reidentificar antes de registrar a mesma pessoa. Consumir sequência após tentativa concluída de registro, inclusive duplicata.
- Preservar modo desligado, qualidade da 001, limiar `0.30`, antispoofing, regra de uma presença por dia e intervalo de comparação de oito frames.

Não implementar ambiguidade top-2, pose, múltiplas referências, tracking, threads, otimização/benchmark, datasets ou outras etapas. Não abrir `.env` real, `avaliacao/`, `storage/`, webcam, banco operacional ou imagens faciais reais. Não baixar modelos, instalar pacotes, executar migrations ou avaliar biometria. Testar com tempo manual e dublês, sem sleeps. Testes sintéticos não provam aumento de acurácia; frames consecutivos são correlacionados.

## Commit e push obrigatórios ao concluir

Mantém-se a instrução do usuário para os pacotes de execução: **fazer commit + push das alterações na `main` quando terminar**. Ao concluir implementação, testes e documentação desta tarefa, execute a publicação sem pedir nova confirmação rotineira. A autorização específica permite commits desta entrega apesar da proibição genérica de commits sem instrução em AGENTS.md; permissões obrigatórias do ambiente continuam valendo.

1. Antes de editar, registre `git status --short`, branch e HEAD. Confira `main`; preserve modificações preexistentes. Na preparação da 002, HEAD era `9d30896` e AGENTS.md já era rastreado; não copiar a suposição antiga da 001 de que ele estava não rastreado. Temporários antigos do pytest não pertencem à tarefa.
2. Confira o remoto existente sem expor credenciais e execute `git fetch origin`. Inspecione relação com `origin/main` e commits locais anteriores. Não criar remoto por suposição nem publicar commits preexistentes desconhecidos junto com a tarefa.
3. Se estiver apenas atrás e não houver conflito com trabalho local, atualizar por fast-forward antes de implementar. Em divergência/conflito que não possa resolver sem afetar trabalho alheio, reportar o bloqueio; não usar reset destrutivo, force push, limpeza de diretórios ou stash indiscriminado.
4. Após verificações aprovadas, revisar diff e adicionar **caminhos explícitos**: código, testes, `.env.example`, README/ARCHITECTURE, `tasks/README.md` e `tasks/002-consistencia-temporal/` desta entrega. Não usar `git add .`, `git add -A`, `git commit -a` ou incluir arquivos da 001 sem necessidade autorizada.
5. Conferir `git diff --cached --stat`, `git diff --cached --check` e conteúdo staged. RESULTADO.md deve conter resultados efetivos e estado honesto anterior à publicação. Commit sugerido: `feat: adiciona confirmacao temporal de reconhecimento`.
6. Executar `git push origin main`, sem `--force`, sem desativar hooks nem contornar proteção da branch. Se o remoto avançar, inspecionar antes de qualquer integração; reportar impedimento se a solução afetar trabalho alheio.
7. Confirmar publicação com `git rev-parse HEAD` e `git ls-remote origin refs/heads/main`. Se não coincidirem por atualização concorrente, fazer fetch e verificar ancestralidade antes de alegar publicação. Não criar outro commit apenas para inserir o próprio hash no relatório; informar hash e resultado do push na resposta final.

Falhas relevantes de teste bloqueiam publicação. Corrija regressões da tarefa. Se ambiente, permissão ou falha preexistente impedir a conclusão, declare entrega parcial e evidência do impedimento, sem afirmar sucesso. Não implantar aplicação ou tocar dados depois do push.

## Resposta final

Informar: comportamento implementado, como habilitar, testes e resultados reais, limitações, caminho de RESULTADO.md, hash do commit e confirmação de push na main (ou bloqueio concreto).

Comece pela inspeção e prossiga até a entrega. Não responda somente com plano/intenção.

## Regra obrigatória de commit e push

Antes de qualquer commit ou push, leia ou releia o arquivo AGENTS.md na raiz do repositório e siga suas instruções vigentes. A autorização desta tarefa pode limitar ou proibir a publicação; esta regra não amplia autorizações.

- Mensagens de commit sempre em PT-BR. Não se identifique como Co Author nem adicione Co-authored-by; use somente a identidade e as credenciais Git já configuradas do solicitante, sem reconfigurar autoria.
- Se a entrega envolver muitos arquivos ou unidades lógicas distintas, divida-a em commits separados e organizados por escopo; não agrupe mudanças independentes em um commit monolítico.
- Adicione ao staging apenas caminhos explícitos e revise git diff --cached --stat, git diff --cached --check e o conteúdo staged antes de cada commit. Faça push somente para o branch/remoto autorizado e sem force.
