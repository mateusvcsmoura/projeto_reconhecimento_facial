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

- [x] **2. Comprovar backup e restore reais — concluído em PostgreSQL/rclone descartáveis.**
  - O fluxo real gerou dump PostgreSQL, cifrou/transmitiu com rclone crypt e `cryptcheck`, e restaurou uma geração conhecida; 3 artefatos e schema `0011` foram verificados.
  - A comparação de origem/destino confirmou registros sintéticos, embedding de 512 dimensões, hash de referência, exclusão posterior ao snapshot, invalidação de credencial/sessão e limpeza do staging.
  - Chave incorreta, manifesto corrompido e alvo sem marcador de descarte foram recusados; o marcador e sentinela do alvo não descartável foram preservados.
  - Falha injetada liberou a manutenção e não deixou staging em claro. Sem Google Drive ou dados pessoais.

- [x] **3. Validar os artefatos Linux em execução — concluído em Compose local descartável.**
  - Targets app/worker/migrate/backup/postgres/caddy construídos; `pip check` passou nas imagens Python, `bash -n` no bootstrap PostgreSQL e `caddy validate` na imagem efetiva.
  - Corrigidos e cobertos por regressões: comando ausente no target PostgreSQL, autenticação local incompatível no bootstrap de papéis, capability de arquivo Caddy incompatível com o hardening e NumPy ausente no runtime HTTP.
  - PostgreSQL inicializou, as migrations chegaram a `0011`; `alembic current` e `alembic check` passaram. App/worker ficaram healthy; Caddy serviu HTTPS local e redirecionou HTTP.
  - App, worker e Caddy executaram como UID 10001, rootfs somente leitura, sem privilégios novos e sem capabilities; processos PostgreSQL usam UID 999.
  - Smoke pós-recriação carregou pesos FaceNet512 e MediaPipe locais; array sintético vazio produziu zero faces. Nenhuma webcam/rede de download foi usada.
  - Recriação dos serviços preservou volumes: após subir novamente, o destino continuou em `0011` com 21 tabelas e 3 linhas sintéticas; o volume privado reteve o marcador e 1 arquivo de referência.
  - Health HTTPS respondeu 200, caminho privado 404 e HTTP redirecionou com 308. Logs não continham credenciais, cookies ou payload vetorial.

- [x] **4. Completar proteção contra abuso no cadastro público — implementação, HTTP e concorrência PostgreSQL aprovadas.**
  - Arquivos principais: `src/presentation/web/routes/cadastros.py`, composição `src/web_main.py`, configuração e repositório de limitação existente; testes em `tests/unit/test_cadastro_web_rate_limit.py` (novo).
  - Reaproveitar limitação persistida e chaves HMAC existentes, com namespaces separados; não armazenar matrícula/token/IP em claro nas chaves ou logs.
  - Cobrir emissão de credencial/solicitação, envio de capturas e consultas públicas. Aplicar a proteção antes de operações caras, inclusive em pedidos inválidos.
  - Adotar inicialmente limites configuráveis: 10 operações de criação/envio por minuto por origem e contexto, 60 consultas por minuto por credencial; teto agregado por origem configurável para impedir rotação ilimitada de links. Documentar que são guardas iniciais, sujeitos a medição.
  - Definir origem confiável atrás do Caddy; não aceitar `X-Forwarded-For` arbitrário nem agregar todos os alunos sob o IP do proxy. Testar acesso direto e cabeçalhos forjados.
  - Testar 429/Retry-After, reset por relógio, concorrência PostgreSQL, isolamento de chaves e respostas sem enumeração; considerar alunos compartilhando NAT ao ajustar teto agregado.
  - Preservar limites de payload, fila, consentimento e expiração. Não adicionar CAPTCHA.

- [x] **5. Completar a cadeia funcional — fluxo HTTP/PostgreSQL aprovado até painel e CSV.**
  - Expandir `tests/integration/test_web_fluxo_completo.py` até consulta do painel e exportação CSV do aluno/sessão criados nesse próprio cenário.
  - Verificar filtros, campos, ausência de biometria/tokens, CSV seguro, recusa de professor sem ownership e atualização da leitura após correção manual justificada/auditada.
  - Reaproveitar testes existentes para janela +120s, três tentativas, replay, matrícula existente, revogação, duplicidade e corrida revisão/worker; acrescentar testes somente onde a matriz mostrar lacuna.

- [ ] **6. Regressão, documentação e decisão — provas e documentos atualizados; publicar o índice de tasks ficou pendente após bloqueio do auto-review.**
  - Executar testes novos/focados, unitários completos e integrações PostgreSQL pertinentes em bancos descartáveis. Inspecionar fixtures antes de rodar; não executar a suíte global contra configuração operacional.
  - Executar Ruff, formato, `python -m mypy src scripts` e `git diff --check`; guardar comandos completos sanitizados, totais, skips e justificativas.
  - Criar `RESULTADO.md` nesta pasta com evidências de cada item, limitações e os dois gates.
  - Atualizar resultados 017–019 por adendo datado, índice de tasks, AGENTS.md, CLAUDE.md e docs de estado/runtime/roadmap; preservar resultados históricos e distinguir schema local de outros ambientes.
  - Atualizar a dependência da 020 para incluir o fechamento 019A; não iniciar a interface automaticamente.
  - Aprovar `GATE_BACKEND_PARA_INTERFACE` somente com restore real, runtime local, controles de abuso e cadeia funcional comprovados. Checks obrigatórios ignorados mantêm o gate bloqueado.
  - Manter `GATE_OPERACIONAL_DADOS_REAIS=PENDENTE` enquanto faltarem provas operacionais autorizadas; listar responsável/pré-requisito para cada uma.
  - Quando esta task for solicitada para implementação, seguir a autorização vigente do AGENTS para commits PT-BR por escopo e push para main; reler AGENTS antes de publicar, revisar staging e excluir segredos/artefatos/alterações alheias. Sem force push.
  - O índice `tasks/README.md` já tinha alterações antes desta execução. O auto-review rejeitou seu staging por risco de publicar trabalho preexistente; mantive o arquivo como estava e o deixei fora dos commits. A atualização do índice requer aprovação explícita para prosseguir.
