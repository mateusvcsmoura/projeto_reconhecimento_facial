"""Contratos de sessão/tentativa web sem banco ou dados biométricos."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from uuid import uuid4

import pytest

from src.application.services.fila_facial import (
    EstadoJobFacial,
    JobFacial,
    ReservaFacial,
    TipoJobFacial,
)
from src.application.use_cases.gerenciar_links import AcessoLinkEmitido
from src.application.use_cases.gerenciar_sessoes import GerenciarSessoes
from src.application.use_cases.iniciar_tentativa_presenca import IniciarTentativa
from src.application.use_cases.receber_captura_presenca import ReceberCaptura
from src.application.use_cases.verificar_presenca_web import ConcluirPresenca
from src.domain.entities.sessao_presenca import SessaoPresenca
from src.domain.entities.tentativa_presenca import (
    EstadoTentativaPresenca,
    ResultadoPresencaPersistida,
    TentativaPresenca,
    calcular_prazo_tentativa,
)
from src.domain.services.autorizacao import AtorWeb
from src.domain.services.desafio_captura import (
    Desafio,
    DirecaoMovimento,
    EstadoDesafio,
    OrientacaoPose,
    ResultadoEtapaDesafio,
)
from src.domain.services.face_recognition import ResultadoFacial

UTC = dt.UTC
AGORA = dt.datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


class RepositorioSessoesFake:
    def __init__(self) -> None:
        self.criada: SessaoPresenca | None = None
        self.revogada: tuple[AtorWeb, int, dt.datetime] | None = None

    def criar_sessao(self, ator: AtorWeb, sessao: SessaoPresenca) -> SessaoPresenca:
        assert ator.ativa
        self.criada = sessao
        return replace(sessao, id=41)

    def revogar_sessao(
        self, ator: AtorWeb, sessao_id: int, *, agora: dt.datetime
    ) -> tuple[int, tuple[object, ...]]:
        self.revogada = (ator, sessao_id, agora)
        return 1, ()


class RepositorioConclusaoFake:
    def __init__(self, persisted: bool = True) -> None:
        self.persisted = persisted
        self.chamadas: list[tuple[object, ResultadoFacial, dt.datetime]] = []

    def concluir_presenca(
        self, job: JobFacial, decisao: ResultadoFacial, *, agora: dt.datetime
    ) -> ResultadoPresencaPersistida | None:
        self.chamadas.append((job, decisao, agora))
        return ResultadoPresencaPersistida(5, False) if self.persisted else None


class FilaTentativaFake:
    def __init__(self) -> None:
        self.reservada: tuple[object, ...] | None = None
        self.canceladas: list[tuple[object, ...]] = []
        self.submetidos: list[tuple[object, ...]] = []

    def reservar(self, tipo, dono, chave, prazo):
        self.reservada = (tipo, dono, chave, prazo)
        return ReservaFacial(uuid4(), "credencial-sintetica", prazo)

    def cancelar(self, job_id, credencial):
        self.canceladas.append((job_id, credencial))
        return True

    def submeter(self, job_id, manifesto):
        self.submetidos.append((job_id, manifesto))
        return None


class RepositorioInicioFake:
    def __init__(
        self, *, repetida: bool = False, erro: Exception | None = None
    ) -> None:
        self.repetida = repetida
        self.erro = erro
        self.kwargs: dict[str, object] | None = None
        self.rejeitadas: list[object] = []
        self.sessao = SessaoPresenca.nova(
            turma_id=2,
            criada_por_conta_id=10,
            titulo="Aula",
            inicio_em=AGORA,
            fim_em=AGORA + dt.timedelta(minutes=5),
            criada_em=AGORA - dt.timedelta(minutes=1),
        )

    def consultar_contexto_inicio(self, **kwargs):
        assert kwargs["matricula"] == "00042"
        return {
            "sessao": self.sessao,
            "aluno_id": 12,
            "conjunto_id": 14,
            "versao_referencia": 3,
        }

    def reservar_tentativa(self, **kwargs):
        self.kwargs = kwargs
        if self.erro is not None:
            raise self.erro
        tentativa = TentativaPresenca(
            id=kwargs["job_id"],
            sessao_id=7,
            turma_id=2,
            aluno_id=12,
            ordinal=1,
            estado=EstadoTentativaPresenca.INICIADA,
            iniciada_em=AGORA,
            prazo_envio=kwargs["prazo_envio"],
            versao_sessao=1,
            conjunto_id=14,
            versao_referencia=3,
        )
        return tentativa, self.repetida

    def rejeitar_tentativa(self, tentativa_id, motivo, *, agora):
        self.rejeitadas.append((tentativa_id, motivo, agora))


class DesafiosFake:
    def __init__(self, resultado: ResultadoEtapaDesafio | None = None) -> None:
        self.emitidos: list[tuple[object, dt.datetime]] = []
        self.registrados: list[tuple[object, ...]] = []
        self.resultado = resultado or ResultadoEtapaDesafio(
            id=uuid4(),
            estado=EstadoDesafio.ETAPA_RECEBIDA,
            etapa_validada=0,
            proxima_etapa=None,
            proxima_orientacao=None,
            desafio_ok=False,
            motivo_tecnico=None,
        )

    def emitir(self, contexto, agora):
        self.emitidos.append((contexto, agora))
        return Desafio(
            id=contexto.job_id,
            nonce="n" * 64,
            direcao=DirecaoMovimento.DIREITA,
            primeira_orientacao=OrientacaoPose.FRENTE,
            expira_em=contexto.prazo_recebimento,
            proxima_etapa=1,
        )

    def registrar_etapa_recebida(self, job_id, nonce, etapa, agora):
        self.registrados.append((job_id, nonce, etapa, agora))
        return self.resultado


class RepositorioRecebimentoFake:
    def __init__(self, *, nova: bool = True, erro: Exception | None = None) -> None:
        self.nova = nova
        self.erro = erro
        self.capturas: list[dict[str, object]] = []
        self.rejeitadas: list[tuple[object, ...]] = []
        self.tentativa = TentativaPresenca(
            id=uuid4(),
            sessao_id=7,
            turma_id=2,
            aluno_id=12,
            ordinal=1,
            estado=EstadoTentativaPresenca.INICIADA,
            iniciada_em=AGORA,
            prazo_envio=AGORA + dt.timedelta(seconds=120),
            versao_sessao=1,
            conjunto_id=14,
            versao_referencia=3,
        )

    def consultar_tentativa(self, tentativa_id, credencial_hash):
        if tentativa_id != self.tentativa.id:
            return None
        return {"tentativa": self.tentativa, "recebimentos": 0}

    def registrar_captura(self, **kwargs):
        self.capturas.append(kwargs)
        if self.erro is not None:
            raise self.erro
        return self.nova

    def rejeitar_tentativa(self, tentativa_id, motivo, *, agora):
        self.rejeitadas.append((tentativa_id, motivo, agora))


class ArmazenamentoFake:
    def __init__(self) -> None:
        self.salvas: list[tuple[object, ...]] = []

    def salvar_captura(self, job_id, ordinal, conteudo):
        self.salvas.append((job_id, ordinal, conteudo))

    def manifesto(self, job_id):
        return (job_id, "manifesto")


def _ator() -> AtorWeb:
    return AtorWeb(10, "professor", True, False, 3)


def test_sessao_normaliza_titulo_e_preserva_instantes_utc() -> None:
    sessao = SessaoPresenca.nova(
        turma_id=2,
        criada_por_conta_id=10,
        titulo="  Aula   de IA ",
        inicio_em=AGORA,
        fim_em=AGORA + dt.timedelta(hours=1),
        criada_em=AGORA,
    )

    assert sessao.titulo == "Aula de IA"
    assert sessao.inicio_em == AGORA
    assert sessao.fim_em == AGORA + dt.timedelta(hours=1)


@pytest.mark.parametrize(
    "inicio,fim",
    [
        (AGORA.replace(tzinfo=None), AGORA + dt.timedelta(hours=1)),
        (AGORA, AGORA.replace(tzinfo=None)),
        (AGORA, AGORA),
    ],
)
def test_sessao_rejeita_intervalo_sem_fuso_ou_nao_positivo(
    inicio: dt.datetime, fim: dt.datetime
) -> None:
    with pytest.raises(ValueError):
        SessaoPresenca.nova(
            turma_id=2,
            criada_por_conta_id=10,
            titulo="Aula",
            inicio_em=inicio,
            fim_em=fim,
            criada_em=AGORA,
        )


def test_gerenciar_sessoes_passa_ator_e_instantes_normalizados_ao_repository() -> None:
    repositorio = RepositorioSessoesFake()
    caso = GerenciarSessoes(repositorio, relogio=lambda: AGORA)

    sessao = caso.criar(
        _ator(),
        turma_id=2,
        inicio_em=AGORA + dt.timedelta(minutes=5),
        fim_em=AGORA + dt.timedelta(hours=1),
        titulo="Aula de IA",
    )

    assert sessao.id == 41
    assert repositorio.criada is not None
    assert repositorio.criada.criada_por_conta_id == 10


def test_criar_sessao_rejeita_fim_anterior_antes_de_acessar_repository() -> None:
    repositorio = RepositorioSessoesFake()
    caso = GerenciarSessoes(repositorio, relogio=lambda: AGORA)

    with pytest.raises(ValueError):
        caso.criar(
            _ator(),
            turma_id=2,
            inicio_em=AGORA + dt.timedelta(hours=1),
            fim_em=AGORA,
            titulo="Aula",
        )

    assert repositorio.criada is None


def test_janela_aceita_inicio_exato_e_nao_inicio_no_fim() -> None:
    sessao = SessaoPresenca.nova(
        turma_id=2,
        criada_por_conta_id=10,
        titulo="Aula",
        inicio_em=AGORA,
        fim_em=AGORA + dt.timedelta(seconds=60),
        criada_em=AGORA - dt.timedelta(minutes=1),
    )

    prazo = calcular_prazo_tentativa(sessao, AGORA)
    assert prazo == AGORA + dt.timedelta(seconds=120)
    with pytest.raises(ValueError):
        calcular_prazo_tentativa(sessao, sessao.fim_em)


def test_prazo_da_tentativa_tem_teto_de_fim_mais_120_segundos() -> None:
    sessao = SessaoPresenca.nova(
        turma_id=2,
        criada_por_conta_id=10,
        titulo="Aula",
        inicio_em=AGORA - dt.timedelta(minutes=2),
        fim_em=AGORA + dt.timedelta(seconds=30),
        criada_em=AGORA - dt.timedelta(minutes=3),
    )

    prazo = calcular_prazo_tentativa(sessao, AGORA)
    assert prazo == AGORA + dt.timedelta(seconds=120)
    assert prazo <= sessao.fim_em + dt.timedelta(seconds=120)


def test_conclusao_so_pede_persistencia_apos_verificacao_completa() -> None:
    repositorio = RepositorioConclusaoFake()
    caso = ConcluirPresenca(repositorio)
    job_id = uuid4()
    job = JobFacial(
        id=job_id,
        dono_id="presenca:2:3",
        tipo=TipoJobFacial.PRESENCA,
        estado=EstadoJobFacial.PROCESSANDO,
        criada_em=AGORA,
        prazo=AGORA + dt.timedelta(minutes=2),
        prazo_execucao=AGORA + dt.timedelta(minutes=10),
        atualizada_em=AGORA,
        manifesto=None,
        lease="lease-sintetico",
        lease_expira_em=AGORA + dt.timedelta(minutes=1),
        resultado_codigo=None,
        credencial_hash="a" * 64,
    )
    decisao = ResultadoFacial(
        identidade_ok=True,
        desafio_ok=True,
        antispoofing_ok=True,
        qualidade_ok=True,
        motivo_tecnico=None,
        versao_referencia=1,
        politica="mediana-3",
    )

    resultado = caso.executar(job, decisao, agora=AGORA)

    assert resultado.presenca_id == 5
    assert repositorio.chamadas == [(job, decisao, AGORA)]


def test_conclusao_recusa_decisao_incompleta_sem_persistir() -> None:
    repositorio = RepositorioConclusaoFake()
    caso = ConcluirPresenca(repositorio)
    decisao = ResultadoFacial(
        identidade_ok=True,
        desafio_ok=False,
        antispoofing_ok=True,
        qualidade_ok=True,
        motivo_tecnico="movimento_nao_confirmado",
        versao_referencia=1,
        politica="mediana-3",
    )

    with pytest.raises(ValueError):
        job = JobFacial(
            id=uuid4(),
            dono_id="presenca:2:3",
            tipo=TipoJobFacial.PRESENCA,
            estado=EstadoJobFacial.PROCESSANDO,
            criada_em=AGORA,
            prazo=AGORA + dt.timedelta(minutes=2),
            prazo_execucao=AGORA + dt.timedelta(minutes=10),
            atualizada_em=AGORA,
            manifesto=None,
            lease="lease-sintetico",
            lease_expira_em=AGORA + dt.timedelta(minutes=1),
            resultado_codigo=None,
            credencial_hash="a" * 64,
        )
        caso.executar(job, decisao, agora=AGORA)

    assert repositorio.chamadas == []


def test_iniciar_tentativa_preserva_matricula_e_hash_da_chave_idempotente() -> None:
    repositorio = RepositorioInicioFake()
    fila = FilaTentativaFake()
    desafios = DesafiosFake()
    acesso = AcessoLinkEmitido(
        "token-do-link",
        uuid4(),
        2,
        "presenca",
        AGORA + dt.timedelta(hours=1),
        AGORA + dt.timedelta(hours=1),
        sessao_id=7,
    )

    resultado = IniciarTentativa(repositorio, fila, desafios).executar(
        acesso, "00042", "chave-idempotente-0001", agora=AGORA
    )

    assert resultado.tentativa.ordinal == 1
    assert resultado.credencial_captura == "credencial-sintetica"
    assert resultado.desafio is not None
    assert repositorio.kwargs is not None
    assert repositorio.kwargs["idempotencia_hash"] != "chave-idempotente-0001"
    assert fila.reservada is not None
    assert fila.reservada[1] == "presenca:7:12"
    assert fila.reservada[3] == AGORA + dt.timedelta(seconds=120)


def test_iniciar_tentativa_repetida_nao_emite_novo_desafio() -> None:
    repositorio = RepositorioInicioFake(repetida=True)
    desafios = DesafiosFake()
    acesso = AcessoLinkEmitido(
        "token-do-link",
        uuid4(),
        2,
        "presenca",
        AGORA + dt.timedelta(hours=1),
        AGORA + dt.timedelta(hours=1),
        sessao_id=7,
    )

    resultado = IniciarTentativa(repositorio, FilaTentativaFake(), desafios).executar(
        acesso, "00042", "chave-idempotente-0001", agora=AGORA
    )

    assert resultado.desafio is None
    assert desafios.emitidos == []


def test_inicio_sem_vaga_na_fila_nao_chama_reserva_de_quota() -> None:
    repositorio = RepositorioInicioFake(erro=RuntimeError("quota fake"))
    fila = FilaTentativaFake()
    acesso = AcessoLinkEmitido(
        "token-do-link",
        uuid4(),
        2,
        "presenca",
        AGORA + dt.timedelta(hours=1),
        AGORA + dt.timedelta(hours=1),
        sessao_id=7,
    )

    with pytest.raises(RuntimeError, match="quota fake"):
        IniciarTentativa(repositorio, fila, DesafiosFake()).executar(
            acesso, "00042", "chave-idempotente-0001", agora=AGORA
        )

    assert fila.canceladas


def test_captura_recebida_no_instante_limite_e_enviada_uma_vez() -> None:
    repositorio = RepositorioRecebimentoFake()
    fila = FilaTentativaFake()
    storage = ArmazenamentoFake()
    instante_limite = repositorio.tentativa.prazo_envio

    resultado = ReceberCaptura(
        repositorio, DesafiosFake(), fila, storage, max_bytes=1024
    ).executar(
        repositorio.tentativa.id,
        "credencial",
        nonce="n" * 64,
        etapa=1,
        conteudo=b"frame sintetico",
        recebida_em_servidor=instante_limite,
    )

    assert resultado.repetida is False
    assert len(storage.salvas) == 1
    assert len(fila.submetidos) == 1
    assert repositorio.capturas[0]["recebida_em"] == instante_limite


def test_reenvio_igual_e_idempotente_sem_gravar_frame_duas_vezes() -> None:
    repositorio = RepositorioRecebimentoFake(nova=False)
    desafio = DesafiosFake(
        ResultadoEtapaDesafio(
            id=repositorio.tentativa.id,
            estado=EstadoDesafio.AGUARDANDO_ETAPA,
            etapa_validada=1,
            proxima_etapa=2,
            proxima_orientacao=OrientacaoPose.DIREITA,
            desafio_ok=False,
            motivo_tecnico=None,
            recebimento_repetido=True,
        )
    )
    storage = ArmazenamentoFake()
    fila = FilaTentativaFake()

    resultado = ReceberCaptura(
        repositorio, desafio, fila, storage, max_bytes=1024
    ).executar(
        repositorio.tentativa.id,
        "credencial",
        nonce="n" * 64,
        etapa=1,
        conteudo=b"frame sintetico",
        recebida_em_servidor=AGORA + dt.timedelta(seconds=30),
    )

    assert resultado.repetida is True
    assert storage.salvas == []
    assert fila.submetidos == []


def test_captura_um_milisegundo_depois_do_limite_e_recusada() -> None:
    repositorio = RepositorioRecebimentoFake()
    desafios = DesafiosFake()
    fila = FilaTentativaFake()

    with pytest.raises(TimeoutError):
        ReceberCaptura(
            repositorio, desafios, fila, ArmazenamentoFake(), max_bytes=1024
        ).executar(
            repositorio.tentativa.id,
            "credencial",
            nonce="n" * 64,
            etapa=1,
            conteudo=b"frame sintetico",
            recebida_em_servidor=repositorio.tentativa.prazo_envio
            + dt.timedelta(milliseconds=1),
        )

    assert desafios.registrados == []
    assert repositorio.rejeitadas
