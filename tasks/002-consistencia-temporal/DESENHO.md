# 002 — Desenho técnico: consistência temporal

Estado: aprovado internamente para execução; implementação pendente.

Executor previsto: Luna 6, esforço High. Pré-requisito: tarefa 001 concluída.

## 1. Análise da 001 e do ponto de partida

Inspeção realizada em `main`, HEAD `9d30896`, após os commits `0ddf6e0` (qualidade), `8fdc085` (resultado) e `9d30896` (AGENTS.md). Nenhuma alteração foi listada por `git status --short` antes deste pacote; houve avisos de acesso negado aos diretórios temporários antigos de pytest. O remoto não foi consultado nesta preparação.

O relatório da 001 registra 611 testes unitários aprovados, Ruff/mypy aprovados e publicação do commit de implementação. São evidências registradas pelo executor anterior; esta análise não reexecutou testes nem verificou novamente o push.

O código inspecionado confirma:

- `DeepFaceAdapter._preparar_recorte` aplica qualidade opcional depois da detecção única e antispoofing, antes da representação.
- `preparar_cadastro` entrega recorte e embedding da mesma detecção; o menu permite recaptura por qualidade.
- `MenuCLI._laco_de_reconhecimento` limpa o candidato na recusa de qualidade, mas uma única identificação continua suficiente para Enter.
- A comparação ocorre a cada `INTERVALO_DE_COMPARACAO=8` frames; entre comparações, o resultado anterior permanece disponível sem prazo de validade.
- `ReconhecerAluno.identificar` retorna `None` para desconhecido, ausência ou múltiplos rostos; propaga erros de qualidade, fraude e infraestrutura.
- `CameraProvider.ler_frame` devolve somente a imagem. Não fornece timestamp do sensor nem garantia de ausência de buffering.

Conclusão para esta entrega: preservar a 001 e acrescentar uma política de sequência e validade, com confirmação sobre uma nova leitura de câmera no momento do Enter. A inspeção foi orientada a essa integração, não uma certificação completa da implementação 001.

## 2. Objetivo, escolha e limites

Com a política temporal ligada, disponibilizar registro somente após **N observações consecutivas aceitas da mesma identidade**, dentro de uma janela temporal, e confirmar essa identidade em nova leitura ao pressionar Enter.

Escolha: sequência estrita, em vez de maioria em uma janela. Uma observação desconhecida/recusada interrompe a sequência; não pode ser vencida pelos votos anteriores. Reutilizar a decisão 1:N de cada frame, sem calcular média de embeddings, distâncias ou probabilidades.

Uma observação é uma chamada nova a `identificar` sobre uma leitura de câmera. Renderizar oito frames ou chamar o relógio oito vezes não produz oito observações. Nenhuma imagem/embedding será guardada pelo componente temporal.

Não inclui margem top-2, pose, rastreamento de pessoas, múltiplas referências, mudança de frequência de comparação, processamento assíncrono, benchmark, datasets, treinamento, banco ou API. Preservar qualidade da 001, `FACE_THRESHOLD=0.30`, antispoofing e confirmação manual.

## 3. Ativação e parâmetros

Política optativa, independente da qualidade: `FACE_TEMPORAL_ENABLED=false` mantém o comportamento operacional da 001, incluindo a ausência de inferência adicional no Enter. Não editar `.env` real nem ativar a política silenciosamente. Flags de qualidade e temporal devem funcionar nas quatro combinações.

| Ambiente / campo Settings | Default | Validação |
|---|---:|---|
| `FACE_TEMPORAL_ENABLED` / `face_temporal_enabled` | false | booleano |
| `FACE_TEMPORAL_MIN_OBSERVATIONS` / `face_temporal_min_observations` | 3 | inteiro >= 2; recusar booleano e valor fracionário |
| `FACE_TEMPORAL_WINDOW_SECONDS` / `face_temporal_window_seconds` | 5.0 | número finito > 0, não booleano |
| `FACE_TEMPORAL_MAX_AGE_SECONDS` / `face_temporal_max_age_seconds` | 2.0 | número finito > 0, não booleano, <= janela |

São parâmetros iniciais de engenharia, sem calibração biométrica ou medição de adequação à webcam. Uma inferência muito lenta pode impedir confirmação; a interface deve solicitar nova observação e nunca ampliar automaticamente os tempos. Não existe fallback de aceitação de frame único.

## 4. Componente de domínio

Criar `src/domain/services/consistencia_temporal.py`, usando somente biblioteca padrão. Interfaces fixadas:

```python
@dataclass(frozen=True, slots=True)
class ParametrosTemporais:
    min_observacoes: int = 3
    janela_segundos: float = 5.0
    validade_segundos: float = 2.0

@dataclass(frozen=True, slots=True)
class EstadoTemporal:
    aluno_id: int | None
    observacoes: int
    confirmado: bool

class ConfirmadorTemporal:
    def __init__(self, parametros: ParametrosTemporais) -> None: ...
    def observar(self, aluno_id: int | None, capturado_em: float) -> EstadoTemporal: ...
    def consultar(self, agora: float) -> EstadoTemporal: ...
    def reiniciar(self) -> None: ...
```

As assinaturas acima são especificações, não código a copiar com corpos vazios. `confirmado` significa sequência satisfeita e ainda válida no instante consultado, não presença gravada nem identidade biometricamente comprovada.

Estado interno limitado: um ID, uma deque de no máximo N timestamps e o último timestamp de observação recebido. Não guardar `Aluno`, nomes, imagem, embedding ou histórico ilimitado. Instância local a cada entrada no reconhecimento; nunca singleton/global ou objeto compartilhado entre sessões.

Validar parâmetros na dataclass e em Settings. IDs válidos: inteiros positivos, excluindo booleanos, ou `None`. Tempos: reais finitos >= 0, excluindo booleanos. Observações têm timestamps estritamente crescentes, inclusive observações `None`. Timestamp repetido ou regressivo gera `ValueError` sem alterar estado; evita contar duas vezes a mesma observação enviada pelo chamador. `consultar` aceita o mesmo instante repetidamente, mas recusa instante menor que o último timestamp de observação. O chamador deve usar relógio monotônico e consultas cronológicas; nenhum acesso a relógio real no domínio.

`reiniciar` limpa sequência e marcador de timestamp; é usado ao encerrar a sessão ou consumir uma confirmação. Expiração ou `None` limpa a sequência, mas mantém o marcador de última observação, para não aceitar reenvio da mesma amostra na sessão.

### Algoritmo de observar

1. Validar todos os argumentos antes de alterar o estado.
2. Expirar a sequência relativamente a `capturado_em`, conforme as regras abaixo.
3. Se `aluno_id is None`, esvaziar sequência e devolver `(None, 0, False)`.
4. Se o ID difere do ID acumulado, substituir a sequência por uma observação desse novo ID.
5. Se o ID é igual, acrescentar o timestamp. Manter somente os N mais recentes.
6. Remover timestamps anteriores à janela relativamente a `capturado_em`; devolver snapshot. N observações sobreviventes implicam `confirmado=True`.

### Algoritmo de consultar/expirar

- Se não há sequência, devolver `(None, 0, False)`.
- Se `agora - ultimo_timestamp > validade_segundos`, limpar toda a sequência.
- Caso contrário, remover timestamps para os quais `agora - timestamp > janela_segundos`.
- Se restar algum, manter ID e contagem; confirmar somente se a contagem for N. Se esvaziar, limpar ID.
- Igualdade nos limites de janela/validade é aceita. Usar comparação direta `>` sem epsilon inventado.
- Consulta nunca acrescenta observação nem renova a validade. Após expirar, voltar o relógio não ressuscita evidência removida.

Exemplos com defaults, usando `A=1` e `B=2`:

| Entrada | Resultado |
|---|---|
| A@0.0, A@0.5 | A, 2, não confirmado |
| A@0.0, A@0.5, A@1.0 | A, 3, confirmado |
| A@0.0, A@0.5, B@1.0 | B, 1, não confirmado |
| A@0.0, A@0.5, None@1.0, A@1.5 | A, 1, não confirmado |
| A@0.0, A@0.5, A@1.0; consultar(3.0) | A, 3, confirmado |
| Mesma sequência; consultar(3.0001) | vazio, não confirmado |
| A@0.0, A@0.5, A@3.0 | A, 1, não confirmado (intervalo excedido) |

Para testar a janela separadamente da validade, usar N=3, janela=1.0, validade=1.0 e A@0.0, A@0.6, A@1.2: restam duas observações.

## 5. Integração e tempo da captura

Acrescentar argumentos opcionais nomeados a `MenuCLI.__init__`:

```python
temporal: ParametrosTemporais | None = None
relogio: Callable[[], float] = time.monotonic
```

`main.montar_menu` constrói `ParametrosTemporais` somente com a flag habilitada e injeta em MenuCLI. Não alterar construtor/semântica do matcher, `ReconhecerAluno` ou do provider. Domínio decide contagem e validade; CLI coordena câmera, relógio, mensagens e persistência já existente.

Quando habilitado, colher `capturado_em = relogio()` **imediatamente antes de `camera.ler_frame()`**. Esse é um marco conservador do início da leitura, não timestamp do sensor: inclui espera da câmera e inferência na idade. Evita datar um resultado lento como se tivesse sido capturado após a inferência. Não calcular idade com `datetime.now` nem FPS presumido.

No ciclo normal de comparação:

1. Executar `identificar(frame, referencias)` uma vez no intervalo já existente.
2. Para resultado válido, chamar `observar(resultado.aluno.id, capturado_em)`; para `None`, chamar `observar(None, capturado_em)`.
3. Em qualidade insuficiente, chamar `observar(None, capturado_em)`, limpar último reconhecimento e preservar orientação da 001.
4. Depois da inferência, chamar `consultar(relogio())` antes de exibir estado. Resultado que ficou velho durante processamento não habilita Enter.
5. Também consultar em cada frame não analisado para expirar a exibição e o candidato. Frames não analisados não incrementam contagem nem interrompem sequência por si mesmos.
6. Conservar apenas o último `Reconhecimento` enquanto seu ID corresponde ao estado vigente; o único caminho de registro temporal exige estado confirmado e fresco. Nunca usar somente `reconhecido is not None` nesse modo.

Fraude e falhas de modelo continuam propagando para o tratamento existente, encerrando o modo e liberando recursos. Não convertê-las em voto válido/`None` silencioso. A instância local é descartada ao sair. Falha de leitura mantém mensagem e liberação existentes.

## 6. Enter e prevenção de uso de resultado antigo

Ao receber Enter no modo temporal, consultar novamente o relógio: a janela pode ter demorado enquanto aguardava a tecla. ESC sai sem inferência adicional.

Se a sequência não estiver confirmada/fresca, não registrar e não executar inferência extra para tentar promovê-la. Mostrar progresso ou solicitar nova observação.

Se estiver confirmada:

1. Guardar o ID confirmado naquele instante.
2. Obter **nova leitura de câmera após a tecla**, com novo marco anterior à leitura. Não reutilizar o frame recém-exibido ou o resultado do último ciclo.
3. Executar `ReconhecerAluno.identificar` normalmente, preservando qualidade, antispoofing e limiar; exatamente uma inferência adicional por Enter elegível.
4. Alimentar essa observação na mesma política e consultar o relógio depois da inferência. A nova observação pode atualizar uma sequência que já estava confirmada; Enter nunca promove uma sequência antes incompleta.
5. Registrar somente se a nova identificação tiver o mesmo ID guardado e o estado resultante ainda estiver confirmado/fresco. Usar o `Aluno` da identificação nova. Se houve troca, a sequência fica com o novo ID e contagem 1, sem registrar ninguém naquele Enter.
6. Se `None`/qualidade ruim, limpar sequência e mostrar mensagem correspondente; se ultrapassou validade/janela, solicitar novas observações. Se fraude/modelo/câmera falhar, preservar o tratamento existente e não registrar.
7. Após tentativa de persistência concluída normalmente (registro novo ou presença já existente), `reiniciar`, limpar candidato e voltar a procurar. Enter repetido exige nova sequência; unicidade diária do banco continua intacta. Falha na persistência continua com o tratamento existente, sem confirmação de sucesso.

A leitura adicional não avança `contador` dos frames do laço e não chama o viewer. Atualizar mensagens no próximo frame exibido. Não drenar buffer via hacks, não criar thread de captura e não mudar CameraProvider nesta entrega.

Limite explícito: uma nova chamada de leitura não prova frescor físico do sensor; câmeras podem manter buffers. A implementação reduz uso de resultado antigo da aplicação, mas não elimina latência de hardware nem oferece rastreamento contínuo da pessoa. Não alegar garantia de que a pessoa permanece diante da câmera entre amostras.

## 7. Estados apresentados

Usar texto curto sem acentos na janela, seguindo as cores existentes. No modo desligado, rótulos e comportamento anteriores permanecem.

| Situação no modo temporal | Texto / cor |
|---|---|
| Sem sequência | `Procurando...` / branco |
| 1 a N-1 observações | `Validando identidade: k/N. Olhe para a camera.` / amarelo |
| Sequência confirmada | `Identidade consistente: NOME. ENTER para confirmar.` / verde |
| Estado expirou ou inferência ficou velha | `Reconhecimento expirado. Olhe para a camera novamente.` / amarelo |
| Qualidade ruim | Orientação específica da tarefa 001 / amarelo |
| Nova pessoa na confirmação | `Identidade mudou. Aguarde nova validacao.` / amarelo |
| Enter sem sequência suficiente | `Aguarde a validacao da identidade.` / amarelo |

Rodapé temporal: `ENTER = confirmar identidade e registrar | ESC = sair`.

Progresso k/N é contagem de observações, nunca probabilidade/confiança. Não exibir nome de candidato em estado parcial. Não aumentar logs com nomes, matrícula, distâncias ou sequências individuais.

## 8. Aceite e limites de evidência

1. Três decisões aceitas consecutivas confirmam; duas não. ID diferente, `None` e qualidade insuficiente interrompem a sequência.
2. Expiração funciona sem novo ciclo de inferência, após inferência lenta e após espera da tecla.
3. Enter confirmado reavalia uma leitura nova e só registra a mesma identidade ainda válida; desconhecido ou troca não aproveita a sequência anterior.
4. Reentrada no modo e confirmação consumida não reutilizam histórico. Memória do domínio permanece limitada a N timestamps e um ID.
5. Modo desligado preserva a 001 e não adiciona inferência no Enter. Qualidade/temporal independentes.
6. Testes com relógio manual, resultados/embeddings sintéticos, câmeras e providers falsos; sem sleep, webcam, dados reais ou serviços.
7. Testes demonstram regras de decisão. Frames correlacionados não provam melhoria biométrica; repetição consistente pode repetir uma identificação errada.
8. Nenhum ajuste de limiar, schema, antispoofing ou política de qualidade; documentação e publicação seguem o prompt.
