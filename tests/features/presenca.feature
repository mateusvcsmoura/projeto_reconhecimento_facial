# language: pt
Funcionalidade: Registro de presenca
  Como operador do sistema
  Quero registrar a presenca do aluno reconhecido
  Para manter o controle de frequencia da turma

  Contexto:
    Dado que o sistema esta operacional

  Cenario: Primeira presenca do dia
    Dado que o aluno "Ana Souza" esta cadastrado
    Quando o operador confirmar a presenca de "Ana Souza"
    Entao a presenca deve ser registrada

  Cenario: Tentativa de duplicacao no mesmo dia
    Dado que o aluno "Ana Souza" esta cadastrado
    E que a presenca de "Ana Souza" ja foi registrada hoje
    Quando o operador confirmar a presenca de "Ana Souza"
    Entao nenhuma nova presenca deve ser registrada
    E o operador deve ser informado de que a presenca ja existe

  Cenario: Mesmo aluno em dias diferentes
    Dado que o aluno "Ana Souza" esta cadastrado
    E que a presenca de "Ana Souza" foi registrada ontem
    Quando o operador confirmar a presenca de "Ana Souza"
    Entao a presenca deve ser registrada

  Cenario: Aluno inexistente
    Dado que nenhum aluno esta cadastrado
    Quando o operador confirmar a presenca de um aluno inexistente
    Entao o registro deve falhar porque o aluno nao pertence a turma
