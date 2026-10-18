# Plano executável — 012: Worker facial único, fila limitada e temporários

> Executor: **Luna 6 High**, inline, sem delegação. Usar
> `superpowers:executing-plans` quando disponível. Ler [DESENHO.md](DESENHO.md)
> e [contrato comum](../WEB-CONTRATO-EXECUCAO.md) integralmente.
> Execução concluída em 18/10/2026; consulte [RESULTADO.md](RESULTADO.md).

**Objetivo:** Worker facial único, fila limitada e temporários.
**Dependências:** 011 e runtime009 validado para a parte executada.
**Stack:** arquitetura Python/PostgreSQL existente + componentes web definidos
pela009; acrescentar apenas dependência estritamente necessária ao escopo.
**Especificação:** [planejamento consolidado](../../docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md).
**Interface:** fora do escopo; nenhuma tela de produto até020.

Execução concluída no workspace em 18/10/2026. Evidências e gates estão em
[RESULTADO.md](RESULTADO.md); o checklist abaixo foi atualizado ao final da
validação.

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

### 1. Definir schema/job/lease e contrato de storage temporário com limites e relógio injetável.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 2. Testar admissão 10+1, reserva concorrente, lease vencido, idempotência e limpeza com fakes.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 3. Implementar worker e aquecimento separado; usar executor fake para testes sem pesos.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 4. Preparar integração com PostgreSQL e smoke headless autorizado; medir saúde sem usar rostos reais.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 5. Documentar recuperação de falha, armazenamento, fila e ajustes reservados ao benchmark019.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

## 3. Revisão de aceite específica

- [x] Provar: Uma execução ativa e no máximo dez aguardando/reservadas sob corrida.
- [x] Provar: Timeout/restart/resultado tardio não duplicam inferência válida nem persistência.
- [x] Provar: Job de proprietário alheio não é consultável; payload excessivo falha antes de decodificar.
- [x] Provar: Arquivo ausente, modelo indisponível ou is_real ausente falham fechado; temporários removidos.

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
- [x] Não avançar à próxima task automaticamente. Fila/worker/temporários funcionais com testes de lógica e integração preparada; limites e estados públicos definidos. Sem UI e sem falsa prova de capacidade da VPS.
- [x] Commit/push somente se explicitamente autorizados para a execução corrente;
  observar o contrato comum. Este plano não publica alterações por conta própria.
