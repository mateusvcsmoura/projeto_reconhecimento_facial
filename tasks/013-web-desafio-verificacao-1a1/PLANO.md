# Plano executável — 013: Desafio facial no servidor e verificação 1:1

> Executor: **Luna 6 High**, inline, sem delegação. Usar
> `superpowers:executing-plans` quando disponível. Ler [DESENHO.md](DESENHO.md)
> e [contrato comum](../WEB-CONTRATO-EXECUCAO.md) integralmente.
> Execução autorizada em 18/10/2026; evidências e limites em [RESULTADO.md](RESULTADO.md).

**Objetivo:** Desafio facial no servidor e verificação 1:1.
**Dependências:** 012.
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

### 1. Escrever testes puros de mediana, limiar inclusivo0,30, incompatibilidade, referência trocada e não busca global.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 2. Implementar máquina de desafio com nonces, ordenação, expiração e validação no servidor usando detector fake.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 3. Integrar adaptador de pose Linux e fila012 sem alterar CLI/overlay desnecessariamente; documentar protocolo completo de frames.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 4. Implementar antispoofing obrigatório, consistência de rosto e resultado estruturado sem vazamento.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 5. Preparar ensaios autorizados de movimento/acessibilidade e registrar quais verificações reais não foram executadas.

- [x] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [x] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [x] Implementar somente esse passo, preservando contratos e regras anteriores.
- [x] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

## 3. Revisão de aceite específica

- [x] Provar: Distâncias [0,20;0,29;0,80] aceitam identidade; [0,20;0,31;0,80] recusam; igualdade0,30 aceita conforme política.
- [x] Provar: Frame estático, sequência invertida, nonce errado, etapa antiga e cliente declarando sucesso não aprovam.
- [x] Provar: Frames de duas identidades/múltiplas faces recusam; ausência de evidência de vida não aprova.
- [x] Provar: Serviço não retorna foto/embedding ao professor e não registra presença; risco residual documentado.

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
- [x] Não avançar à próxima task automaticamente. Verificador1:1 e desafio com protocolo implementado/testado funcionalmente, sem threshold alterado nem promessa de acurácia. Validação biométrica real pendente bloqueia liberação pública, não é substituída por mocks.
- [x] Commit/push somente se explicitamente autorizados para a execução corrente;
  observar o contrato comum. Este plano não publica alterações por conta própria.
