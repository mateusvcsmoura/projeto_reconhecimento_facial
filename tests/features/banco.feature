# language: pt
Funcionalidade: Integridade do banco de dados
  Como responsavel pelo sistema
  Quero que o banco garanta as regras por conta propria
  Para que um bug na aplicacao nao produza registro invalido

  Cenario: Migrations criam o schema esperado
    Dado um banco PostgreSQL vazio
    Quando as migrations forem aplicadas
    Entao as tabelas "alunos" e "presencas" devem existir
    E a constraint de presenca unica por dia deve existir

  Cenario: Constraint de matricula unica
    Dado um banco com as migrations aplicadas
    Quando eu inserir dois alunos com a mesma matricula
    Entao o banco deve recusar o segundo

  Cenario: Chave estrangeira de presenca
    Dado um banco com as migrations aplicadas
    Quando eu inserir uma presenca para um aluno inexistente
    Entao o banco deve recusar a insercao

  Cenario: Exclusao em cascata
    Dado um aluno com presencas registradas
    Quando o aluno for excluido
    Entao as presencas dele devem desaparecer junto

  Cenario: Rollback das migrations
    Dado um banco com as migrations aplicadas
    Quando as migrations forem revertidas
    Entao as tabelas da aplicacao nao devem existir
