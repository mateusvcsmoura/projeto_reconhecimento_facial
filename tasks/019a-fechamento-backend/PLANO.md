# Plano executável — Task 019A

- **Objetivo:** fechar o gate funcional antes da task 020.
- **Arquitetura/stack:** preservar Python, FastAPI, PostgreSQL, worker único, Docker Compose, Caddy e rclone crypt.
- **Especificação:** [DESENHO.md](DESENHO.md), resultados 017–019 e planejamento web consolidado.
- **Workflow:** usar `superpowers:executing-plans`, quando disponível, inline; executar uma etapa por vez.
- **Restrições globais:** sem interface, produção, Drive, banco `escola`, biometria real, mudança de limiar ou deploy. Respeitar permissões obrigatórias do ambiente.
- **Foco da revisão:** cifra inválida, exclusões após restore, reinício com job pendente, abuso do cadastro público e isolamento entre professores.

- [x] **1. Preparar ambiente e matriz de evidências.**
  - Ler AGENTS.md, CLAUDE.md, contrato comum, WEB-MIGRACOES.md, desenhos e resultados 017–019 e os testes antes de executá-los.
  - Registrar HEAD, branch, alterações existentes e versões Python/PostgreSQL/rclone/Docker/Compose; preservar temporários e trabalho alheio.
  - Verificar `docker info`, `docker compose version` e disponibilidade de `rclone`, `pg_dump`, `pg_restore` e `psql` sem imprimir segredos.
  - Usar ambiente local descartável autorizado. Se faltar acesso ao daemon ou instalação exigir permissão, registrar o impedimento exato; não desativar controles nem declarar aprovação.
  - Mapear requisito → teste → comando → resultado, reaproveitando provas válidas sem tratar resultados antigos como execução atual.

- [ ] **2. Comprovar backup e restore reais — bloqueado por ambiente.**
  - Trabalhar em `tests/integration/test_web_restore_local.py`, `src/application/services/web_backup.py`, `src/infrastructure/backup/` e scripts de backup/restore apenas quando uma falha justificar correção.
  - Criar origem e destino PostgreSQL descartáveis identificados, diretórios privados separados e config crypt temporária fora do Git; usar bytes e embeddings sintéticos.
  - Preparar registros e arquivos conhecidos, gerar backup pelo fluxo real com `pg_dump`, cifrar com rclone crypt e restaurar usando `pg_restore`.
  - Assertar contagens/relacionamentos, conteúdo dos registros e hashes de arquivos restaurados; não se limitar ao código de saída do processo.
  - Provar exclusões posteriores ao snapshot reaplicadas e credenciais/sessões restauradas invalidadas.
  - Provar corrupção/chave incorreta recusadas, alvo não descartável recusado, manutenção liberada após falha e ausência de staging em claro ao finalizar.
  - Exercitar bloqueio de escritas e drenagem/lock com PostgreSQL real para demonstrar consistência banco/arquivos.
  - Executar o teste com seus opt-ins documentados, sem skips; registrar comandos sanitizados e resultado. Não conectar Google Drive.

- [ ] **3. Validar os artefatos Linux em execução — bloqueado por ambiente.**
  - Revisar `deploy/web/README.md`, `compose.yaml`, `Dockerfile`, `Caddyfile`, entrypoints e testes de deploy antes de iniciar serviços locais.
  - Usar projeto Compose exclusivo, secrets sintéticos, volumes descartáveis e portas de teste locais; não reutilizar volumes ou credenciais de produção.
  - Construir os targets app/worker/migrate/backup/postgres/caddy; executar `pip check`, `bash -n` nos scripts PostgreSQL e `caddy validate` na imagem efetiva.
  - Validar inicialização PostgreSQL/papéis, migração explícita no banco descartável, API, healthchecks, permissões UID/volumes e conectividade do proxy. Não emitir certificados públicos; usar configuração local de teste.
  - Exercitar worker único, reinício/lease, fila limitada, expiração e limpeza de capturas. Provar que falhas não geram presença.
  - Fazer smoke dos modelos locais e runtime sem GUI/rede de download; entrada sintética sem face deve ser recusada com segurança, sem alegar validação biométrica.
  - Recriar containers preservando volumes e verificar registros/referências sintéticos; verificar que banco/arquivos privados não ficam acessíveis pela entrada pública.
  - Inspecionar logs sintéticos para ausência de tokens, senhas, cookies, frames e embeddings.
  - Corrigir apenas erros reproduzidos, adicionar regressões e registrar versões APT resolvidas. Não marcar testes estáticos como prova de runtime.

- [ ] **4. Completar proteção contra abuso no cadastro público — implementação e testes HTTP passaram; falta executar a concorrência PostgreSQL.**
  - Arquivos principais: `src/presentation/web/routes/cadastros.py`, composição `src/web_main.py`, configuração e repositório de limitação existente; testes em `tests/unit/test_cadastro_web_rate_limit.py` (novo).
  - Reaproveitar limitação persistida e chaves HMAC existentes, com namespaces separados; não armazenar matrícula/token/IP em claro nas chaves ou logs.
  - Cobrir emissão de credencial/solicitação, envio de capturas e consultas públicas. Aplicar a proteção antes de operações caras, inclusive em pedidos inválidos.
  - Adotar inicialmente limites configuráveis: 10 operações de criação/envio por minuto por origem e contexto, 60 consultas por minuto por credencial; teto agregado por origem configurável para impedir rotação ilimitada de links. Documentar que são guardas iniciais, sujeitos a medição.
  - Definir origem confiável atrás do Caddy; não aceitar `X-Forwarded-For` arbitrário nem agregar todos os alunos sob o IP do proxy. Testar acesso direto e cabeçalhos forjados.
  - Testar 429/Retry-After, reset por relógio, concorrência PostgreSQL, isolamento de chaves e respostas sem enumeração; considerar alunos compartilhando NAT ao ajustar teto agregado.
  - Preservar limites de payload, fila, consentimento e expiração. Não adicionar CAPTCHA.

- [ ] **5. Completar a cadeia funcional — teste PostgreSQL preparado, execução bloqueada por ausência do opt-in local.**
  - Expandir `tests/integration/test_web_fluxo_completo.py` até consulta do painel e exportação CSV do aluno/sessão criados nesse próprio cenário.
  - Verificar filtros, campos, ausência de biometria/tokens, CSV seguro, recusa de professor sem ownership e atualização da leitura após correção manual justificada/auditada.
  - Reaproveitar testes existentes para janela +120s, três tentativas, replay, matrícula existente, revogação, duplicidade e corrida revisão/worker; acrescentar testes somente onde a matriz mostrar lacuna.

- [ ] **6. Regressão, documentação e decisão — documentos atualizados; faltam suíte completa e validações estáticas finais antes de publicar.**
  - Executar testes novos/focados, unitários completos e integrações PostgreSQL pertinentes em bancos descartáveis. Inspecionar fixtures antes de rodar; não executar a suíte global contra configuração operacional.
  - Executar Ruff, formato, `python -m mypy src scripts` e `git diff --check`; guardar comandos completos sanitizados, totais, skips e justificativas.
  - Criar `RESULTADO.md` nesta pasta com evidências de cada item, limitações e os dois gates.
  - Atualizar resultados 017–019 por adendo datado, índice de tasks, AGENTS.md, CLAUDE.md e docs de estado/runtime/roadmap; preservar resultados históricos e distinguir schema local de outros ambientes.
  - Atualizar a dependência da 020 para incluir o fechamento 019A; não iniciar a interface automaticamente.
  - Aprovar `GATE_BACKEND_PARA_INTERFACE` somente com restore real, runtime local, controles de abuso e cadeia funcional comprovados. Checks obrigatórios ignorados mantêm o gate bloqueado.
  - Manter `GATE_OPERACIONAL_DADOS_REAIS=PENDENTE` enquanto faltarem provas operacionais autorizadas; listar responsável/pré-requisito para cada uma.
  - Quando esta task for solicitada para implementação, seguir a autorização vigente do AGENTS para commits PT-BR por escopo e push para main; reler AGENTS antes de publicar, revisar staging e excluir segredos/artefatos/alterações alheias. Sem force push.
