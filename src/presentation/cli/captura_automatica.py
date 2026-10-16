"""Orquestracao automatica de cadastro e presenca na camada de apresentacao."""

from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic
from types import TracebackType
from typing import Any, Protocol

from src.application.use_cases.cadastrar_aluno import CadastrarAluno
from src.application.use_cases.reconhecer_aluno import ReconhecerAluno, Reconhecimento
from src.domain.entities.aluno import Aluno
from src.domain.errors import (
    FalhaNaLeituraDaCamera,
    IdentificacaoAmbigua,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
    PossivelFraude,
    QualidadeCapturaInsuficiente,
)
from src.domain.services.camera_provider import CameraProvider
from src.domain.services.captura_automatica import (
    ConfirmadorCapturaAutomatica,
    EstadoCapturaAutomatica,
    ParametrosCapturaAutomatica,
)
from src.domain.services.consistencia_temporal import (
    ConfirmadorTemporal,
    EstadoTemporal,
    ParametrosTemporais,
)
from src.domain.services.matcher import MatrizDeReferencia
from src.presentation.cli.mensagens import para_operador
from src.presentation.cli.teclas import AMARELO, BRANCO, ESC, VERDE

logger = logging.getLogger(__name__)

Linha = tuple[str, tuple[int, int, int]]


class JanelaAutomatica(Protocol):
    def __enter__(self) -> JanelaAutomatica: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def mostrar(self, frame: Any, linhas: list[Linha]) -> int: ...


class CapturaAutomaticaCLI:
    """Mantem temporizadores e confirmadores restritos a uma sessao de camera."""

    def __init__(
        self,
        *,
        cadastrar_aluno: CadastrarAluno,
        reconhecer_aluno: ReconhecerAluno,
        registrar: Callable[[Aluno], None],
        abrir_camera: Callable[[], CameraProvider],
        abrir_janela: Callable[[str], JanelaAutomatica],
        parametros: ParametrosCapturaAutomatica,
        turma_id: int,
        temporal: ParametrosTemporais | None,
        relogio: Callable[[], float] = monotonic,
        escrever: Callable[[str], None] = print,
    ) -> None:
        self._cadastrar_aluno = cadastrar_aluno
        self._reconhecer_aluno = reconhecer_aluno
        self._registrar = registrar
        self._abrir_camera = abrir_camera
        self._abrir_janela = abrir_janela
        self._parametros = parametros
        self._turma_id = turma_id
        self._temporal = temporal
        self._relogio = relogio
        self._escrever = escrever

    def cadastrar(self, matricula: str, nome: str) -> Aluno | None:
        confirmador = ConfirmadorCapturaAutomatica(self._parametros)
        fim_analise: float | None = None
        orientacao: str | None = None
        rodape: Linha = ("Captura automatica | ESC cancela", BRANCO)

        with (
            self._abrir_camera() as camera,
            self._abrir_janela("Cadastro facial") as janela,
        ):
            while True:
                capturado_em = self._relogio()
                try:
                    frame = camera.ler_frame()
                except FalhaNaLeituraDaCamera as erro:
                    self._reportar_falha_de_camera(erro)
                    return None

                analisar = (
                    fim_analise is None
                    or capturado_em - fim_analise
                    >= self._parametros.intervalo_amostragem_segundos
                )
                if analisar:
                    try:
                        self._cadastrar_aluno.validar_captura(frame)
                    except (
                        NenhumRostoDetectado,
                        MultiplosRostosDetectados,
                        QualidadeCapturaInsuficiente,
                        PossivelFraude,
                    ) as erro:
                        estado = confirmador.observar(
                            None, capturado_em, self._relogio()
                        )
                        orientacao = para_operador(erro)
                    else:
                        estado = confirmador.observar(
                            "cadastro", capturado_em, self._relogio()
                        )
                        orientacao = None
                    finally:
                        fim_analise = self._relogio()
                else:
                    estado = confirmador.consultar(self._relogio())

                if estado.chave is None and orientacao is None:
                    status = "Posicione um rosto unico diante da camera."
                    cor = BRANCO
                elif orientacao is not None:
                    status = orientacao
                    cor = AMARELO
                elif estado.pronto:
                    status = "Captura validada. Preparando confirmacao final."
                    cor = VERDE
                elif estado.tempo_restante == 0.0 and estado.observacoes < 3:
                    status = f"Validando captura: {estado.observacoes}/3 observacoes."
                    cor = AMARELO
                else:
                    status = (
                        f"Validando captura: {estado.observacoes}/3; "
                        f"aguarde {estado.tempo_restante:.1f}s."
                    )
                    cor = AMARELO

                tecla = janela.mostrar(frame, [(status, cor), rodape])
                if tecla == ESC:
                    return None

                agora = self._relogio()
                estado = confirmador.consultar(agora)
                if not estado.pronto:
                    if estado.chave is None and orientacao is None:
                        status = "Amostras vencidas. Mantenha o rosto visivel."
                    continue

                timestamp_final = self._relogio()
                try:
                    frame_final = camera.ler_frame()
                except FalhaNaLeituraDaCamera as erro:
                    self._reportar_falha_de_camera(erro)
                    return None

                try:
                    preparada = self._cadastrar_aluno.preparar_captura(frame_final)
                except (
                    NenhumRostoDetectado,
                    MultiplosRostosDetectados,
                    QualidadeCapturaInsuficiente,
                    PossivelFraude,
                ) as erro:
                    confirmador.reiniciar()
                    orientacao = para_operador(erro)
                    linha_final: Linha = (orientacao, AMARELO)
                    tecla = janela.mostrar(frame_final, [linha_final, rodape])
                    if tecla == ESC:
                        return None
                    fim_analise = self._relogio()
                    continue

                estado_final = confirmador.observar(
                    "cadastro", timestamp_final, self._relogio()
                )
                if estado_final.pronto:
                    linha_final = (
                        "Confirmando captura. ESC cancela antes de gravar.",
                        VERDE,
                    )
                else:
                    linha_final = (
                        "A validacao expirou. Continue diante da camera.",
                        AMARELO,
                    )

                tecla = janela.mostrar(frame_final, [linha_final, rodape])
                if tecla == ESC:
                    return None

                agora = self._relogio()
                estado_final = confirmador.consultar(agora)
                if estado_final.pronto and agora - timestamp_final <= (
                    self._parametros.idade_maxima_segundos
                ):
                    agora = self._relogio()
                    estado_final = confirmador.consultar(agora)
                    if estado_final.pronto and agora - timestamp_final <= (
                        self._parametros.idade_maxima_segundos
                    ):
                        return self._cadastrar_aluno.concluir_cadastro(
                            matricula,
                            nome,
                            preparada,
                            consentiu=True,
                            turma_id=self._turma_id,
                        )

                fim_analise = self._relogio()

    def reconhecer(self, referencias: MatrizDeReferencia) -> None:
        confirmador = ConfirmadorCapturaAutomatica(self._parametros)
        confirmador_temporal = (
            ConfirmadorTemporal(self._temporal) if self._temporal is not None else None
        )
        fim_analise: float | None = None
        reconhecido: Reconhecimento | None = None
        orientacao: str | None = None
        rodape: Linha = ("Captura automatica | ESC sai", BRANCO)

        with (
            self._abrir_camera() as camera,
            self._abrir_janela("Reconhecimento") as janela,
        ):
            while True:
                capturado_em = self._relogio()
                try:
                    frame = camera.ler_frame()
                except FalhaNaLeituraDaCamera as erro:
                    self._reportar_falha_de_camera(erro)
                    return

                analisar = (
                    fim_analise is None
                    or capturado_em - fim_analise
                    >= self._parametros.intervalo_amostragem_segundos
                )
                if analisar:
                    try:
                        reconhecido = self._reconhecer_aluno.identificar(
                            frame, referencias, turma_id=self._turma_id
                        )
                    except (
                        QualidadeCapturaInsuficiente,
                        IdentificacaoAmbigua,
                        PossivelFraude,
                    ) as erro:
                        reconhecido = None
                        confirmador.observar(None, capturado_em, self._relogio())
                        if confirmador_temporal is not None:
                            confirmador_temporal.observar(None, capturado_em)
                        orientacao = para_operador(erro)
                    else:
                        chave: str | None = None
                        id_observado: int | None = None
                        if reconhecido is not None:
                            chave = str(reconhecido.aluno.id)
                            id_observado = reconhecido.aluno.id
                        estado = confirmador.observar(
                            chave, capturado_em, self._relogio()
                        )
                        if confirmador_temporal is not None:
                            confirmador_temporal.observar(id_observado, capturado_em)
                        orientacao = None
                        if estado.chave is None:
                            reconhecido = None
                    finally:
                        fim_analise = self._relogio()

                agora = self._relogio()
                estado = confirmador.consultar(agora)
                estado_temporal = (
                    confirmador_temporal.consultar(agora)
                    if confirmador_temporal is not None
                    else None
                )
                if estado.chave is None or (
                    reconhecido is not None
                    and estado.chave != str(reconhecido.aluno.id)
                ):
                    reconhecido = None

                status, cor = self._rotulo(
                    reconhecido, estado, estado_temporal, orientacao
                )
                tecla = janela.mostrar(frame, [(status, cor), rodape])
                if tecla == ESC:
                    return

                agora = self._relogio()
                estado = confirmador.consultar(agora)
                estado_temporal = (
                    confirmador_temporal.consultar(agora)
                    if confirmador_temporal is not None
                    else None
                )
                if reconhecido is None or not self._pronto_para_registrar(
                    reconhecido, estado, estado_temporal
                ):
                    continue

                identidade_confirmada = reconhecido.aluno.id
                timestamp_final = self._relogio()
                try:
                    frame_final = camera.ler_frame()
                except FalhaNaLeituraDaCamera as erro:
                    self._reportar_falha_de_camera(erro)
                    return

                try:
                    novo_reconhecimento = self._reconhecer_aluno.identificar(
                        frame_final,
                        referencias,
                        turma_id=self._turma_id,
                    )
                except (
                    QualidadeCapturaInsuficiente,
                    IdentificacaoAmbigua,
                    PossivelFraude,
                ) as erro:
                    novo_reconhecimento = None
                    orientacao = para_operador(erro)
                else:
                    orientacao = None

                timestamp_conclusao = self._relogio()
                chave_final = (
                    str(novo_reconhecimento.aluno.id)
                    if novo_reconhecimento is not None
                    else None
                )
                estado = confirmador.observar(
                    chave_final, timestamp_final, timestamp_conclusao
                )
                if confirmador_temporal is not None:
                    estado_temporal = confirmador_temporal.observar(
                        novo_reconhecimento.aluno.id
                        if novo_reconhecimento is not None
                        else None,
                        timestamp_final,
                    )
                reconhecido = novo_reconhecimento

                if novo_reconhecimento is None:
                    estado = confirmador.consultar(self._relogio())
                    status, cor = self._rotulo(
                        None, estado, estado_temporal, orientacao
                    )
                elif novo_reconhecimento.aluno.id != identidade_confirmada:
                    status = "Identidade mudou. Aguardando nova validacao."
                    cor = AMARELO
                else:
                    status, cor = self._rotulo(
                        novo_reconhecimento,
                        estado,
                        estado_temporal,
                        orientacao,
                    )

                tecla = janela.mostrar(frame_final, [(status, cor), rodape])
                if tecla == ESC:
                    return

                agora = self._relogio()
                estado = confirmador.consultar(agora)
                estado_temporal = (
                    confirmador_temporal.consultar(agora)
                    if confirmador_temporal is not None
                    else None
                )
                if (
                    novo_reconhecimento is not None
                    and novo_reconhecimento.aluno.id == identidade_confirmada
                    and agora - timestamp_final
                    <= self._parametros.idade_maxima_segundos
                    and self._pronto_para_registrar(
                        novo_reconhecimento, estado, estado_temporal
                    )
                ):
                    agora = self._relogio()
                    estado = confirmador.consultar(agora)
                    estado_temporal = (
                        confirmador_temporal.consultar(agora)
                        if confirmador_temporal is not None
                        else None
                    )
                    if (
                        agora - timestamp_final
                        <= self._parametros.idade_maxima_segundos
                        and self._pronto_para_registrar(
                            novo_reconhecimento, estado, estado_temporal
                        )
                    ):
                        self._registrar(novo_reconhecimento.aluno)
                        return

                fim_analise = self._relogio()

    def _rotulo(
        self,
        reconhecido: Reconhecimento | None,
        estado: EstadoCapturaAutomatica,
        estado_temporal: EstadoTemporal | None,
        orientacao: str | None,
    ) -> tuple[str, tuple[int, int, int]]:
        if orientacao is not None:
            return orientacao, AMARELO
        if reconhecido is None or estado.chave is None:
            return "Procurando... Olhe para a camera.", BRANCO
        if estado_temporal is not None and not estado_temporal.confirmado:
            minimo = self._temporal.min_observacoes if self._temporal else 3
            return (
                f"Validando identidade: {estado_temporal.observacoes}/{minimo}.",
                AMARELO,
            )
        if estado.pronto:
            return f"Identidade confirmada: {reconhecido.aluno.nome}.", VERDE
        if estado.tempo_restante == 0.0 and estado.observacoes < 3:
            return f"Validando identidade: {estado.observacoes}/3 observacoes.", AMARELO
        return (
            f"Validando identidade: {estado.observacoes}/3; "
            f"aguarde {estado.tempo_restante:.1f}s.",
            AMARELO,
        )

    @staticmethod
    def _pronto_para_registrar(
        reconhecido: Reconhecimento,
        estado: EstadoCapturaAutomatica,
        estado_temporal: EstadoTemporal | None,
    ) -> bool:
        return (
            estado.pronto
            and estado.chave == str(reconhecido.aluno.id)
            and (
                estado_temporal is None
                or (
                    estado_temporal.confirmado
                    and estado_temporal.aluno_id == reconhecido.aluno.id
                )
            )
        )

    def _reportar_falha_de_camera(self, erro: FalhaNaLeituraDaCamera) -> None:
        logger.error("Leitura da camera falhou: %s", erro)
        self._escrever(f"ERRO: {para_operador(erro)}")
