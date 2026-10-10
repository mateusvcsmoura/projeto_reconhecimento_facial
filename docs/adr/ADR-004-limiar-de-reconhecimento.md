# ADR-004 — Critério de escolha do limiar de reconhecimento

- **Status:** aceito; **valor em uso ainda herdado** — calibração 1:1 medida na Etapa 1 (candidato 0,4282 para FAR ≤ 0,1%), adoção pendente
- **Data:** 2026-09-07
- **Fase:** 7 (decisão) / pendente de medição

---

## Problema

O sistema decide "é a mesma pessoa" comparando a distância cosseno entre
dois embeddings contra um limiar. Esse número determina os dois erros
possíveis:

| Erro | O que acontece | Custo |
|---|---|---|
| **Falso positivo** (FAR) | Um impostor é aceito | A presença vai para a pessoa errada. Corrompe o registro oficial |
| **Falso negativo** (FRR) | Um aluno legítimo é recusado | O aluno tenta de novo |

O protótipo não escolhia limiar nenhum: lia apenas `verified: bool` do
`DeepFace.verify()` e descartava `distance` e `threshold`. O valor efetivo
era o interno da biblioteca — invisível, não ajustável e não justificável
diante de uma banca.

## Alternativas de critério

Depois que FAR e FRR são medidos sobre um conjunto de pares, resta escolher
**qual ponto da curva** adotar.

| Critério | O que faz | Avaliação |
|---|---|---|
| **EER** (FAR = FRR) | Ponto onde os dois erros se igualam | Serve para **comparar modelos**, não para operar um. Trata os dois erros como igualmente caros, e aqui eles não são |
| **Acurácia balanceada máxima** | Minimiza a média dos erros | Mesmo problema: assume custos iguais |
| **Teto de FAR** | Fixa quanto de fraude se tolera; aceita o FRR que vier | Traduz uma decisão de negócio em número |
| Herdar o padrão da biblioteca | Nenhum trabalho | É o que o protótipo fazia; indefensável academicamente |

## Decisão

**Teto de FAR.** Fixa-se o quanto de aceitação indevida o sistema tolera, e
adota-se o **maior limiar** que ainda respeita esse teto — o que minimiza o
FRR dentro da restrição.

`scripts/evaluate_model.py` reporta o limiar sugerido para tetos de 0%,
0,1%, 1% e 5%, além de EER e AUC para comparação.

### Justificativa

Os erros não custam o mesmo. Recusar um aluno legítimo custa uma segunda
tentativa diante da câmera — irritante, recuperável em segundos. Aceitar um
impostor grava presença de quem não estava presente, num registro que a
instituição trata como oficial. É um erro silencioso: ninguém percebe no
momento, e ele não se corrige sozinho.

Um critério que trata os dois como equivalentes está respondendo à pergunta
errada.

## Estado atual — não calibrado

`FACE_THRESHOLD = 0.30`, que é o valor que o DeepFace usa para o par
(Facenet512, cosseno). **Isso continua sendo herança, não medição.**

O que já existe:

- `scripts/metricas.py` — FAR, FRR, EER, AUC e "maior limiar para um teto de
  FAR", em funções puras, **cobertas por 16 testes** que rodam sem o modelo;
- `scripts/evaluate_model.py` — percorre um conjunto organizado por pessoa,
  monta os pares genuínos e impostores e reporta tudo.

O que falta: rodar sobre imagens reais, num ambiente Python 3.12/3.13 com
DeepFace instalado.

```bash
python -m scripts.evaluate_model --dataset ./avaliacao/dataset
```

Estrutura esperada — mínimo de 2 pessoas com 2+ fotos cada; útil de verdade
a partir de 10 pessoas:

```text
dataset/
  pessoa-1/  foto-a.jpg  foto-b.jpg
  pessoa-2/  foto-a.jpg  foto-b.jpg
```

O conjunto de imagens **nunca** deve ser versionado.

**Atualização 2026-10-10 (Etapa 0):** rodar o script como acima mede o erro
sobre os mesmos pares em que o limiar é sugerido; a saída passou a se
declarar exploratória. A calibração que este ADR pede deve escolher o limiar
em treino/validação e medi-lo uma única vez no teste, com divisão por
identidade — infraestrutura pronta (`--validar-divisao`,
`scripts/divisao_por_identidade.py`), calibração pendente para a Etapa 1.
Ver `docs/ML-EXPERIMENT-SETUP.md`.

**Atualização 2026-10-10 (Etapa 1) — primeira calibração medida.**
Detalhes em `docs/ML-ETAPA-1-RESULTADO.md`.

- **Método.** `scripts/calibrar_limiar.py` divide o LFW por identidade
  (seed 42, 60/20/20), escolhe `τ` na validação pelo critério deste ADR e
  abre o teste uma única vez, com o baseline e os limiares calibrados
  congelados juntos.
- **Escopo.** Verificação 1:1, sem prova de vida.

| Teto de FAR | τ (validação) | FAR no teste (IC95) | FRR no teste (IC95) |
|---|---|---|---|
| **0,30 herdado** | — | 0,0018% (0–0,005%) | 38,0% (32,6–43,9%) |
| **0,1% — candidato** | **0,4282** | 0,063% (0,042–0,090%) | 16,4% (12,4–21,0%) |
| 1% | 0,5653 | 0,92% (0,74–1,11%) | 7,9% (5,3–11,1%) |
| 5% | 0,6860 | 4,8% (4,2–5,5%) | 4,8% (2,9–7,3%) |

AUC no teste: 0,983 (a mesma para qualquer limiar).

- **O 0,30 já não é desconhecido.** Nesta configuração, ele opera com um
  teto implícito de ~0,005% (medido na validação), cerca de 18 vezes mais
  rigoroso que 0,1%, e paga isso com o FRR.
- **O valor em uso não mudou.** 0,4282 é um **candidato**. Adotá-lo depende
  de três coisas:
  1. a decisão de negócio sobre o teto;
  2. a avaliação 1:N (FPIR/FNIR), da Etapa 3;
  3. a validação na webcam da sala.

  O dataset público difere da operação em domínio, não tem prova de vida e
  não tem N.

## Trade-offs aceitos

| Ganho | Custo |
|---|---|
| O limiar deixa de ser mágico e passa a ser justificável | Exige um conjunto de imagens e o tempo de rodar a medição |
| A decisão de negócio fica explícita ("toleramos 0,1% de fraude") | Alguém precisa **tomar** essa decisão; não há default correto |
| A matemática é testável sem o modelo | A medição em si continua dependendo de hardware e biblioteca |

## Consequências

- Enquanto não houver calibração, o número em uso é declaradamente
  herdado — está registrado aqui, no `.env.example` e no `ARCHITECTURE.md`.
- Trocar `FACE_MODEL` invalida a calibração junto com os embeddings:
  distâncias de modelos diferentes não são comparáveis.
- A porcentagem de confiança exibida na tela é derivada deste limiar. Ela
  **não é probabilidade** — é uma leitura linear de quão longe do limiar a
  decisão ficou. Com o limiar calibrado, ela passa a significar algo; sem,
  é apenas uma escala relativa.
