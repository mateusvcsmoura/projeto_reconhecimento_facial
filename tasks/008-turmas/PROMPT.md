# Prompt de execução — 008 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório `projeto_reconhecimento_facial`.

**Execute a task008: implementar CRUD de turmas e operações de alunos/presenças por turma, preparando a migration sem aplicá-la. Desenho e plano estão definidos e aprovados internamente. Apenas execute, teste o que está autorizado, documente e faça commit + push na main. Não reabra brainstorming nem delegue.**

Leia AGENTS.md atualizado, CLAUDE.md, instructions/, arquitetura, resultado007 e integralmente:

1. `tasks/008-turmas/DESENHO.md`
2. `tasks/008-turmas/MIGRACAO.md`
3. `tasks/008-turmas/PLANO.md`

Use Superpowers executing-plans e princípios de migration. Decisões rotineiras podem ser aprovadas internamente; isso não concede autorização para executar migrations.

## Decisões obrigatórias

- O usuário confirmou N:N: um aluno participa de várias turmas. Matrícula permanece **UK global**; biometria e consentimento ficam no cadastro único do aluno.
- Turma exige materia (texto 1–120, normalizado) e periodo exatamente matutino/diurno/noturno. ID interno; não exigir campo extra ou unicidade matéria/período.
- Cadastro novo dentro da turma cria aluno+vínculo em uma transação SQL. Matrícula existente deve ser vinculada, nunca duplicada/recapturada/sobrescrita. Não inventar consentimento ausente.
- Remover aluno da turma desativa vínculo; excluir aluno do sistema é ação global separada com confirmação e remoção de dados existente.
- Excluir turma é exclusão lógica, preservando histórico e alunos. Turmas excluídas ficam fora de cadastro/reconhecimento e podem ter histórico consultado.
- Presença única por turma+aluno+dia; duas turmas no mesmo dia são permitidas. Verificar vínculo/turma ativos no limite transacional antes de registrar, inclusive após reconhecimento automático.
- Galeria de reconhecimento deve ser filtrada por turma ativa no SQL. Nenhum fallback silencioso para galeria global. Limpar mapas/candidatos/temporais ao trocar turma.
- Preservar captura007, fallback manual, worker006, limiar0.30, antispoofing e políticas existentes. Não salvar nova foto na verificação.

## Migração e autorização

Preparar revisão após0003 conforme head real. Preservar presenças antigas com turma_id NULL; sem turma/período/matéria fictícios. Criar UK composta e índice parcial legado; adaptar importador SQLite ao conflito novo. Não executar importador.

**Não executar upgrade/downgrade, fixtures de integração/BDD com migrations, conexões a banco, TRUNCATE ou alterações de dados nesta tarefa.** AGENTS.md exige instrução explícita; o usuário pediu o pacote e não autorizou aplicar schema. Escrever migration/testes é permitido. Integração PostgreSQL e aplicação do schema ficam pendentes para etapa autorizada em ambiente descartável identificado. Não declarar sistema pronto no banco atual nem skips como testes aprovados.

Downgrade deve recusar antes de alterações destrutivas se houver dados de turmas/vínculos/presenças novas. A versão antiga usa a UK removida: documentar implantação coordenada com parada de escritores; não prometer compatibilidade simultânea. Nenhuma auto-migration no boot.

Sem dependências novas ou instalações. Não abrir .env, webcam, dados/embeddings reais ou imagem da conversa; não baixar pesos/datasets, alterar CI sem necessidade ou usar cadastros para pesquisa. Testar unitariamente com dados sintéticos e preparar testes PostgreSQL para execução futura.

## Entrega e publicação

Entregar código, migration, testes, documentação de turmas/transição, RESULTADO.md e índice. Documentar regras de exclusão, legado e prova de integração pendente. Nenhuma implementação deve apagar fotos de outro cadastro em corrida de matrícula; usar nome exclusivo por tentativa e limpeza restrita.

Permanece a autorização explícita do usuário destes pacotes: **commit + push na main ao terminar a etapa autorizada**. Isso publica código; não implanta nem migra banco.

1. Registrar branch/status/HEAD; preparação `6d56409`, main. Preservar trabalho alheio, pacotes antigos e temporários. Sem branch/worktree alternativa.
2. Conferir remoto sem expor credenciais; git fetch origin e inspeção de divergência/commits locais. Não publicar commits desconhecidos. Fast-forward só quando preservar trabalho; reportar impedimentos reais.
3. Concluir unitários e checks do plano. Falha obrigatória bloqueia declarar etapa concluída; ausência de integração autorizada deve ser registrada como pendência explícita.
4. Revisar diff/staged por caminhos explícitos da entrega; não usar git add . / -A / commit -a. Conferir git diff --cached --stat e --check, ausência de dados/modelos/segredos.
5. Commit em PT-BR, sugerido `feat: organiza alunos e presenças por turma`. Sem Co-Authored-By; usar apenas identidade/credenciais Git já configuradas do solicitante, sem alterá-las.
6. git push origin main, sem force, reset destrutivo, limpeza de diretórios ou contorno de hooks/proteções. Se houver avanço remoto, integrar apenas preservando trabalho; senão reportar bloqueio.
7. Confirmar git rev-parse HEAD e git ls-remote origin refs/heads/main; em corrida, fetch e ancestralidade. Informar hash na resposta final sem commit extra apenas para registrar o próprio hash.

Resposta final: CRUD/contexto implementados, UK e N:N preservados, comandos/resultados reais, links de documentação e RESULTADO.md, hash/confirmação de push e aviso claro **migration não aplicada; integração PostgreSQL pendente de autorização**. Não avançar para essa etapa por iniciativa própria.

## Regra obrigatória de commit e push

Antes de qualquer commit ou push, leia ou releia o arquivo AGENTS.md na raiz do repositório e siga suas instruções vigentes. A autorização desta tarefa pode limitar ou proibir a publicação; esta regra não amplia autorizações.

- Mensagens de commit sempre em PT-BR. Não se identifique como Co Author nem adicione Co-authored-by; use somente a identidade e as credenciais Git já configuradas do solicitante, sem reconfigurar autoria.
- Se a entrega envolver muitos arquivos ou unidades lógicas distintas, divida-a em commits separados e organizados por escopo; não agrupe mudanças independentes em um commit monolítico.
- Adicione ao staging apenas caminhos explícitos e revise git diff --cached --stat, git diff --cached --check e o conteúdo staged antes de cada commit. Faça push somente para o branch/remoto autorizado e sem force.
