# Resultado — task 011: referências e cadastro pendente

Data: 18/10/2026. Branch `main`; HEAD inicial `863d4cc31dde0082d528c4c05b9c173b44fc881f`.
O workspace estava limpo antes da implementação. Nenhum commit ou push foi feito.

## Entrega

A task 011 implementa a camada de domínio, aplicação, persistência e migration
para solicitações de cadastro separadas do aluno ativo, três referências
faciais versionadas e aprovação independente. A entrega não contém convite,
rotas HTTP, formulário/câmera, fila ou worker; essas partes pertencem às tarefas
posteriores. Não houve uso de imagens ou dados biométricos reais.

`0006_cadastro_web_referencias` acrescenta solicitações com os estados de ciclo
de vida, conjuntos pendentes/ativos/substituídos/descartados e referências de
ordinal 1–3. Cada referência guarda embedding `float32` de dimensão 512,
identificação do modelo, consentimento versionado e caminho privado relativo.
Um índice parcial impede mais de um conjunto ativo por aluno. A migration não
removeu as colunas legadas de foto/embedding.

Solicitações não reservam matrícula. Aprovação revalida a matrícula global, o
responsável/turma e o consentimento dentro da transação. Se o aluno já existir,
preserva nome, foto e embedding globais, cria/reactiva somente o vínculo e
descarta as referências provisórias da solicitação. A corrida real de duas
aprovações foi exercitada no PostgreSQL descartável.

Atualização biométrica é uma solicitação separada; o responsável da turma ou
admin pode solicitá-la e somente admin aprova o conjunto novo. A ativação da
versão nova e desativação da anterior são atômicas e auditadas. Em falha SQL, o
candidato é descartado e sua remoção de arquivos é tentada sem afetar o conjunto
ativo anterior. Consultas internas retornam apenas referências ativas.

Rejeição e expiração marcam dados provisórios para descarte, registram auditoria
e permitem nova tentativa de limpeza quando a remoção de arquivo falha. O
armazenamento recebe por injeção uma raiz privada e grava nomes relativos
aleatórios; não há rota para servi-los. No Windows, a conta do serviço ainda
precisa de ACL restrita. Essa raiz não foi configurada em runtime.

## Arquivos

- Entidades e storage protocol: `src/domain/entities/referencia_facial.py`,
  `src/domain/entities/solicitacao_cadastro.py` e
  `src/domain/services/reference_storage.py`.
- Casos de uso: `src/application/use_cases/solicitar_cadastro_web.py`,
  `anexar_referencias_web.py`, `aprovar_cadastro_web.py`,
  `solicitar_atualizacao_biometrica.py`, `aprovar_atualizacao_biometrica.py`,
  `rejeitar_cadastro_web.py` e `limpar_referencias_provisorias.py`.
- Persistência: `src/infrastructure/repositories/postgres_solicitacao_repository.py`,
  `src/infrastructure/storage/private_reference_storage.py`,
  `src/infrastructure/database/models.py` e
  `migrations/versions/0006_cadastro_web_referencias.py`.
- Provas: `tests/unit/test_cadastro_web_pendente.py`,
  `tests/unit/test_fluxo_referencias_web.py`,
  `tests/unit/test_private_reference_storage.py`,
  `tests/unit/test_repositorio_solicitacao_web.py` e
  `tests/integration/test_referencias_web_postgresql.py`.
- Registros atualizados: `AGENTS.md`, `tasks/README.md`,
  `tasks/WEB-MIGRACOES.md`, `tasks/WEB-CONTRATO-EXECUCAO.md`,
  `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md` e
  `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`.

Não foram alterados requirements: a implementação usa dependências já presentes.

## Validação executada

Ambientes de testes: `.venv-app` com Python 3.12.0rc2 para os testes focados e
`.venv-ml` com Python 3.14.3 para a suíte unitária completa, integração e gates
estáticos. São ambientes locais de teste; isso não declara compatibilidade
dessas versões pré-release com produção.

- `.venv-app\Scripts\python.exe -m pytest tests/unit/test_cadastro_web_pendente.py tests/unit/test_fluxo_referencias_web.py tests/unit/test_private_reference_storage.py tests/unit/test_repositorio_solicitacao_web.py -p no:cacheprovider --basetemp .pytest-task011-app-final`: 27 testes aprovados em Python 3.12.0rc2.
- `.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider --basetemp .pytest-task011-unit-final`: **1011 passaram** em Python 3.14.3.
- O wrapper de preflight local chamou `pytest.main(['-q', 'tests/integration/test_referencias_web_postgresql.py', '-p', 'no:cacheprovider', '--basetemp', '.pytest-task011-pg-final'])`: **3 passaram** em Python 3.14.3 no banco descartável local `task011_web_references_test_20261018`, identificado pelo comentário `projeto_reconhecimento_facial: task 011 disposable references database`.
- A fixture aplicou `upgrade head`, executou `alembic check`, testou downgrade protegido e concorrência de aprovação; ao terminar limpou as fixtures e reverteu o schema a `base`. Verificação somente de leitura confirmou o marcador, zero revisões aplicadas e nenhuma tabela pública além da tabela `alembic_version` vazia.
- Ruff e formatação passaram sobre os 20 caminhos Python da entrega: migration,
  `src/domain/errors.py`, `src/infrastructure/database/models.py`, os sete
  casos de uso, as duas entidades, o protocolo de storage, o repositório, o
  storage privado, os quatro testes unitários e o teste de integração. Comandos:
  `.venv-ml\Scripts\python.exe -m ruff check @paths` e
  `.venv-ml\Scripts\python.exe -m ruff format --check @paths`.
- `.venv-ml\Scripts\python.exe -m mypy src scripts`: aprovado, 105 arquivos-fonte.
- `git diff --check`: aprovado.

O primeiro comando amplo foi tentado no `.venv` (Python 3.14.3 sem SciPy,
scikit-learn e FastAPI) e falhou na coleta por dependências ausentes. A execução
foi repetida em `.venv-ml`, que contém as dependências de teste; a suíte completa
passou. A validação focada de PostgreSQL confirmou o marcador e o host local
antes de qualquer DDL. O banco local `escola` não foi alterado nesta task.

Não houve alteração de dependências; `pip check` não foi necessário. Não foi
executado smoke de inferência/modelo: esta task não contém provider facial e os
embeddings/bytes dos testes são sintéticos. Também não houve validação visual,
avaliação biométrica, medição de latência, deploy ou teste HTTP de convite.

## Limitações e próximos contratos

- A integração com convite, API, fila/worker e interface não existe; task 011
  não fica ativa na aplicação até as tasks responsáveis conectarem esses fluxos.
- A fila da task 012 ainda não existe. Quando jobs forem implementados, devem
  guardar o ID/versão do conjunto usado e revalidá-lo antes de persistir; a
  invalidação de jobs que referenciem uma versão substituída será integrada
  nessa camada futura.
- A limpeza é um caso de uso disponível, mas ainda não há scheduler/worker que
  o execute automaticamente.
- A tarefa não prova identidade biométrica, qualidade de captura ou ganho de
  acurácia; consentimento e aprovação independente seguem necessários.

## Migration, ativação e rollback

A revisão `0006` foi validada somente no banco descartável acima, e a fixture
deixou-o em `base`. A migration não foi aplicada ao banco `escola`. Para ativação
futura, preparar backup e janela coordenada, confirmar o banco de destino e
aplicar a revisão explicitamente antes de ligar os consumidores; configurar a
raiz de armazenamento fora da webroot, com permissões/ACL exclusivas. Não há
upgrade automático no boot.

O downgrade para `0005` recusa remover solicitações/referências persistidas.
Para rollback, primeiro interromper escritores e preservar backup consistente;
restaurar versão de aplicação/schema somente conforme os dados permitirem. Não
apagar registros para forçar downgrade. As colunas legadas de aluno permanecem
intactas.

**Estado: concluída para o escopo de domínio, casos de uso, persistência e
validação da task 011 no workspace; não publicada nem implantada.** A conexão
com API, fila/worker, invalidação de jobs futuros, interface e validação visual
permanece pendente nas tarefas seguintes.
