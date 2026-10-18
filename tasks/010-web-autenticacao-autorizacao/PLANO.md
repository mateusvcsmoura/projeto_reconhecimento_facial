# Plano executável — 010: Contas, autenticação, professor responsável e auditoria

> Executor: **Luna 6 High**, inline, sem delegação. Usar
> `superpowers:executing-plans` quando disponível. Ler [DESENHO.md](DESENHO.md)
> e [contrato comum](../WEB-CONTRATO-EXECUCAO.md) integralmente.
> Executado em 18/10/2026 após autorização explícita para migrations e testes
> em bancos locais de desenvolvimento/teste. Evidências em [RESULTADO.md](RESULTADO.md).

**Objetivo:** Contas, autenticação, professor responsável e auditoria.
**Dependências:** 009.
**Stack:** arquitetura Python/PostgreSQL existente + componentes web definidos
pela009; acrescentar apenas dependência estritamente necessária ao escopo.
**Especificação:** [planejamento consolidado](../../docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md).
**Interface:** fora do escopo; nenhuma tela de produto até020.

## 1. Baseline e preparação

- [x] Ler AGENTS.md, CLAUDE.md, instructions relevantes, docs web, contrato comum,
  desenho/plano desta tarefa e RESULTADO das dependências.
- [x] Conferir branch, HEAD, status e código real; baseline documental original
  `02611f3`, mas executar sobre o estado efetivo após dependências. Preservar
  alterações alheias e arquivos temporários; não fazer reset/clean.
- [x] Confirmar se pré-requisitos estão implementados/testados. Documento pronto
  não é funcionalidade pronta. Registrar impedimento concreto sem simular êxito.
- [x] Mapear os arquivos listados no desenho e chamadas atuais antes de mudar
  assinaturas. Escolher o menor ponto responsável sem refatoração geral.

## 2. Passos de implementação e prova

### 1. Preparar migration incremental após head real para conta/professor, sessão, auditoria e responsável nullable apenas no legado.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; executar os testes PostgreSQL
  após autorização explícita em banco descartável identificado.

### 2. Escrever testes de login/reset/expiração/CSRF e fake de autorização; implementação sem tela HTML.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; executar os testes PostgreSQL
  após autorização explícita em banco descartável identificado.

### 3. Implementar hash, sessão, autenticação e autorização por turma; adicionar bootstrap explícito e reset administrativo.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; executar os testes PostgreSQL
  após autorização explícita em banco descartável identificado.

### 4. Adicionar testes PostgreSQL descartáveis de unicidade, auditoria atômica e ownership; não executar sem autorização de ambiente.

Autorização explícita registrada em 18/10/2026: o usuário autorizou executar
testes/migrations em bancos locais de desenvolvimento/teste, inclusive reset e
seed sintético. Para esta etapa, usar o banco descartável identificado e validar
host/nome antes de permitir que a fixture aplique DDL.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; executar os testes PostgreSQL
  após autorização explícita em banco descartável identificado.

### 5. Documentar política de senha, limites, credenciais temporárias, admin inicial e impacto nas turmas legadas.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; executar os testes PostgreSQL
  após autorização explícita em banco descartável identificado.

## 3. Revisão de aceite específica

- [x] Provar: Professor A não obtém nem altera turma B; admin é explícito; conta desativada perde sessões.
- [x] Provar: Expiração em 30min idle/8h absoluta e reset revogam; credencial temporária não reutiliza.
- [x] Provar: Falha de auditoria reverte; cookie/CSRF/Origin incorretos negam; senha/token não aparecem em logs.
- [x] Provar: Bootstrap repetido não cria admin público nem substitui senha silenciosamente.

## 4. Verificação final da etapa

- [x] Rodar unitários/HTTP focados e regressões afetadas; depois `python -m pytest
  tests/unit -p no:cacheprovider --basetemp <diretorio-temporario-exclusivo>`
  no ambiente de teste correto. Substituir o caminho antes de executar.
- [x] Inspecionar conftest/fixtures antes de selecionar integração/BDD. Nunca
  executar `pytest` global sem conferir se acessa banco. Integração exige
  ambiente descartável identificado e autorização específica.
- [x] Executar `python -m ruff check <arquivos-python-alterados>`,
  `python -m ruff format --check <arquivos-python-alterados>`,
  `python -m mypy src scripts` e `git diff --check`; registrar comandos
  resolvidos, resultado e limitações do ambiente, sem instalar tooling em
  ambiente de produção para contornar erro.
- [x] Verificar ausência de biometria/segredos/arquivos gerados sensíveis no diff;
  conferir que não há mudanças de interface antecipadas fora de020.
- [x] Se etapa envolver SQL, não considerar metadata/mocks prova de locks ou
  migrations. Distinguir “preparado” de “executado” no resultado.

## 5. Documentação e encerramento

- [x] Criar `RESULTADO.md` nesta pasta: HEAD inicial, arquivos, contratos,
  comandos/resultados efetivos, testes não executados, motivo, riscos e status.
- [x] Atualizar o índice e documentos atuais apenas no que foi entregue; não
  marcar deploy, banco aplicado ou avaliação biométrica sem evidência.
- [x] Não avançar à próxima task automaticamente. A autenticação e a autorização
  foram exercitadas por HTTP/testes, sem interface; `0005` foi aplicada ao banco local,
  e nenhuma conta real foi criada.
- [x] Após autorização explícita do usuário, separar implementação, testes e
  documentação em commits e publicar na `main`, sem deploy.
