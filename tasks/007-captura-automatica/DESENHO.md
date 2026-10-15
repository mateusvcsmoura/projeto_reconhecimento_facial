# Desenho — 007: cadastro e presença automáticos

**Executor: Luna 6 High. Estado: preparado; implementação pendente.** Desenho aprovado internamente conforme AGENTS.md. Base inspecionada em 15/10/2026: main, `f4763c7`. Nenhuma instalação, teste ou operação com câmera/banco foi executada na preparação.

## Objetivo e decisões

Ao selecionar cadastro ou reconhecimento, iniciar a busca por rosto assim que a câmera abrir e concluir automaticamente quando as condições forem atendidas. Cadastro ainda solicita identificação e consentimento antes de abrir a câmera. Remover a necessidade de ESPAÇO e ENTER do fluxo padrão; ESC continua cancelando.

Uma operação por abertura: cadastro salva um aluno; reconhecimento registra uma presença (ou informa que já foi registrada hoje), fecha a câmera e retorna ao menu. Modo contínuo de fila de alunos fica fora do escopo. Na verificação não armazenar nova foto.

Usar espera **configurável de 5 segundos**, medida desde a primeira observação válida da sequência. O intervalo de 5–7 segundos discutido é preferência de experiência, não critério biométrico calibrado. Passagem do tempo sozinha não autoriza persistência. O prazo pode superar 5 segundos devido à inferência, reinícios e validação final.

## Estado atual confirmado

- `MenuCLI.cadastrar()` valida identificação e consentimento, chama `_capturar_rosto()` e só captura com ESPAÇO. Qualidade recusada reinicia a captura.
- `CadastrarAluno.executar()` prepara recorte/embedding e persiste na mesma chamada; não deve ser chamado para sondar frames.
- `FaceRecognition.extrair_face_unica()` já aplica detecção, antispoofing e qualidade configurados, sem gerar embedding. `preparar_cadastro()` produz `FacePreparada` com recorte e embedding correspondentes.
- Reconhecimento tem caminhos manual simples e temporal; ambos dependem de ENTER. O temporal faz uma nova leitura e identificação antes de registrar. `ReconhecerAluno.identificar()` retorna None para ausência, múltiplas faces e desconhecido; não permite distinguir esses casos pela resposta atual.
- `ConfirmadorTemporal` mantém apenas os últimos N timestamps; não serve sozinho para medir 5 segundos contínuos, pois a janela é móvel.
- Tarefa 006 usa worker MediaPipe separado, com inspeção visual manual pendente. Viewer desenha sobre cópia e não oferece aprovação biométrica. Preservar o worker e seus ambientes.

## Configuração

Adicionar em Settings e `.env.example`:

| Chave | Padrão | Regra |
|---|---:|---|
| `FACE_AUTO_CAPTURE_ENABLED` | `true` | Automação padrão explicitamente solicitada; false restaura caminhos manuais existentes |
| `FACE_AUTO_CAPTURE_WAIT_SECONDS` | `5.0` | Real finito > 0 |
| `FACE_AUTO_CAPTURE_SAMPLE_SECONDS` | `0.5` | Real finito > 0 e menor que max_age |
| `FACE_AUTO_CAPTURE_MAX_AGE_SECONDS` | `2.0` | Real finito > 0; máximo de idade e intervalo entre observações válidas |

Mínimo fixo de três observações válidas distintas, além do tempo; uma observação e sleep não bastam. Rejeitar bool como número, NaN e infinito no serviço puro. A validação de Settings deve refletir os limites. Os valores são limites de engenharia; não prometer funcionamento em hardware cuja inferência exceda a validade.

Não alterar defaults de qualidade, margem, temporal, limiar ou antispoofing. Quando qualidade estiver desligada, não exibir “qualidade aprovada”. Automação funciona sem landmarks e sem `FACE_TEMPORAL_ENABLED`: tem sua própria exigência mínima de sequência. Se temporal estiver ligado, exigir também o estado confirmado e vigente do ConfirmadorTemporal existente para a mesma identidade.

## Controlador puro e agenda

Criar `src/domain/services/captura_automatica.py` com `ParametrosCapturaAutomatica`, `EstadoCapturaAutomatica` e `ConfirmadorCapturaAutomatica`. Sem relógio real, sleeps, imagens ou I/O nesse módulo.

Contrato proposto: `observar(chave: str | None, capturado_em: float, agora: float) -> EstadoCapturaAutomatica`, `consultar(agora: float) -> EstadoCapturaAutomatica`, `reiniciar() -> None`. Estado imutável: chave, quantidade de observações, tempo restante e pronto. Guardar só início/último timestamp/chave/contador, não lista ilimitada nem frames.

Chave no cadastro: constante `cadastro`; no reconhecimento: ID do aluno convertido para string. A chave de cadastro significa somente uma face válida observada, não identidade comprovada nem tracking da mesma pessoa. Não inventar matching entre faces não cadastradas ou prometer continuidade de identidade no cadastro.

Regras: timestamps finitos, não negativos e estritamente crescentes nas observações; agora >= captura; consulta não renova evidência. None, troca de chave, resultado com idade > max_age ou intervalo entre capturas > max_age interrompem sequência. Nova observação válida após intervalo excessivo inicia sequência nova. Exatamente max_age ainda é válido. Pronto exige três observações, mesma chave, evidência vigente e **última captura - primeira captura >= espera**; consulta após tempo ocioso nunca transforma duas observações em captura autorizada.

Agenda automática por tempo monotônico, não pelo contador de 8 frames do modo manual: primeira análise imediata; próximas no mínimo sample_seconds após terminar a anterior. Continuar renderizando/consultando teclas entre análises, sem sleep de 5 segundos, busy loop adicional ou catch-up acumulado. Inferência permanece síncrona e pode bloquear a UI pelo tempo do modelo; não prometer responsividade durante chamada nativa.

Timestamp conservador antes de `camera.ler_frame()`, idade checada depois da inferência, depois de `janela.mostrar()` (landmarks podem atrasar) e imediatamente antes da persistência. Tempo de software não comprova frescor físico do buffer da webcam.

## Cadastro

1. Validar nome/matrícula e colher consentimento uma vez. Só então abrir câmera e janela.
2. Em cada análise programada, chamar novo método `CadastrarAluno.validar_captura(imagem) -> None`, que delega a `extrair_face_unica`, descarta recorte e não grava nem gera embedding.
3. Face aceita alimenta controlador; ausência, múltiplos rostos, qualidade insuficiente ou possível fraude limpam sequência e exibem orientação. Modelo indisponível, câmera quebrada ou falha de persistência são erros técnicos, não “procurando rosto”. Encerrar/reportar, sem retry de gravação.
4. Quando pronto, respeitar ESC antes de iniciar confirmação. Ler **novo frame bruto**, preparar uma única `FacePreparada` com detecção, antispoofing, qualidade configurada e embedding; não reutilizar recorte de sondagem.
5. Antes de gravar, renovar checagens de idade/continuidade, renderizar status usando cópia e verificar ESC novamente. Qualquer recusa/expiração descarta preparação e reinicia busca na mesma janela, sem repetir identificação/consentimento.
6. Salvar apenas a preparação final aceita, uma vez. Fechar janela/worker/câmera; informar sucesso e retornar ao menu.

Para separar validação de gravação sem duplicar inferência, estender CadastrarAluno com `preparar_captura(imagem) -> FacePreparada` e `concluir_cadastro(matricula, nome, preparada, consentiu) -> Aluno`. `concluir_cadastro` verifica consentimento e identificação novamente antes da mesma persistência atual. A UI verifica frescor antes de chamá-lo. Manter `executar(...)` compatível, validando consentimento/identificação antes de preparar e delegando a persistência comum. Não expor nova entrada que aceite pixels/embedding arbitrários de arquivos externos; FacePreparada vem do provider nesta sessão e não é serializada.

Testar ausência de side effects em sondagem/preparação, identidade e consentimento preservados, uma única extração de embedding final, mesmo recorte usado no embedding e storage. Não redesenhar transação filesystem/banco nesta task; falha de gravação deve encerrar com erro explícito e sem tentativa automática repetida.

## Reconhecimento e presença

Carregar referências como hoje; galeria vazia informa e não abre câmera. Cada análise chama `identificar` mantendo limiar, antispoofing e políticas configuradas. Alimentar controlador por ID; None ou rejeição recuperável reinicia. Não chamar None de “nenhuma face” com certeza: pode ser desconhecido ou múltiplas faces.

Após 5 segundos e mínimo de observações, e confirmação temporal adicional se habilitada, ler novo frame e identificar novamente. A identidade final precisa ser a mesma; resultado diferente, recusado ou vencido reinicia a busca, nunca registra o candidato antigo. Processar ESC e revalidar frescor após exibição, imediatamente antes de `_registrar`.

Registrar uma vez e encerrar a sessão inclusive se a presença já existir hoje. A proteção de duplicação do caso de uso/repositório permanece. Não repetir chamadas de banco por frame. Não gravar foto de verificação. ENTER/ESPAÇO são ignorados no modo automático, nunca atalhos que contornam a espera.

## Interface e estados

| Estado | Texto sugerido | Próxima ação |
|---|---|---|
| Busca no cadastro | `Posicione o rosto. Captura automatica | ESC cancela` | Primeira observação válida inicia contagem |
| Busca no reconhecimento | `Buscando aluno cadastrado | ESC sai` | Identificação válida inicia contagem |
| Contagem | `Mantenha o rosto na camera. Aguarde 5 s` (atualizado) | Renderizar tempo restante, sem prometer conclusão no zero |
| Confirmação final | `Validando captura... | ESC cancela` | Nova leitura e validações |
| Recusa | Mensagem de `para_operador`, sem apagar por mensagem genérica no mesmo frame | Limpar contagem e aguardar nova sequência |
| Sucesso / já registrada | Mensagem explícita no terminal | Fechar câmera e voltar ao menu |

Quando tempo decorrido ainda não tiver quantidade de observações suficiente, mostrar “Validando...” e não “0 segundos” indefinidamente. Mensagens atuais do viewer/landmarks não autorizam ações; ausência/falha do overlay não bloqueia a automação.

## Limites e aceite

Nenhuma dependência nova ou instalação. Sem migrações, alteração de dados reais, datasets, pesos, `.env`, calibração ou câmera nesta execução automatizada. Testes usam arrays/relógio/serviços dublados; roteiro manual posterior fica documentado, sem declarar que ocorreu.

Aceite: ambos os fluxos concluem sem teclas de confirmação; cancelamento prevalece antes da gravação; relógio sozinho não dispara ação; candidato vencido ou trocado nunca registra; modo manual continua disponível; falhas de modelo/persistência não viram loops; uma gravação por sessão; recursos fechados em todos os caminhos. Preservar pixels originais e worker006. Não alegar aumento de acurácia por esperar ou observar frames correlacionados.
