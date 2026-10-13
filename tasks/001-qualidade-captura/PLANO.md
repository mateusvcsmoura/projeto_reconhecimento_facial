# Qualidade de captura — plano de implementação

> Para o executor Luna 6 High: usar `superpowers:executing-plans`, se disponível, e executar as tarefas abaixo no próprio agente. Não delegar nem reabrir brainstorming. O usuário autorizou aprovação interna das decisões rotineiras e solicitou execução deste pacote.

**Objetivo:** implementar a política de qualidade definida no desenho, integrada ao cadastro e reconhecimento.

**Arquitetura:** avaliação NumPy pura; adaptador aplica a política antes do embedding; CLI trata recusas recuperáveis. Preparação conjunta de imagem/embedding evita segunda detecção no cadastro.

**Stack:** Python, NumPy, Pydantic Settings e Pytest existentes; nenhuma dependência nova.

**Especificação:** [DESENHO.md](DESENHO.md), fonte normativa para interfaces, algoritmo, defaults e mensagens.

## Restrições globais

- `FACE_THRESHOLD=0.30`; antispoofing preservado; `FACE_QUALITY_ENABLED=false` por padrão.
- Dados e imagens somente sintéticos nos testes. Não abrir `.env`, `avaliacao/`, `storage/` ou banco operacional.
- Não executar migrations, baixar pesos/datasets, modificar experimentos ou implementar outras melhorias.
- Preservar alterações anteriores do usuário. Commit apenas dos arquivos desta tarefa e do pacote em `tasks/`.
- O estado inicial do executor deve ser inspecionado novamente; este pacote não certifica Git/testes futuros.

## Pontos de revisão obrigatória

- Frame com texto de overlay: original precisa continuar intacto (tarefa 3).
- Cadastro duplicando detecção: exigir contadores e mesma face representada/salva (tarefa 2).
- Candidato anterior seguido de captura ruim e Enter: nenhuma presença (tarefa 3).
- Metadados ausentes com flag ligada/desligada: falha explícita versus compatibilidade (tarefa 2).
- Fronteiras numéricas e configuração inválida: igualdade aceita, NaN/inf recusados (tarefa 1).

## 0. Inspeção e baseline

- [ ] Ler AGENTS.md, CLAUDE.md, instructions/, arquitetura, este desenho e código/testes citados.
- [ ] Executar `git status --short`, `git branch --show-current`, `git log -1 --oneline`; confirmar `main` e registrar alterações preexistentes sem incluí-las na tarefa.
- [ ] Localizar intérprete existente com pytest/NumPy/Pydantic e Ruff/mypy. Preferir `.venv-ml/Scripts/python.exe` se funcional. Não instalar DeepFace para testes.
- [ ] Inspecionar fixtures antes de rodar testes; rodar baseline de `tests/unit` sem banco. Registrar comando, versão e resultado no futuro `RESULTADO.md`.
- [ ] Usar `rg` para localizar implementadores de `FaceRecognition`, chamadas de extração/embedding, testes da CLI e viewer. Não presumir que só tests/fakes.py será afetado.

## 1. Avaliador, erros e Settings

Criar `src/domain/services/qualidade_captura.py` e `tests/unit/test_qualidade_captura.py`. Alterar `src/domain/errors.py`, `src/config/settings.py`, `tests/unit/test_prompts_e_settings.py` e `.env.example`.

Interfaces produzidas: `ParametrosQualidade`, `MedidasQualidade`, `avaliar_qualidade` e os cinco erros exatamente como no desenho.

- [ ] Escrever e executar testes antes da implementação; confirmar falha pela funcionalidade ausente.
- [ ] Testar patches constantes escuro/claro, patch plano de luminosidade intermediária, padrão xadrez determinístico e face pequena usando metadados. Ex.: plano BGR=120 com parâmetros padrão lança `RostoSemNitidez`; dimensão 79 lança `RostoMuitoPequeno` antes das outras recusas.
- [ ] Testar limites de brilho 40 e 215 com `min_sharpness=0`, dimensão 80 aceita, nitidez exatamente no limiar aceita, BGR com canais diferentes, ausência de mutação e ordem de recusa.
- [ ] Cobrir arrays vazios/menores que 3x3, canais/dtype inválidos, dimensões zero/negativas/booleanas, parâmetros negativos/NaN/inf e mínimo de brilho >= máximo. Para borda de nitidez, calcular a referência explicitamente em fixture pequena; não usar o próprio avaliador como oráculo.
- [ ] Implementar o algoritmo do desenho e Settings com validação de campos e validação cruzada. Explicar no `.env.example` que são heurísticas optativas não calibradas.
- [ ] Rodar testes focais até aprovação, incluindo construção direta da dataclass.

## 2. Integração do adaptador e cadastro

Alterar `src/domain/services/face_recognition.py`, `src/infrastructure/face_recognition/deepface_adapter.py`, `src/application/use_cases/cadastrar_aluno.py`, `src/main.py`, `tests/fakes.py`, `tests/unit/test_deepface_adapter.py`, `tests/unit/test_cadastrar_aluno.py` e consumidores do contrato identificados na inspeção.

Consome: interfaces da tarefa 1. Produz: `FacePreparada(imagem, embedding)`, `FaceRecognition.preparar_cadastro(imagem)` e argumento `qualidade` do adaptador.

- [ ] Criar testes com contadores do DeepFace falso: aprovado = uma extração e uma representação; qualidade ruim = nenhuma representação; cadastro recusado = zero gravação de imagem e zero cadastro no repositório.
- [ ] Cobrir fraude e múltiplas faces recusadas com qualidade ligada e desligada, falha de modelo preservada, retorno BGR uint8 e embedding normalizado.
- [ ] Cobrir `facial_area` faltante/malformado com política ligada e compatibilidade de fixtures antigas com política desligada. Não transformar erro estrutural em `None`.
- [ ] Implementar preparação única e atualizar fakes sem apagar os testes de consentimento, matrícula duplicada ou erros do provider. Consentimento negado não deve chamar a preparação.
- [ ] Testar composição de Settings -> política com dublês, sem conexão de banco, incluindo flag desligada e valores personalizados. Criar `tests/unit/test_main_qualidade.py` se não houver teste equivalente.
- [ ] Rodar testes focais. Não importar DeepFace/OpenCV reais para provar estes contratos.

## 3. Recaptura, mensagens e frame original

Alterar `src/presentation/cli/menu.py`, `mensagens.py`, `viewer.py`, `tests/unit/test_menu.py`, `test_mensagens.py`, `test_viewer.py` e, se necessário para documentação de exceções, `src/application/use_cases/reconhecer_aluno.py` e contrato do provider.

- [ ] Criar teste de cadastro com primeira tentativa ruim, segunda válida: identificação e consentimento solicitados uma vez, somente a tentativa válida persistida. Testar ESC depois de recusa sem persistência e liberação de câmera/janela.
- [ ] Criar sequência de reconhecimento com candidato válido, erro de qualidade no próximo ciclo de comparação e Enter nesse ciclo: zero registro, orientação exibida, recuperação no próximo ciclo válido. Fornecer frames suficientes para `INTERVALO_DE_COMPARACAO=8`.
- [ ] Garantir que falha de modelo mantém o tratamento anterior, sem ser engolida pelo novo handler.
- [ ] Implementar handlers específicos, mensagens do desenho e remoção da sugestão de desligar antispoofing. Ajustar registro de orientações para que subclasses recebam mensagem específica.
- [ ] Implementar cópia no viewer e teste com `putText` falso que efetivamente modifica o array recebido: original deve permanecer idêntico, `imshow` recebe a cópia alterada.
- [ ] Rodar testes focais de CLI, mensagens, viewer, reconhecimento e cadastro; preservar os cenários existentes.

## 4. Documentação, verificação e entrega

- [ ] Atualizar README e ARCHITECTURE somente nas seções afetadas: configuração, fluxo, recaptura, opt-in e limites de evidência. Não reescrever memórias históricas nem marcar outras prioridades como implementadas.
- [ ] Criar `tasks/001-qualidade-captura/RESULTADO.md` com resumo, arquivos, decisões, comandos/resultados reais, limitações, estado de commit/push. Marcar as caixas deste plano somente após execução e atualizar o estado em `tasks/README.md`.
- [ ] Executar, substituindo o intérprete se necessário:

```powershell
.\.venv-ml\Scripts\python.exe -m pytest tests/unit -p no:cacheprovider
.\.venv-ml\Scripts\python.exe -m ruff check src scripts tests
.\.venv-ml\Scripts\python.exe -m mypy
git diff --check
```

Se pytest tiver conflito de diretório temporário, usar `--basetemp` com um novo caminho exclusivo em `$env:TEMP`, não um diretório existente nem a raiz do projeto. Não remover temporários preexistentes. Executar Ruff format check somente nos arquivos Python da tarefa, sem reformatação global.

- [ ] Não executar a suíte completa ou migrations cegamente: testes de integração/BDD podem acessar PostgreSQL real. Não são necessários para esta mudança sem schema. Declarar seu escopo não executado; cenários de fluxo devem estar cobertos pelos fakes da suíte unitária.
- [ ] Revisar o diff final: ausência de biometria/secrets, nenhuma mudança no matcher, limiar, schema ou configuração real; testes novos testam comportamento e não apenas detalhes de implementação.
- [ ] Fazer commit e push conforme PROMPT.md. Não marcar a tarefa concluída se testes relevantes falharem ou publicação não for confirmada.
