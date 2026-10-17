# Prompt de execução — 013 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório
`projeto_reconhecimento_facial`.

**Execute somente a task 013 — Desafio facial no servidor e verificação 1:1. O desenho e o plano estão
definidos. Apenas execute o escopo autorizado, teste e documente; não reabra
brainstorming, não delegue e não avance automaticamente para outra task.**

## Leitura obrigatória

1. `AGENTS.md`, `CLAUDE.md`, instruções relevantes e arquitetura atual.
2. `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`.
3. `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`.
4. `tasks/WEB-CONTRATO-EXECUCAO.md` e `tasks/WEB-MIGRACOES.md`.
5. `tasks/013-web-desafio-verificacao-1a1/DESENHO.md` e `tasks/013-web-desafio-verificacao-1a1/PLANO.md`, integralmente.
6. Resultados reais das dependências: **012**.

Use Superpowers executing-plans quando disponível; aprove internamente escolhas
rotineiras, sem pedir confirmações de decisões já definidas. Isso não amplia
permissões de banco, dados reais, contratação ou publicação.

## Entrega específica

Verificação usa somente três referências ativas da matrícula declarada. Reutilizar FaceEmbedding e distância cosseno normalizada, sem chamar reconhecimento 1:N ou buscar outra matrícula quando houver falha. Política inicial recomendada: mediana das três distâncias <=0,30. Validar FaceNet512/512D, finitude e versão; registrar política como não calibrada. A decisão final exige também desafio, qualidade e antispoofing.

Desafio curto: frente, movimento leve em direção aleatória e retorno; backend emite nonce/etapas e analisa evidências, nunca aceita booleano desafio_ok ou landmarks calculados pelo cliente como prova. Receber sequência limitada de frames. Cada próxima orientação depende do recebimento/validação da etapa anterior. Amplitude/duração e amostragem precisam de medição; declarar parametrização e não fabricar valores de eficácia.

Backend de pose exige prova técnica Linux: adaptar contrato MediaPipe isolado quando adequado, não considerar overlay atual suficiente. Guardar estado/nonce no servidor com prazo curto, ordenar etapas e verificar continuidade da mesma pessoa e uma face em frames relevantes. Para cadastro, consistência entre três referências exige política explícita testável, sem afirmar validade biométrica por sintéticos.

Toda inferência/pose/antispoofing usa o worker012, preservando uma execução ativa. Etapas intermediárias recebem prioridade dentro do mesmo trabalho apenas com timeout e sem manter slot enquanto aguarda câmera; reservar capacidade por tentativa para não prometer continuação sem vaga. Não criar segunda fila oculta.

Alternativa acessível é motivo de revisão manual; não há fallback de aprovação. A emissão de movimento não comprova instante físico da câmera e não elimina deepfake/replay sofisticado.

### Contratos que você deve respeitar

VerificarIdentidade.executar(consulta, referencias[3], politica) -> DecisaoIdentidade.
DesafioCaptura.emitir(contexto, agora) -> Desafio; validar_etapa(desafio_id, sequencia, evidencias, agora) -> EstadoDesafio.
ResultadoFacial: identidade_ok, desafio_ok, antispoofing_ok, qualidade_ok, motivo_tecnico, versao_referencia/politica; detalhes restritos ao backend.
Nenhum serviço facial grava presença por conta própria. O contrato recebe prazos do caso de uso015 e não os amplia.

### Provas mínimas

- Distâncias [0,20;0,29;0,80] aceitam identidade; [0,20;0,31;0,80] recusam; igualdade0,30 aceita conforme política.
- Frame estático, sequência invertida, nonce errado, etapa antiga e cliente declarando sucesso não aprovam.
- Frames de duas identidades/múltiplas faces recusam; ausência de evidência de vida não aprova.
- Serviço não retorna foto/embedding ao professor e não registra presença; risco residual documentado.

## Limites e conclusão

**Não criar interface, páginas, templates ou fluxo de câmera no navegador.** Use testes/cliente HTTP para provar a funcionalidade. UI fica exclusivamente na020.

Não executar migration, acessar banco operacional, conectar Google Drive,
provisionar VPS, realizar deploy ou usar rostos reais sem autorização específica
vigente. Preparar código/migration/testes não significa autorização para aplicá-los.
Não desabilitar antispoofing ou alterar threshold0,30 para fazer testes passarem.
Não interpretar matrícula informada como autenticação.

Verificador1:1 e desafio com protocolo implementado/testado funcionalmente, sem threshold alterado nem promessa de acurácia. Validação biométrica real pendente bloqueia liberação pública, não é substituída por mocks.

Ao terminar, criar `tasks/013-web-desafio-verificacao-1a1/RESULTADO.md`, atualizar índice e relatar comandos
efetivos, contratos, pendências e estado dos gates. **Não fazer commit/push por
autorização herdada de tasks001–008.** A restrição da consolidação atual prevalece;
se o usuário autorizar explicitamente publicação nesta execução, fazer commit
em PT-BR e push na main conforme procedimento do contrato comum. Não contratar
ou implantar como consequência do push.
