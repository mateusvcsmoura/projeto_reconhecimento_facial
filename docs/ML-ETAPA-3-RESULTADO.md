# Etapa 3 — Avaliação operacional experimental 1:N (open-set)

**Data:** 2026-10-10

**Estado:** implementação concluída; avaliação biométrica real pendente.

**Escopo:** pipeline experimental isolado de identificação facial aberta. Nenhuma imagem, embedding ou resultado biométrico real foi carregado, calculado ou publicado nesta etapa.

## 1. Resumo executivo

Foi implementada uma infraestrutura experimental para montar galerias, identificar consultas conhecidas, rejeitar pessoas desconhecidas, selecionar limiar na validação e medir o conjunto de teste uma única vez. A lógica de decisão é independente do matcher operacional. O executor exige um documento local de autorização antes de inventariar imagens, ler o cache de embeddings ou importar o DeepFace; produz artefatos apenas em `avaliacao/`, ignorado pelo Git.

O gate permaneceu fechado: não foi localizada autorização específica para o uso experimental do LFW, e as identidades do teste da Etapa 1 já foram consultadas historicamente. Não houve execução biométrica. Os testes desta entrega usam vetores sintéticos e demonstram comportamento do software, não desempenho facial.

## 2. Objetivo da avaliação 1:N

Para cada consulta, comparar o embedding com uma galeria, selecionar a identidade mais próxima e aceitar somente se a distância cosseno estiver abaixo do limiar congelado. Consultas são classificadas como conhecidas ou desconhecidas por identidade, antes da avaliação. Este experimento mede identificação open-set em uma galeria controlada; não representa a operação completa em sala, prova de vida, webcam ou taxas de presença.

## 3. Estado das etapas anteriores

| Etapa | Estado observado na documentação | Implicação para esta entrega |
|---|---|---|
| 0 | Infraestrutura experimental e divisão por identidade documentadas como validadas; o relatório registra 322 testes naquele momento. | Reutilizada a API pura de divisão, sem abrir dados da Etapa 1. |
| 1 | Calibração 1:1 executada e documentada. O candidato de validação é `0.42817932706540435`; o baseline histórico é `0.30`. O teste da Etapa 1 foi consultado. | `T1` é apenas baseline histórico. Não é assumido como apropriado para 1:N. |
| 2 | Código M0–M4 concluído; avaliação com biometria real pendente. Os classificadores M2–M4 foram exercitados com dados sintéticos. | Nenhum score M2–M4 foi usado nem apresentado como resultado biométrico. |

## 4. Gate de autorização

`avaliacao/` está ignorado pelo Git, assim como extensões de imagens, vetores e caches. Não foram consultados webcam, PostgreSQL, credenciais ou imagens de alunos. A etapa 1 já expôs resultados de teste do LFW; não há inventário nominal autorizado que permita provar que uma nova divisão sobre o mesmo LFW não reutilizaria identidades previamente examinadas.

O LFW não foi carregado. A documentação de origem descreve imagens obtidas de notícias, informa que não houve aviso explícito ou consentimento dos indivíduos, registra que o copyright pertence às publicações originais e que o dataset não tem licença formal, apesar de declarar ausência de taxas ou restrições. Isso não constitui autorização específica para este projeto, sua finalidade ou seu contexto institucional. [Datasheet do LFW, seção de licença e considerações legais](https://www.microsoft.com/en-us/research/wp-content/uploads/2019/01/1803.09010.pdf). A implementação não cria nem presume autorização.

O gate implementado verifica que foi fornecido um arquivo local não vazio; esse teste técnico não julga a validade jurídica, ética ou institucional do documento. Antes de uma futura execução, uma pessoa responsável deve confirmar a proveniência, a finalidade permitida e as aprovações aplicáveis. A existência de um arquivo não substitui essa análise.

## 5. Dataset e proveniência

**Dataset utilizado nesta Etapa 3: nenhum.** Não foram abertas imagens, arrays, pares ou embeddings do LFW. O LFW continua sendo somente um candidato não autorizado para esta execução. Nenhum dado de estudantes ou voluntários foi utilizado.

A documentação scikit-learn descreve o LFW como 13.233 imagens de 5.749 pessoas, mas essas contagens não foram recalculadas neste experimento nem usadas como observações. [Documentação do `fetch_lfw_people`](https://scikit-learn.org/stable/modules/generated/sklearn.datasets.fetch_lfw_people.html).

Há ainda risco de sobreposição com pessoas incluídas no pré-treinamento do FaceNet512; não há evidência de independência que permita descartá-lo. O executor registra FaceNet512, detector OpenCV, alinhamento, normalização, versões e chave de configuração do cache. Hash das imagens de pesos do modelo não foi registrado; essa proveniência permanece uma limitação conhecida.

## 6. Separação de identidades

O cache da Etapa 3 fica isolado por hash da execução e por partição em
`avaliacao/cache/etapa3/<execucao_sha256>/<validacao|teste>`. O hash da execução
inclui dataset, autorização, seed, assinatura da divisão, configuração de
extração e protocolo. A preparação não instancia nem lê o cache compartilhado
das Etapas 1/2 nem qualquer cache de teste; a avaliação final abre somente o
diretório `teste`. Uma divisão ou autorização diferente recebe outro cache.

O pipeline divide identidades em desenvolvimento/calibração, validação e teste na proporção 60/20/20, com seed fixa e configurável. A divisão é realizada antes da construção de galerias ou consultas. Dentro de cada partição, as identidades conhecidas são separadas das desconhecidas; para cada identidade conhecida, imagens distintas são sorteadas deterministicamente para referência e consulta. Imagens desconhecidas nunca entram na galeria.

Hashes de conteúdo eliminam duplicatas exatas antes da divisão, incluindo duplicatas entre identidades. A auditoria heurística conta pares da mesma identidade com distância de embedding inferior a `0.01`, sem remover dados. Esse indicador é executado após extração autorizada e não equivale a detecção visual/perceptual de duplicatas; duplicatas quase iguais entre identidades não são classificadas por esse indicador.

O teste fica sem embeddings e sem scores na fase `preparar`. A fase `avaliar` grava um marcador exclusivo antes de inventariar o dataset ou ler o cache. O marcador é consumido mesmo que a execução posterior falhe; isso é conservador e evita reabertura acidental do holdout.

## 7. Construção da galeria

O cenário de três referências é construído primeiro. O cenário pareado de uma
referência escolhe deterministicamente uma referência válida dentro das três
reservadas e mantém exatamente as mesmas identidades conhecidas/desconhecidas
e as mesmas imagens de consulta. Assim, a diferença entre esses dois cenários
não decorre de novas consultas ou de uma população diferente. A comparação
fica restrita às identidades com imagens suficientes para três referências e
uma consulta; seus denominadores são registrados separadamente. T0/T1 são
avaliados mesmo se T2 não puder ser calibrado.

`Galeria` aceita embeddings com dimensão e modelo homogêneos, normaliza os vetores na fronteira e mantém pseudônimos somente em memória. A estratégia executada por padrão é a menor distância entre as referências da identidade. Para galerias de tamanhos diferentes, identidades removidas deixam de ser conhecidas e suas consultas passam ao grupo desconhecido; não são descartadas do denominador.

O pipeline compara uma referência por identidade e, quando há imagens suficientes, três referências por identidade. A seleção de T2 para três referências é feita separadamente na validação. Há também estratégia de centroide normalizado implementada e testada em unidade, mas não incluída no executor comparativo desta etapa.

## 8. Construção das consultas

Consultas conhecidas usam imagens diferentes daquelas escolhidas como referência. Consultas desconhecidas vêm de identidades que não possuem referência na galeria daquele cenário. Ao reduzir a galeria, consultas de identidades removidas passam a ser desconhecidas para aquele tamanho. A semente governa o sorteio dos papéis e das imagens; quantidades de referências, consultas e falhas são agregadas nos metadados.

## 9. Algoritmo de identificação

Os vetores são L2-normalizados; a distância utilizada é `1 - similaridade cosseno`, limitada numericamente ao intervalo `[0, 2]`. O menor valor seleciona o candidato. Valores iguais dentro da tolerância de `1e-12` causam rejeição conservadora e desempate independente da ordem da galeria. Galeria vazia não retorna identidade fictícia. Modelo, dimensão, valores finitos e limiar são validados.

## 10. Estratégias de limiar

| Código | Valor/uso |
|---|---|
| T0 | `0.30`, baseline histórico, sem recalibração. |
| T1 | `0.42817932706540435`, limiar de validação 1:1 da Etapa 1, usado somente como referência comparativa. |
| T2 | Maior limiar observável selecionado na validação para o alvo exploratório de FPIR `0.001` (0,1%), com cenário separado para uma e três referências. |

Além do T2 principal de uma referência, o congelamento mantém calibrações
separadas para uma e três referências no subconjunto pareado. Se qualquer T2
não puder ser estimado, esse baseline fica indisponível; T0 e T1 continuam
comparáveis no cenário correspondente.

O alvo de 0,1% é carregado como hipótese experimental associada ao critério de FAR da Etapa 1, não como teto validado para 1:N nem requisito de produção. O tamanho efetivo da amostra desconhecida determina se o critério é informativo. Com alvo `0.001`, a regra de três exige cerca de 3.000 identidades desconhecidas independentes para que zero falsas identificações dê um limite superior aproximado de 95% nesse nível; uma validação típica menor será marcada como insuficiente. Mesmo quando insuficiente, um valor empírico de T2 não é apresentado como garantia.

Empates são rejeitados e permanecem no denominador de consultas desconhecidas extraídas usado para aplicar o orçamento FPIR. Se todos os candidatos válidos forem empates, o limiar máximo é avaliado; se a galeria não tiver referências extraídas, T2 fica indisponível.

O conjunto de teste nunca seleciona limiar. A curva de teste, se uma execução autorizada ocorrer, é apenas descritiva; o uso do gráfico não autoriza escolher novo limiar após observar o teste.

## 11. Métricas implementadas

FPIR e FNIR são computados end-to-end e condicionados à extração bem-sucedida, com denominadores expostos. FNIR inclui rejeição de conhecido, troca de identidade, empate, referência indisponível e falha de extração. Também são contabilizados identificação correta, top-1, rejeição de desconhecido, trocas, falsas identificações, empates, falhas de extração de consulta/referência e galeria vazia.

Falha de extração não é silenciosamente removida: conta como erro no FNIR end-to-end; para desconhecidos, entra no denominador end-to-end e não gera falsa aceitação, mas também não entra como rejeição bem-sucedida na taxa de rejeição. As taxas condicionais usam somente consultas com embedding válido.

O tempo mediano é medido separadamente para comparação de embeddings e decisão por consulta, em diferentes tamanhos de galeria. A inferência FaceNet512 não faz parte desses tempos. Intervalos percentis de 95% reamostram grupos de consultas por identidade. Eles condicionam a galeria fixa; a variação de identidade da galeria não é reamostrada e permanece fora desses intervalos.

## 12. Resultados reais

Não há resultados biométricos reais medidos nesta etapa. Valores T0/T1/T2 registrados acima descrevem apenas parâmetros candidatos; não são taxas de erro. A tabela comparativa permanece indisponível até haver dataset autorizado e execução sob o protocolo congelado.

| Cenário | FPIR | FNIR | Identificação correta | Top-1 | IC agrupado | Estado |
|---|---:|---:|---:|---:|---|---|
| T0, uma referência | Pendente | Pendente | Pendente | Pendente | Pendente | Não executado |
| T1, uma referência | Pendente | Pendente | Pendente | Pendente | Pendente | Não executado |
| T2, uma referência | Pendente | Pendente | Pendente | Pendente | Pendente | Não executado |
| T0/T1/T2, três referências | Pendente | Pendente | Pendente | Pendente | Pendente | Não executado |

## 13. Gráficos

O gerador está implementado para produzir, a partir de resultados reais mantidos em memória: FPIR versus FNIR, identificação em função do limiar entre 0 e 2, identificação correta e top-1 por tamanho da galeria, tabela agregada de tipos de erro no T2 (ou T0 se T2 estiver indisponível), distribuição de distâncias, comparação dos limiares disponíveis, latência por tamanho e comparação pareada de uma versus três referências com T0 fixo. **Nenhum gráfico foi produzido nesta entrega**, pois não houve avaliação biométrica real. Os arquivos PNG futuros serão gravados apenas em `avaliacao/resultados/etapa3/graficos/`.

## 14. Avaliação por tamanho da galeria

O executor predefine tamanhos `1`, `10`, `25`, `50`, `100` e o tamanho completo, removendo valores acima do número disponível. A identidade selecionada para cada subconjunto segue ordenação determinística por pseudônimo. O T2 calibrado na validação para a galeria completa fica fixo na comparação de tamanhos; portanto a série mede sensibilidade ao tamanho sob o mesmo limiar, e não recalibração por tamanho. O conjunto de consultas conhecidas reduz-se junto com a galeria; consultas das identidades retiradas entram no grupo aberto.

## 15. Avaliação de múltiplos embeddings

Quando a validação comporta o cenário, o pipeline reserva três imagens de referência e usa imagens distintas como consulta. O cenário de uma referência seleciona uma referência válida dentre as mesmas três; as consultas e a população são idênticas. A regra padrão usa distância mínima, e T2 é calibrado separadamente para os dois cenários na validação. T0/T1 não dependem da disponibilidade de T2. Se o número de imagens ou identidades for insuficiente, o comparativo é marcado como indisponível. Nenhuma conclusão sobre superioridade está disponível sem execução real.

## 16. Falhas de extração

Ausência de rosto, múltiplos rostos, imagem ilegível, erro de leitura, falha de inferência e embedding inválido são contabilizados separadamente. Uma falha inesperada aborta o processamento com mensagem sanitizada, sem imprimir caminhos ou IDs. Falhas de cadastro/referência são contadas além das falhas de consulta. Nesta entrega nenhuma imagem passou por extração; as categorias só foram validadas por fixtures sintéticas.

## 17. Intervalos de confiança

O bootstrap agrupa consultas pela identidade, preservando a dependência entre múltiplas imagens da mesma pessoa. O estimador é condicionado à composição fixa da galeria e não representa variação entre galerias reamostradas. Com menos de duas identidades de consulta, o intervalo não é calculado. Para zero falsas identificações, o relatório também mostra o limite superior aproximado da regra de três, usando identidades como unidade conservadora; zero observado não significa FPIR real igual a zero.

## 18. Limitações estatísticas

Sem dataset, quantidade efetiva e intervalos não existem. Pares de consulta e comparações com a galeria compartilham identidades; não são observações independentes. A calibração de 0,1% pode ser impossível de sustentar com uma validação pequena, e o LFW já teve o teste da Etapa 1 consultado. Uma nova seed sobre o mesmo LFW não prova independência histórica. Também há mudança de domínio relevante entre fotografias públicas e webcam da sala, além de possível sobreposição com o pré-treinamento FaceNet512. O risco de viés e representatividade do LFW é documentado na própria datasheet de origem.

## 19. Testes automatizados

Os testes sintéticos cobrem identificação, rejeição, troca, desconhecidos, galeria vazia, empate, dimensão/modelo inválidos, NaN, normalização, múltiplas referências, estratégias, divisão reprodutível, não sobreposição de identidades/imagens, falhas, métricas end-to-end/condicionais, T2, bootstrap por identidade, redução de galeria, gate de autorização e consumo único do teste. Não dependem de webcam, PostgreSQL, rede, dataset facial ou pesos DeepFace.

Verificação executada: **575 testes passaram** na suíte completa, incluindo testes com dados sintéticos para galeria, cenários de decisão, métricas, seleção de limiar, pareamento de referências e uma preparação/avaliação do executor com extrator e cache sintéticos. O teste de integração confirma que o teste não é extraído durante a calibração, que validação e teste usam caches diferentes e que T0/T1 permanecem disponíveis quando T2 falta. **Ruff** passou na base completa e **mypy** passou nos 64 arquivos configurados. Os testes sintéticos não constituem validação biométrica.

## 20. Impacto no sistema operacional

Nenhum arquivo de `src/` foi alterado. `FACE_THRESHOLD`, matcher, FaceNet512 operacional, anti-spoofing, webcam, cadastro, PostgreSQL, schema, migrations e interface permanecem intactos. Os modelos e artefatos experimentais não são ligados ao reconhecimento 1:N da aplicação. Não houve commit.

## 21. Conclusão acadêmica

A implementação viabiliza uma avaliação open-set 1:N com identidades disjuntas entre desenvolvimento, validação e teste, rejeição conservadora de empates, métricas que incluem falhas e holdout consumido uma vez. A evidência disponível sustenta a correção do software em cenários sintéticos; não sustenta taxas de reconhecimento, segurança, equidade ou adequação operacional. A validação biométrica continua pendente.

## 22. Pendências

1. Obter autorização verificável para uma finalidade de pesquisa compatível e registrar a decisão institucional; ou escolher participantes voluntários com consentimento específico, retenção mínima e procedimento aprovado.
2. Usar fonte e identidades que não reutilizem o holdout histórico da Etapa 1, ou documentar formalmente a sobreposição inevitável sem chamar o resultado de teste independente.
3. Confirmar qual teto FPIR 1:N é um requisito de negócio defensável; o alvo atual `0.001` é apenas exploratório.
4. Executar preparação, congelamento e uma única avaliação final em ambiente experimental isolado.
5. Revisar distribuição demográfica, erros e riscos de reidentificação antes de compartilhar qualquer resultado.

## 23. Preparação para a Etapa 4

A Etapa 4 pode planejar um piloto controlado com participantes e consentimento apropriado, avaliação de domínio com câmera real, verificação de segurança/anti-spoofing e governança institucional. Não conectar os modelos experimentais ao matcher nem alterar o limiar operacional com base nesta entrega. Qualquer adoção requer autorização explícita, dados representativos, critérios FPIR/FNIR aprovados, revisão de riscos e aprovação separada.

### Comandos previstos para uma execução autorizada

```powershell
python -m scripts.experimento_identificacao_aberta preparar `
  --dataset avaliacao/datasets/<dataset-autorizado> `
  --autorizacao-dataset avaliacao/autorizacoes/<documento-real> `
  --seed 42

python -m scripts.experimento_identificacao_aberta avaliar `
  --dataset avaliacao/datasets/<dataset-autorizado> `
  --autorizacao-dataset avaliacao/autorizacoes/<documento-real>
```

O arquivo de autorização deve existir legitimamente; o comando não o cria. A fase `preparar` usa apenas a validação para congelar T2. A fase `avaliar` confere a assinatura do congelamento e consome o teste uma vez. Um novo experimento exige novo checkout/ambiente de holdout, não a remoção manual do marcador.
