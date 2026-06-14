import os
from pathlib import Path

from SwiftProPDF.database import database_url


def run_migrations(database_path: Path | str) -> None:
    """Apply database migrations for the configured SQLite or PostgreSQL database."""
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError as exc:
        raise RuntimeError("Install alembic to run database migrations.") from exc

    project_root = Path(__file__).resolve().parents[2]
    alembic_ini = project_root / "alembic.ini"
    migration_url = _sqlalchemy_url(database_url()) or _sqlite_url(Path(database_path))

    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))
    command.upgrade(config, "head")


def _sqlite_url(database_path: Path) -> str:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{database_path.resolve()}"


def _sqlalchemy_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url
