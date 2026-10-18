"""Erros de dominio.

Existem para que uma falha tenha significado. O prototipo transformava
qualquer excecao em "rosto nao reconhecido" com `except Exception: continue`,
o que tornava indistinguiveis "nenhum rosto no frame" e "TensorFlow
quebrado" (problema A6 do REFACTORING_PLAN.md).
"""

from __future__ import annotations


class ErroDeDominio(Exception):
    """Base de todos os erros esperados do sistema."""


class DadosInvalidos(ErroDeDominio):
    """Entrada do operador nao passou na validacao."""


class QualidadeCapturaInsuficiente(ErroDeDominio):
    """A captura nao atende a politica optativa de qualidade."""


class IdentificacaoAmbigua(ErroDeDominio):
    """Duas identidades candidatas nao estao separadas pela margem exigida."""


class RostoMuitoPequeno(QualidadeCapturaInsuficiente):
    """O rosto ocupa poucos pixels para a avaliacao configurada."""


class IluminacaoInsuficiente(QualidadeCapturaInsuficiente):
    """A luminosidade media do recorte esta abaixo do limite."""


class IluminacaoExcessiva(QualidadeCapturaInsuficiente):
    """A luminosidade media do recorte esta acima do limite."""


class RostoSemNitidez(QualidadeCapturaInsuficiente):
    """A variancia do Laplaciano nao atingiu o limite configurado."""


class AlunoJaCadastrado(ErroDeDominio):
    def __init__(self, matricula: str) -> None:
        super().__init__(f"Ja existe um aluno com a matricula {matricula}.")
        self.matricula = matricula


class CameraIndisponivel(ErroDeDominio):
    def __init__(self, indice: int) -> None:
        super().__init__(f"Nao foi possivel abrir a camera de indice {indice}.")
        self.indice = indice


class FalhaNaLeituraDaCamera(ErroDeDominio):
    """A camera abriu mas parou de entregar frames."""


class NenhumRostoDetectado(ErroDeDominio):
    """O detector nao encontrou rosto na imagem."""


class MultiplosRostosDetectados(ErroDeDominio):
    def __init__(self, quantidade: int) -> None:
        super().__init__(f"A imagem contem {quantidade} rostos; era esperado 1.")
        self.quantidade = quantidade


class ModeloIndisponivel(ErroDeDominio):
    """Pesos ausentes, backend quebrado ou modelo impossivel de carregar."""


class PossivelFraude(ErroDeDominio):
    """O rosto apresentado nao parece uma pessoa real.

    Foto impressa, tela de celular, mascara. Distinto de
    NenhumRostoDetectado de proposito: ha um rosto, e justamente por isso o
    caso merece uma mensagem propria ao operador.
    """

    def __init__(self, pontuacao: float | None = None) -> None:
        detalhe = f" (score {pontuacao:.2f})" if pontuacao is not None else ""
        super().__init__(f"Apresentacao de foto ou tela detectada{detalhe}.")
        self.pontuacao = pontuacao


class AlunoNaoEncontrado(ErroDeDominio):
    def __init__(self, matricula: str) -> None:
        super().__init__(f"Nenhum aluno com a matricula {matricula}.")
        self.matricula = matricula


class TurmaNaoEncontrada(ErroDeDominio):
    def __init__(self, turma_id: int) -> None:
        super().__init__(f"Nao existe uma turma com o identificador {turma_id}.")
        self.turma_id = turma_id


class TurmaInativa(ErroDeDominio):
    def __init__(self, turma_id: int) -> None:
        super().__init__(f"A turma {turma_id} foi excluida e nao aceita operacoes.")
        self.turma_id = turma_id


class AlunoSemConsentimento(ErroDeDominio):
    def __init__(self, matricula: str) -> None:
        super().__init__(
            f"O aluno {matricula} nao possui consentimento biometrico registrado."
        )
        self.matricula = matricula


class VinculoNaoEncontrado(ErroDeDominio):
    def __init__(self, turma_id: int, matricula: str) -> None:
        super().__init__(
            f"O aluno {matricula} nao possui vinculo nesta turma ({turma_id})."
        )
        self.turma_id = turma_id
        self.matricula = matricula


class VinculoInativo(ErroDeDominio):
    def __init__(self, turma_id: int, aluno_id: int) -> None:
        super().__init__(f"O aluno {aluno_id} nao esta vinculado a turma {turma_id}.")
        self.turma_id = turma_id
        self.aluno_id = aluno_id


class ConsentimentoNaoRegistrado(ErroDeDominio):
    """Cadastro biometrico sem consentimento explicito nao pode ocorrer."""


class AnexoJaProcessado(Exception):
    """Sinaliza corrida idempotente para compensar arquivos recém-criados."""

    def __init__(self, estado: str) -> None:
        super().__init__("O job já anexou referências para esta solicitação.")
        self.estado = estado
