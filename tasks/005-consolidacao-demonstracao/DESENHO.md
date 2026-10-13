# Desenho — tarefa 005: consolidação e demonstração acadêmica

Desenho aprovado internamente para execução por **Luna 6, esforço High**.

## Objetivo e base analisada

Reconciliar memórias e documentação com o código entregue nas tarefas 001–004 e preparar uma demonstração acadêmica offline reproduzível. A entrega é documental, sem implementar funcionalidades.

Esta numeração segue o roteiro da conversa: a tarefa 005 é distinta da Etapa 5 histórica de ML e da prioridade 5 do AGENTS.md. O benchmark dessa prioridade foi aprofundado na tarefa 004. Múltiplas referências por identidade continuam pendentes.

Na análise de 13/10/2026, a branch local era `main`, HEAD `e5cc961` (`perf: amplia benchmark sintetico de matching`). Existiam apenas os pacotes 001–004. A mensagem “005 finalizada” foi interpretada como referência à 004, dando origem à preparação deste pacote. A publicação remota não foi verificada nesta preparação.

| Entrega | Estado encontrado | Limite da evidência |
|---|---|---|
| 001 — qualidade | Checagens optativas de nitidez, iluminação e dimensão, antes do embedding | Heurísticas e testes sintéticos; não afirmar orientação facial implementada |
| 002 — temporal | Confirmação optativa de identidade e revalidação antes do registro | Frames correlacionados; timestamp de software não garante frescor físico do sensor |
| 003 — ambiguidade | Rejeição optativa entre identidades candidatas | Margem positiva sem calibração; zero rejeita empates exatos |
| 004 — benchmark | Referência em laço Python/NumPy comparada ao matcher vetorizado | Vetores sintéticos; não mede inferência DeepFace nem acurácia facial |

O RESULTADO.md da 004 registra 812 testes **unitários**, Ruff e mypy aprovados. Os três JSONs foram inspecionados nesta preparação: cada execução registra 240 comparações, nenhuma divergência fora dos critérios do benchmark e erro absoluto máximo aproximadamente `1,19209e-7`. São evidências históricas consultadas; testes e medições não foram reexecutados na preparação da 005.

## Problemas documentais

| Documento | Correção necessária |
|---|---|
| `CLAUDE.md` | Separar as carências do protótipo inicial do estado atual |
| `AGENTS.md` | Atualizar próxima direção e prioridades que ainda descrevem entregas 001–004 como futuras |
| `REFACTORING_PLAN.md` | Reconciliar cabeçalho “nenhuma alteração realizada” com fases executadas e referência a `docs/baseline-arquitetura.md` |
| `docs/apresentacao.md` | Substituir roteiro padrão dependente de câmera/banco e referência atual a 281 testes |
| Documentos acadêmicos `ML-*` | Identificar 518 testes como resultado histórico da Etapa 5 e incorporar as melhorias recentes |

## Organização da entrega

### Referência atual

Criar `docs/ESTADO-ATUAL-E-EVIDENCIAS.md`, contendo:

1. Data, revisão local analisada e objetivo de disciplina de IA da Fatec: identificação aberta 1:N para presença.
2. Pipeline atual e tabela das tarefas 001–004: comportamento, defaults, módulos, testes, relatório e limites.
3. Registro de evidências com origem, contexto/data, comando quando disponível, resultado e escopo. Distinguir resultados históricos inspecionados dos comandos executados na 005.
4. Mapa das três séries: fases de refatoração, etapas experimentais de ML e tarefas de melhoria.
5. Pendências confirmadas: avaliação biométrica autorizada e representativa, calibração 1:N, múltiplas referências operacionais, orientação facial se ausente e validação real do pipeline completo. Neon/API permanecem propostas enquanto não houver implementação confirmada.

Essa página organiza links e resolve afirmações conflitantes; não replica integralmente os relatórios. Não chamar 812 unitários de suíte completa.

### Memórias e páginas de entrada

- `AGENTS.md`: preservar regras e histórico experimental; acrescentar snapshot atual e atualizar próximas prioridades.
- `CLAUDE.md`: enquadrar explicitamente o protótipo como histórico e descrever o estado atual confirmado, preservando instruções aplicáveis.
- `REFACTORING_PLAN.md`: identificar plano histórico e estado verificado; não marcar pendências como concluídas sem evidência.
- `README.md` e `ARCHITECTURE.md`: ajustes pontuais de navegação, estado, configurações e evidências. Qualificar “confiança em porcentagem” como indicador derivado da distância, sem interpretação probabilística calibrada.

Ledgers ignorados de `.superpowers/` podem ser consultados para contexto; não editar nem forçar seu versionamento. Resolver divergências relevantes na documentação rastreada, com base no código e nos relatórios.

### Material acadêmico

- `docs/ML-CONSOLIDACAO-ACADEMICA.md`: preservar a Etapa 5 original como histórico e adicionar atualização identificada sobre 001–004.
- `docs/ML-MATRIZ-RASTREABILIDADE.md`: incluir qualidade, temporal, ambiguidade e benchmark, ligando código, testes, evidência e limites.
- `docs/ML-GUIA-REPRODUTIBILIDADE.md`: seção atual de reprodução offline, distinguindo comandos/resultados históricos.
- `docs/ML-ROTEIRO-APRESENTACAO.md`: roteiro de 13–15 minutos com soma explícita dos tempos, mantendo conceitos acadêmicos e integrando melhorias e limites.
- `docs/ML-PERGUNTAS-BANCA.md`: respostas sobre opt-in, correlação temporal, margem versus limiar, equivalência, latência e memória. O nome histórico do arquivo não torna o projeto um TCC.
- `docs/apresentacao.md`: demonstração offline de aproximadamente 5 minutos, usando testes e CLI existentes, com comandos, interpretação e alternativa de apresentar evidências históricas se o ambiente não estiver disponível.

## Contratos factuais

- Confirmar defaults em `src/config/settings.py`: qualidade, temporal e ambiguidade desligadas por padrão; limiar operacional `0.30` preservado.
- Qualidade não substitui antispoofing. Consistência temporal não prova melhora de acurácia.
- Ambiguidade considera a segunda identidade diferente, inclusive acima do limiar. O melhor candidato precisa passar pelo limiar primeiro. Sem competidor não há rejeição por ambiguidade; empate rejeita; diferença estritamente menor que a margem positiva rejeita e igualdade aceita. Confirmar no matcher atual.
- Benchmark usa vetores sintéticos de 512 dimensões; referência sequencial executa `NumPy dot` por embedding. Não apresentá-la como protótipo DeepFace nem repetir a estimativa `2N × 80 ms`.
- Tempos locais exigem cenário, tamanho da galeria, política, estatística, ambiente e variação entre execuções. Não representam FPS de câmera ou latência ponta a ponta.
- `tracemalloc` não é RSS nem toda memória nativa; payload/nbytes não é memória total do processo.
- Candidato histórico `0.42817932706540435` continua sem aprovação operacional. Não alegar nova calibração, autorização de dataset ou ganho biométrico.

## Escopo permitido e aceite

Alterar somente os documentos citados, `tasks/README.md` e o pacote 005. Preservar resultados históricos `docs/ML-ETAPA-*-RESULTADO.md`, `docs/baseline-arquitetura.md`, pacotes 001–004 e seus JSONs. Eventual erro histórico recebe contexto no novo registro, sem apagar a fonte.

Não alterar código, scripts, testes, dependências, CI, ADRs ou configuração. Não criar testes, slides, gráficos ou aplicação de demonstração. Não ler `.env`, imagens, embeddings reais, `storage/` ou `avaliacao/`; não abrir câmera/banco, executar migrations, instalar pacotes, baixar modelos/datasets ou mudar antispoofing/limiar.

Aceite: documentos coerentes com fontes, histórico identificável, links locais válidos, UTF-8 íntegro, roteiro com tempos coerentes e comandos existentes. Executar as verificações offline do plano e registrar resultados efetivos em `RESULTADO.md`. Commit e push na main após concluir os critérios, conforme autorização do usuário.
