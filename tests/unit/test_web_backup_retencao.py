from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

try:
    import src.application.services.web_backup as backup
except ModuleNotFoundError:
    backup = None  # type: ignore[assignment]
try:
    import src.infrastructure.workers.maintenance_gate as maintenance
except ModuleNotFoundError:
    maintenance = None  # type: ignore[assignment]
try:
    import src.infrastructure.backup.rclone as rclone_backup
except ModuleNotFoundError:
    rclone_backup = None  # type: ignore[assignment]
try:
    import src.infrastructure.backup.exclusions as exclusions
    import src.infrastructure.backup.postgres as postgres_backup
    import src.infrastructure.backup.postgres_restore as postgres_restore
    import src.infrastructure.backup.retention as retention
except ModuleNotFoundError:
    exclusions = None  # type: ignore[assignment]
    postgres_backup = None  # type: ignore[assignment]
    postgres_restore = None  # type: ignore[assignment]
    retention = None  # type: ignore[assignment]


AGORA = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


@dataclass
class RuntimeFalso:
    eventos: list[str]
    falhar_criptografia: bool = False
    arquivo_staging: Path | None = None
    geracoes_completas: set[str] | None = None

    @contextmanager
    def lock_backup(self) -> Iterator[None]:
        self.eventos.append("lock")
        yield

    def solicitar_manutencao(self) -> None:
        self.eventos.append("manutencao:on")

    def aguardar_jobs_ociosos(self, timeout_seconds: float) -> None:
        self.eventos.append("jobs:ociosos")

    @contextmanager
    def lock_snapshot(self, timeout_seconds: float) -> Iterator[None]:
        self.eventos.append("snapshot:lock")
        yield

    def criar_staging(self, generation_id: str) -> Path:
        assert self.arquivo_staging is not None
        self.eventos.append("staging:create")
        return self.arquivo_staging

    def criar_snapshot(
        self,
        staging: Path,
        generation_id: str,
        agora: datetime,
        modo: str,
    ) -> backup.ManifestoBackup:
        self.eventos.append("snapshot:create")
        return backup.ManifestoBackup(
            geracao=generation_id,
            criado_em=agora,
            modo=modo,
            versao_aplicacao="abc1234",
            revisao_schema="0011",
            arquivos=(),
        )

    def limpar_staging(self, staging: Path) -> None:
        self.eventos.append("staging:remove")
        staging.unlink(missing_ok=True)

    def liberar_manutencao(self) -> None:
        self.eventos.append("manutencao:off")


class CriptografiaFalsa:
    def __init__(self, runtime: RuntimeFalso) -> None:
        self.runtime = runtime

    def cifrar(self, staging: Path, destino: str, geracao: str) -> None:
        self.runtime.eventos.append("encrypt")
        if self.runtime.falhar_criptografia:
            raise RuntimeError("falha sintetica de cifra")

    def verificar(self, staging: Path, destino: str, geracao: str) -> None:
        self.runtime.eventos.append("cryptcheck")

    def descartar_incompleta(self, destino: str, geracao: str) -> None:
        self.runtime.eventos.append("discard-incomplete")

    def marcar_completa(self, destino: str, manifesto: backup.ManifestoBackup) -> None:
        self.runtime.eventos.append("complete")


def test_gerar_backup_pausa_escritas_espera_worker_e_liberar_staging(
    tmp_path: Path,
) -> None:
    assert backup is not None, "módulo de backup ainda não implementado"
    staging = tmp_path / "staging.tar"
    staging.write_bytes(b"plaintext")
    runtime = RuntimeFalso(eventos=[], arquivo_staging=staging)
    service = backup.GerarBackup(runtime, CriptografiaFalsa(runtime))

    result = service.executar(
        destino_local="local-crypt:backups",
        agora=AGORA,
        modo="manual_pre_apresentacao",
    )

    assert result.revisao_schema == "0011"
    assert (
        runtime.eventos.index("manutencao:on")
        < runtime.eventos.index("jobs:ociosos")
        < runtime.eventos.index("snapshot:lock")
    )
    assert runtime.eventos.index("cryptcheck") < runtime.eventos.index("complete")
    assert runtime.eventos.index("staging:remove") < runtime.eventos.index("complete")
    assert runtime.eventos[-1] == "manutencao:off"
    assert not staging.exists()


def test_falha_de_cifra_nao_marca_geracao_completa_e_limpa_staging(
    tmp_path: Path,
) -> None:
    assert backup is not None, "módulo de backup ainda não implementado"
    staging = tmp_path / "staging.tar"
    staging.write_bytes(b"plaintext")
    runtime = RuntimeFalso(
        eventos=[], falhar_criptografia=True, arquivo_staging=staging
    )
    service = backup.GerarBackup(runtime, CriptografiaFalsa(runtime))

    with pytest.raises(RuntimeError, match="falha sintetica"):
        service.executar(
            destino_local="local-crypt:backups", agora=AGORA, modo="diario"
        )

    assert "complete" not in runtime.eventos
    assert "discard-incomplete" in runtime.eventos
    assert runtime.eventos[-2:] == ["staging:remove", "manutencao:off"]
    assert not staging.exists()


class RestoreFalso:
    def __init__(self, *, chave: bool = True) -> None:
        self.chave = chave
        self.eventos: list[str] = []
        self.staging = Path("restore-staging")

    def validar_alvo_descartavel(
        self, banco: str, autorizacao: backup.AutorizacaoRestore
    ) -> None:
        self.eventos.append("target:validated")

    def descriptografar(self, geracao: str) -> Path:
        self.eventos.append("decrypt")
        if not self.chave:
            raise backup.ChaveBackupAusente("Chave do backup não configurada.")
        return self.staging

    def verificar_manifesto(self, staging: Path) -> backup.ManifestoBackup:
        self.eventos.append("manifest:verified")
        return backup.ManifestoBackup(
            geracao="gen-1",
            criado_em=AGORA,
            modo="diario",
            versao_aplicacao="abc1234",
            revisao_schema="0011",
            arquivos=(),
        )

    def restaurar_banco(self, staging: Path, banco: str) -> None:
        self.eventos.append("database:restored")

    def restaurar_referencias(self, staging: Path, banco: str) -> None:
        self.eventos.append("references:restored")

    def reaplicar_exclusoes(self, banco: str) -> int:
        self.eventos.append("exclusions:reapplied")
        return 2

    def invalidar_sessoes_e_tokens(self, banco: str) -> int:
        self.eventos.append("sessions:invalidated")
        return 3

    def validar_restore(self, banco: str, manifesto: backup.ManifestoBackup) -> None:
        self.eventos.append("restore:validated")

    def limpar_staging(self, staging: Path) -> None:
        self.eventos.append("staging:removed")


def test_restore_sintetico_reaplica_exclusoes_e_invalida_sessoes() -> None:
    assert backup is not None, "módulo de backup ainda não implementado"
    restore = RestoreFalso()
    service = backup.RestaurarEnsaio(restore)
    auth = backup.AutorizacaoRestore(
        banco="task017_restore_test",
        confirmacao="RESTAURAR-TASK017-task017_restore_test",
    )

    evidence = service.executar("gen-1", "task017_restore_test", auth)

    assert evidence.exclusoes_reaplicadas == 2
    assert evidence.sessoes_tokens_invalidos == 3
    assert restore.eventos.index("exclusions:reapplied") < restore.eventos.index(
        "restore:validated"
    )
    assert restore.eventos[-1] == "staging:removed"


def test_restore_sem_chave_falha_antes_de_tocar_o_banco() -> None:
    assert backup is not None, "módulo de backup ainda não implementado"
    restore = RestoreFalso(chave=False)
    service = backup.RestaurarEnsaio(restore)
    auth = backup.AutorizacaoRestore(
        banco="task017_restore_test",
        confirmacao="RESTAURAR-TASK017-task017_restore_test",
    )

    with pytest.raises(backup.ChaveBackupAusente, match="Chave do backup"):
        service.executar("gen-1", "task017_restore_test", auth)

    assert "database:restored" not in restore.eventos


class CatalogoExpurgoFalso:
    def __init__(self) -> None:
        self.aplicados: list[str] = []

    def planejar(
        self,
        agora: datetime,
        finalidade_ate: datetime,
        max_geracoes: int,
        retencao_logs: timedelta,
    ) -> tuple[str, ...]:
        if agora >= finalidade_ate:
            return ("all-backups", "all-logs", "web-data")
        return ("old-generation", "old-log")

    def aplicar(self, alvo: str) -> None:
        self.aplicados.append(alvo)


def test_expurgo_planeja_sem_apagar_e_apply_exige_confirmar_alvo() -> None:
    assert backup is not None, "módulo de backup ainda não implementado"
    catalogo = CatalogoExpurgoFalso()
    service = backup.ExpurgarWeb(
        catalogo,
        ambiente="development",
        alvo="local-dev",
        finalidade_ate=AGORA + timedelta(days=10),
    )

    plan = service.planejar(AGORA)

    assert isinstance(plan, backup.PlanoExpurgo)
    assert plan.alvos == ("old-generation", "old-log")
    assert catalogo.aplicados == []
    with pytest.raises(ValueError, match="confirmação"):
        service.aplicar(plan, confirmacao="")
    assert catalogo.aplicados == []

    service.aplicar(plan, confirmacao="APLICAR-EXPURGO-development-local-dev")

    assert catalogo.aplicados == ["old-generation", "old-log"]


def test_expurgo_no_fim_da_finalidade_planeja_limpeza_completa() -> None:
    assert backup is not None, "módulo de backup ainda não implementado"
    catalogo = CatalogoExpurgoFalso()
    service = backup.ExpurgarWeb(
        catalogo,
        ambiente="test",
        alvo="task017_test",
        finalidade_ate=AGORA,
    )

    plan = service.planejar(AGORA + timedelta(seconds=1))

    assert plan.finalidade_encerrada is True
    assert plan.alvos == ("all-backups", "all-logs", "web-data")


class TransportAdapterFalso:
    def __init__(self, falhar: bool = False) -> None:
        self.falhar = falhar
        self.completo = False

    def copiar_e_verificar(self, geracao: str) -> tuple[int, str]:
        if self.falhar:
            raise RuntimeError("upload interrompido")
        return 128, "a" * 64

    def marcar_completa(self, geracao: str, sha256: str) -> None:
        self.completo = True


@dataclass
class ArchiveFalso:
    existe: bool = True

    def exigir_geracao_completa(self, geracao: str) -> None:
        if not self.existe:
            raise ValueError("geração local incompleta")

    def iniciar_transporte(self, geracao: str, destino: str) -> None:
        return None

    def abortar_transporte(self, geracao: str, destino: str) -> None:
        return None

    def marcar_transporte_completo(
        self, geracao: str, destino: str, tamanho_bytes: int, sha256: str
    ) -> None:
        return None


def test_upload_falho_nao_marca_externa_como_completa() -> None:
    assert backup is not None, "módulo de backup ainda não implementado"
    adapter = TransportAdapterFalso(falhar=True)
    service = backup.TransportarBackup(ArchiveFalso())

    with pytest.raises(RuntimeError, match="interrompido"):
        service.executar("gen-1", adapter)

    assert not adapter.completo


def test_hash_externo_divergente_nao_marca_transporte_completo() -> None:
    assert backup is not None, "módulo de backup ainda não implementado"

    class AdapterHashInvalido(TransportAdapterFalso):
        def copiar_e_verificar(self, geracao: str) -> tuple[int, str]:
            return 128, "hash-invalido"

    adapter = AdapterHashInvalido()
    service = backup.TransportarBackup(ArchiveFalso())

    with pytest.raises(ValueError, match="hash"):
        service.executar("gen-1", adapter)

    assert not adapter.completo


def test_http_mutacao_recusada_enquanto_manutencao_esta_ativa(tmp_path: Path) -> None:
    assert maintenance is not None, "gate de manutenção ainda não implementado"
    gate = maintenance.ManutencaoWeb(tmp_path / "maintenance")

    gate.solicitar_manutencao()
    try:
        with pytest.raises(maintenance.ManutencaoAtiva), gate.mutacao_http():
            pytest.fail("a mutação HTTP não deveria iniciar")
    finally:
        gate.liberar_manutencao()


def test_worker_pode_esvaziar_fila_antes_do_lock_do_snapshot(tmp_path: Path) -> None:
    assert maintenance is not None, "gate de manutenção ainda não implementado"
    gate = maintenance.ManutencaoWeb(tmp_path / "maintenance")

    gate.solicitar_manutencao()
    try:
        with gate.mutacao_worker() as adquirido:
            assert adquirido is True
            with pytest.raises(TimeoutError), gate.lock_snapshot(timeout_seconds=0.05):
                pytest.fail("o snapshot não deve concorrer com o worker")
    finally:
        gate.liberar_manutencao()


def test_lock_do_snapshot_aguarda_escrita_em_andamento(tmp_path: Path) -> None:
    assert maintenance is not None, "gate de manutenção ainda não implementado"
    gate = maintenance.ManutencaoWeb(tmp_path / "maintenance")

    with gate.mutacao_http():
        gate.solicitar_manutencao()
        with pytest.raises(TimeoutError), gate.lock_snapshot(timeout_seconds=0.05):
            pytest.fail("o snapshot não deve interromper a escrita")
    try:
        with gate.lock_snapshot(timeout_seconds=0.5):
            assert gate.manutencao_ativa
    finally:
        gate.liberar_manutencao()


class RunnerRcloneFalso:
    def __init__(self) -> None:
        self.comandos: list[list[str]] = []

    def executar(self, argumentos: list[str]) -> str:
        self.comandos.append(argumentos)
        return ""


def test_rclone_crypt_cifra_e_cryptcheck_sem_expor_segredos_em_argumentos(
    tmp_path: Path,
) -> None:
    assert rclone_backup is not None, "adaptador rclone ainda não implementado"
    config = tmp_path / "rclone.conf"
    config.write_text(
        "[local-crypt]\n"
        "type = crypt\n"
        "remote = local-raw:backups\n"
        "password = segredo-sintetico-cifra\n"
        "password2 = segredo-sintetico-nomes\n"
        "filename_encryption = standard\n"
        "directory_name_encryption = false\n",
        encoding="utf-8",
    )
    source = tmp_path / "staging"
    source.mkdir()
    runner = RunnerRcloneFalso()
    adapter = rclone_backup.RcloneCryptArchive(
        runner,
        config_path=config,
        remote="local-crypt:backups",
        state_dir=tmp_path / "state",
    )

    with pytest.raises(ValueError, match="remote crypt"):
        adapter.cifrar(source, "local-raw:backups", "a" * 32)
    assert runner.comandos == []

    adapter.cifrar(source, "local-crypt:backups", "a" * 32)
    adapter.verificar(source, "local-crypt:backups", "a" * 32)

    assert runner.comandos == [
        ["copy", str(source), f"local-crypt:backups/{'a' * 32}"],
        ["cryptcheck", str(source), f"local-crypt:backups/{'a' * 32}"],
    ]
    assert all(
        "segredo-sintetico" not in " ".join(comando) for comando in runner.comandos
    )


def test_rclone_config_exige_crypt_com_cifra_de_nomes(tmp_path: Path) -> None:
    assert rclone_backup is not None, "adaptador rclone ainda não implementado"
    config = tmp_path / "rclone.conf"
    config.write_text(
        "[local-crypt]\n"
        "type = crypt\n"
        "remote = local-raw:backups\n"
        "password = segredo-sintetico\n"
        "filename_encryption = obfuscate\n"
        "directory_name_encryption = false\n",
        encoding="utf-8",
    )
    runner = RunnerRcloneFalso()
    adapter = rclone_backup.RcloneCryptArchive(
        runner,
        config_path=config,
        remote="local-crypt:backups",
        state_dir=tmp_path / "state",
    )

    with pytest.raises(ValueError, match="cifra de nomes"):
        adapter.validar_configuracao()

    assert runner.comandos == []


def test_rclone_sem_chave_lanca_erro_explicito(tmp_path: Path) -> None:
    assert rclone_backup is not None, "adaptador rclone ainda nao implementado"
    from src.application.services.web_backup import ChaveBackupAusente

    config = tmp_path / "rclone.conf"
    config.write_text(
        "[local-crypt]\n"
        "type = crypt\n"
        "remote = local-raw:backups\n"
        "filename_encryption = standard\n"
        "directory_name_encryption = false\n",
        encoding="utf-8",
    )
    adapter = rclone_backup.RcloneCryptArchive(
        RunnerRcloneFalso(),
        config_path=config,
        remote="local-crypt:backups",
        state_dir=tmp_path / "state",
    )

    with pytest.raises(ChaveBackupAusente):
        adapter.validar_configuracao()


def test_retencao_remove_backup_local_e_remoto_configurado(tmp_path: Path) -> None:
    assert rclone_backup is not None, "adaptador rclone ainda não implementado"
    import json

    config = tmp_path / "rclone.conf"
    config.write_text(
        "[local-crypt]\n"
        "type = crypt\n"
        "remote = local-raw:backups\n"
        "password = key\n"
        "filename_encryption = standard\n"
        "directory_name_encryption = false\n"
        "[local-raw]\ntype = local\n"
        "[remote-drive]\ntype = drive\n",
        encoding="utf-8",
    )
    runner = RunnerRcloneFalso()
    state = tmp_path / "state"
    adapter = rclone_backup.RcloneCryptArchive(
        runner,
        config_path=config,
        remote="local-crypt:backups",
        state_dir=state,
        external_remote="remote-drive:opaque-bucket",
    )
    generation = "f" * 32
    state.mkdir()
    (state / f"{generation}.complete.json").write_text("{}", encoding="utf-8")
    (state / f"{generation}.external.json").write_text(
        json.dumps({"geracao": generation, "destino": "remote-drive:opaque-bucket"}),
        encoding="utf-8",
    )

    adapter.remover_geracao(generation, "local-crypt:backups")

    assert runner.comandos == [
        ["purge", f"remote-drive:opaque-bucket/{generation}"],
        ["purge", f"local-crypt:backups/{generation}"],
    ]
    assert not (state / f"{generation}.external.json").exists()


def test_transporte_falho_limpa_destino_remoto_ou_preserva_marcador(
    tmp_path: Path,
) -> None:
    assert rclone_backup is not None, "adaptador rclone ainda não implementado"
    import json

    config = tmp_path / "rclone.conf"
    config.write_text(
        "[local-crypt]\n"
        "type = crypt\n"
        "remote = local-raw:backups\n"
        "password = key\n"
        "filename_encryption = standard\n"
        "directory_name_encryption = false\n"
        "[local-raw]\ntype = local\n"
        "[remote-drive]\ntype = drive\n",
        encoding="utf-8",
    )
    runner = RunnerRcloneFalso()
    state = tmp_path / "state"
    adapter = rclone_backup.RcloneCryptArchive(
        runner,
        config_path=config,
        remote="local-crypt:backups",
        state_dir=state,
        external_remote="remote-drive:opaque-bucket",
    )
    generation = "e" * 32
    state.mkdir()
    (state / f"{generation}.complete.json").write_text(
        json.dumps(
            {
                "geracao": generation,
                "criado_em": AGORA.isoformat(),
                "modo": "diario",
                "versao_aplicacao": "test",
                "revisao_schema": "0011",
                "tamanho_bytes": 1,
                "manifesto_sha256": "a" * 64,
            }
        ),
        encoding="utf-8",
    )

    class UploadFalho:
        def copiar_e_verificar(self, geracao: str) -> tuple[int, str]:
            raise RuntimeError("upload interrompido")

    service = backup.TransportarBackup(adapter)
    with pytest.raises(RuntimeError, match="interrompido"):
        service.executar(
            generation,
            UploadFalho(),
            destino="remote-drive:opaque-bucket",
        )

    assert runner.comandos == [["purge", f"remote-drive:opaque-bucket/{generation}"]]
    assert not (state / f"{generation}.external-inprogress.json").exists()
    assert not (state / f"{generation}.external.json").exists()


def test_geracao_so_fica_completa_depois_de_cryptcheck(tmp_path: Path) -> None:
    assert rclone_backup is not None, "adaptador rclone ainda não implementado"
    config = tmp_path / "rclone.conf"
    config.write_text(
        "[local-crypt]\n"
        "type = crypt\n"
        "remote = local-raw:backups\n"
        "password = chave-primaria\n"
        "password2 = chave-nomes\n"
        "filename_encryption = standard\n"
        "directory_name_encryption = false\n",
        encoding="utf-8",
    )
    runner = RunnerRcloneFalso()
    adapter = rclone_backup.RcloneCryptArchive(
        runner,
        config_path=config,
        remote="local-crypt:backups",
        state_dir=tmp_path / "state",
    )
    generation = "b" * 32
    manifest = backup.ManifestoBackup(
        geracao=generation,
        criado_em=AGORA,
        modo="diario",
        versao_aplicacao="abc1234",
        revisao_schema="0011",
        arquivos=(backup.ArquivoManifestoBackup("database.dump", 10, "c" * 64),),
    )

    adapter.cifrar(tmp_path, "local-crypt:backups", generation)
    with pytest.raises(ValueError, match="incompleta"):
        adapter.exigir_geracao_completa(generation)
    adapter.verificar(tmp_path, "local-crypt:backups", generation)
    adapter.marcar_completa("local-crypt:backups", manifest)

    adapter.exigir_geracao_completa(generation)
    marker = (tmp_path / "state" / f"{generation}.complete.json").read_text()
    assert "database.dump" not in marker


def test_registro_de_exclusoes_preserva_pendentes_e_confirmadas_sem_dados_biometricos(
    tmp_path: Path,
) -> None:
    assert exclusions is not None, "registro de exclusÃµes ainda nÃ£o implementado"
    project = tmp_path / "repo"
    project.mkdir()
    ledger = exclusions.RegistroExclusoes(
        tmp_path / "private" / "exclusions.jsonl", project_root=project
    )

    pendente = ledger.registrar_pendente("aluno", 21)
    ledger.confirmar(pendente, "aluno", 21)
    cancelada = ledger.registrar_pendente("aluno", 22)
    ledger.cancelar(cancelada, "aluno", 22)

    aplicaveis = ledger.exclusoes_a_reaplicar()
    assert [(item.identificador, item.estado) for item in aplicaveis] == [
        (21, "confirmada")
    ]
    conteudo = (tmp_path / "private" / "exclusions.jsonl").read_text()
    assert (
        "nome" not in conteudo
        and "imagem" not in conteudo
        and "embedding" not in conteudo
    )


def test_registro_de_exclusoes_rejeita_corrupcao_da_cadeia(tmp_path: Path) -> None:
    assert exclusions is not None, "registro de exclusÃµes ainda nÃ£o implementado"
    project = tmp_path / "repo"
    project.mkdir()
    path = tmp_path / "private" / "exclusions.jsonl"
    ledger = exclusions.RegistroExclusoes(path, project_root=project)
    ledger.registrar_pendente("aluno", 21)
    path.write_text(
        path.read_text().replace('"identificador":21', '"identificador":22')
    )

    with pytest.raises(RuntimeError, match="invÃ¡lido"):
        ledger.exclusoes_a_reaplicar()


def test_snapshot_postgres_manifesta_hashes_de_dump_e_referencias(
    tmp_path: Path,
) -> None:
    assert postgres_backup is not None, "coordenador PostgreSQL ainda nÃ£o implementado"
    from sqlalchemy import create_engine, text

    project = tmp_path / "repo"
    project.mkdir()
    references = tmp_path / "references"
    references.mkdir()
    (references / "21").mkdir()
    opaque_original = "a" * 48
    (references / "21" / f"1-{opaque_original}.bin").write_bytes(b"reference-bytes")
    service_file = tmp_path / "private" / "pg_service.conf"
    service_file.parent.mkdir()
    service_file.write_text("[task017]\nhost=localhost\n", encoding="utf-8")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE jobs_faciais_web (estado TEXT NOT NULL)"))
        connection.execute(
            text("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        )
        connection.execute(text("INSERT INTO alembic_version VALUES ('test-rev')"))

    class RunnerPostgresFake:
        def executar(self, argumentos: list[str], *, ambiente: dict[str, str]) -> str:
            if argumentos[0] == "psql":
                return ":memory:"
            assert argumentos[0] == "pg_dump"
            arquivo = Path(argumentos[argumentos.index("--file") + 1])
            arquivo.write_bytes(b"synthetic-postgres-dump")
            return ""

    gate = maintenance.ManutencaoWeb(tmp_path / "maintenance")
    coordinator = postgres_backup.CoordenacaoBackupPostgres(
        engine,
        gate,
        reference_root=references,
        staging_root=tmp_path / "staging",
        pg_service="task017",
        pg_service_file=service_file,
        project_root=project,
        app_version="test-version",
        runner=RunnerPostgresFake(),
        database_size_bytes=lambda: 1,
    )
    staging = coordinator.criar_staging("a" * 32)
    manifesto = coordinator.criar_snapshot(staging, "a" * 32, AGORA, "diario")

    assert manifesto.revisao_schema == "test-rev"
    reference_entry = next(
        item for item in manifesto.arquivos if item.caminho.startswith("references/")
    )
    assert {item.caminho for item in manifesto.arquivos} == {
        "database.dump",
        reference_entry.caminho,
    }
    assert reference_entry.caminho.startswith("references/")
    assert len(Path(reference_entry.caminho).name) == 52
    assert reference_entry.restaurar_em == f"21/1-{opaque_original}.bin"
    assert (staging / reference_entry.caminho).read_bytes() == b"reference-bytes"
    assert (staging / "MANIFEST.json").is_file()
    coordinator.limpar_staging(staging)
    engine.dispose()


def test_transporte_cifra_bytes_nao_repassa_destino_por_crypt(tmp_path: Path) -> None:
    assert rclone_backup is not None, "adaptador rclone ainda nÃ£o implementado"
    config = tmp_path / "rclone.conf"
    config.write_text(
        "[crypt-local]\n"
        "type = crypt\n"
        "remote = local-raw:backups\n"
        "password = key\n"
        "filename_encryption = standard\n"
        "directory_name_encryption = false\n"
        "[local-raw]\ntype = local\n"
        "[remote-drive]\ntype = drive\n",
        encoding="utf-8",
    )

    class RunnerTransporteFake(RunnerRcloneFalso):
        def executar(self, argumentos: list[str]) -> str:
            self.comandos.append(argumentos)
            if argumentos[0] == "lsjson":
                return (
                    '[{"Path":"encrypted-name.bin","Size":6,"Hashes":{"SHA-256":"x"}}]'
                )
            if argumentos[0] == "copyto":
                Path(argumentos[-1]).write_bytes(b"cipher")
            return ""

    runner = RunnerTransporteFake()
    transport = rclone_backup.RcloneCiphertextTransport(
        runner,
        config_path=config,
        encrypted_remote="crypt-local:backups",
        external_remote="remote-drive:opaque-bucket",
        scratch_dir=tmp_path / "scratch",
    )

    size, digest = transport.copiar_e_verificar("c" * 32)

    assert size == 6 and len(digest) == 64
    assert runner.comandos[0] == [
        "copy",
        f"local-raw:backups/{'c' * 32}",
        f"remote-drive:opaque-bucket/{'c' * 32}",
    ]
    assert runner.comandos[1][-1] == "--download"


def test_manifesto_restore_valida_hash_e_recusa_escape_de_caminho(
    tmp_path: Path,
) -> None:
    assert postgres_restore is not None, "adaptador de restore ainda nÃ£o implementado"
    import json

    from sqlalchemy import create_engine

    project = tmp_path / "repo"
    project.mkdir()
    staging_root = tmp_path / "restore"
    staging = staging_root / ("d" * 32)
    (staging / "references").mkdir(parents=True)
    (staging / "database.dump").write_bytes(b"dump")
    opaque_reference = "b" * 48
    (staging / "references" / f"{opaque_reference}.bin").write_bytes(b"reference")
    import hashlib

    manifest = {
        "geracao": "d" * 32,
        "criado_em": AGORA.isoformat(),
        "modo": "diario",
        "versao_aplicacao": "test",
        "revisao_schema": "test-rev",
        "arquivos": [
            {
                "caminho": "database.dump",
                "tamanho_bytes": 4,
                "sha256": hashlib.sha256(b"dump").hexdigest(),
            },
            {
                "caminho": f"references/{opaque_reference}.bin",
                "tamanho_bytes": 9,
                "sha256": hashlib.sha256(b"reference").hexdigest(),
                "restaurar_em": f"21/1-{'c' * 48}.bin",
            },
        ],
    }
    (staging / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    exclusion_ledger = exclusions.RegistroExclusoes(
        tmp_path / "private" / "exclusions.jsonl", project_root=project
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    adapter = postgres_restore.PostgresRestoreAdapter(
        engine,
        RunnerPostgresFakeForRestore(),
        FonteRestoreFake(),
        pg_service="task017",
        pg_service_file=tmp_path / "pg_service.conf",
        references_root=tmp_path / "restore-references",
        staging_root=staging_root,
        exclusions=exclusion_ledger,
        project_root=project,
    )

    checked = adapter.verificar_manifesto(staging)
    assert checked.geracao == "d" * 32 and len(checked.arquivos) == 2
    assert checked.arquivos[1].restaurar_em == f"21/1-{'c' * 48}.bin"
    reference_root = tmp_path / "restore-references"
    reference_root.mkdir()
    (reference_root / ".task017-disposable").write_text(
        "task017_test", encoding="utf-8"
    )
    adapter._base_validada = True
    adapter._database = "task017_test"
    adapter.restaurar_referencias(staging, "task017_test")
    assert (reference_root / "21" / f"1-{'c' * 48}.bin").read_bytes() == b"reference"
    manifest["arquivos"][0]["caminho"] = "../../fora.dump"
    (staging / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Caminho do manifesto"):
        adapter.verificar_manifesto(staging)
    engine.dispose()


class RunnerPostgresFakeForRestore:
    def executar(self, argumentos: list[str], *, ambiente: dict[str, str]) -> str:
        return "task017_test"


class FonteRestoreFake:
    def descriptografar(self, geracao: str) -> Path:
        raise AssertionError("descriptografia nao esperada neste teste")


def test_retencao_dry_run_nao_apaga_e_apply_fica_confinado_a_raizes(
    tmp_path: Path,
) -> None:
    assert retention is not None, "catalogo de retencao ainda nao implementado"
    from sqlalchemy import create_engine, text

    project = tmp_path / "repo"
    project.mkdir()
    logs = tmp_path / "private-logs"
    logs.mkdir()
    old_log = logs / "old.log"
    old_log.write_text("synthetic", encoding="utf-8")
    old_time = (AGORA - timedelta(days=4)).timestamp()
    import os

    os.utime(old_log, (old_time, old_time))
    captures_root = tmp_path / "private-captures"
    orphan = captures_root / "11111111-1111-1111-1111-111111111111"
    orphan.mkdir(parents=True)
    (orphan / "capture.bin").write_bytes(b"temporary")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE solicitacoes_cadastro_web (id INTEGER, limpa_em TEXT, "
                "estado TEXT, expira_em TEXT)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE conjuntos_referencias_web "
                "(id INTEGER, solicitacao_id INTEGER, estado TEXT)"
            )
        )

    class ArchiveRetentionFake:
        def __init__(self) -> None:
            self.removed: list[str] = []

        def listar_geracoes_completas(self) -> tuple[dict[str, object], ...]:
            return ()

        def listar_incompletas(self) -> tuple[str, ...]:
            return ("e" * 32,)

        def listar_transportes_incompletos(self) -> tuple[str, ...]:
            return ()

        def remover_geracao(self, geracao: str, destino: str) -> None:
            self.removed.append(geracao)

        def remover_transporte_incompleto(self, geracao: str) -> None:
            self.removed.append(f"external:{geracao}")

    class CaptureStorageFake:
        raiz = captures_root

        def remover_job(self, job_id) -> None:
            import shutil

            shutil.rmtree(self.raiz / str(job_id))

        def limpar_orfaos(self, ids_ativos: set) -> int:
            return 0

    archive = ArchiveRetentionFake()
    catalog = retention.CatalogoRetencaoWeb(
        engine,
        archive,
        backup_remote="crypt:backups",
        logs_root=logs,
        capture_storage=CaptureStorageFake(),
        reference_root=tmp_path / "private-references",
        active_job_ids=lambda: set(),
        limpar_referencias_provisorias=lambda: (0, ()),
        project_root=project,
    )
    service = backup.ExpurgarWeb(
        catalog,
        ambiente="test",
        alvo="db-task017-local",
        finalidade_ate=AGORA + timedelta(days=10),
    )
    plan = service.planejar(AGORA)

    assert plan.quantidade_alvos == 3
    assert old_log.exists() and orphan.exists() and archive.removed == []
    with pytest.raises(ValueError, match="confirma"):
        service.aplicar(plan, confirmacao="APLICAR-EXPURGO-errado")
    result = service.aplicar(plan, confirmacao="APLICAR-EXPURGO-test-db-task017-local")
    assert len(result.removidos) == 3
    assert not old_log.exists() and not orphan.exists()
    assert archive.removed == ["e" * 32]
    engine.dispose()
