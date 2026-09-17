from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlsplit


class BackupError(RuntimeError):
    """A backup or restore verification step failed."""


@dataclass(frozen=True)
class BackupConfig:
    project_dir: Path
    staging_dir: Path
    backup_status_file: Path
    restore_status_file: Path
    database_url: str
    verify_database_url: str | None
    repository: str
    password_file: Path
    data_paths: tuple[Path, ...]
    keep_daily: int = 7
    keep_weekly: int = 5
    keep_monthly: int = 12
    check_subset: str = "5%"
    require_offsite: bool = True

    @classmethod
    def from_env(cls) -> "BackupConfig":
        project_dir = Path(os.getenv("BACKUP_PROJECT_DIR", Path.cwd())).resolve()
        status_dir = Path(
            os.getenv("BACKUP_STATUS_DIR", project_dir / "data" / "backup")
        ).resolve()
        configured_paths = os.getenv(
            "BACKUP_DATA_PATHS", "data,/etc/wbozon/backup.env"
        )
        data_paths = tuple(
            (project_dir / value.strip()).resolve()
            if not Path(value.strip()).is_absolute()
            else Path(value.strip()).resolve()
            for value in configured_paths.split(",")
            if value.strip()
        )
        return cls(
            project_dir=project_dir,
            staging_dir=Path(
                os.getenv("BACKUP_STAGING_DIR", "/var/backups/wbozon")
            ).resolve(),
            backup_status_file=status_dir / "backup-status.json",
            restore_status_file=status_dir / "restore-status.json",
            database_url=os.getenv("DATABASE_URL", "").strip(),
            verify_database_url=os.getenv("BACKUP_VERIFY_DATABASE_URL") or None,
            repository=os.getenv("RESTIC_REPOSITORY", "").strip(),
            password_file=Path(
                os.getenv("RESTIC_PASSWORD_FILE", "/etc/wbozon/restic-password")
            ).resolve(),
            data_paths=data_paths,
            keep_daily=int(os.getenv("BACKUP_KEEP_DAILY", "7")),
            keep_weekly=int(os.getenv("BACKUP_KEEP_WEEKLY", "5")),
            keep_monthly=int(os.getenv("BACKUP_KEEP_MONTHLY", "12")),
            check_subset=os.getenv("BACKUP_CHECK_SUBSET", "5%").strip(),
            require_offsite=_env_bool("BACKUP_REQUIRE_OFFSITE", True),
        )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _repository_kind(repository: str) -> str:
    for prefix in ("sftp:", "rest:", "s3:", "b2:", "azure:", "gs:", "rclone:"):
        if repository.startswith(prefix):
            return prefix[:-1]
    return "local"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _postgres_env(database_url: str) -> tuple[dict[str, str], str]:
    normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise BackupError("DATABASE_URL must be a PostgreSQL URL")
    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise BackupError("PostgreSQL database name is missing")
    env = os.environ.copy()
    if parsed.hostname:
        env["PGHOST"] = parsed.hostname
    if parsed.port:
        env["PGPORT"] = str(parsed.port)
    if parsed.username:
        env["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)
    query = parse_qs(parsed.query)
    if query.get("sslmode"):
        env["PGSSLMODE"] = query["sslmode"][-1]
    env["PGDATABASE"] = database
    return env, database


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:
            pass
        except BlockingIOError as exc:
            raise BackupError("another backup operation is already running") from exc
        yield
    finally:
        handle.close()


class BackupService:
    def __init__(self, config: BackupConfig):
        self.config = config

    @classmethod
    def from_env(cls) -> "BackupService":
        return cls(BackupConfig.from_env())

    def _validate(self, *, restore: bool = False) -> None:
        config = self.config
        if not config.database_url:
            raise BackupError("DATABASE_URL is not configured")
        if not config.repository:
            raise BackupError("RESTIC_REPOSITORY is not configured")
        if config.require_offsite and _repository_kind(config.repository) == "local":
            raise BackupError("RESTIC_REPOSITORY must be an off-site repository")
        if not config.password_file.is_file():
            raise BackupError("RESTIC_PASSWORD_FILE does not exist")
        if os.name != "nt" and config.password_file.stat().st_mode & 0o077:
            raise BackupError("RESTIC_PASSWORD_FILE must not be accessible by group or others")
        if shutil.which("restic") is None:
            raise BackupError("restic executable is not installed")
        if shutil.which("pg_dump") is None or shutil.which("pg_restore") is None:
            raise BackupError("PostgreSQL client tools are not installed")
        if restore:
            if not config.verify_database_url:
                raise BackupError("BACKUP_VERIFY_DATABASE_URL is not configured")
            _, production_db = _postgres_env(config.database_url)
            _, verify_db = _postgres_env(config.verify_database_url)
            if production_db == verify_db:
                raise BackupError("restore verification database must differ from production")
            if not any(marker in verify_db.lower() for marker in ("restore", "backup", "test")):
                raise BackupError("restore database name must contain restore, backup, or test")
            if shutil.which("psql") is None:
                raise BackupError("psql executable is not installed")

    def _restic_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["RESTIC_REPOSITORY"] = self.config.repository
        env["RESTIC_PASSWORD_FILE"] = str(self.config.password_file)
        return env

    def _run(
        self,
        command: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        timeout: int = 21600,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            list(command),
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout or "no command output").strip()
            if self.config.repository:
                detail = detail.replace(self.config.repository, "<repository>")
            raise BackupError(f"{command[0]} failed: {detail[-1500:]}")
        return result

    def _write_status(
        self,
        path: Path,
        *,
        operation: str,
        status: str,
        started_at: datetime,
        error: str | None = None,
        **details: object,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "operation": operation,
            "status": status,
            "started_at": _iso(started_at),
            "finished_at": _iso(_now()),
            "repository_kind": _repository_kind(self.config.repository),
            "error": error,
            **details,
        }
        _atomic_json(path, payload)
        return payload

    def initialize_repository(self) -> dict[str, object]:
        self._validate()
        initialized = False
        try:
            result = self._run(["restic", "snapshots", "--json"], env=self._restic_env())
        except BackupError:
            self._run(["restic", "init"], env=self._restic_env())
            initialized = True
            result = self._run(["restic", "snapshots", "--json"], env=self._restic_env())
        return {
            "status": "ready",
            "repository_kind": _repository_kind(self.config.repository),
            "snapshots": len(json.loads(result.stdout or "[]")),
            "initialized": initialized,
        }

    def run_backup(self) -> dict[str, object]:
        started = _now()
        status_path = self.config.backup_status_file
        try:
            self._validate()
            with _exclusive_lock(self.config.staging_dir / ".backup.lock"):
                return self._run_backup_locked(started)
        except Exception as exc:
            self._write_status(
                status_path,
                operation="backup",
                status="failed",
                started_at=started,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

    def _run_backup_locked(self, started: datetime) -> dict[str, object]:
        config = self.config
        current_dir = config.staging_dir / "current"
        current_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(current_dir, 0o700)
        dump_path = current_dir / "database.dump"
        manifest_path = current_dir / "manifest.json"
        dump_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        try:
            pg_env, database = _postgres_env(config.database_url)
            self._run(
                [
                    "pg_dump",
                    "--format=custom",
                    "--compress=9",
                    "--no-password",
                    "--file",
                    str(dump_path),
                    database,
                ],
                env=pg_env,
            )
            os.chmod(dump_path, 0o600)
            self._run(["pg_restore", "--list", str(dump_path)])
            digest = _sha256(dump_path)
            manifest = {
                "created_at": _iso(_now()),
                "database": database,
                "database_dump": dump_path.name,
                "database_dump_bytes": dump_path.stat().st_size,
                "database_dump_sha256": digest,
            }
            _atomic_json(manifest_path, manifest)

            targets = [current_dir, config.project_dir / ".env"]
            targets.extend(path for path in config.data_paths if path.exists())
            missing = [str(path) for path in targets if not path.exists()]
            if missing:
                raise BackupError(f"required backup paths are missing: {', '.join(missing)}")
            result = self._run(
                ["restic", "backup", "--json", "--tag", "wbozon", *map(str, targets)],
                env=self._restic_env(),
            )
            snapshot_id = None
            for line in result.stdout.splitlines():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if message.get("message_type") == "summary":
                    snapshot_id = message.get("snapshot_id")

            self._run(
                [
                    "restic",
                    "forget",
                    "--tag",
                    "wbozon",
                    "--keep-daily",
                    str(config.keep_daily),
                    "--keep-weekly",
                    str(config.keep_weekly),
                    "--keep-monthly",
                    str(config.keep_monthly),
                    "--prune",
                ],
                env=self._restic_env(),
            )
            self._run(
                ["restic", "check", f"--read-data-subset={config.check_subset}"],
                env=self._restic_env(),
            )
            return self._write_status(
                config.backup_status_file,
                operation="backup",
                status="completed",
                started_at=started,
                snapshot_id=snapshot_id,
                database_dump_bytes=dump_path.stat().st_size,
                database_dump_sha256=digest,
                backed_up_paths=len(targets),
                integrity_check=config.check_subset,
            )
        finally:
            dump_path.unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)

    def verify_restore(self) -> dict[str, object]:
        started = _now()
        status_path = self.config.restore_status_file
        try:
            self._validate(restore=True)
            with _exclusive_lock(self.config.staging_dir / ".backup.lock"):
                return self._verify_restore_locked(started)
        except Exception as exc:
            self._write_status(
                status_path,
                operation="restore",
                status="failed",
                started_at=started,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

    def _verify_restore_locked(self, started: datetime) -> dict[str, object]:
        config = self.config
        with tempfile.TemporaryDirectory(prefix="restore-", dir=config.staging_dir) as temp:
            target = Path(temp)
            dump_source = str(config.staging_dir / "current" / "database.dump")
            self._run(
                [
                    "restic",
                    "restore",
                    "latest",
                    "--tag",
                    "wbozon",
                    "--target",
                    str(target),
                    "--include",
                    dump_source,
                ],
                env=self._restic_env(),
            )
            candidates = list(target.rglob("database.dump"))
            if len(candidates) != 1:
                raise BackupError(f"expected one restored database dump, found {len(candidates)}")
            dump_path = candidates[0]
            self._run(["pg_restore", "--list", str(dump_path)])

            verify_url = config.verify_database_url or ""
            verify_env, verify_database = _postgres_env(verify_url)
            self._run(
                [
                    "psql",
                    "--no-password",
                    "--set",
                    "ON_ERROR_STOP=1",
                    "--dbname",
                    verify_database,
                    "--command",
                    "DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION CURRENT_USER;",
                ],
                env=verify_env,
            )
            self._run(
                [
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    "--dbname",
                    verify_database,
                    str(dump_path),
                ],
                env=verify_env,
            )
            smoke = self._run(
                [
                    "psql",
                    "--no-password",
                    "--tuples-only",
                    "--no-align",
                    "--dbname",
                    verify_database,
                    "--command",
                    "SELECT version_num FROM alembic_version; SELECT count(*) FROM pg_tables WHERE schemaname='public';",
                ],
                env=verify_env,
            )
            smoke_lines = [line.strip() for line in smoke.stdout.splitlines() if line.strip()]
            if len(smoke_lines) < 2 or int(smoke_lines[-1]) < 1:
                raise BackupError("restored database smoke test returned an invalid result")
            return self._write_status(
                config.restore_status_file,
                operation="restore",
                status="completed",
                started_at=started,
                alembic_revision=smoke_lines[0],
                public_tables=int(smoke_lines[-1]),
                database_dump_bytes=dump_path.stat().st_size,
            )
