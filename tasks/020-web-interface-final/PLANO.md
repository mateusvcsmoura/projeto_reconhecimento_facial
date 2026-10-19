# Plano executável — 020: Interface web responsiva e validação ponta a ponta

> Executor: **Luna 6 High**, inline, sem delegação. Usar
> `superpowers:executing-plans` quando disponível. Ler [DESENHO.md](DESENHO.md)
> e [contrato comum](../WEB-CONTRATO-EXECUCAO.md) integralmente.
> Este arquivo prepara uma execução futura; não a inicia nesta conversa.

**Objetivo:** Interface web responsiva e validação ponta a ponta.
**Dependências:** 019 e 019A com GATE_BACKEND_PARA_INTERFACE=APROVADO; todas as funcionalidades009–019A prontas e testadas.
**Stack:** arquitetura Python/PostgreSQL existente + componentes web definidos
pela009; acrescentar apenas dependência estritamente necessária ao escopo.
**Especificação:** [planejamento consolidado](../../docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md).
**Interface:** esta é a última task de desenvolvimento; exigir gates019 e 019A aprovados.

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

### 1. Verificar gates019/019A e contratos; listar todas as telas/estados antes de construir interface.

- [ ] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [ ] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [ ] Implementar somente esse passo, preservando contratos e regras anteriores.
- [ ] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 2. Implementar autenticação e painel/CRUD/aprovação/revisões/CSV consumindo APIs existentes, sem nova lógica de domínio.

- [ ] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [ ] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [ ] Implementar somente esse passo, preservando contratos e regras anteriores.
- [ ] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 3. Implementar cadastro3capturas e presença/desafio com permissão, feedback, acessibilidade e descarte de tracks/frames.

- [ ] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [ ] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [ ] Implementar somente esse passo, preservando contratos e regras anteriores.
- [ ] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 4. Adicionar E2E com fixtures e câmera fake, testes de polling15s, erro de rede/reload/idempotência e autorização.

- [ ] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [ ] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [ ] Implementar somente esse passo, preservando contratos e regras anteriores.
- [ ] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

### 5. Reexecutar regressões backend e aceitar UI; preparar ensaio móvel/real, backup pré-apresentação, contingência e gates operacionais finais, sem deploy automático.

- [ ] Escrever primeiro os casos automatizados pertinentes do desenho em arquivos
  de teste previstos; usar fakes/relógio/embeddings sintéticos conforme a fronteira.
- [ ] Executar os testes focados no ambiente permitido e registrar falha esperada
  antes da implementação, quando se tratar de comportamento novo.
- [ ] Implementar somente esse passo, preservando contratos e regras anteriores.
- [ ] Reexecutar os testes focados e registrar o resultado; preparar separadamente
  testes que dependem de autorização de banco/infraestrutura ainda ausente.

## 3. Revisão de aceite específica

- [ ] Provar: Fluxo completo no navegador com backend testado; matrícula existente não permite assumir identidade.
- [ ] Provar: Professor não acessa fotos/embeddings; usuário de outra turma negado mesmo alterandoURL.
- [ ] Provar: Captura automática após permissão e condições, três referências no cadastro, replay/erro nunca exibem sucesso.
- [ ] Provar: Polling15s sem duplicar requests; reload consulta tentativa em vez de consumir quota; CSV correto.
- [ ] Provar: Android/Chrome, iOS/Safari e notebook planejados/ensaiados com evidência; falhas de câmera/rede e revisão acessível cobertas.

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
- [ ] Não avançar à próxima task automaticamente. Interface completa sobre funcionalidades comprovadas, E2E aprovado com evidências; nenhuma decisão biométrica no cliente. Prontidão para dados reais/deploy só se gates operacionais adicionais forem efetivamente cumpridos.
- [ ] Commit/push somente se explicitamente autorizados para a execução corrente;
  observar o contrato comum. Este plano não publica alterações por conta própria.
