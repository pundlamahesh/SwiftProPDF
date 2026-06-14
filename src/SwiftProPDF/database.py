import os
import re
import sqlite3
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any


DBIntegrityError = sqlite3.IntegrityError
DBRow = sqlite3.Row


def database_url() -> str:
    return os.getenv("DATABASE_URL", os.getenv("SWIFTPROPDF_DATABASE_URL", ""))


def using_postgres() -> bool:
    url = database_url()
    return url.startswith("postgresql://") or url.startswith("postgres://")


def connect(database_path: Path | str):
    if using_postgres():
        return PostgresConnection(database_url())

    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


class CompatRow(Mapping):
    def __init__(self, columns: list[str], values: tuple[Any, ...]):
        self._columns = columns
        self._values = values
        self._by_name = dict(zip(columns, values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._by_name[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._columns)

    def __len__(self) -> int:
        return len(self._columns)

    def keys(self):
        return self._by_name.keys()


class PostgresConnection:
    def __init__(self, url: str):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Install psycopg[binary] to use PostgreSQL.") from exc

        self._psycopg = psycopg
        self._connection = psycopg.connect(url)
        self.row_factory = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type:
            self._connection.rollback()
        else:
            self._connection.commit()
        self._connection.close()
        return False

    def execute(self, sql: str, params: tuple[Any, ...] = ()):
        translated = translate_sql(sql)
        cursor = self._connection.cursor()
        try:
            cursor.execute(translated, params)
        except Exception as exc:
            if exc.__class__.__name__ == "UniqueViolation":
                raise sqlite3.IntegrityError(str(exc)) from exc
            raise
        return PostgresCursor(cursor)


class PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self.rowcount = cursor.rowcount
        self.lastrowid = None
        if cursor.description and cursor.description[0].name == "id":
            row = cursor.fetchone()
            if row:
                self.lastrowid = row[0]
                self._prefetched = [row]
            else:
                self._prefetched = []
        else:
            self._prefetched = []

    def _columns(self) -> list[str]:
        return [column.name for column in self._cursor.description or []]

    def _wrap(self, row):
        if row is None:
            return None
        return CompatRow(self._columns(), row)

    def fetchone(self):
        if self._prefetched:
            return self._wrap(self._prefetched.pop(0))
        return self._wrap(self._cursor.fetchone())

    def fetchall(self):
        rows = self._prefetched + list(self._cursor.fetchall())
        self._prefetched = []
        columns = self._columns()
        return [CompatRow(columns, row) for row in rows]


def translate_sql(sql: str) -> str:
    translated = sql
    translated = translated.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    translated = translated.replace("CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP")
    translated = translated.replace("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT(key) DO NOTHING")
    translated = translated.replace("?", "%s")

    if re.search(r"INSERT\s+INTO\s+users\s*\(", translated, re.IGNORECASE) and "RETURNING" not in translated.upper():
        translated = translated.rstrip().rstrip(";") + " RETURNING id"

    return translated


def ensure_column(connection, table_name: str, column_name: str, definition: str) -> None:
    if using_postgres():
        row = connection.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            (table_name, column_name),
        ).fetchone()
        if row is None:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {translate_column_definition(definition)}")
        return

    columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def translate_column_definition(definition: str) -> str:
    return definition.replace("INTEGER", "INTEGER").replace("TEXT", "TEXT")
