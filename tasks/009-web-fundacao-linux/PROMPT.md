# Prompt de execução — 009 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório
`projeto_reconhecimento_facial`.

**Execute somente a task 009 — Fundação web e compatibilidade Linux. O desenho e o plano estão
definidos. Apenas execute o escopo autorizado, teste e documente; não reabra
brainstorming, não delegue e não avance automaticamente para outra task.**

## Leitura obrigatória

1. `AGENTS.md`, `CLAUDE.md`, instruções relevantes e arquitetura atual.
2. `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`.
3. `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`.
4. `tasks/WEB-CONTRATO-EXECUCAO.md` e `tasks/WEB-MIGRACOES.md`.
5. `tasks/009-web-fundacao-linux/DESENHO.md` e `tasks/009-web-fundacao-linux/PLANO.md`, integralmente.
6. Resultados reais das dependências: **008 como referência histórica; planejamento consolidado**.

Use Superpowers executing-plans quando disponível; aprove internamente escolhas
rotineiras, sem pedir confirmações de decisões já definidas. Isso não amplia
permissões de banco, dados reais, contratação ou publicação.

## Entrega específica

Adicionar FastAPI/Uvicorn como apresentação sobre os casos de uso existentes. Não substituir CLI nem ORM. Criar aplicação por fábrica sem importar DeepFace/MediaPipe na API; modelos pertencem ao futuro worker. Endpoints somente de saúde e contrato, sem interface visual, páginas de produto ou login ainda.

Python 3.12 e Ubuntu 24.04 x86_64 são candidatos a validar em ambiente descartável, não compatibilidade presumida. Resolver pins atuais com TensorFlow/tf-keras, PyTorch CPU, NumPy e OpenCV. Se pacote headless for necessário, isolar a imagem web e evitar distribuições cv2 sobrepostas; justificar qualquer mudança. MediaPipe mantém isolamento até prova de compatibilidade. Não baixar datasets ou usar webcam. Download de pesos exige autorização específica de rede/artefatos; ausência dessa prova é pendência registrada.

Criar bootstrap de configuração exclusivamente web: valores obrigatórios de banco, segredos e retenção não podem herdar silenciosamente defaults da CLI. Definir tipo de ambiente e guardas para banco descartável. Modelo de erros HTTP não contém mensagens brutas de biblioteca ou credenciais. Documentar rotas futuras no contrato compartilhado, sem implementá-las antecipadamente.

### Contratos que você deve respeitar

create_app(settings, services) -> FastAPI; injeção de serviços fakes em testes.
GET /health/live -> {status}; GET /health/ready -> {status, componentes}, sem detalhes internos.
Relógio injetável retorna datetime UTC aware. Configuração de produção nunca aponta implicitamente ao banco local.
Erro público padrão: {codigo, mensagem, request_id}; nenhum traceback.
Novas rotas usarão prefixo /api/v1 e a mesma origem.

### Provas mínimas

- API factory importa sem carregar modelos ou abrir banco/câmera.
- Configuração incompleta falha explicitamente; live não revela segredo; ready distingue componente indisponível.
- Regressões de main/Settings/CLI permanecem; ambiente web não contamina .venv-app/.venv-landmarks.

## Limites e conclusão

**Não criar interface, páginas, templates ou fluxo de câmera no navegador.** Use testes/cliente HTTP para provar a funcionalidade. UI fica exclusivamente na020.

Não executar migration, acessar banco operacional, conectar Google Drive,
provisionar VPS, realizar deploy ou usar rostos reais sem autorização específica
vigente. Preparar código/migration/testes não significa autorização para aplicá-los.
Não desabilitar antispoofing ou alterar threshold0,30 para fazer testes passarem.
Não interpretar matrícula informada como autenticação.

Fábrica web testável e runtime documentado, sem UI. Compatibilidade Linux executada ou pendência bloqueadora explícita para gate019; não marcar ambiente validado com testes mockados.

Ao terminar, criar `tasks/009-web-fundacao-linux/RESULTADO.md`, atualizar índice e relatar comandos
efetivos, contratos, pendências e estado dos gates. **Não fazer commit/push por
autorização herdada de tasks001–008.** A restrição da consolidação atual prevalece;
se o usuário autorizar explicitamente publicação nesta execução, fazer commit
em PT-BR e push na main conforme procedimento do contrato comum. Não contratar
ou implantar como consequência do push.
