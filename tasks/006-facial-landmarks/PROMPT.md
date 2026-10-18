# Prompt de execução — 006 / Luna 6 High

> **Nota de correção (14/10/2026):** este prompt registra o plano original. A recomendação de `mediapipe==0.10.31` e o pedido de commit/push foram supersedidos por [`PLANO-CORRECAO.md`](PLANO-CORRECAO.md), [`DEPENDENCIAS.md`](DEPENDENCIAS.md) e [`RESULTADO.md`](RESULTADO.md). Use MediaPipe 0.10.35 somente no `.venv-landmarks`; mantenha esta entrega sem commit ou push.

Você é **Luna 6, esforço High**, executor no repositório `projeto_reconhecimento_facial`.

**Execute a task 006: landmarks visuais na janela Cadastro facial. Desenho e plano estão definidos e aprovados internamente. Apenas execute, instale as dependências previstas na etapa de execução, teste, documente e faça commit + push na main ao terminar. Não reabra brainstorming nem delegue.** O planejador apenas escreveu este pacote: não instalou bibliotecas, baixou modelo ou implementou código.

Leia AGENTS.md, CLAUDE.md, instructions/ e integralmente:

1. `tasks/006-facial-landmarks/DESENHO.md`
2. `tasks/006-facial-landmarks/DEPENDENCIAS.md`
3. `tasks/006-facial-landmarks/PLANO.md`

Use Superpowers executing-plans e testes/verificação apropriados. Decisões rotineiras podem ser aprovadas internamente conforme AGENTS.md; não solicitar reconfirmação da tarefa. Respeitar permissões obrigatórias do ambiente.

## Dependências que você precisará preparar

- Criar `requirements-landmarks.txt` com `-r requirements.txt` e **`mediapipe==0.10.31`**.
- MediaPipe declara `absl-py~=2.3`, `numpy`, `sounddevice~=0.5`, `flatbuffers~=25.9`; transitivas adicionais serão resolvidas por pip (como cffi via sounddevice). Não usar áudio/microfone.
- Reutilizar OpenCV 4.13.0.92 e NumPy 2.5.3 existentes. Não instalar opencv-contrib/headless junto do opencv-python. MediaPipe 0.10.32/0.10.35/1.1.0 consultados exigem contrib; por isso foi selecionada 0.10.31. Não instalar latest nem usar --no-deps.
- Usar `.venv-app`, Windows AMD64, Python reportado 3.12.0rc2; `.venv-ml` 3.14 é apenas para testes dublados. Não substituir o interpretador nem alterar pins de TensorFlow/DeepFace/NumPy para contornar falhas.
- Rodar `pip check`, depois `pip install --dry-run --only-binary=:all: -r requirements-landmarks.txt`; inspecionar resolução antes de `pip install --only-binary=:all: -r requirements-landmarks.txt`. Registrar versões e repetir pip check. Incompatibilidade real bloqueia conclusão e deve ser reportada.
- Obter bundle `face_landmarker.task` pelo link de Models da documentação oficial indicada em DEPENDENCIAS.md, em setup explícito. Guardar em `models/`, ignorar peso no Git e registrar origem/hash/termos no README desse diretório. Nenhum download automático na aplicação ou testes.
- Fazer smoke CPU com array sintético e modelo real, sem webcam/banco. Metadados de wheel não bastam para declarar compatibilidade.

## Contratos essenciais

478 pontos estimados pelo modelo, contornos finos, modo VIDEO síncrono, num_faces=2, sem blendshapes/matrizes. Uma instância por janela de cadastro; usar timestamps crescentes. O desenho detalha DTOs, factories, arquivos e estados.

`FACE_LANDMARKS_ENABLED=false` por padrão, caminho local configurável. Flag false não importa MediaPipe. Falha do recurso opcional mostra aviso e mantém cadastro normal; liberação garantida e sem tentativas por frame.

Desenhar somente na cópia de exibição; o frame bruto deve chegar intacto ao cadastro/qualidade/antispoofing/embedding/storage. Não usar landmarks para decidir identidade, bloquear captura, declarar prova de vida ou melhorar artificialmente a confiança. Não alterar limiar 0.30, políticas 001–003 ou janelas de reconhecimento.

Não abrir `.env`, banco, webcam ou dados reais. Não processar nem versionar a imagem enviada pelo usuário, coordenadas reais, fotos, pesos ou vídeos. Não baixar datasets, rodar migrations, mudar CI, implementar head pose, emoções ou nova API. Registrar validação visual com rosto como pendente para o usuário quando não realizada; não fabricar evidências.

## Publicação autorizada

Permanece a instrução do usuário para estes pacotes: **commit + push das alterações na main quando terminar**.

1. Registrar status/branch/HEAD; base preparada `f116a95`, main. Preservar trabalho alheio, pacotes históricos e temporários. Sem branch/worktree alternativa nesta execução.
2. Conferir remoto sem expor credenciais, `git fetch origin`, inspecionar divergência e commits locais. Se somente atrás, fast-forward quando seguro. Não publicar commits desconhecidos, usar force/reset destrutivo ou limpar diretórios.
3. Concluir testes unitários, Ruff/mypy, pip check, smoke real sintético e revisão dos arquivos. Falha de gate impede declarar/publicar concluído; limite de avaliação visual deve ser explícito no relatório.
4. Criar RESULTADO.md e atualizar tasks/README.md. Fazer staging por caminhos explícitos somente da feature, dependências/documentação necessárias e pacote006. Não usar git add . / -A / commit -a. Inspecionar staged e executar git diff --cached --check.
5. Commit sugerido `feat: adiciona landmarks visuais no cadastro`; `git push origin main`, sem contornar hooks/proteções. Se remoto avançou, integrar apenas preservando trabalho; senão reportar bloqueio.
6. Confirmar `git rev-parse HEAD` e `git ls-remote origin refs/heads/main`; se houver corrida, fetch e checar ancestralidade. Informar hash/confirmação na resposta final, sem commit extra apenas para inserir o próprio hash.

Resposta final: arquivos/feature entregues, dependências efetivas, comandos/resultados, link de RESULTADO.md, instruções para ativar e validar visualmente, limites e confirmação de publicação ou bloqueio. Execute o pacote; não responda apenas com outro plano.

## Regra obrigatória de commit e push

Antes de qualquer commit ou push, leia ou releia o arquivo AGENTS.md na raiz do repositório e siga suas instruções vigentes. A autorização desta tarefa pode limitar ou proibir a publicação; esta regra não amplia autorizações.

- Mensagens de commit sempre em PT-BR. Não se identifique como Co Author nem adicione Co-authored-by; use somente a identidade e as credenciais Git já configuradas do solicitante, sem reconfigurar autoria.
- Se a entrega envolver muitos arquivos ou unidades lógicas distintas, divida-a em commits separados e organizados por escopo; não agrupe mudanças independentes em um commit monolítico.
- Adicione ao staging apenas caminhos explícitos e revise git diff --cached --stat, git diff --cached --check e o conteúdo staged antes de cada commit. Faça push somente para o branch/remoto autorizado e sem force.
