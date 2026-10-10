# Perguntas e respostas para a banca

As respostas refletem o código e os relatórios auditados em 10/10/2026. Onde não há medição, a resposta diz isso diretamente.

1. **O FaceNet512 foi treinado por vocês?**
   Não. O projeto utiliza o FaceNet512 pré-treinado para inferência e geração de embeddings de 512 dimensões. As etapas deste estudo não fizeram fine-tuning nem alteraram seus pesos.

2. **Qual é a diferença entre treinamento e inferência?**
   Treinamento ajusta parâmetros do modelo a partir de exemplos. Inferência aplica parâmetros já existentes a uma entrada e gera uma saída. Aqui, o FaceNet512 faz inferência; a Etapa 1 ajustou um limiar, e as Etapas 2–4 construíram protocolos de decisão e agrupamento derivados dos embeddings.

3. **Onde existe aprendizado supervisionado no projeto?**
   Na Etapa 1, pares de imagens com rótulos de mesma/diferente identidade foram usados para escolher um limiar na validação. A Etapa 2 implementa classificadores supervisionados, mas seus modelos não foram treinados com dados biométricos reais.

4. **Por que utilizar regressão logística?**
   É um baseline supervisionado interpretável que estima uma fronteira sobre a distância cosseno escalar. O coeficiente e intercepto permitem examinar a relação aprendida, mas não há evidência real de que ela melhore a decisão operacional.

5. **Qual é a diferença entre regressão logística e Naive Bayes?**
   Regressão logística estima diretamente a probabilidade condicional da classe a partir das características. Gaussian Naive Bayes estima distribuições por classe e usa o teorema de Bayes, com hipóteses distributivas. A comparação real não foi executada.

6. **Por que utilizar uma árvore de decisão?**
   Uma árvore rasa representa regras de corte fáceis de interpretar. Com profundidade 1, ela se aproxima de uma regra de limiar; maior profundidade pode ajustar ruído e sobreajustar. Não existe evidência biométrica para escolher uma profundidade vencedora.

7. **Como funciona a distância cosseno?**
   Ela mede a diferença de orientação entre vetores. Com embeddings L2-normalizados, a similaridade é o produto escalar e a distância usada pelo projeto é `1 − produto escalar`. Distância menor indica vetores mais próximos, mas a decisão depende de um limiar.

8. **O que significa FAR?**
   *False Acceptance Rate*: fração de pares impostores aceitos em verificação 1:1. Ela não é igual a FPIR, que mede aceitações indevidas de consultas desconhecidas em identificação 1:N.

9. **O que significa FRR?**
   *False Rejection Rate*: fração de pares genuínos rejeitados em 1:1. Na identificação 1:N, a métrica relacionada é FNIR, que considera também troca de identidade e rank 1.

10. **Qual é a diferença entre 1:1 e 1:N?**
    Em 1:1, duas amostras são comparadas para verificar se são da mesma pessoa. Em 1:N, uma consulta é comparada com uma galeria de N identidades para identificar o candidato mais próximo ou rejeitar como desconhecido.

11. **Como o sistema rejeita desconhecidos?**
    O matcher experimental escolhe a menor distância à galeria e aplica um limiar. Se nenhum candidato ficar abaixo dele, a consulta é rejeitada. A Etapa 3 implementa e testa isso com embeddings sintéticos; não há FPIR real medido.

12. **Por que utilizar DBSCAN?**
    Ele permite agrupar por densidade sem fixar antecipadamente o número de clusters e marcar amostras como ruído. Sua sensibilidade a `eps`, `min_samples` e densidades diferentes precisa ser avaliada; o pipeline está implementado, mas não foi executado com biometria real.

13. **Qual é a diferença entre DBSCAN e K-Means?**
    DBSCAN usa vizinhança/densidade e pode deixar ruído sem cluster. K-Means exige escolher K e atribui os pontos a centroides, sem uma classe de ruído explícita. Ambos são agrupadores, não reconhecedores prontos para uso operacional.

14. **O que significa ARI?**
    Adjusted Rand Index compara a partição encontrada com rótulos externos, ajustando a concordância esperada ao acaso. Nesta implementação, os rótulos só devem entrar depois de o agrupamento ser ajustado.

15. **O que significa Silhouette?**
    Silhouette compara a proximidade de cada ponto ao próprio cluster e ao cluster alternativo mais próximo. Requer número/distribuição de clusters apropriados. Para DBSCAN, o relatório mede os pontos cobertos e informa a cobertura e o ruído em separado.

16. **Como foi evitado vazamento de dados?**
    A infraestrutura divide identidades antes de formar pares; os executores leem partições separadamente, congelam escolhas na validação e reservam o teste para avaliação final. Esse protocolo foi exercitado por testes sintéticos. O holdout da Etapa 1 já foi historicamente consultado, portanto não é tratado como teste intocado para as etapas posteriores.

17. **Como foram protegidos os dados biométricos?**
    Esta consolidação não abriu imagens, embeddings, webcam, PostgreSQL ou credenciais. A política coloca dados experimentais em `avaliacao/`, ignorado pelo Git, e proíbe usar alunos cadastrados como dataset. Dado biométrico é sensível; a instituição deve revisar finalidade, base legal, acesso, retenção, segurança e descarte. O projeto não declara conformidade integral com LGPD.

18. **Qual é a precisão real do sistema?**
    Não há uma estimativa válida da precisão de identificação 1:N em sala. A Etapa 1 mediu verificação 1:1 no LFW: AUC 0,9830; no teste histórico, o baseline 0,30 teve FRR 38,03% e FAR 0,0018%, e o candidato 0,42817932706540435 teve FRR 16,39% e FAR 0,063%. Esses resultados têm outro domínio, não incluem anti-spoofing e não são uma medida operacional da Fatec.

19. **Por que alguns experimentos não foram executados?**
    Os relatórios das Etapas 2–4 não encontraram autorização específica verificada para o uso experimental do LFW. Além disso, o teste da Etapa 1 já tinha sido consultado e não pode ser apresentado como holdout independente. Em vez de inventar licença ou métricas, os gates ficaram fechados e o software foi testado com dados sintéticos.

20. **Quais seriam os próximos passos?**
    Aprovar uma fonte e finalidade de pesquisa com revisão institucional; definir consentimento e proteção dos dados; usar identidades e teste final independentes do holdout anterior; executar protocolo 1:N em condições representativas, medir anti-spoofing em estudo separado e avaliar subgrupos e câmeras. Integração operacional exigiria decisão e aprovação específicas.

21. **O anti-spoofing foi validado contra ataques?**
    Não. MiniFASNet está integrado e habilitado por padrão, mas os documentos registram falso positivo em contraluz e ausência de um conjunto de ataques apropriado para medir APCER/BPCER. A eficácia contra ataques não foi medida.

22. **Por que os 518 testes aprovados não provam a precisão do reconhecimento?**
    Eles verificam regras e contratos do software com fixtures e dublês. Uma medida de precisão exige um conjunto biométrico apropriado, protocolo de avaliação, identificação de erros e amostra estatística, além de autorização. São evidências diferentes.
