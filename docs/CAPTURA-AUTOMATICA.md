# Captura automática

A captura automática é o modo padrão para cadastrar uma pessoa e registrar a
presença de um aluno. Cada abertura da câmera atende a uma única operação e
retorna ao menu quando termina. O recurso não muda o limiar `0.30`, o modelo de
embedding, o anti-spoofing ou as regras de reconhecimento.

## Configuração

As opções ficam no `.env`:

| Variável | Padrão | Uso |
|---|---:|---|
| `FACE_AUTO_CAPTURE_ENABLED` | `true` | `false` recupera ESPAÇO no cadastro e ENTER no reconhecimento |
| `FACE_AUTO_CAPTURE_WAIT_SECONDS` | `5.0` | Tempo mínimo entre o início e a observação válida mais recente |
| `FACE_AUTO_CAPTURE_SAMPLE_SECONDS` | `0.5` | Intervalo mínimo entre análises, contado do fim da análise anterior |
| `FACE_AUTO_CAPTURE_MAX_AGE_SECONDS` | `2.0` | Idade máxima de uma análise e gap máximo entre observações |

Os três tempos precisam ser finitos e positivos. O intervalo de análise precisa
ser menor que a idade máxima. A política sempre exige ao menos três análises
com timestamps distintos; esse mínimo não é configurável.

## Como a sequência funciona

O controlador puro recebe uma chave, o instante anterior à leitura do frame e
o instante atual após a análise. Ele mantém apenas a chave, o primeiro e o
último timestamp e uma contagem. Não guarda imagens, coordenadas ou embeddings.
Uma sequência só fica pronta depois do tempo mínimo, de três observações
válidas da mesma chave e enquanto a evidência mais recente não venceu. Troca
de chave, resultado ausente, recusa ou gap excessivo reiniciam a contagem. O
relógio sozinho não cria observações nem torna a sequência pronta.

O intervalo de análise é medido desde o fim da inferência anterior. Enquanto
aguarda, a aplicação segue lendo e exibindo frames e consultando ESC; não faz
uma espera cega de cinco segundos. A inferência de reconhecimento continua
síncrona e pode pausar momentaneamente a interface. O timestamp é coletado
antes de chamar a câmera, mas o dispositivo pode entregar um frame antigo de
seu buffer.

No cadastro, nome, matrícula e consentimento são tratados antes da câmera
abrir. As análises de sondagem só validam uma face única, sem gerar embedding e
sem gravar dados. Quando a sequência fica pronta, o sistema lê outro frame e
prepara uma única face com a detecção, qualidade e anti-spoofing já existentes.
Depois de mostrar o frame final e processar ESC, verifica novamente os prazos
antes de gravar o recorte e o embedding. Recusas ou expiração descartam essa
preparação e retomam a busca na mesma sessão, sem pedir identificação ou
consentimento de novo.

No reconhecimento, cada análise usa o caso de uso existente e a galeria já
carregada. O mesmo ID precisa permanecer válido durante a sequência e ser
identificado novamente num frame final. Resultado desconhecido, ambiguidade,
qualidade insuficiente, fraude suspeita, troca de pessoa ou evidência vencida
impedem o registro. Se `FACE_TEMPORAL_ENABLED=true`, a confirmação temporal
existente também precisa estar atual e confirmada para o mesmo ID. Uma sessão
registra no máximo uma presença. Se ela já existir naquele dia, informa isso e
fecha a câmera sem tentar um segundo registro.

ESPAÇO e ENTER são ignorados no modo automático; ESC cancela antes da
persistência. Erros de câmera, modelo ou armazenamento são reportados e
encerram a operação, sem retry automático de gravação. A câmera e a janela
fecham também em cancelamentos e exceções. A janela de landmarks continua
desenhando somente sobre uma cópia para exibição. Sua presença, ausência ou
lentidão não aprova a captura; o prazo é revalidado depois da apresentação.

## Fallback manual

Para voltar ao comportamento manual, ajuste no `.env`:

```dotenv
FACE_AUTO_CAPTURE_ENABLED=false
```

No cadastro, ESPAÇO tenta capturar e ESC cancela. No reconhecimento, ENTER
registra a identidade mostrada e ESC sai. Com `FACE_TEMPORAL_ENABLED=true`, o
fluxo manual conserva a confirmação e a reidentificação já existentes.

Para reverter a configuração, defina novamente `true`; não é preciso migrar o
banco, recriar embeddings nem alterar arquivos de modelo. Os demais controles
continuam independentes.

## Roteiro visual manual

Este roteiro ainda precisa ser executado no computador da aplicação. Não foi
usado como parte da validação automatizada desta tarefa.

1. Configure a câmera, o `.env` e o banco conforme o [README](../README.md),
   com a autorização e o consentimento aplicáveis ao cadastro de teste.
2. Execute `python -m src.main`, abra Cadastro e aceite o termo. Confira que a
   câmera abre sem pedir ESPAÇO e que a interface mostra o progresso.
3. Mantenha uma única pessoa diante da câmera; confirme que o cadastro só é
   persistido após a sequência e a validação do frame final. Repita usando
   ESC durante a busca e antes da gravação para conferir o cancelamento.
4. Abra Reconhecimento e confirme que uma identidade permanece indicada até a
   nova verificação e que o registro fecha a janela. Se a presença já existir,
   confira a mensagem e o mesmo encerramento.
5. Defina `FACE_AUTO_CAPTURE_ENABLED=false`, reinicie a aplicação e confira
   ESPAÇO e ENTER. Volte a `true` ao terminar.

Os testes automatizados usam relógio, frames e serviços dublados. Eles cobrem
contratos e efeitos de software, mas não validam visualmente uma pessoa,
qualidade biométrica, identificação 1:N nem eficácia do anti-spoofing. As
observações usam frames correlacionados e não são evidência de melhora de
acurácia.
