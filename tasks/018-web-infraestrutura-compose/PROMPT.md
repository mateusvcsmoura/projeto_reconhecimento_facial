# Prompt de execução — 018 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório
`projeto_reconhecimento_facial`.

**Execute somente a task 018 — Artefatos de implantação Ubuntu, Compose e Caddy. O desenho e o plano estão
definidos. Apenas execute o escopo autorizado, teste e documente; não reabra
brainstorming, não delegue e não avance automaticamente para outra task.**

## Leitura obrigatória

1. `AGENTS.md`, `CLAUDE.md`, instruções relevantes e arquitetura atual.
2. `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`.
3. `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`.
4. `tasks/WEB-CONTRATO-EXECUCAO.md` e `tasks/WEB-MIGRACOES.md`.
5. `tasks/018-web-infraestrutura-compose/DESENHO.md` e `tasks/018-web-infraestrutura-compose/PLANO.md`, integralmente.
6. Resultados reais das dependências: **017**.

Use Superpowers executing-plans quando disponível; aprove internamente escolhas
rotineiras, sem pedir confirmações de decisões já definidas. Isso não amplia
permissões de banco, dados reais, contratação ou publicação.

## Entrega específica

Criar artefatos revisáveis para KVM2, não contratar/provisionar/deploy. Serviços: Caddy, appAPI sem modelos, worker facial único, PostgreSQL e backup agendado. Redes web e dados interna; somente TCP80/443 publicados, SSH22 no host restrito; PostgreSQL5432 e app8000 sem host binding. Backup tem saída HTTPS separada para destino futuro. Nenhum docker.sock na aplicação.

Volumes persistentes para PostgreSQL, referências privadas, modelos, Caddy e backups cifrados. Temporários compartilhados via tmpfs do host com bind limitado entre app/worker, não dois tmpfs independentes. Limitar tamanho e documentar swap/core dumps. Caddy não monta biometria. Contêineres sem privilégios desnecessários, secrets por arquivo restrito e imagem fixada.

Nenhuma migration no boot. Script/runbook explícito de banco/migração, base demonstrativa nova recomendada. Health/readiness separados, restart seguro de worker/leases. Limites de CPU/memória iniciais precisam de019, não números garantidos. Reserva para SO/banco/API.

Domínio Hostinger depende da elegibilidade real do contrato de1mês. Alternativa: subdomínio autorizado existente ou compra separada autorizada; nunca HTTPIP para câmera. Registrar renovação/preço verificado como histórico, sem contratar. Plano de rollback app/schema com backup e recusa de downgrade destrutivo.

Neste estágio não servir página provisória de produto: readiness/rotasAPI bastam para validar transporte. UI será020.

### Contratos que você deve respeitar

Compose usa serviços caddy/app/face-worker/postgres/backup; nomes internos e diretórios constam no README de deploy.
Variáveis: ambiente, domínio, timezone, fim_operacao, limites, caminhos de secrets; não credenciais no YAML.
Bootstrap/migration/backup são ações explícitas documentadas, não entrypoint automático.
Configuração suporta ligar frontend020 posteriormente na mesma origem sem segundo servidor.

### Provas mínimas

- Nenhuma porta5432/8000 publicada; somente app conecta às dependências necessárias.
- Referências não montadas no proxy; secrets não embutidos em imagem/compose.
- Migrations não rodam no boot; tmpfs compartilhado documentado e volume persistente sobrevive recreação em teste autorizado.
- Caddy config válida com placeholders sintéticos; ausência de UI não impede saúdeAPI.

## Limites e conclusão

**Não criar interface, páginas, templates ou fluxo de câmera no navegador.** Use testes/cliente HTTP para provar a funcionalidade. UI fica exclusivamente na020.

Não executar migration, acessar banco operacional, conectar Google Drive,
provisionar VPS, realizar deploy ou usar rostos reais sem autorização específica
vigente. Preparar código/migration/testes não significa autorização para aplicá-los.
Não desabilitar antispoofing ou alterar threshold0,30 para fazer testes passarem.
Não interpretar matrícula informada como autenticação.

Artefatos de infraestrutura revisados e prontos para ensaio autorizado; nenhum recurso contratado ou deploy realizado.

Ao terminar, criar `tasks/018-web-infraestrutura-compose/RESULTADO.md`, atualizar índice e relatar comandos
efetivos, contratos, pendências e estado dos gates. **Não fazer commit/push por
autorização herdada de tasks001–008.** A restrição da consolidação atual prevalece;
se o usuário autorizar explicitamente publicação nesta execução, fazer commit
em PT-BR e push na main conforme procedimento do contrato comum. Não contratar
ou implantar como consequência do push.
