"""Traducao de erro de dominio em mensagem acionavel.

Duas regras aqui:

  * cada falha tem mensagem propria. No prototipo, qualquer erro no
    reconhecimento virava "Rosto nao reconhecido", e o operador nunca sabia
    se o problema era o enquadramento ou a instalacao do TensorFlow;
  * toda mensagem diz o que FAZER. "Modelo indisponivel" informa; "verifique
    a instalacao e rode o cadastro de novo" resolve.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain import errors


@dataclass(frozen=True, slots=True)
class Orientacao:
    problema: str
    acao: str

    def __str__(self) -> str:
        return f"{self.problema} {self.acao}"


_ORIENTACOES: dict[type[Exception], Orientacao] = {
    errors.NenhumRostoDetectado: Orientacao(
        problema="Nenhum rosto na camera.",
        acao="Aproxime-se, olhe para a lente e verifique a iluminacao.",
    ),
    errors.MultiplosRostosDetectados: Orientacao(
        problema="Mais de um rosto na camera.",
        acao="Peca que as outras pessoas saiam do enquadramento.",
    ),
    errors.IdentificacaoAmbigua: Orientacao(
        problema="Identificacao ambigua.",
        acao="Olhe de frente para a camera, ajuste a posicao e tente novamente.",
    ),
    errors.RostoMuitoPequeno: Orientacao(
        problema="Rosto muito pequeno.",
        acao="Aproxime-se da camera e tente novamente.",
    ),
    errors.IluminacaoInsuficiente: Orientacao(
        problema="Rosto escuro.",
        acao="Melhore a iluminacao frontal e tente novamente.",
    ),
    errors.IluminacaoExcessiva: Orientacao(
        problema="Rosto muito claro.",
        acao="Reduza a luz direta e tente novamente.",
    ),
    errors.RostoSemNitidez: Orientacao(
        problema="Rosto sem nitidez.",
        acao="Fique parado, ajuste o foco e tente novamente.",
    ),
    errors.QualidadeCapturaInsuficiente: Orientacao(
        problema="Captura inadequada.",
        acao="Ajuste o enquadramento e tente novamente.",
    ),
    errors.PossivelFraude: Orientacao(
        problema="Apresentacao de foto ou tela detectada.",
        acao=(
            "Se voce esta ao vivo, o modelo errou: melhore a iluminacao "
            "(evite janela ou luz forte atras de voce), aproxime o rosto e "
            "tente de novo."
        ),
    ),
    errors.ModeloIndisponivel: Orientacao(
        problema="Modelo de reconhecimento indisponivel.",
        acao=(
            "Verifique a instalacao do DeepFace e a conexao "
            "(a primeira execucao baixa os pesos)."
        ),
    ),
    errors.CameraIndisponivel: Orientacao(
        problema="Nao foi possivel abrir a camera.",
        acao="Feche outros programas que a estejam usando e ajuste CAMERA_INDEX.",
    ),
    errors.FalhaNaLeituraDaCamera: Orientacao(
        problema="A camera parou de responder.",
        acao="Verifique o cabo ou a conexao e tente de novo.",
    ),
    errors.ConsentimentoNaoRegistrado: Orientacao(
        problema="Cadastro cancelado: o consentimento e obrigatorio.",
        acao="Sem o aceite do titular o dado biometrico nao pode ser coletado.",
    ),
    errors.AlunoNaoEncontrado: Orientacao(
        problema="Nenhum aluno com essa matricula.",
        acao="Confira a matricula na opcao de listar alunos.",
    ),
    errors.AlunoJaCadastrado: Orientacao(
        problema="Ja existe um aluno com essa matricula.",
        acao="Use outra matricula, ou exclua o cadastro anterior.",
    ),
}


def orientacao_para(erro: Exception) -> Orientacao | None:
    for tipo, orientacao in _ORIENTACOES.items():
        if isinstance(erro, tipo):
            return orientacao
    return None


def para_operador(erro: Exception) -> str:
    orientacao = orientacao_para(erro)
    if orientacao is None:
        # DadosInvalidos ja nasce com texto especifico ("Informe a matricula.").
        return str(erro)

    mensagem = str(orientacao)

    # ModeloIndisponivel embrulha qualquer falha da biblioteca de ML, entao a
    # orientacao sozinha e generica demais para diagnosticar. Anexar a causa
    # original e o que separa "verifique a instalacao" de "instale o torch".
    detalhe = str(erro).strip()
    if isinstance(erro, errors.ModeloIndisponivel) and detalhe:
        mensagem = f"{mensagem}\n  Causa: {detalhe}"

    return mensagem
