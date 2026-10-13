# Resultado — tarefa 002: consistência temporal

## Implementação

Foi adicionada a política optativa de consistência temporal. `ConfirmadorTemporal`
é um serviço puro que retém somente o ID e até N timestamps; `MenuCLI` cria uma
instância nova para cada sessão de reconhecimento. Com a flag desligada, o laço
de reconhecimento continua no fluxo anterior.

Com a política ativa, apenas as identificações já executadas a cada oito frames
contam como observações. O padrão exige três decisões iguais dentro de 5 s e
descarta a evidência quando a última observação passa de 2 s. Ausência, mudança
de ID, qualidade insuficiente e expiração interrompem ou reduzem a sequência. O
progresso na janela é uma contagem e não mostra o nome antes da confirmação.

ENTER elegível consulta novamente a validade, lê um novo frame e identifica essa
captura com o pipeline atual. A presença só é registrada se a identificação nova
mantiver o mesmo ID e a sequência ainda estiver confirmada. Uma tentativa de
registro concluída consome a sequência, inclusive quando a presença do dia já
existe. O timestamp é lido imediatamente antes da leitura da câmera; o tempo da
leitura e da inferência conta para a validade.

As quatro configurações de qualidade e temporalidade foram verificadas como
independentes. O limiar `FACE_THRESHOLD=0.30`, o anti-spoofing, o intervalo de
comparação e a política de qualidade da tarefa 001 foram preservados.

## Evidências executadas

Ambiente: `.venv-ml`, Python 3.14.3. A suíte usa apenas relógio controlado,
embeddings sintéticos e dublês. Nenhuma imagem facial real, webcam, modelo ou
banco foi aberto.

- Baseline antes das alterações: branch `main`, HEAD `9d3089644b43211ec8fce3c7ac5fc7b53e13f41e`, `origin/main` alinhado após `git fetch origin`, sem commits locais à frente. `git log -4 --oneline`: `9d30896 chore(ai): add agents md`, `8fdc085 docs: conclui registro da tarefa de qualidade`, `0ddf6e0 feat: adiciona validacao de qualidade de captura`, `c58bb98 docs(ml): consolidate academic stage five`.
- Estado preexistente no workspace: `tasks/README.md` modificado com o índice e os documentos da tarefa 002 não rastreados; quatro diretórios temporários antigos do pytest também não rastreados. O baseline foi `.\.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider` — **611 passed**.
- Suíte unitária final: `.\.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider` — **707 passed in 7.02s**.
- `.\.venv-ml\Scripts\python.exe -m ruff check src scripts tests` — aprovado.
- `.\.venv-ml\Scripts\python.exe -m mypy` — aprovado, sem problemas nos 69 módulos de origem.
- `.\.venv-ml\Scripts\python.exe -m ruff format --check` nos oito arquivos Python alterados — aprovado.
- `git diff --check` — código de saída 0. Git emitiu apenas um aviso de conversão LF/CRLF para `tasks/README.md`.

Não foram executadas migrations, testes de integração/BDD ou operações de banco;
esta mudança não altera schema. O diretório `tasks/README.md` e o pacote da tarefa
002 já estavam preparados no workspace; quatro diretórios temporários antigos do
pytest também preexistiam. Eles não foram removidos, e os temporários não fazem
parte da entrega. Nenhum arquivo da tarefa 001 foi alterado.

## Limites da evidência

Os testes demonstram regras funcionais com dados sintéticos. Frames consecutivos
são correlacionados, então consistência temporal não comprova aumento de
acurácia e pode repetir uma identificação errada. Os valores temporais são
parâmetros iniciais de engenharia, sem calibração biométrica. A nova chamada de
leitura reduz o reaproveitamento de um resultado antigo da aplicação, mas não
garante frescor físico: a câmera pode entregar frames bufferizados, e não há
rastreamento contínuo da pessoa.

## Publicação

Este relatório registra o estado local após verificações e antes da publicação,
conforme o prompt da tarefa. Na hora de escrevê-lo, commit e push ainda estavam
pendentes. O hash do commit e a confirmação de `origin/main` são informados na
resposta final, sem um commit adicional apenas para acrescentar o hash aqui.
