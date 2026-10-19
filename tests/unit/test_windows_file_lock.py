from __future__ import annotations

from types import SimpleNamespace

from src.infrastructure.workers.windows_file_lock import alterar_lock_windows


def test_lock_windows_chama_msvcrt_para_adquirir_e_liberar(monkeypatch) -> None:
    chamadas: list[tuple[int, int, int]] = []
    msvcrt_fake = SimpleNamespace(
        LK_NBLCK=1,
        LK_UNLCK=2,
        locking=lambda fd, modo, tamanho: chamadas.append((fd, modo, tamanho)),
    )
    monkeypatch.setattr(
        "src.infrastructure.workers.windows_file_lock.importlib.import_module",
        lambda nome: msvcrt_fake if nome == "msvcrt" else None,
    )

    alterar_lock_windows(12, adquirir=True)
    alterar_lock_windows(12, adquirir=False)

    assert chamadas == [(12, 1, 1), (12, 2, 1)]
