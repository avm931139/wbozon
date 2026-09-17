from pathlib import Path

import pytest

from backup.service import BackupConfig, BackupError, BackupService, _postgres_env, _repository_kind


def _config(tmp_path: Path, **overrides) -> BackupConfig:
    values = {
        "project_dir": tmp_path,
        "staging_dir": tmp_path / "staging",
        "backup_status_file": tmp_path / "status" / "backup.json",
        "restore_status_file": tmp_path / "status" / "restore.json",
        "database_url": "postgresql+psycopg://app:secret@db.example:5433/app_db?sslmode=require",
        "verify_database_url": "postgresql://app:secret@db.example/app_restore_test",
        "repository": "sftp:backup@example:/srv/backups/wbozon",
        "password_file": tmp_path / "restic-password",
        "data_paths": (tmp_path / "data",),
    }
    values.update(overrides)
    return BackupConfig(**values)


def test_postgres_env_keeps_password_out_of_database_argument():
    env, database = _postgres_env(
        "postgresql+psycopg://app:p%40ss@db.example:5433/app_db?sslmode=require"
    )

    assert database == "app_db"
    assert env["PGPASSWORD"] == "p@ss"
    assert env["PGHOST"] == "db.example"
    assert env["PGPORT"] == "5433"
    assert env["PGSSLMODE"] == "require"
    assert "p@ss" not in database


@pytest.mark.parametrize("repository", ["/var/backups/wbozon", "C:/backups/wbozon"])
def test_repository_kind_marks_filesystem_destinations_local(repository):
    assert _repository_kind(repository) == "local"


def test_validate_rejects_local_repository_when_offsite_is_required(tmp_path, monkeypatch):
    password_file = tmp_path / "restic-password"
    password_file.write_text("secret", encoding="utf-8")
    password_file.chmod(0o600)
    service = BackupService(_config(
        tmp_path,
        repository=str(tmp_path / "repository"),
        password_file=password_file,
    ))
    monkeypatch.setattr("backup.service.shutil.which", lambda name: f"/usr/bin/{name}")

    with pytest.raises(BackupError, match="off-site"):
        service._validate()


def test_validate_rejects_production_database_as_restore_target(tmp_path, monkeypatch):
    password_file = tmp_path / "restic-password"
    password_file.write_text("secret", encoding="utf-8")
    password_file.chmod(0o600)
    database_url = "postgresql://app:secret@localhost/app_db"
    service = BackupService(_config(
        tmp_path,
        database_url=database_url,
        verify_database_url=database_url,
        password_file=password_file,
    ))
    monkeypatch.setattr("backup.service.shutil.which", lambda name: f"/usr/bin/{name}")

    with pytest.raises(BackupError, match="must differ"):
        service._validate(restore=True)
