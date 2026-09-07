# language: pt
Funcionalidade: Cadastro de aluno
  Como operador do sistema
  Quero cadastrar um aluno a partir do seu rosto
  Para que ele possa ter a presenca reconhecida depois

  Contexto:
    Dado que o sistema esta operacional

  Cenario: Aluno valido
    Dado que a camera entrega o rosto de uma pessoa real
    Quando eu cadastrar o aluno "Ana Souza" com a matricula "1001"
    Entao o aluno deve estar cadastrado
    E o embedding facial deve ter sido gravado
    E a data do consentimento deve estar registrada

  Cenario: Matricula duplicada
    Dado que ja existe um aluno com a matricula "1001"
    E que a camera entrega o rosto de uma pessoa real
    Quando eu cadastrar o aluno "Outra Pessoa" com a matricula "1001"
    Entao o cadastro deve falhar com "AlunoJaCadastrado"
    E nenhuma imagem deve ter sido gravada

  Cenario: Nome invalido
    Dado que a camera entrega o rosto de uma pessoa real
    Quando eu cadastrar o aluno "   " com a matricula "1001"
    Entao o cadastro deve falhar com "DadosInvalidos"

  Cenario: Nenhum rosto na imagem
    Dado que a camera nao entrega nenhum rosto
    Quando eu cadastrar o aluno "Ana Souza" com a matricula "1001"
    Entao o cadastro deve falhar com "NenhumRostoDetectado"
    E nenhuma imagem deve ter sido gravada

  Cenario: Mais de um rosto na imagem
    Dado que a camera entrega mais de um rosto
    Quando eu cadastrar o aluno "Ana Souza" com a matricula "1001"
    Entao o cadastro deve falhar com "MultiplosRostosDetectados"

  Cenario: Imagem invalida ou modelo quebrado
    Dado que o modelo de reconhecimento esta indisponivel
    Quando eu cadastrar o aluno "Ana Souza" com a matricula "1001"
    Entao o cadastro deve falhar com "ModeloIndisponivel"

  Cenario: Foto impressa no lugar da pessoa
    Dado que a camera entrega uma foto impressa
    Quando eu cadastrar o aluno "Ana Souza" com a matricula "1001"
    Entao o cadastro deve falhar com "PossivelFraude"
    E nenhuma imagem deve ter sido gravada

  Cenario: Sem consentimento do titular
    Dado que a camera entrega o rosto de uma pessoa real
    Quando eu cadastrar o aluno "Ana Souza" com a matricula "1001" sem consentimento
    Entao o cadastro deve falhar com "ConsentimentoNaoRegistrado"
    E nenhuma imagem deve ter sido gravada
