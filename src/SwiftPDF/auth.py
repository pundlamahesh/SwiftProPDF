import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash


class AuthError(Exception):
    """Raised when user authentication fails."""


def init_db(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL DEFAULT '',
                last_name TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ensure_column(connection, "users", "first_name", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "users", "last_name", "TEXT NOT NULL DEFAULT ''")


def ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def create_user(database_path: Path, first_name: str, last_name: str, email: str, password: str) -> int:
    first_name = normalize_name(first_name)
    last_name = normalize_name(last_name)
    email = normalize_email(email)
    validate_name(first_name, "First name")
    validate_name(last_name, "Last name")
    validate_credentials(email, password)

    password_hash = generate_password_hash(password)
    try:
        with sqlite3.connect(database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (first_name, last_name, email, password_hash)
                VALUES (?, ?, ?, ?)
                """,
                (first_name, last_name, email, password_hash),
            )
            return int(cursor.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise AuthError("An account with this email already exists.") from exc


def authenticate_user(database_path: Path, email: str, password: str) -> dict[str, str | int]:
    email = normalize_email(email)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        user = connection.execute(
            "SELECT id, first_name, last_name, email, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if user is None or not check_password_hash(user["password_hash"], password):
        raise AuthError("Invalid email or password.")

    return user_to_dict(user)


def get_user(database_path: Path, user_id: int) -> dict[str, str | int] | None:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        user = connection.execute(
            "SELECT id, first_name, last_name, email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    if user is None:
        return None

    return user_to_dict(user)


def user_to_dict(user: sqlite3.Row) -> dict[str, str | int]:
    first_name = user["first_name"] or ""
    last_name = user["last_name"] or ""
    full_name = f"{first_name} {last_name}".strip()
    return {
        "id": user["id"],
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name or user["email"],
        "email": user["email"],
    }


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_name(name: str) -> str:
    return " ".join(name.strip().split())


def validate_name(name: str, label: str) -> None:
    if not name:
        raise AuthError(f"{label} is required.")

    if len(name) > 80:
        raise AuthError(f"{label} must be 80 characters or less.")


def validate_credentials(email: str, password: str) -> None:
    if not email or "@" not in email:
        raise AuthError("Enter a valid email address.")

    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters.")
