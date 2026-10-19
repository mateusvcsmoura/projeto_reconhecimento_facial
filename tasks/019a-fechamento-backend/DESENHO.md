# Task 019A — Fechamento das pendências antes da interface

- **Estado do planejamento:** registrado em 19/10/2026 antes da implementação.
- **Baseline inspecionado:** `main`, HEAD `1e7c608`. Inspeção documental e estática; os resultados históricos abaixo não foram reexecutados nesta revisão.
- **Objetivo:** fechar as pendências de 017–019 e emitir evidência suficiente para liberar a 020.
- **Executor previsto:** Luna 6 High, inline, sem delegação.
- **Evidências e diagnóstico:**
  - `../019-web-validacao-backend/RESULTADO.md`: gate explicitamente `BLOQUEADO_POR_AMBIENTE`; registra 1228 unitários e 20 integrações PostgreSQL aprovados, mas restore real ausente.
  - `../017-web-backup-retencao/RESULTADO.md`: implementação parcial; falta roundtrip cifrado com PostgreSQL, arquivos e exclusões. A 019 encontrou ferramentas PostgreSQL, mas não rclone; verificar novamente o ambiente, sem repetir esse diagnóstico como fato atual.
  - `tests/integration/test_web_restore_local.py`: executa restore de geração fornecida externamente e verifica código de saída; não cria o backup nem compara por si só os registros esperados de origem e destino. Expandir a prova integrada.
  - `../018-web-infraestrutura-compose/RESULTADO.md`: build, parser Caddy, permissões, healthchecks e persistência dos volumes não foram executados por falta de acesso ao daemon Docker.
  - `deploy/web/Dockerfile`: imagens-base por digest e rclone por checksum; pacotes APT transitivos não congelados. Registrar versões resolvidas e limitação de reprodutibilidade; isso isoladamente não comprova defeito funcional.
  - `src/presentation/web/routes/cadastros.py`: limites de tamanho existem, mas não há limitação de frequência equivalente à de presença. Login já possui controle próprio; não removê-lo ou duplicá-lo indiscriminadamente.
  - `tests/integration/test_web_fluxo_completo.py`: termina verificando presença persistida; painel e CSV possuem provas separadas, mas falta fechar a cadeia no mesmo cenário integrado previsto no plano 019.
  - `CLAUDE.md`: ainda descreve 0004 como não aplicada; `AGENTS.md` termina na 016. Corrigir o retrato atual com evidências, preservando históricos datados e sem inferir estado de bancos externos.
- **Desenho da solução:**
  - Reutilizar API FastAPI, repositórios PostgreSQL, worker serial, backup rclone crypt e Compose existentes.
  - Preferir correções pontuais nos componentes que falharem; não reescrever arquitetura nem adicionar serviços.
  - Executar provas locais isoladas com dados sintéticos; usar modelos locais autorizados somente para smoke técnico sem rostos reais.
  - Manter dois gates: backend para interface e operação com dados reais. Não converter benchmark fake em capacidade da KVM 2.
- **Fora do escopo:**
  - Telas, deploy, contratação, domínio, Google Drive real, alterações em `escola`, dados pessoais ou datasets externos.
  - Alteração do threshold `0.30`, remoção do anti-spoofing ou alegações de acurácia.
- **Pendências posteriores que não bloqueiam o desenvolvimento da interface:**
  - Benchmark real na KVM 2, limites/timeouts finais, DNS/HTTPS público e firewall do host.
  - OAuth/transferência/restore do Google Drive, custódia de chaves e retenção do provedor.
  - Consentimento, piloto biométrico autorizado, câmeras/navegadores móveis e ensaio da apresentação.
  - PSS em Windows indisponível não é defeito; medir em Linux quando aplicável.
  - Integração/BDD legada da 008 deve permanecer registrada separadamente; executar regressões relevantes se as correções atingirem seus módulos.

## Atualização de execução — 19/10/2026

A execução implementou o rate limit das rotas públicas de cadastro e ampliou
testes para o fluxo até painel/CSV, isolamento de professor, correção auditada,
concorrência do contador e reinício com job pendente. O resultado ficou parcial:
restore cifrado e runtime Compose/Linux não puderam ser executados por falta de
ferramentas e acesso ao daemon. Consulte [RESULTADO.md](RESULTADO.md); o gate do
backend permanece bloqueado por ambiente.
