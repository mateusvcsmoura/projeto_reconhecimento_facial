# 003 — Desenho técnico: rejeição por ambiguidade

Estado: aprovado internamente para execução; implementação pendente.

Executor: Luna 6, esforço High. Pré-requisitos: tarefas 001 e 002 concluídas.

## 1. Análise do estado atual

Inspeção em `main`, HEAD `0e17c12`, após `0ebe1f7` (implementação temporal) e `0e17c12` (registro documental). Antes deste pacote, `git status --short` não listou alterações; emitiu avisos de acesso aos temporários antigos de pytest. O remoto não foi consultado nesta análise.

O relatório da 002 registra 707 testes unitários, Ruff e mypy aprovados. São resultados históricos do executor anterior, não testes reexecutados nesta preparação. O índice marca a 002 publicada; a seção final do RESULTADO.md ainda descreve o instante anterior ao push. Os commits locais confirmam a implementação e a atualização do índice, mas esta análise não certifica novamente o remoto. Não editar o relatório histórico como parte da 003.

Código confirmado:

- `ConfirmadorTemporal` acumula ID/timestamps, interrompe com `None` e expira conforme janela/validade.
- A CLI separa o laço anterior do laço temporal; este reidentifica uma nova leitura ao receber Enter elegível e consome a sequência após registrar.
- Existem **três pontos** de chamada a `ReconhecerAluno.identificar` na CLI: laço sem temporal, ciclo temporal normal e confirmação temporal no Enter. Os três tratam qualidade insuficiente.
- `MatrizDeReferencia.melhor_candidato` calcula uma única vez `1.0 - matriz @ consulta.vetor`, escolhe `np.argmin` e aplica somente o limiar. Não examina o segundo melhor candidato.
- Em empate exato, `np.argmin` escolhe a primeira linha. A docstring atual exagera ao dizer que a ordem deixa de decidir empates; essa afirmação deve ser corrigida.
- `ReconhecerAluno` converte ausência/múltiplos rostos em `None` e propaga as demais falhas. O mesmo caso de uso é utilizado na confirmação do Enter.

Conclusão: a 002 não resolve candidatos próximos; repetir uma decisão pode repetir um empate escolhido pela ordem. A 003 deve recusar essa observação antes de alimentar o confirmador. A análise foi direcionada à integração, não uma revisão completa de todos os módulos da 002.

## 2. Objetivo e fronteiras

Adicionar uma política optativa que compare as duas melhores **identidades distintas** e recuse quando não houver separação suficiente, mesmo se a melhor distância atender ao limiar operacional.

Não alterar a forma de calcular embeddings/distâncias, `FACE_THRESHOLD=0.30`, detector, modelo, antispoofing, qualidade, contagem/tempos temporais ou frequência de inferência. Não implementar cadastro de múltiplas referências, pose, aprendizado/calibração, benchmarks, API, Neon ou migrações.

Reutilizar o matcher NumPy existente. Não criar ranking completo, serviço externo, novo pipeline de inferência, DTO geral de diagnóstico ou UI para escolher entre pessoas. O operador não pode ignorar a recusa escolhendo um dos candidatos.

## 3. Configuração sem margem supostamente calibrada

| Ambiente / campo Settings | Default | Regra |
|---|---|---|
| `FACE_AMBIGUITY_ENABLED` / `face_ambiguity_enabled` | false | booleano |
| `FACE_AMBIGUITY_MIN_MARGIN` / `face_ambiguity_min_margin` | None | quando fornecida, número finito em [0, 2], não booleano |

- Com flag desligada, injetar política `None`: preservar exatamente a decisão anterior, inclusive desempate pela primeira linha, e não fazer comparação adicional top-2.
- Com flag ligada, margem é **obrigatória**, inclusive para escolher explicitamente `0.0`. Sem ela, Settings falha com mensagem acionável, antes de abrir câmera ou conectar ao banco. Não escolher um default positivo por conta própria.
- `0.0` ativa somente recusa de empates exatos nas distâncias computadas. Uma margem positiva permite recusar candidatos próximos, mas não possui valor recomendado/calibrado nesta entrega.
- Valor inválido fornecido é erro mesmo quando a flag estiver desligada. Campo ausente é None; não escrever variável vazia na `.env.example`.
- No exemplo de ambiente: incluir `FACE_AMBIGUITY_ENABLED=false` e `# FACE_AMBIGUITY_MIN_MARGIN=0.0`, explicando que descomentar e ligar recusa somente empates. Não editar `.env` real.
- Qualidade, temporalidade e ambiguidade são flags independentes: oito combinações possíveis, sem alterar limiar ou antispoofing.

Nenhuma calibração biométrica pode ser inferida de vetores de teste. Os valores positivos usados em testes/documentos são exemplos matemáticos, não recomendação operacional.

## 4. Contratos e algoritmo

### Política no matcher

Adicionar em `src/domain/services/matcher.py`:

```python
@dataclass(frozen=True, slots=True)
class PoliticaAmbiguidade:
    margem_minima: float
```

Campo obrigatório, sem default. Validar na construção direta: número real finito em [0, 2], rejeitar booleano, string e valores inválidos com `ValueError`; aceitar inteiro numérico e converter para float. Settings aceita strings numéricas de ambiente, mas valida antes da coerção para não aceitar booleanos como margem.

Estender o método existente com argumento somente nomeado:

```python
def melhor_candidato(
    self,
    consulta: FaceEmbedding,
    limiar: float,
    *,
    ambiguidade: PoliticaAmbiguidade | None = None,
) -> Identificacao | None:
```

As assinaturas são contratos para implementar; não copiar corpos vazios. `Identificacao` permanece com `aluno_id` e `distancia`. Não adicionar segundo ID/nomes ou probabilidades ao retorno.

### Regra de decisão

1. Validar o argumento de política (None ou `PoliticaAmbiguidade`). Preservar os controles existentes de galeria vazia, modelo e dimensão.
2. Calcular o vetor de distâncias uma única vez, exatamente pelo caminho atual. Escolher índice/d1 como hoje.
3. Se d1 > limiar, retornar `None` **antes** de avaliar ambiguidade. Empate entre desconhecidos não é identificação candidata ambígua.
4. Se política None, devolver o resultado anterior sem consultar segundo candidato.
5. Se ligada, encontrar d2 = menor distância entre linhas cujo ID seja **diferente** do ID do melhor candidato. Não filtrar os concorrentes pelo limiar: alguém logo acima de 0.30 ainda pode estar muito próximo do primeiro.
6. Se não existir outra identidade, aceitar o único candidato quando d1 satisfizer o limiar; não inventar d2=0/2 nem margem infinita no resultado.
7. Converter d1/d2 para floats Python e calcular `gap = d2 - d1` sem arredondar. Recusar quando `gap <= 0.0` (empate) **ou** `gap < politica.margem_minima`.
8. Caso contrário, devolver o mesmo `Identificacao` do baseline. Gap positivo exatamente igual à margem é aceito. Empate continua recusado mesmo com margem zero.

Implementar busca do concorrente por máscara/redução linear sobre IDs distintos. Não ordenar N candidatos nem executar novo produto matriz-vetor para obter o segundo. Não transformar o trabalho em benchmark ou otimização da galeria.

Embora o schema atual use um embedding por pessoa, o construtor do matcher recebe pares e permite IDs repetidos. Ignorar linhas do mesmo ID ao procurar d2 evita falsa ambiguidade da pessoa consigo mesma e não implementa múltiplas referências no cadastro/banco. Exemplo: A0, A0, B0.5 compara A com B; A0, A0, B0 recusa A/B.

### Exemplos matemáticos

Distâncias abaixo são exemplos didáticos, não resultados biométricos:

| d1 / d2 de identidades distintas | Margem | Resultado com política ligada e limiar 0.30 |
|---|---:|---|
| 0.10 / 0.10 | 0.0 | ambíguo |
| 0.10 / 0.11 | 0.02 | ambíguo |
| 0.10 / 0.20 | 0.02 | aceita melhor candidato |
| 0.29 / 0.31 | 0.03 | ambíguo; segundo acima do limiar ainda conta |
| 0.40 / 0.40 | 0.02 | None; melhor candidato fora do limiar |
| 0.10 / inexistente | 0.02 | aceita única identidade |

Não usar estes decimais como teste de igualdade binária exata. Testes de fronteira devem usar valores exatamente representáveis ou referência independente. Não usar `np.isclose`, epsilon arbitrário, clipping ou arredondamento para modificar a regra. Distâncias float32 podem ter pequenas diferenças entre plataformas; margem zero detecta apenas igualdade calculada. A política não é uma probabilidade.

## 5. Erro, caso de uso e composição

Criar `IdentificacaoAmbigua(ErroDeDominio)` em `src/domain/errors.py`, sem argumentos obrigatórios e sem IDs/nomes/embeddings/distâncias armazenados na exceção. O matcher lança esse erro nas recusas da política. Trata-se de duas identidades próximas para **um rosto**, não de `MultiplosRostosDetectados` ou de `QualidadeCapturaInsuficiente`.

Em `ReconhecerAluno.__init__`, acrescentar ao final argumento somente nomeado `ambiguidade: PoliticaAmbiguidade | None = None`. Preservar os quatro argumentos posicionais antigos, pois testes os utilizam. Guardar a política e repassá-la ao matcher. `identificar` mantém retorno `Reconhecimento | None` e **propaga** `IdentificacaoAmbigua`; não converter em None, qualidade ou erro do modelo. A extração continua uma vez por chamada.

Em `main.montar_menu`, construir a política quando a flag estiver ligada e injetá-la no caso de uso, não no DeepFaceAdapter ou confirmador temporal. Usar a validação prévia de Settings e estreitamento explícito de tipo para o valor opcional; não fazer fallback silencioso para zero/None se a configuração deveria estar ativa.

## 6. CLI: três caminhos obrigatórios

Adicionar orientação em `mensagens.py`:

- Problema: `Identificacao ambigua.`
- Ação: `Olhe de frente para a camera, ajuste a posicao e tente novamente.`

Exibir a mensagem completa em amarelo, sem nomes, lista de candidatos, pontuações ou opção de ignorar. Essa orientação não significa que estimativa de pose foi implementada.

Tratar a nova exceção especificamente nos três pontos de identificação. Pode compartilhar handler com qualidade via tupla de exceções, mantendo os tipos distintos e usando `para_operador`.

| Caminho | Efeito obrigatório da recusa |
|---|---|
| Sem temporal, ciclo normal | limpar `reconhecido`, mostrar orientação, manter câmera; Enter não registra candidato anterior |
| Temporal, ciclo normal | limpar `reconhecido`, `confirmador.observar(None, capturado_em)`, consultar estado; mostrar orientação; nenhuma observação válida |
| Temporal, nova captura no Enter | mesmo reset com timestamp da nova leitura; não registrar; continuar câmera aberta e exigir sequência nova |

Usar `observar(None, capturado_em)`, não `reiniciar`, para preservar a regra de timestamps da 002. Ambiguidade repetida nunca acumula contagem. Falhas de modelo, fraude e leitura mantêm tratamento anterior; não ampliar catch para toda `ErroDeDominio`.

No modo temporal, o Enter atualmente pode substituir a orientação de uma recusa pelo texto genérico `Aguarde a validacao da identidade.`. Para ambiguidade, preservar sua orientação até a próxima observação válida ou outra recusa específica; Enter sem elegibilidade não deve ocultá-la. Manter um indicador local de recusa recuperável, ou estado equivalente, sem comparar strings para decidir regra. Não transformar isso numa reescrita da máquina temporal. A orientação de qualidade pode usufruir do mesmo mecanismo, sem mudar sua regra de aceitação.

Não há nova inferência para top-2: a confirmação temporal existente já chama o caso de uso e portanto aplica a política. Não adicionar inferência no Enter do modo sem temporal. Não modificar cadastro, viewer, schema ou script experimental.

## 7. Aceite e limites de evidência

1. Flag desligada preserva identidade/distância/None e ordem de empate do baseline; testes anteriores continuam válidos.
2. Flag ligada recusa empates e gap abaixo da margem explícita; igualdade positiva aceita; melhor fora do limiar permanece desconhecido.
3. Segundo candidato tem ID distinto e é considerado mesmo acima do limiar; uma identidade não causa falsa ambiguidade.
4. Nenhum dos três caminhos de CLI registra após ambiguidade ou reaproveita sequência/candidato anteriores. Câmera continua aberta, recuperação ocorre em decisões não ambíguas.
5. Qualidade, temporalidade e ambiguidade funcionam independentemente; limiar e antispoofing preservados.
6. Testes com embeddings sintéticos, relógio manual e fakes; sem rostos, serviços ou treinamento.
7. Documentação não recomenda margem positiva como calibrada, não afirma ganho de precisão e informa que a política pode aumentar recusas e não impede erros com grande separação.
8. Registro de comandos reais, relatório, commit e push conforme prompt; não repetir resultados antigos como se fossem novos.
