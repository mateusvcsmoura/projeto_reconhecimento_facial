# ADR-004 — Critério de escolha do limiar de reconhecimento

- **Status:** aceito; **valor ainda não calibrado**
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
