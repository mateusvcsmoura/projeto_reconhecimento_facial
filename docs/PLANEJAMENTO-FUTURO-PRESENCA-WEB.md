# Planejamento futuro — verificação de presença pela web

Última atualização: **17/10/2026**.

Documento vivo das conversas com o usuário. Registra intenções, propostas e pendências; **não é uma task autorizada para implementação ou implantação**. Acrescentar decisões futuras neste arquivo e marcar explicitamente propostas substituídas. Não transformar estimativas em resultados medidos.

## Intenção confirmada pelo usuário

- Evoluir para um serviço de verificação de presença em tempo real, acessível por link no navegador de celular, desktop ou notebook.
- O professor gera e compartilha o link; o aluno permite a câmera, fornece as informações necessárias e valida a presença. A aplicação persiste os registros pelo backend.
- A presença pode ser remota: **não há exigência de localização física em sala**. Geolocalização, Wi-Fi institucional e comprovação de presença física não fazem parte do requisito.
- O objetivo não inclui videoconferência ou sala de aula virtual.
- A captura deve acontecer naquele momento, dentro de uma faixa de horário configurada pelo professor.
- Manter o contexto de turmas, matrícula global única e possibilidade de um aluno participar de várias turmas, conforme decisão anterior.
- Preferência anterior por captura automática após abertura da câmera, sem botão obrigatório de captura, deve orientar a experiência web; os detalhes precisam ser adaptados ao navegador.
- Escala inicial informada: poucas requisições; no dia da apresentação, aproximadamente **30 links gerados e 50 imagens**. Esses números não significam 30 servidores, 50 usuários simultâneos ou 50 imagens por segundo.
- Estimativa atual solicitada: hospedagem disponível **24 horas por dia durante 10 dias (240 horas)**. A estimativa mensal anterior fica como referência de preços. Nenhum serviço foi contratado ou provisionado nesta conversa.
- Confirmado cadastro remoto por link específico de turma: aluno informa nome/matrícula e captura a foto; backend registra cadastro e vínculo para verificações posteriores.
- Professor recebe confirmação da presença validada e pode exportar relatório simples da turma selecionada, de um dia ou de intervalos abrangendo outros dias/meses.
- Manter criação, leitura, atualização e exclusão de turmas/alunos, além do compartilhamento dos links. “Enviar turma/alunos” foi interpretado como compartilhar acesso/convites; envio de arquivos ou importação em lote não foi definido.

## Fluxo proposto, ainda a detalhar

1. Professor autenticado seleciona uma turma e configura início/fim da janela de presença.
2. Sistema gera link temporário associado à turma e à janela; QR Code é uma conveniência sugerida, não um requisito confirmado.
3. Aluno acessa pelo navegador, recebe explicação do tratamento dos dados e solicita acesso à câmera.
4. Backend cria uma tentativa temporária; captura e validação ficam vinculadas a essa tentativa.
5. Backend verifica janela de horário, identidade, vínculo com turma, validade da tentativa e duplicidade.
6. A presença aceita é persistida; aluno recebe confirmação e professor acompanha o resultado no contexto de sua turma. Não confirmar sucesso antes de concluir a persistência.
7. Professor seleciona turma e data/período e exporta relatório de presenças.

### Cadastro por link — confirmado

Professor gera link com finalidade **cadastro** vinculado à turma. Aluno informa nome e matrícula, recebe informações de tratamento/consentimento, permite câmera e captura sua foto. Backend valida os dados, prepara referência facial e persiste cadastro/vínculo. Manter matrícula global única e N:N: matrícula existente não pode ter foto/nome substituídos por alguém que apenas acessou um link. A autorização para vincular cadastro existente e verificar a identidade declarada permanece a definir.

Informações estruturadas e referência ao artefato facial ficam no banco; a exigência de armazenar o cadastro não obriga guardar bytes da foto em PostgreSQL. Proposta: preservar armazenamento privado da referência e embedding no banco, com retenção/acesso definidos. Não duplicar a foto por turma.

Links de cadastro e presença têm finalidades distintas, validadas no servidor; um não pode ser usado no endpoint do outro. A janela de aula é requisito confirmado do link de presença. Expiração do convite de cadastro deve ser definida separadamente.

### Professor, relatórios e manutenção

- Introduzir entidade Professor e relação de autorização com turmas; cardinalidade (um ou vários professores por turma) ainda a decidir. Login/conta não pode ser substituído por um ID enviado livremente pelo cliente.
- Proposta inicial de confirmação: atualizar o painel do professor por consulta periódica, sem exigir e-mail, WhatsApp, push ou WebSockets. Canal e intervalo ainda não foram escolhidos.
- Relatório simples: CSV UTF-8 como proposta inicial, filtrado por turma e data inicial/final inclusivas no fuso do projeto. Seleção de mês vira intervalo de datas. Incluir turma, matéria, período, matrícula, nome, data e horário da presença; não exportar fotos/embeddings/tokens.
- Autorizar o professor para a turma também no download do relatório. Tratar CSV com escape correto e proteção contra fórmulas em campos fornecidos pelo usuário. Não inferir faltas a partir de ausência de registro sem calendário/roster histórico apropriado.
- CRUD de turmas/alunos permanece. Preservar distinção entre desvincular aluno, excluir turma logicamente e excluir aluno globalmente. Atualização de nome/vínculo não implica recaptura facial; mudança de matrícula e substituição de biometria precisam de regras próprias.

Os nomes “janela” ou “sessão de presença” representam uma autorização temporal de registro; não uma chamada de vídeo. O link não dá acesso direto ao PostgreSQL nem contém credenciais do banco.

## Captura recente e identidade

HTTPS e permissão do navegador são necessários para acessar a câmera na web. Não é possível ativá-la silenciosamente. Captura automática significa automatizar o fluxo **depois** da permissão necessária.

Abrir a câmera na interface, ocultar seleção de arquivos ou receber uma imagem dentro do horário não comprova, por si só, que a imagem foi produzida naquele instante. O cliente pode ser modificado e requisições podem ser repetidas.

Proposta a desenhar: tentativa com identificador/desafio emitido pelo servidor, expiração curta, consumo controlado e proteção contra reenvio. Avaliar prova de vida adequada ao fluxo remoto, sem afirmar que token ou MiniFASNet isoladamente comprovam frescor/autenticidade. Não prometer segurança absoluta ou resultados biométricos não medidos.

O horário do servidor deve ser a referência. Ainda definir se a tentativa precisa ser iniciada, recebida ou concluída antes do encerramento, incluindo tratamento de rede lenta e processamento em fila. Não confiar em timestamp enviado pelo celular para autorizar presença.

Separar **cadastro facial inicial** de **verificação de presença**. Ambos os fluxos web foram confirmados pelo usuário. Link de presença não pode permitir substituir a face de uma matrícula. Ainda definir como validar a identidade informada no cadastro remoto e autorizar o vínculo de matrícula existente.

## Arquitetura sugerida

### Hospedagem do frontend no Render

Confirmado na documentação oficial consultada em 17/10/2026: Render hospeda
também a página acessada pelos alunos, com URL onrender.com e HTTPS.
Há duas alternativas, ainda não contratadas:

- **Frontend servido pela própria API:** proposta inicial para simplificar
  este projeto pequeno, com páginas/arquivos estáticos e endpoints no mesmo
  Web Service e domínio. Não exige outra instância de compute; compartilha
  os recursos e limites já orçados.
- **Static Site separado:** frontend HTML/CSS/JavaScript ou build estático
  de React, servido por CDN, chamando a API paga. Sem custo de compute do
  frontend, mas sujeito às franquias/custos de tráfego e build do workspace.
  Configurar origens permitidas e autenticação adequadamente. Renderização
  dinâmica no servidor não se enquadra como Static Site gratuito.

Para o escopo proposto, não é necessário contratar um segundo servidor
apenas para exibir a página. Links de cadastro/presença são rotas da mesma
aplicação, não sites ou serviços separados para cada aluno/turma.
Fontes: [Static Sites](https://render.com/docs/static-sites) e
[Web Services](https://render.com/docs/web-services).

| Componente | Papel |
|---|---|
| Frontend responsivo | Formulário, permissão da câmera, orientação e confirmação, em diferentes dispositivos |
| API Python | Autenticação/autorização, links/tentativas, horário, turmas e orquestração dos casos de uso |
| Processamento facial | Reaproveitar reconhecimento e antispoofing com limites de concorrência; medir compatibilidade e recursos no ambiente hospedado |
| PostgreSQL | Alunos, vínculos, turmas, janelas/tentativas e presenças conforme modelo futuro |
| Armazenamento privado | Somente artefatos cuja persistência for necessária e autorizada; definir retenção e acesso |

Framework web e estratégia de execução ainda não escolhidos. Docker foi sugerido para empacotar a API e suas dependências. Não assumir que o programa CLI/OpenCV e o worker Windows atuais podem ser hospedados sem adaptação.

Acesso ao banco somente pelo backend. Reaproveitar regras de negócio existentes, preservando limiar operacional e separação entre funcionalidade, desempenho computacional e desempenho biométrico.

Limitar inferências simultâneas e sinalizar “validando” pode evitar multiplicar cópias dos modelos na memória. Fila é proposta técnica, não infraestrutura adicional já aprovada; medir se uma implementação simples é suficiente para a apresentação. Definir capacidade máxima, timeout e resposta em sobrecarga.

## Modelo de dados: decisões pendentes

- Relacionar link/janela à turma e ao professor autorizado; definir revogação e expiração.
- Decidir link compartilhado por turma/janela ou individual por aluno. Link compartilhado precisa admitir vários alunos, enquanto cada tentativa deve ter controle próprio contra reutilização.
- Definir se matrícula/login é informado antes da captura. Isso influencia identificação 1:N versus verificação 1:1; nenhuma mudança do problema operacional foi aprovada ainda.
- Hoje a presença é contextualizada por turma/aluno/dia. Foi sugerida presença por janela/sessão para suportar mais de uma atividade da mesma turma no dia, **mas essa alteração ainda não foi confirmada pelo usuário**.
- Nome, matrícula e captura facial foram confirmados para o link de cadastro. Ainda definir identificação solicitada no link de presença e autorização de matrícula existente.
- Não pressupor armazenamento permanente de todas as imagens de verificação. Preferir descarte após processamento quando não houver finalidade aprovada de retenção.

## Hospedagem e estimativas discutidas

Opção inicial sugerida: **Render pago**, API em Docker e PostgreSQL gerenciado. Neon foi mencionado anteriormente como alternativa de PostgreSQL; não foi escolhido nem migrado nesta conversa. Hospedagem definitiva ainda depende de orçamento e medição.

Preços consultados em **17/10/2026**, para uma instância de aplicação e uma instância básica de PostgreSQL durante um mês inteiro:

| Aplicação | Aplicação/mês | PostgreSQL básico/mês | Total base/mês |
|---|---:|---:|---:|
| 512 MB RAM / 0,5 CPU | US$ 7 | US$ 6 | US$ 13 |
| 2 GB RAM / 1 CPU | US$ 25 | US$ 6 | US$ 31 |
| 4 GB RAM / 2 CPUs | US$ 85 | US$ 6 | US$ 91 |

Referência de workspace Hobby sem mensalidade adicional de workspace; não confundir plano de workspace com tamanho de instância. Valores não incluem armazenamento, eventuais excedentes, serviços extras, domínio próprio, tributos ou conversão/tarifas do cartão. Consultar preços novamente antes de contratar.

Foi proposto **orçamento inicial aproximado de US$ 35/mês** para o cenário de 2 GB, condicionado à medição de memória e pequenos custos adicionais. Se for necessário o cenário de 4 GB, a estimativa discutida foi aproximadamente **US$ 95/mês**. Esses valores são reservas estimadas, não cotação final nem comprovação de capacidade.

512 MB não foi recomendado para a stack atual de modelos. **2 GB e 4 GB também não foram validados** por execução hospedada. O baixo número de imagens não elimina a necessidade de memória para manter modelos carregados. O tamanho necessário depende do pico de RAM, cold start, duração da inferência e concorrência.

30 links/50 imagens sugerem tráfego pequeno, mas o número de frames por validação, tamanho dos uploads e concentração das solicitações permanecem desconhecidos. Não garantir atendimento simultâneo nem latência “instantânea”. Se a validação exigir sequência de frames, 50 imagens podem não representar o volume real.

Não foi feita conversão para reais. Não foi executado benchmark de hospedagem, teste de carga, deploy, compra ou criação de conta.

### Orçamento atualizado: 10 dias disponíveis 24/7

Consulta em 17/10/2026: Render informa cobrança de compute proporcional ao tempo, por segundo. Para estimativa simples, usar **preço mensal × 10/30**, mês de referência de 30 dias. Esta conta é aproximação orçamentária; a fatura depende das taxas e segundos efetivos do provedor, e não da suposição de que qualquer mês tem 30 dias.

| Instância da aplicação | Aplicação por 10 dias | PostgreSQL básico por 10 dias | Total base estimado |
|---|---:|---:|---:|
| 512 MB / 0,5 CPU | US$ 2,33 | US$ 2,00 | **US$ 4,33** |
| 2 GB / 1 CPU | US$ 8,33 | US$ 2,00 | **US$ 10,33** |
| 4 GB / 2 CPUs | US$ 28,33 | US$ 2,00 | **US$ 30,33** |

Hipóteses: uma aplicação incluindo API/processamento, um PostgreSQL básico, workspace Hobby sem taxa adicional, sem worker pago separado e sem serviços de notificação pagos. CRUD, geração dos links e exportação CSV simples compartilham essa aplicação; não existe custo fixo por link nesta estimativa.

Reserva sugerida **US$ 12–15 para 10 dias no cenário 2 GB**, condicionada à medição, ou **US$ 32–35 no cenário 4 GB**, também não validado. Reservas não são teto contratual; não incluem impostos/câmbio/cartão, excedentes relevantes, domínio próprio ou serviços adicionais. O cenário512 MB continua não recomendado para a stack atual.

Armazenamento é separado: a tabela pública consultada indica 1 GB incluído no PostgreSQL e expansão a US$0,30/GB; discos persistentes da aplicação custam US$0,25/GB/mês. Confirmar franquias e cobrança efetiva na contratação. Para a foto de referência persistir entre deploys, planejar disco ou armazenamento privado apropriado; filesystem efêmero não atende essa necessidade. Número/tamanho das imagens e espaço dos modelos ainda precisam ser medidos.

Os 10 dias são **tempo total dos recursos cobrados**, não apenas dias com acessos. Criação para ensaios antes da apresentação também conta. Manter recursos após esse prazo continua podendo gerar cobrança; exportar um relatório não desliga a hospedagem. Antes de encerrar recursos, definir preservação autorizada de dados e backup, e conferir separadamente cobranças de aplicação, banco e armazenamento. Não apagar banco automaticamente para economizar.

O novo escopo de cadastro+presença+relatórios não altera a aritmética da instância fixa; pode alterar a instância necessária. Cinquenta imagens e trinta links não demonstram capacidade para cinquenta inferências simultâneas. Não assumir que 2 GB bastam sem teste.

## Próximas decisões antes de uma task de implementação

1. Detalhar os dois fluxos confirmados (cadastro e presença), autenticação/autorização de professor/aluno, matrícula existente e relação professor–turma.
2. Definir semântica do prazo, expiração/revogação e presença única por dia ou por janela.
3. Definir protocolo de captura recente e seus limites, sem reutilizar dados operacionais para pesquisa por suposição.
4. Inspecionar código atual e planejar adaptação web sem perder regras de turmas/captura e consentimento.
5. Medir memória e latência dos modelos e estimar pico de concorrência com testes adequados; validação biométrica real exige autorização específica.
6. Escolher hospedagem/armazenamento a partir das medições e orçamento; revisar valores antes da contratação.
7. Só então preparar pacote de task com desenho, plano, testes, migração se necessária e prompt de execução. Este documento não concede autorização para implementar, migrar, publicar ou contratar.

## Referências consultadas na conversa

- [Câmera no navegador — getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia): contexto seguro e permissão.
- [Render Web Services](https://render.com/docs/web-services): hospedagem de serviços.
- [Render Docker](https://render.com/docs/docker): implantação em contêiner.
- [Render Pricing](https://render.com/pricing): planos e preços, verificar novamente antes da contratação.
- [Render Compute Plans](https://render.com/docs/compute-plans): correspondência entre CPU/RAM e planos.
- [Render Persistent Disks](https://render.com/docs/disks): persistência de arquivos.
- [Render Free](https://render.com/docs/free): limitações e suspensão do serviço gratuito.
- [Render Scaling — billing](https://render.com/docs/scaling): compute proporcional por segundo.

## Registro de evolução

- **17/10/2026:** consolidada proposta de acesso por link/câmera e janela de horário; incorporada correção do usuário de que presença física e videoconferência não são necessárias; registrados volume estimado, custos consultados e limitações de captura recente/hospedagem. Nenhuma implementação iniciada.
- **17/10/2026 — atualização:** confirmado link separado para cadastro com nome/matrícula/foto, confirmação para professor, relatório por turma e dia/intervalo de dias/meses e manutenção do CRUD. Prazo orçado mudou de um mês para 10 dias 24/7; tabelas e hipóteses atualizadas. Cadastro remoto deixa de ser dúvida de escopo; sua autorização detalhada continua pendente. Nenhuma implementação ou contratação iniciada.
