# Etapa 5 — Consolidação acadêmica e preparação da apresentação

**Data:** 10/10/2026
**Estado:** consolidação documental concluída; avaliação biométrica real das Etapas 2–4 continua pendente.
**Escopo:** auditoria dos registros das Etapas 0–4, descrição da arquitetura existente, criação de materiais acadêmicos e verificação atual de testes unitários/qualidade. Nenhum experimento biométrico foi iniciado.

## 1. Resumo executivo

Foram consolidadas a arquitetura operacional, as cinco etapas do plano, suas evidências, resultados e limitações. Foram produzidos o documento acadêmico principal, uma matriz de rastreabilidade, comparação de abordagens, guia de reprodução, roteiro de 13–15 minutos e respostas para a banca.

O estado dos resultados foi preservado sem extrapolação: a Etapa 1 é a única com métricas biométricas reais reportadas, em verificação 1:1 no LFW. As Etapas 2–4 têm código e testes de software com dados sintéticos, sem treino, avaliação ou resultados biométricos reais. A aplicação operacional continua usando `FACE_THRESHOLD=0.30`; não foram alterados FaceNet512, MiniFASNet, matcher, webcam, banco, schema ou interface.

Na verificação atual da Etapa 5, passaram 518 testes unitários, Ruff e mypy. A suíte completa não foi executada porque os testes de integração/BDD podem usar PostgreSQL, cujo acesso estava fora do escopo solicitado. O relatório da Etapa 4 registra 597 testes aprovados na execução completa histórica; esse dado está identificado como histórico, não como uma nova execução.

## 2. Objetivos

- auditar documentação, código operacional e experimental, dependências, testes e Git;
- consolidar a metodologia e os resultados das Etapas 0–4;
- deixar clara a diferença entre implementação, teste sintético e avaliação biométrica;
- oferecer material rastreável e acessível para a apresentação acadêmica;
- registrar verificações atuais sem abrir dados ou serviços proibidos.

## 3. Documentos consultados

Foram lidos e confrontados:

- `CLAUDE.md`; `instructions/00-orquestrador.md`, `01-arquiteto.md`, `02-desenvolvedor.md`, `03-qa.md`;
- `ARCHITECTURE.md`; `REFACTORING_PLAN.md`;
- `docs/ML-LEARNING-AUDIT.md`; `docs/ML-EXPERIMENT-SETUP.md`;
- `docs/ML-ETAPA-0-RESULTADO.md` até `docs/ML-ETAPA-4-RESULTADO.md`;
- `docs/adr/ADR-004-limiar-de-reconhecimento.md`; `docs/lgpd.md`;
- `README.md`; `pyproject.toml`; `requirements-dev.txt`, `requirements-ml.txt`, `requirements-experimentos.txt`; `.gitignore`;
- código de `src/config/settings.py`, `src/domain/entities/face_embedding.py`, `src/domain/services/matcher.py`, `src/infrastructure/face_recognition/deepface_adapter.py`, casos de uso de reconhecimento/presença;
- scripts experimentais e testes unitários correspondentes às Etapas 0–4.

Não existe `AGENTS.md` na raiz examinada. Os materiais do Superpowers foram usados internamente para planejar e revisar esta consolidação, conforme autorização dada pelo usuário; os documentos intermediários ignorados pelo Git não são entregáveis acadêmicos.

## 4. Arquitetura identificada

A aplicação operacional segue camadas de apresentação, aplicação, domínio e infraestrutura. `src/main.py` compõe os adaptadores; o domínio contém o embedding e o matcher; a infraestrutura abriga OpenCV, DeepFace, armazenamento e PostgreSQL.

O adaptador operacional aceita uma face detectada/alinhada e, por padrão, exige aprovação do anti-spoofing. O FaceNet512 pré-treinado gera embedding 512D, normalizado em L2. O matcher escolhe a menor distância cosseno entre as referências compatíveis e aplica o limiar. O operador confirma antes do caso de uso gravar presença. O fluxo completo está no documento [ML-CONSOLIDACAO-ACADEMICA.md](ML-CONSOLIDACAO-ACADEMICA.md), com quatro diagramas Mermaid.

## 5. Consolidação das Etapas 0–4

| Etapa | Implementação conforme auditoria | Testes registrados | Resultado biométrico |
|---|---|---|---|
| 0 — infraestrutura | Diretório experimental protegido, divisão por identidade, teste lacrado, extração com falhas contadas e métricas | Histórico: 322 passaram; cobertura reportada 92,67%; divisão sintética 8/2/2 identidades | Nenhuma medição facial |
| 1 — limiar 1:1 | Geração de pares, seleção de limiar na validação e avaliação única do teste | Histórico: 489 passaram, 2 ignorados; relatório registra ainda 53 focais S1 | Medição histórica LFW 1:1, descrita em §8 |
| 2 — classificação supervisionada | M0–M4, seleção e congelamento implementados | Histórico: 528 passaram; testes com vetores sintéticos | Nenhum classificador M2–M4 treinado com biometria real |
| 3 — identificação open-set | Galeria, conhecido/desconhecido, FPIR/FNIR, rank 1, tamanhos e limiares | Histórico: 575 passaram; fixtures sintéticas | Não executada |
| 4 — clustering | DBSCAN, K-Means, seleção interna sem rótulos, cobertura/ruído e métricas | Histórico: 22 focais; 597 na suíte completa | Não executada |

Os totais são snapshots, não se somam entre si. “Implementado” significa código experimental e testes dos contratos declarados; não significa desempenho facial medido. M2–M4, a avaliação 1:N e o clustering permanecem pendentes de uso autorizado e execução válida.

## 6. Evidências de implementação

- **Código operacional:** `DeepFaceAdapter`, `FaceEmbedding`, `MatrizDeReferencia`, `ReconhecerAluno`, `RegistrarPresenca` e `Settings` confirmam o fluxo descrito. Configuração observada: `Facenet512`, detector `opencv`, alinhamento habilitado no adaptador, anti-spoofing true por padrão e limiar 0,30.
- **Etapa 0/1:** `scripts/divisao_por_identidade.py`, `scripts/evaluate_model.py`, `scripts/metricas.py` e `scripts/calibrar_limiar.py` contêm a infraestrutura e protocolo 1:1.
- **Etapa 2:** `scripts/classificadores_binarios.py`, `scripts/avaliacao_classificadores.py` e `scripts/experimento_classificacao_binaria.py` implementam os modelos e fluxo experimental.
- **Etapa 3:** `scripts/identificacao_aberta.py` e `scripts/experimento_identificacao_aberta.py` implementam a decisão open-set experimental separada do matcher operacional.
- **Etapa 4:** `scripts/agrupamento_embeddings.py`, `scripts/experimento_agrupamento.py` e `scripts/graficos_agrupamento.py` implementam agrupamento e avaliação.
- **Testes:** `tests/unit/test_*.py` tem testes de embeddings, métricas, classificadores, galerias e agrupamento com fixtures/fakes; não constituem validação biométrica.

A matriz completa, incluindo as evidências por conceito e os itens não implementados, está em [ML-MATRIZ-RASTREABILIDADE.md](ML-MATRIZ-RASTREABILIDADE.md).

## 7. Evidências de testes executados nesta Etapa 5

Executados em Windows PowerShell, Python 3.14.3, usando o ambiente `.venv-ml` (NumPy 2.5.3, scikit-learn 1.9.1, Matplotlib 3.11.2, pytest 9.1.1, Ruff 0.16.6 e mypy 2.3.1):

| Comando | Resultado atual |
|---|---|
| `.\.venv-ml\Scripts\python.exe -m pytest tests/unit --basetemp "$env:TEMP\pytest-stage5-unit-20261010"` | **518 passaram** em 6,11 s; nenhum teste falho ou ignorado apareceu no resumo |
| `.\.venv-ml\Scripts\ruff.exe check src scripts tests` | **Aprovado**, `All checks passed!` |
| `.\.venv-ml\Scripts\mypy.exe` | **Aprovado**, 67 arquivos, sem apontamentos |
| Suíte completa (`pytest`) | **Não executada nesta Etapa 5**: os testes de integração/BDD podem acessar PostgreSQL; a etapa não acessou o serviço |

O comando de testes limitou-se a `tests/unit`, cujo conteúdo foi inspecionado para garantir que as URLs PostgreSQL nos testes unitários são apenas valores de validação/configuração, não conexões. Nenhum comando de teste biométrico foi executado. O valor de 597 testes completos vem somente do relatório da Etapa 4. A cobertura não foi medida nesta Etapa 5. `ruff format --check` também não foi executado nesta etapa; o relatório da Etapa 4 registra que a checagem global então encontrou 32 arquivos existentes fora do formato, enquanto os seis arquivos alterados na Etapa 4 passaram na checagem focada.

## 8. Resultados biométricos existentes e pendentes

### Medição histórica disponível

A Etapa 1 registra uma medição de verificação 1:1 no LFW. O teste tinha 336 identidades, 1.099 imagens, 2.001 pares genuínos e 601.350 pares impostores após extração. O baseline 0,30 apresentou FAR 0,0018% (IC95 reportado 0–0,005%) e FRR 38,03% (32,59–43,95%). O limiar candidato 0,42817932706540435, selecionado na validação para FAR ≤ 0,1%, apresentou FAR de teste 0,063% (0,042–0,090%) e FRR 16,39% (12,40–20,99%). A AUC reportada foi 0,9830.

São métricas históricas de **verificação 1:1**, com anti-spoofing desligado. Não são precisão da aplicação em sala, não medem identificação 1:N e não autorizam alterar o `FACE_THRESHOLD`. A extração reportou 11,8% de falha; as métricas biométricas são condicionadas às imagens que produziram embedding. A possível sobreposição do LFW com o pré-treinamento FaceNet512 não foi descartada.

### Pendências

- Etapa 2: FAR/FRR/AUC/F1/Brier e tempos reais de M2–M4 indisponíveis.
- Etapa 3: FPIR/FNIR, top-1, trocas, rejeições e latência 1:N indisponíveis.
- Etapa 4: ARI/NMI, silhouette/cobertura, distribuição de ruído e tempos de cluster indisponíveis.
- Anti-spoofing: não há protocolo de ataque com APCER/BPCER medido; há limitação de falso positivo em contraluz relatada em `docs/lgpd.md`.
- Não há estimativa de precisão em sala de aula, nem validação por webcam/iluminação/subgrupo.

Os gráficos biométricos históricos da Etapa 1 são referenciados no respectivo relatório. Nenhum gráfico novo de dados biométricos ou sintéticos foi gerado na Etapa 5.

## 9. Matriz, comparação, diagramas e apresentação

- [Matriz de rastreabilidade](ML-MATRIZ-RASTREABILIDADE.md): caminhos, etapas, testes e estado de cada conceito.
- [Comparação de abordagens](ML-COMPARACAO-ABORDAGENS.md): limiar, classificadores supervisionados, DBSCAN e K-Means sem declarar vencedor.
- [Consolidação acadêmica](ML-CONSOLIDACAO-ACADEMICA.md): inclui diagramas Mermaid da arquitetura operacional e pipelines supervisionado, 1:N e clustering.
- [Guia de reprodutibilidade](ML-GUIA-REPRODUTIBILIDADE.md): dependências, versões, comandos efetivos e limites de autorização.
- [Roteiro de apresentação](ML-ROTEIRO-APRESENTACAO.md): exposição estimada de 13–15 minutos, falas e questões prováveis.
- [Perguntas da banca](ML-PERGUNTAS-BANCA.md): 22 perguntas respondidas com base nas evidências disponíveis.

## 10. Segurança e privacidade

Nenhuma imagem, embedding, dado do PostgreSQL, credencial ou dado de aluno foi aberto nesta consolidação. O gate das Etapas 2–4 não foi contornado; a documentação não cria consentimento ou licença. `avaliacao/` e formatos biométricos estão protegidos por `.gitignore` e controles do CI, mas qualquer execução futura ainda exige revisar proveniência, finalidade, autorização, armazenamento, acesso, retenção, descarte e risco de reidentificação.

Embeddings faciais são dados biométricos sensíveis. `docs/lgpd.md` é a declaração interna do projeto, não um parecer jurídico nem uma auditoria completa; o próprio documento reconhece ausência de criptografia em repouso, autenticação de operador e trilha de auditoria. Não se declara conformidade integral com LGPD. A fonte oficial legal está indicada para consulta e revisão institucional na [consolidação acadêmica](ML-CONSOLIDACAO-ACADEMICA.md#referências-e-documentos-relacionados).

## 11. Divergências e decisões documentais

- `README.md` e `ARCHITECTURE.md` continham a contagem antiga de 281 testes. Foram atualizados para mostrar os 518 testes unitários verificados nesta data e separar os 597 da execução completa histórica da Etapa 4.
- Relatórios de Etapas 0–4 contêm contagens de suíte de datas diferentes; foram preservadas como registros históricos e não somadas.
- `ARCHITECTURE.md` continua descrevendo um snapshot antigo da estrutura/contagem em outras partes; este relatório aponta código atual e chama atenção para diferenças quando relevantes. O documento de arquitetura mais amplo não foi reescrito.
- A Etapa 1 descreve o LFW como publicado para pesquisa sem licença formal; relatórios posteriores não encontraram autorização específica para novos usos do projeto. A consolidação conserva os resultados históricos como registrados, mas não trata essa descrição como autorização para novos experimentos.
- Ao consultar Git, HEAD estava em `main` (`e1040ca`, alinhada a `origin/main`) e sem alterações rastreadas antes desta Etapa 5. O `git status` também emitiu avisos de acesso negado ao enumerar quatro diretórios temporários antigos `.pytest-stage4-tmp-20261010*`; eles não foram alterados ou removidos. Nenhum commit foi realizado.

## 12. Impacto operacional

Não foram alterados arquivos em `src/`, scripts de execução, configurações do reconhecimento, banco ou migrações. As alterações desta etapa são documentação em `docs/`, atualização dos contadores de teste no `README.md` e `ARCHITECTURE.md`, e o relatório atual. `FACE_THRESHOLD`, FaceNet512, MiniFASNet, matcher, câmera, cadastro, presença, PostgreSQL, schema, migrations, Neon e interface permanecem sem alteração.

## 13. Critérios de aceite

| Critério | Estado | Evidência |
|---|---|---|
| Relatórios das Etapas 0–4 analisados | Atendido | Documentos consultados e tabelas §5/§8 |
| Arquitetura real documentada | Atendido | Código operacional revisado; diagrama no documento principal |
| Conceitos de ML explicados | Atendido | Documento principal e comparação |
| Implementação separada de validação | Atendido | Estados explícitos por etapa e conceito |
| Matriz de rastreabilidade | Atendido | `ML-MATRIZ-RASTREABILIDADE.md` |
| Comparação entre abordagens | Atendido | `ML-COMPARACAO-ABORDAGENS.md` |
| Guia reproduzível sem inventar comandos | Atendido | `ML-GUIA-REPRODUTIBILIDADE.md`; comandos biométricos claramente condicionados a autorização |
| Diagramas técnicos corretos | Atendido | Quatro diagramas Mermaid no documento principal |
| Roteiro e perguntas da banca | Atendido | Roteiro de 13–15 min e 22 respostas |
| Testes/verificações atuais documentados | Atendido, com limite | 518 unitários, Ruff e mypy atuais; full suite não executada por envolver PostgreSQL |
| Resultados biométricos pendentes identificados | Atendido | Etapas 2–4 e avaliação operacional separadas da Etapa 1 |
| Código operacional sem alteração | Atendido | Diff atual restrito à documentação; `src/` sem alterações |
| Relatório final da Etapa 5 completo | Atendido | Este documento |

## 14. Conclusão

A Etapa 5 está concluída como consolidação acadêmica e preparação para apresentação. A documentação é rastreável aos relatórios e ao código auditado, e as verificações executadas estão identificadas como atuais ou históricas. A evidência biométrica continua limitada ao estudo 1:1 da Etapa 1; as Etapas 2–4 não demonstram desempenho real. Nenhuma implementação nova ou etapa seguinte foi iniciada.

## 15. Trabalhos futuros

Uma avaliação posterior exige fonte de dados e finalidade legitimamente autorizadas, revisão institucional, teste final historicamente independente, protocolo estatístico pré-registrado e condições de captura representativas. A Etapa 3 operacional (plano futuro separado) deve depender de resultados 1:N e de segurança/privacidade revisados; o limiar atual não deve ser alterado com base apenas no resultado 1:1 do LFW.
