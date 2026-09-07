# Roteiro de apresentação

Guia para demonstrar e defender o projeto. Pensado para ~15 minutos mais
perguntas.

A tese: **o trabalho não é o sistema funcionar — é a distância entre onde
ele começou e onde chegou, e a justificativa de cada passo.**

---

## Antes de começar — checklist

```powershell
docker compose up -d              # PostgreSQL
alembic upgrade head              # schema
python -m src.main                # a aplicação
```

- [ ] Banco de pé e migrations aplicadas
- [ ] Pelo menos um aluno cadastrado **antes** da apresentação (o primeiro
      cadastro baixa os pesos e demora)
- [ ] Iluminação **de frente**, nunca de costas para janela — ver seção 6
- [ ] `pytest` rodado uma vez, para a suíte estar quente
- [ ] Terminal com fonte grande

---

## 1. O ponto de partida (2 min)

Abra [`docs/baseline-arquitetura.md`](baseline-arquitetura.md).

> "O projeto começou como 364 linhas num arquivo só. Não é crítica: é o
> ponto de partida honesto de um protótipo que funcionava."

Mostre o que a auditoria encontrou, com os números:

| Achado | Evidência |
|---|---|
| Apresentação, câmera, IA e SQL na mesma função | `cadastro.py`, duas funções de ~90 linhas |
| Schema divergente do código | O `NOT NULL` declarado não existia no banco |
| A regra central quebrada | `date(data_hora)` retornava `NULL` em **39 de 39** linhas |
| Custo inviável | Até `2N` inferências por ciclo de comparação |
| `except Exception: continue` | Modelo quebrado indistinguível de "sem rosto" |
| Zero testes | — |

**A pergunta que orientou tudo:** *como transformar isso sem quebrar o que
já funcionava?*

---

## 2. O plano (1 min)

[`REFACTORING_PLAN.md`](../REFACTORING_PLAN.md) — 18 problemas catalogados
com ID, impacto, evidência e prioridade; nove fases; ordem de execução.

> "Nenhuma fase começou antes de a anterior estar verde. Cada uma virou um
> Pull Request próprio."

Mostre a tabela de problemas: **18 de 18 fechados**, cada um com a fase e a
evidência.

---

## 3. A arquitetura (3 min)

[`ARCHITECTURE.md`](../ARCHITECTURE.md) — mostre o diagrama de camadas.

Não descreva as camadas: **prove** que elas existem.

```bash
grep -rn "import cv2\|from deepface\|sqlalchemy" src/domain/ src/application/
# vazio

grep -rln "from deepface" src/
# 1 arquivo
```

> "O domínio não sabe que DeepFace existe. Trocar o modelo é mudar uma
> variável de ambiente e rodar um backfill."

**Se perguntarem por que tantas camadas num projeto pequeno:** a resposta
está nos testes. 281 rodam sem webcam e sem TensorFlow. No protótipo, nada
era testável sem hardware.

---

## 4. As três decisões que vale defender (4 min)

### 4.1 A regra de negócio virou constraint

```sql
UNIQUE (aluno_id, data_referencia)
```

> "O protótipo fazia `SELECT`, verificava, depois `INSERT`. Isso tem uma
> corrida entre os dois passos — e, sobre os dados legados, simplesmente
> não funcionava: o formato de data gravado fazia o `date()` do SQLite
> retornar `NULL`."

Demonstre ao vivo: reconheça um aluno, ENTER, ENTER de novo.

**Ponto forte:** a regra deixou de depender de a aplicação lembrar de
aplicá-la.

### 4.2 Embeddings persistidos — e por que não `pgvector`

[`ADR-002`](adr/ADR-002-armazenamento-de-embeddings.md).

```bash
python -m scripts.benchmark_matcher
```

| Alunos | Comparação |
|---:|---:|
| 200 | 0,0142 ms |

> "O desenho anterior fazia até 400 inferências por ciclo com 200 alunos.
> Hoje é uma. E não usamos `pgvector`: nesta escala, o índice aproximado é
> mais lento que a varredura exata e adiciona uma extensão à infraestrutura.
> Dizer *por que não* adotar, com o número na mão, vale mais do que adotar."

### 4.3 O melhor candidato, não o primeiro

> "O protótipo aceitava o primeiro aluno que passasse no limiar — e a ordem
> era a da consulta SQL. Com dois rostos parecidos, a presença ia para quem
> aparecesse primeiro na lista."

Mostre `tests/unit/test_matcher.py::test_escolhe_o_MELHOR_candidato_e_nao_o_primeiro`:
o teste prova que o primeiro candidato **passaria** no limiar e mesmo assim
perde para o mais próximo.

---

## 5. Demonstração ao vivo (3 min)

Ordem sugerida:

1. **Listar** (3) — mostre a coluna *situação*: alunos sem embedding não
   serão reconhecidos, e o sistema avisa antes da aula.
2. **Cadastrar** (1) — pare no termo de consentimento.
   > "A câmera não liga antes do aceite. Coletar biometria para só então
   > perguntar inverteria o que a LGPD exige."
3. **Reconhecer** (2) — mostre nome e porcentagem no overlay.
   > "Essa porcentagem **não é probabilidade**. É uma leitura de quão longe
   > do limiar a decisão ficou. Chamar de probabilidade seria enganoso."
4. **ENTER duas vezes** — a segunda avisa que já existe.
5. **Presenças de hoje** (4).
6. **Excluir** (5) — linha, embedding, imagem e presenças.

---

## 6. Se algo der errado na hora

| Sintoma | Resposta |
|---|---|
| "Apresentação de foto detectada" com você ao vivo | Falso positivo do MiniFASNet com contraluz. Explique que **está documentado** e siga com `FACE_ANTI_SPOOFING=false` |
| Câmera demora | Não deve mais: `CAMERA_BACKEND=auto`. Se demorar, o backend caiu para MSMF |
| Nada reconhecido | Confira na opção 3 se o aluno tem embedding |

**Transformar o erro em argumento:** se o anti-spoofing recusar você, essa é
uma oportunidade, não um acidente.

> "Isto é o comportamento que documentamos em `docs/lgpd.md`: o modelo
> recusa pessoas reais em contraluz, com 86% a 96% de confiança. A
> verificação funciona; o modelo erra nessas condições. Preferimos registrar
> a limitação a fingir que ela não existe."

---

## 7. Qualidade (2 min)

```bash
pytest -q          # 281 passed
ruff check .       # All checks passed
mypy               # no issues in 54 source files
```

Mostre um `.feature`:

```gherkin
Cenario: Tentativa de duplicacao no mesmo dia
  Dado que o aluno "Ana Souza" esta cadastrado
  E que a presenca de "Ana Souza" ja foi registrada hoje
  Quando o operador confirmar a presenca de "Ana Souza"
  Entao nenhuma nova presenca deve ser registrada
```

> "São 24 cenários em Gherkin, executados de verdade pelo pytest-bdd. E a
> distinção que a disciplina exige: teste de software verifica se o pipeline
> faz o que promete; avaliação de modelo mede se o modelo acerta. São coisas
> diferentes, e temos ferramenta para as duas."

---

## 8. O que não foi feito (1 min)

**Não pule esta parte.** Declarar limite é o que separa trabalho honesto de
promessa.

| Pendência | Situação |
|---|---|
| Calibração do `FACE_THRESHOLD` | Script pronto e testado; falta rodar sobre imagens. [ADR-004](adr/ADR-004-limiar-de-reconhecimento.md) |
| Eficácia do anti-spoofing | Medida só a falha em contraluz; falta iluminação frontal e teste com foto impressa |
| Criptografia em repouso | Não implementada; declarada em `docs/lgpd.md` |
| Autenticação de operador | Fora do escopo de um sistema local monousuário |

> "O limiar em uso é 0.30, que é o valor herdado da biblioteca. Sabemos que
> isso é herança e não medição, e está escrito no ADR-004. Com o script que
> temos, calibrar é questão de conseguir um conjunto de imagens."

---

## Perguntas prováveis

**"Por que PostgreSQL num projeto acadêmico pequeno?"**
Não é pelo tamanho. É porque as regras de negócio viraram constraints — e o
SQLite não aplicava nem a integridade referencial: o `PRAGMA foreign_keys`
precisava ser ligado por conexão e nunca era.

**"Por que não usaram um framework pronto de reconhecimento?"**
Usamos: DeepFace. O trabalho foi construir tudo em volta — persistência,
regra, segurança, testes — de forma que ele possa ser trocado.

**"Como sabem que os testes testam algo?"**
Pela cobertura ter encontrado um bug real: ela apontou o método de
consentimento como código morto, e ele era — a CLI nunca o chamava. O
sistema cadastrava biometria sem pedir consentimento. Está no commit
`fix(cli): pedir o consentimento antes de cadastrar`.

**"Qual foi a parte mais difícil?"**
Não foi o reconhecimento facial. Foi descobrir que cinco defeitos só
aparecem quando o sistema roda em hardware real — duas dependências não
declaradas, a câmera levando 27 segundos, a janela que não redimensionava e
uma mensagem de erro que escondia a causa. Nenhum deles apareceu em oito
fases de refatoração e testes.

**"O que fariam a seguir?"**
Nesta ordem: calibrar o limiar com dados reais, validar o anti-spoofing e só
então pensar em API. As duas primeiras são medições que faltam; a terceira é
funcionalidade que ninguém pediu.

---

## Materiais

| Documento | Serve para |
|---|---|
| [`ARCHITECTURE.md`](../ARCHITECTURE.md) | Diagramas e estrutura atual |
| [`docs/baseline-arquitetura.md`](baseline-arquitetura.md) | O ponto de partida |
| [`REFACTORING_PLAN.md`](../REFACTORING_PLAN.md) | Os 18 problemas e as 9 fases |
| [`docs/adr/`](adr/) | As quatro decisões, com alternativas descartadas |
| [`docs/lgpd.md`](lgpd.md) | Dados pessoais e limites conhecidos |
| Histórico do Git | Um PR por fase, com o porquê no corpo de cada commit |
