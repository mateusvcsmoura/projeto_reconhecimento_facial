# language: pt
Funcionalidade: Reconhecimento facial
  Como operador do sistema
  Quero identificar o aluno presente diante da camera
  Para registrar a presenca da pessoa certa

  Contexto:
    Dado que o sistema esta operacional

  Cenario: Aluno reconhecido
    Dado que o aluno "Ana Souza" esta cadastrado com um embedding conhecido
    Quando a camera apresentar o rosto de "Ana Souza"
    Entao o sistema deve identificar "Ana Souza"

  Cenario: Rosto desconhecido
    Dado que o aluno "Ana Souza" esta cadastrado com um embedding conhecido
    Quando a camera apresentar um rosto desconhecido
    Entao o sistema nao deve identificar ninguem

  Cenario: Dois candidatos proximos
    Dado que existem dois alunos com embeddings parecidos
    Quando a camera apresentar o rosto mais parecido com o segundo aluno
    Entao o sistema deve identificar o segundo aluno
    E nao o primeiro que estava dentro do limiar

  Cenario: Modelo indisponivel
    Dado que o aluno "Ana Souza" esta cadastrado com um embedding conhecido
    E que o modelo de reconhecimento esta indisponivel
    Quando a camera apresentar um rosto qualquer
    Entao o reconhecimento deve falhar com "ModeloIndisponivel"
    E a falha nao deve ser confundida com rosto nao reconhecido

  Cenario: Frame sem rosto
    Dado que o aluno "Ana Souza" esta cadastrado com um embedding conhecido
    Quando a camera nao apresentar nenhum rosto
    Entao o sistema nao deve identificar ninguem

  Cenario: Nenhum aluno com embedding
    Dado que nenhum aluno possui embedding cadastrado
    Quando a camera apresentar um rosto qualquer
    Entao o sistema nao deve identificar ninguem
    E o modelo nao deve ser acionado

  Cenario: Custo constante independente do numero de alunos
    Dado que existem 50 alunos cadastrados com embedding
    Quando a camera apresentar um rosto qualquer
    Entao o modelo deve ser acionado exatamente uma vez
