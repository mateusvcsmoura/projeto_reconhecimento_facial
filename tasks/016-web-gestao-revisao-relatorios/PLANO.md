# Plano executável — 016: CRUD autorizado, revisão manual, auditoria e CSV

> Executor: **Luna 6 High**, inline, sem delegação. Usar
> `superpowers:executing-plans` quando disponível. Ler [DESENHO.md](DESENHO.md)
> e [contrato comum](../WEB-CONTRATO-EXECUCAO.md) integralmente.
> Este arquivo prepara uma execução futura; não a inicia nesta conversa.

**Objetivo:** CRUD autorizado, revisão manual, auditoria e CSV.
**Dependências:** 015.
**Stack:** arquitetura Python/PostgreSQL existente + componentes web definidos
pela009; acrescentar apenas dependência estritamente necessária ao escopo.
**Especificação:** [planejamento consolidado](../../docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md).
**Interface:** fora do escopo; nenhuma tela de produto até020.

## 1. Baseline e preparação

- [ ] Ler AGENTS.md, CLAUDE.md, instructions relevantes, docs web, contrato comum,
  desenho/plano desta tarefa e RESULTADO das dependências.
- [ ] Conferir branch, HEAD, status e código real; baseline documental original
  `02611f3`, mas executar sobre o estado efetivo após dependências. Preservar
  alterações alheias e arquivos temporários; não fazer reset/clean.
- [ ] Confirmar se pré-requisitos estão implementados/testados. Documento pronto
  não é funcionalidade pronta. Registrar impedimento concreto sem simular êxito.
- [ ] Mapear os arquivos listados no desenho e chamadas atuais antes de mudar
  assinaturas. Escolher o menor ponto responsável sem refatoração geral.

## 2. Passos de implementação e prova

### 1. Implementar revisão e correção com justificativa, autorização e versão; preparar schema/repositório conforme necessário.

- [ ] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [ ] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [ ] Implementar somente esse passo, preservando contratos e regras anteriores.
- [ ] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 2. Completar CRUD web sobre contratos existentes sem expor operações globais ao professor por acidente.

- [ ] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [ ] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [ ] Implementar somente esse passo, preservando contratos e regras anteriores.
- [ ] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 3. Implementar consulta agregada e CSV com filtros/fuso e proteção de fórmula.

- [ ] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [ ] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [ ] Implementar somente esse passo, preservando contratos e regras anteriores.
- [ ] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 4. Testar correção concorrente com worker, auditoria falhando e escopo professor/admin.

- [ ] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [ ] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [ ] Implementar somente esse passo, preservando contratos e regras anteriores.
- [ ] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 5. Documentar OpenAPI, filtros, formatos, proibições de exposição e exemplos sintéticos para020.

- [ ] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [ ] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [ ] Implementar somente esse passo, preservando contratos e regras anteriores.
- [ ] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

## 3. Revisão de aceite específica

- [ ] Provar: Justificativa vazia ou professor alheio não corrige; revisão não aprova automaticamente.
- [ ] Provar: Worker tardio não altera revisão; conflito de versão devolve erro explícito.
- [ ] Provar: Desvincular não apaga outras turmas; globaldelete é administrativo e audita sem biometria.
- [ ] Provar: CSV não vaza outra turma/biometria; trata fórmula, Unicode, vírgula e meia-noite/filtros.

## 4. Verificação final da etapa

- [ ] Rodar unitários/HTTP focados e regressões afetadas; depois `python -m pytest
  tests/unit -p no:cacheprovider --basetemp <diretorio-temporario-exclusivo>`
  no ambiente de teste correto. Substituir o caminho antes de executar.
- [ ] Inspecionar conftest/fixtures antes de selecionar integração/BDD. Nunca
  executar `pytest` global sem conferir se acessa banco. Integração exige
  ambiente descartável identificado e autorização específica.
- [ ] Executar `python -m ruff check <arquivos-python-alterados>`,
  `python -m ruff format --check <arquivos-python-alterados>`,
  `python -m mypy src scripts` e `git diff --check`; registrar comandos
  resolvidos, resultado e limitações do ambiente, sem instalar tooling em
  ambiente de produção para contornar erro.
- [ ] Verificar ausência de biometria/segredos/arquivos gerados sensíveis no diff;
  conferir que não há mudanças de interface antecipadas fora de020.
- [ ] Se etapa envolver SQL, não considerar metadata/mocks prova de locks ou
  migrations. Distinguir “preparado” de “executado” no resultado.

## 5. Documentação e encerramento

- [ ] Criar `RESULTADO.md` nesta pasta: HEAD inicial, arquivos, contratos,
  comandos/resultados efetivos, testes não executados, motivo, riscos e status.
- [ ] Atualizar o índice e documentos atuais apenas no que foi entregue; não
  marcar deploy, banco aplicado ou avaliação biométrica sem evidência.
- [ ] Não avançar à próxima task automaticamente. Todas as funcionalidades de gestão, presença e relatório disponíveis por API e cobertas por testes, sem interface visual.
- [ ] Commit/push somente se explicitamente autorizados para a execução corrente;
  observar o contrato comum. Este plano não publica alterações por conta própria.
