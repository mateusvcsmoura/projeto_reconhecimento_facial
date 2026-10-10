"""Etapa 0 -- confiabilidade do script de avaliacao.

Uma imagem descartada em silencio encolhe a amostra sem aviso, e um erro de
programacao contado como "imagem ruim" vira estatistica (lacuna G5). Estes
testes fixam que toda falha e contada e classificada, que o inesperado
aborta, e que sem dados suficientes nenhum numero e impresso.

Sem DeepFace, sem OpenCV, sem banco: o adaptador e o decodificador sao
dubles, e as "imagens" sao bytes sinteticos em tmp_path.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

import scripts.evaluate_model as ev
from scripts.divisao_por_identidade import _pares
from src.domain.entities.face_embedding import EmbeddingInvalido, FaceEmbedding
from src.domain.errors import (
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
    PossivelFraude,
)

MODELO = "Facenet512"
ADAPTADOR = "src.infrastructure.face_recognition.deepface_adapter"


def _dataset(raiz: Path, pessoas: int, imagens: int) -> Path:
    for i in range(pessoas):
        pasta = raiz / f"pessoa-{i}"
        pasta.mkdir()
        for j in range(imagens):
            (pasta / f"foto-{j}.jpg").write_bytes(f"img-{j}".encode())
    return raiz


def _embedding(caminho: Path) -> FaceEmbedding:
    """Vetor sintetico: proximo dentro da pessoa, distante entre pessoas."""
    pessoa = int(caminho.parent.name.split("-")[1])
    variacao = int(caminho.stem.split("-")[1])
    valores = [0.0] * 16
    valores[pessoa] = 1.0
    valores[15] = 0.05 * variacao
    return FaceEmbedding.de_valores(valores, MODELO)


# -- inventario -----------------------------------------------------------


def test_inventario_conta_imagens_e_separa_o_que_ignora(tmp_path: Path) -> None:
    (tmp_path / "ana").mkdir()
    (tmp_path / "ana" / "a.jpg").write_bytes(b"x")
    (tmp_path / "ana" / "b.JPEG").write_bytes(b"x")
    (tmp_path / "ana" / "notas.txt").write_text("x")
    (tmp_path / "bia").mkdir()
    (tmp_path / "solto.png").write_bytes(b"x")

    inventario = ev.inventariar(tmp_path)

    nomes = [p.name for p in inventario.imagens_por_pessoa["ana"]]
    assert nomes == ["a.jpg", "b.JPEG"]
    assert inventario.imagens_por_pessoa["bia"] == []
    assert inventario.total_de_imagens == 2
    assert sorted(p.name for p in inventario.ignorados) == ["notas.txt", "solto.png"]


# -- extracao -------------------------------------------------------------

ERROS_POR_ARQUIVO: dict[str, Exception] = {
    "sem-rosto.jpg": NenhumRostoDetectado("nada"),
    "dois.jpg": MultiplosRostosDetectados(2),
    "modelo.jpg": ModeloIndisponivel("tensorflow quebrado"),
    "foto-de-foto.jpg": PossivelFraude(0.97),
    "nan.jpg": EmbeddingInvalido("NaN"),
    "corrompida.jpg": ev.ImagemIlegivel("formato nao decodificavel"),
    "sumiu.jpg": FileNotFoundError("sumiu.jpg"),
}


def _gerar_ou_falhar(caminho: Path) -> FaceEmbedding:
    erro = ERROS_POR_ARQUIVO.get(caminho.name)
    if erro is not None:
        raise erro
    return _embedding(caminho)


def test_extracao_conta_e_classifica_cada_falha_conhecida() -> None:
    boas = [Path("pessoa-0/foto-0.jpg"), Path("pessoa-0/foto-1.jpg")]
    ruins = [Path(f"pessoa-1/{nome}") for nome in ERROS_POR_ARQUIVO]

    por_pessoa, resumo = ev.extrair_embeddings(
        {"pessoa-0": boas, "pessoa-1": ruins}, lambda p: p, _gerar_ou_falhar
    )

    assert resumo.recebidas == 9
    assert resumo.processadas == 2
    assert len(resumo.falhas) == 7
    assert resumo.por_motivo() == {
        ev.Motivo.SEM_ROSTO: 1,
        ev.Motivo.MULTIPLOS_ROSTOS: 1,
        ev.Motivo.FALHA_DE_INFERENCIA: 1,
        ev.Motivo.PROVA_DE_VIDA: 1,
        ev.Motivo.EMBEDDING_INVALIDO: 1,
        ev.Motivo.ERRO_DE_LEITURA: 2,
    }
    # Pessoa sem nenhum embedding valido nao entra na avaliacao.
    assert list(por_pessoa) == ["pessoa-0"]


def test_falha_preserva_arquivo_e_detalhe_para_diagnostico() -> None:
    _, resumo = ev.extrair_embeddings(
        {"pessoa-1": [Path("pessoa-1/modelo.jpg")]}, lambda p: p, _gerar_ou_falhar
    )
    falha = resumo.falhas[0]
    assert falha.imagem == Path("pessoa-1/modelo.jpg")
    assert falha.motivo is ev.Motivo.FALHA_DE_INFERENCIA
    assert "tensorflow quebrado" in falha.detalhe


def test_erro_de_leitura_e_contado_sem_chamar_o_modelo() -> None:
    chamadas: list[Any] = []

    def ler(_caminho: Path) -> Any:
        raise ev.ImagemIlegivel("arquivo vazio")

    def gerar(imagem: Any) -> FaceEmbedding:
        chamadas.append(imagem)
        raise AssertionError("o modelo nao deveria ser chamado")

    _, resumo = ev.extrair_embeddings(
        {"pessoa-0": [Path("pessoa-0/vazia.jpg")]}, ler, gerar
    )
    assert resumo.por_motivo() == {ev.Motivo.ERRO_DE_LEITURA: 1}
    assert chamadas == []


def test_excecao_inesperada_aborta_e_diz_qual_imagem() -> None:
    """Defeito de programacao nao pode virar 'imagem rejeitada'."""

    def gerar(_imagem: Any) -> FaceEmbedding:
        raise KeyError("bug")

    with pytest.raises(KeyError) as erro:
        ev.extrair_embeddings(
            {"pessoa-0": [Path("pessoa-0/foto-0.jpg")]}, lambda p: p, gerar
        )
    assert any("pessoa-0" in nota for nota in erro.value.__notes__)


# -- leitura da imagem ----------------------------------------------------


@pytest.fixture
def cv2_duble(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    duble = types.SimpleNamespace(IMREAD_COLOR=1, resultado=None)
    duble.imdecode = lambda _dados, _flag: duble.resultado
    monkeypatch.setitem(sys.modules, "cv2", duble)
    return duble


def test_arquivo_vazio_e_ilegivel(tmp_path: Path) -> None:
    vazio = tmp_path / "vazio.jpg"
    vazio.write_bytes(b"")
    with pytest.raises(ev.ImagemIlegivel, match="vazio"):
        ev.ler_imagem(vazio)


def test_arquivo_inexistente_e_erro_de_leitura(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        ev.ler_imagem(tmp_path / "nao-existe.jpg")


def test_formato_nao_decodificavel_e_ilegivel(
    tmp_path: Path, cv2_duble: types.SimpleNamespace
) -> None:
    arquivo = tmp_path / "lixo.jpg"
    arquivo.write_bytes(b"nao e jpeg")
    with pytest.raises(ev.ImagemIlegivel, match="decodificavel"):
        ev.ler_imagem(arquivo)


def test_caminho_com_acento_e_lido(
    tmp_path: Path, cv2_duble: types.SimpleNamespace
) -> None:
    """O DeepFace recusa caminho nao-ASCII; a leitura propria nao."""
    pasta = tmp_path / "José"
    pasta.mkdir()
    arquivo = pasta / "foto.jpg"
    arquivo.write_bytes(b"bytes")
    cv2_duble.resultado = "matriz-bgr"
    assert ev.ler_imagem(arquivo) == "matriz-bgr"


# -- compatibilidade ------------------------------------------------------


def test_montar_pares_bate_com_a_contagem_da_divisao() -> None:
    por_pessoa = {
        f"pessoa-{i}": [
            _embedding(Path(f"pessoa-{i}/foto-{j}.jpg")) for j in range(k)
        ]
        for i, k in enumerate([1, 2, 3, 4])
    }
    genuinas, impostoras = ev.montar_pares(por_pessoa)
    assert (genuinas.size, impostoras.size) == _pares([1, 2, 3, 4])


# -- CLI: --validar-divisao -----------------------------------------------


@pytest.fixture
def sem_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """O modo estrutural nao pode depender de banco nem de .env."""

    def proibido() -> None:
        raise AssertionError("--validar-divisao nao deveria ler as settings")

    monkeypatch.setattr(ev, "get_settings", proibido)


def test_validar_divisao_reporta_contagens_sem_metricas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], sem_settings: None
) -> None:
    dataset = _dataset(tmp_path, pessoas=10, imagens=3)
    argv = ["--dataset", str(dataset), "--validar-divisao", "--seed", "5"]

    assert ev.main(argv) == 0

    saida = capsys.readouterr().out
    assert "seed 5" in saida
    assert "nenhuma (verificada)" in saida
    assert "Assinatura da divisao" in saida
    assert "FAR" not in saida
    assert "AUC" not in saida


def test_validar_divisao_e_reprodutivel(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], sem_settings: None
) -> None:
    dataset = _dataset(tmp_path, pessoas=10, imagens=2)
    argv = ["--dataset", str(dataset), "--validar-divisao", "--seed", "11"]

    ev.main(argv)
    primeira = capsys.readouterr().out
    ev.main(argv)
    assert capsys.readouterr().out == primeira


def test_validar_divisao_com_dados_insuficientes_nao_imprime_resultado(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], sem_settings: None
) -> None:
    dataset = _dataset(tmp_path, pessoas=5, imagens=3)

    assert ev.main(["--dataset", str(dataset), "--validar-divisao"]) == 2

    capturado = capsys.readouterr()
    assert "dados insuficientes" in capturado.err
    assert "Assinatura" not in capturado.out


def test_validar_divisao_sem_pares_genuinos_e_recusada(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], sem_settings: None
) -> None:
    """Uma imagem por pessoa: ha impostores, mas FRR nao teria denominador."""
    dataset = _dataset(tmp_path, pessoas=10, imagens=1)
    assert ev.main(["--dataset", str(dataset), "--validar-divisao"]) == 2
    assert "nenhum par genuino" in capsys.readouterr().err


def test_seed_sem_validar_divisao_e_erro_de_uso(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as saida:
        ev.main(["--dataset", str(tmp_path), "--seed", "3"])
    assert saida.value.code == 2


# -- CLI: modo exploratorio (Avaliacao A) ---------------------------------


class AdaptadorFalso:
    erro_ao_carregar: Exception | None = None

    def __init__(
        self, modelo: str, detector: str, anti_spoofing: bool = True
    ) -> None:
        # Avaliacao A: reconhecimento sem prova de vida, sempre.
        assert anti_spoofing is False

    def preaquecer(self) -> None:
        if self.erro_ao_carregar is not None:
            raise self.erro_ao_carregar

    def gerar_embedding(self, imagem: Any) -> FaceEmbedding:
        if imagem.read_bytes() == b"sem-rosto":
            raise NenhumRostoDetectado("nada")
        return _embedding(imagem)


@pytest.fixture
def exploratorio(monkeypatch: pytest.MonkeyPatch) -> type[AdaptadorFalso]:
    modulo = types.ModuleType(ADAPTADOR)
    modulo.DeepFaceAdapter = AdaptadorFalso  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, ADAPTADOR, modulo)
    monkeypatch.setattr(ev, "ler_imagem", lambda caminho: caminho)
    monkeypatch.setattr(ev, "configurar_logging", lambda _nivel: None)
    monkeypatch.setattr(
        ev,
        "get_settings",
        lambda: types.SimpleNamespace(
            face_model=MODELO, face_detector="opencv", face_threshold=0.30
        ),
    )
    monkeypatch.setattr(AdaptadorFalso, "erro_ao_carregar", None)
    return AdaptadorFalso


def test_exploratorio_avisa_amostra_menor_e_vies(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    exploratorio: type[AdaptadorFalso],
) -> None:
    dataset = _dataset(tmp_path, pessoas=3, imagens=3)
    (dataset / "pessoa-0" / "foto-2.jpg").write_bytes(b"sem-rosto")

    assert ev.main(["--dataset", str(dataset)]) == 0

    saida = capsys.readouterr().out
    assert "Avaliacao A" in saida
    assert "Imagens recebidas : 9" in saida
    assert "Processadas       : 8" in saida
    assert "sem rosto detectado" in saida
    assert "menor que a recebida (9)" in saida
    assert "MODO EXPLORATORIO" in saida
    assert "AUC:" in saida


def test_exploratorio_sem_dados_suficientes_nao_imprime_metricas(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    exploratorio: type[AdaptadorFalso],
) -> None:
    """Todas as imagens de uma das duas pessoas falham: sobra 1 pessoa."""
    dataset = _dataset(tmp_path, pessoas=2, imagens=2)
    for foto in (dataset / "pessoa-1").iterdir():
        foto.write_bytes(b"sem-rosto")

    assert ev.main(["--dataset", str(dataset)]) == 2

    capturado = capsys.readouterr()
    assert "ao menos 2 pessoas" in capturado.err
    assert "AUC" not in capturado.out
    assert "FAR" not in capturado.out


def test_exploratorio_sem_pares_genuinos_nao_imprime_metricas(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    exploratorio: type[AdaptadorFalso],
) -> None:
    dataset = _dataset(tmp_path, pessoas=3, imagens=1)
    assert ev.main(["--dataset", str(dataset)]) == 2
    assert "AUC" not in capsys.readouterr().out


def test_exploratorio_modelo_que_nao_carrega_aborta(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    exploratorio: type[AdaptadorFalso],
) -> None:
    exploratorio.erro_ao_carregar = ModeloIndisponivel("pesos ausentes")
    dataset = _dataset(tmp_path, pessoas=3, imagens=2)

    assert ev.main(["--dataset", str(dataset)]) == 2
    assert "pesos ausentes" in capsys.readouterr().err
