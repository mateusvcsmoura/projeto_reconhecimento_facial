# Plano executável — 020: Interface web responsiva e validação ponta a ponta

> Executor: **Luna 6 High**, inline, sem delegação. Usar
> `superpowers:executing-plans` quando disponível. Ler [DESENHO.md](DESENHO.md)
> e [contrato comum](../WEB-CONTRATO-EXECUCAO.md) integralmente.
> Estado desta execução: implementação parcial; ver [RESULTADO.md](RESULTADO.md).

**Objetivo:** Interface web responsiva e validação ponta a ponta.
**Dependências:** 019 e 019A com `GATE_BACKEND_PARA_INTERFACE=APROVADO`; funcionalidades 009–019A implementadas e testadas conforme seus resultados.
**Stack:** arquitetura Python/PostgreSQL existente + componentes web definidos
pela009; acrescentar apenas dependência estritamente necessária ao escopo.
**Especificação:** [planejamento consolidado](../../docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md).
**Interface:** esta é a última task de desenvolvimento; exigir gates019 e 019A aprovados.

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

### 1. Verificar gates 019/019A, contratos e telas.

- [x] Confirmar nos resultados que o gate de backend está aprovado e ler APIs/DTOs existentes.
- [x] Mapear páginas, estados e contratos consumidos antes de implementar.
- [x] Registrar a fronteira: servidor iniciado com configuração sintética; nenhum banco operacional acessado.

### 2. Implementar painel do professor e integração com as APIs existentes.

- [x] Implementar autenticação, gestão do professor, solicitações, sessões, revisões e CSV consumindo as rotas atuais.
- [x] Manter regra de identidade, decisão facial e persistência no backend; não expor imagem ou embedding no painel.
- [ ] Executar E2E autenticado com PostgreSQL descartável e verificar professor de outra turma nesta interface.

### 3. Implementar os fluxos públicos de cadastro e presença.

- [x] Implementar cadastro e presença por link, câmera, fluxo guiado, envio em memória e consulta de estado no servidor.
- [x] Parar tracks e limpar polling ao sair; manter captura e revisão acessíveis por teclado.
- [x] Garantir que a interface só anuncia presença confirmada após o estado final persistido retornado pela API.
- [ ] Validar câmera e fluxo completo em navegador real; não havia navegador disponível pelo CUA.

### 4. Adicionar testes sintéticos e validar os contratos.

- [x] Adicionar testes Node para polling sem sobreposição, backoff, cancelamento, câmera fake e boot da página.
- [x] Adicionar testes ASGI para páginas, assets, cabeçalhos e resposta JSON para rota desconhecida.
- [ ] Cobrir no browser recarga/idempotência, CSV e autorização entre turmas de ponta a ponta.

### 5. Subir a interface para inspeção e registrar gates pendentes.

- [x] Subir servidor local em `http://127.0.0.1:8000` com URL sintética de banco inexistente, sem conectar dados reais.
- [ ] Revisar no browser a matriz responsiva, acessibilidade visual e desempenho do canvas.
- [ ] Ensaiar em Android/Chrome, iOS/Safari e notebook; isso exige dispositivos e navegador disponíveis.

## 3. Revisão de aceite específica

- [x] Confirmar por inspeção/testes que a interface delega identidade e decisões ao backend e não expõe biometria.
- [x] Testar polling serial de 15 s, cancelamento, backoff e falha de permissão com doubles.
- [ ] Provar no browser o fluxo completo, autorização, reload/idempotência, CSV e matriz de dispositivos.

## 4. Verificação final da etapa

- [x] Rodar unitários/HTTP focados e regressões afetadas; depois `python -m pytest
  tests/unit -p no:cacheprovider --basetemp <diretorio-temporario-exclusivo>`
  no ambiente de teste correto. Substituir o caminho antes de executar.
- [ ] Inspecionar conftest/fixtures antes de selecionar integração/BDD. Nunca
  executar `pytest` global sem conferir se acessa banco. Integração exige
  ambiente descartável identificado e autorização específica.
- [x] Executar `python -m ruff check <arquivos-python-alterados>`,
  `python -m ruff format --check <arquivos-python-alterados>`,
  `python -m mypy src scripts` e `git diff --check`; registrar comandos
  resolvidos, resultado e limitações do ambiente, sem instalar tooling em
  ambiente de produção para contornar erro.
- [x] Verificar ausência de biometria/segredos/arquivos gerados sensíveis no diff;
  conferir que não há mudanças de interface antecipadas fora de020.
- [ ] Se etapa envolver SQL, não considerar metadata/mocks prova de locks ou
  migrations. Distinguir “preparado” de “executado” no resultado.

## 5. Documentação e encerramento

- [x] Criar `RESULTADO.md` nesta pasta: HEAD inicial, arquivos, contratos,
  comandos/resultados efetivos, testes não executados, motivo, riscos e status.
- [x] Atualizar o índice e documentos atuais apenas no que foi entregue; não
  marcar deploy, banco aplicado ou avaliação biométrica sem evidência.
- [ ] Não avançar à próxima task automaticamente. Interface parcial até prova visual e E2E em browser; gate operacional continua independente.
- [x] Commit/push autorizados pela solicitação corrente;
  observar o contrato comum. Este plano não publica alterações por conta própria.

## 6. Plano visual e responsivo complementar — 20/10/2026

- [x] Aplicar a direção visual do DESENHO e mapear landing, autenticação, painel, turma/sessão, aprovações, relatórios e fluxos dos alunos, preservando APIs e gates.
- [x] Registrar tokens, tipografia e estados. Não há arquivo/licença autorizada para Helvetica Now Display; usar fallback `"Helvetica Neue", Helvetica, Arial, sans-serif` sem bloquear a interface.
- [x] Implementar templates, CSS e módulos JavaScript locais em `src/presentation/web/`, sem build ou dependência frontend adicional.
- [x] Implementar os fluxos de professor/aluno e a landing com hero monocromático, sequência explicativa e FAQ FaceDiff.
- [x] Adaptar o canvas ao hero com coordenadas relativas, proteção contra distância zero, pares sem duplicação, opacidade limitada, DPR máximo 2, pausa em aba/viewport oculta e cleanup. Respeitar movimento reduzido.
- [x] Usar `<details>` para FAQ, com controles nativos acessíveis e respostas alinhadas aos contratos.
- [x] Adicionar magnetismo discreto apenas na landing, com cursor nativo, limites de deslocamento e desativação para toque/movimento reduzido.
- [x] Adicionar testes sintéticos em `tests/e2e/web/` para câmera fake, poller/backoff/cancelamento e montagem da landing/login. Esses testes não simulam um browser completo nem validam todos os fluxos por HTTP.
- [ ] Revisar visualmente 320/360/390/768/1024/1440/1920/2560px, paisagem, zoom 200%/400%, teclado virtual e safe areas. Não havia navegador disponível pelo CUA nesta execução.
- [ ] Medir no navegador carregamento e custo de canvas/cursor; nenhum dado de performance foi inventado.
- [x] Revisar a linguagem visual para conteúdo FaceDiff, hierarquia editorial, uso econômico de cards e ausência de métricas fictícias ou recursos comerciais.
- [x] Registrar fallback de fonte, comandos e limitações no RESULTADO; ensaio real em iOS/Android permanece pendente.
