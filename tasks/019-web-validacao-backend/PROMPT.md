# Prompt de execução — 019 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório
`projeto_reconhecimento_facial`.

**Execute somente a task 019 — Validação integrada do backend e gate para a interface. O desenho e o plano estão
definidos. Apenas execute o escopo autorizado, teste e documente; não reabra
brainstorming, não delegue e não avance automaticamente para outra task.**

## Leitura obrigatória

1. `AGENTS.md`, `CLAUDE.md`, instruções relevantes e arquitetura atual.
2. `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`.
3. `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`.
4. `tasks/WEB-CONTRATO-EXECUCAO.md` e `tasks/WEB-MIGRACOES.md`.
5. `tasks/019-web-validacao-backend/DESENHO.md` e `tasks/019-web-validacao-backend/PLANO.md`, integralmente.
6. Resultados reais das dependências: **009–018 implementadas; não basta existirem seus documentos**.

Use Superpowers executing-plans quando disponível; aprove internamente escolhas
rotineiras, sem pedir confirmações de decisões já definidas. Isso não amplia
permissões de banco, dados reais, contratação ou publicação.

## Entrega específica

Esta é a última entrega de funcionalidades/infraestrutura antes da interface. Executar aceitação integrada do backend usando clientes HTTP, fakes deML e dados sintéticos em banco PostgreSQL descartável expressamente autorizado. Sem HTML/CSS/JS de produto. Corrigir defeitos funcionais encontrados dentro de seu escopo, sem esconder falha com skip, desativação de segurança ou mocks substituindo provaSQL.

Duas conclusões separadas: GATE_BACKEND_PARA_INTERFACE e GATE_OPERACIONAL_DADOS_REAIS. O primeiro exige unitários/regressões, API ponta a ponta sintética, PostgreSQL real descartável com constraints/concorrência, validação de artefatos e roundtrip local cifrado. O segundo exige VPS medida, restoreDrive real autorizado, consentimento/identidade e prova com pessoas/dispositivos; normalmente permanece pendente até ensaio posterior à UI020. Não chamar gate funcional de validação biométrica.

Benchmark instrumentado: CPU/RAM/RSS/PSS, cold/warm, inferência/fila, p50/p95 e erros, taxa de chegada e limites1/2/5/10/excesso; distinguir fake throughput de inferência real. Rodar naKVM2 somente se provisionamento e uso autorizados separadamente; não contratar para cumprir benchmark. Definir timeout e recursos de produção só após evidência real. Ferramenta não ingere pasta real ou dataset por default.

A interface020 só começa se GATE_BACKEND_PARA_INTERFACE=APROVADO com evidências. Se banco descartável autorizado não estiver disponível, preparar testes e marcar BLOQUEADO_POR_AMBIENTE, sem declarar funcionalidades integralmente testadas. Concluir tarefas independentes antes de pedir autorização concreta para o ambiente. Não conectar ao banco local existente por conveniência.

### Contratos que você deve respeitar

RESULTADO.md deve conter duas linhas inequívocas:
GATE_BACKEND_PARA_INTERFACE: APROVADO | REPROVADO | BLOQUEADO_POR_AMBIENTE
GATE_OPERACIONAL_DADOS_REAIS: APROVADO | PENDENTE
Cada status aponta comandos, contagens, ambiente e artefatos. Gate operacional não pode ser APROVADO antes de ensaio móvel/restore externo.
Benchmark exporta JSON agregado sem frames/embeddings/matrículas/tokens e informa tipo de carga fake ou inferência autorizada.

### Provas mínimas

- ProfessorA/B, matrícula existente, três referências e ausência de aprovação cobertos no fluxo integrado.
- Duas sessões mesmo dia, duplicidade concorrente, tentativa4, envio tardio, revogação em fila e correção manual concorrente.
- Restore sintético local recompõe banco/fotos e reaplica exclusões; erro de upload/semchave explícito.
- CSV seguro, logs sem dados, artefatos sem porta pública de banco/biometria; nenhuma presença em falha técnica.

## Limites e conclusão

**Não criar interface, páginas, templates ou fluxo de câmera no navegador.** Use testes/cliente HTTP para provar a funcionalidade. UI fica exclusivamente na020.

Não executar migration, acessar banco operacional, conectar Google Drive,
provisionar VPS, realizar deploy ou usar rostos reais sem autorização específica
vigente. Preparar código/migration/testes não significa autorização para aplicá-los.
Não desabilitar antispoofing ou alterar threshold0,30 para fazer testes passarem.
Não interpretar matrícula informada como autenticação.

Gate de backend só aprovado com todos os checks obrigatórios efetivamente executados. UI não inicia em gate reprovado/bloqueado. Operação real permanece separada e sem simulação de aprovação.

Ao terminar, criar `tasks/019-web-validacao-backend/RESULTADO.md`, atualizar índice e relatar comandos
efetivos, contratos, pendências e estado dos gates. **Não fazer commit/push por
autorização herdada de tasks001–008.** A restrição da consolidação atual prevalece;
se o usuário autorizar explicitamente publicação nesta execução, fazer commit
em PT-BR e push na main conforme procedimento do contrato comum. Não contratar
ou implantar como consequência do push.
