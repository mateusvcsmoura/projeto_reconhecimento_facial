"""Traducao de erro de dominio para mensagem ao operador.

Cada falha tem uma mensagem propria. No prototipo, qualquer erro no
reconhecimento virava "Rosto nao reconhecido" -- o operador nunca sabia se
o problema era o enquadramento ou a instalacao do TensorFlow.
"""

from __future__ import annotations

from src.domain import errors

_MENSAGENS: dict[type[Exception], str] = {
    errors.NenhumRostoDetectado: "Nenhum rosto na camera.",
    errors.MultiplosRostosDetectados: "Deixe somente UM rosto na camera.",
    errors.ModeloIndisponivel: (
        "Modelo de reconhecimento indisponivel. "
        "Verifique a instalacao e os pesos baixados."
    ),
    errors.CameraIndisponivel: "Nao foi possivel abrir a camera.",
    errors.FalhaNaLeituraDaCamera: "A camera parou de responder.",
}


def para_operador(erro: Exception) -> str:
    for tipo, mensagem in _MENSAGENS.items():
        if isinstance(erro, tipo):
            return mensagem
    # DadosInvalidos e AlunoJaCadastrado ja nascem com texto proprio.
    return str(erro)
