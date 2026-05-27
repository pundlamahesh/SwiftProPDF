import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash


MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


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
                role TEXT NOT NULL DEFAULT 'user',
                failed_login_count INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                last_login_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ensure_column(connection, "users", "first_name", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "users", "last_name", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "users", "role", "TEXT NOT NULL DEFAULT 'user'")
        ensure_column(connection, "users", "failed_login_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "users", "locked_until", "TEXT")
        ensure_column(connection, "users", "last_login_at", "TEXT")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_type TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                ip_address TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        ensure_admin_exists(connection)


def ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def ensure_admin_exists(connection: sqlite3.Connection) -> None:
    user_total = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    admin_total = connection.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
    if user_total and not admin_total:
        connection.execute(
            """
            UPDATE users
            SET role = 'admin'
            WHERE id = (SELECT id FROM users ORDER BY id ASC LIMIT 1)
            """
        )


def create_user(database_path: Path, first_name: str, last_name: str, email: str, password: str) -> int:
    first_name = normalize_name(first_name)
    last_name = normalize_name(last_name)
    email = normalize_email(email)
    validate_registration_details(database_path, first_name, last_name, email, password)

    password_hash = generate_password_hash(password)
    return create_verified_user(database_path, first_name, last_name, email, password_hash)


def validate_registration_details(
    database_path: Path,
    first_name: str,
    last_name: str,
    email: str,
    password: str,
) -> None:
    first_name = normalize_name(first_name)
    last_name = normalize_name(last_name)
    email = normalize_email(email)
    validate_name(first_name, "First name")
    validate_name(last_name, "Last name")
    validate_credentials(email, password)

    with sqlite3.connect(database_path) as connection:
        existing = connection.execute(
            "SELECT 1 FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    if existing:
        raise AuthError("An account with this email already exists.")


def create_verified_user(
    database_path: Path,
    first_name: str,
    last_name: str,
    email: str,
    password_hash: str,
) -> int:
    first_name = normalize_name(first_name)
    last_name = normalize_name(last_name)
    email = normalize_email(email)
    role = "admin" if user_count(database_path) == 0 else "user"

    try:
        with sqlite3.connect(database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (first_name, last_name, email, password_hash, role)
                VALUES (?, ?, ?, ?, ?)
                """,
                (first_name, last_name, email, password_hash, role),
            )
            return int(cursor.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise AuthError("An account with this email already exists.") from exc


def create_user_with_role(
    database_path: Path,
    first_name: str,
    last_name: str,
    email: str,
    password: str,
    role: str,
) -> int:
    if role not in ("admin", "user"):
        raise AuthError("Invalid role.")

    user_id = create_user(database_path, first_name, last_name, email, password)
    set_user_role(database_path, user_id, role)
    return user_id


def update_user(
    database_path: Path,
    user_id: int,
    first_name: str,
    last_name: str,
    email: str,
    role: str,
    password: str = "",
) -> None:
    first_name = normalize_name(first_name)
    last_name = normalize_name(last_name)
    email = normalize_email(email)
    validate_name(first_name, "First name")
    validate_name(last_name, "Last name")

    if not email or "@" not in email:
        raise AuthError("Enter a valid email address.")

    if role not in ("admin", "user"):
        raise AuthError("Invalid role.")

    if password:
        validate_credentials(email, password)

    try:
        with sqlite3.connect(database_path) as connection:
            if password:
                connection.execute(
                    """
                    UPDATE users
                    SET first_name = ?, last_name = ?, email = ?, role = ?, password_hash = ?
                    WHERE id = ?
                    """,
                    (first_name, last_name, email, role, generate_password_hash(password), user_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE users
                    SET first_name = ?, last_name = ?, email = ?, role = ?
                    WHERE id = ?
                    """,
                    (first_name, last_name, email, role, user_id),
                )
    except sqlite3.IntegrityError as exc:
        raise AuthError("An account with this email already exists.") from exc


def delete_user(database_path: Path, user_id: int) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute("DELETE FROM audit_events WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))


def authenticate_user(database_path: Path, email: str, password: str) -> dict[str, str | int]:
    email = normalize_email(email)
    now = utc_now()

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        user = connection.execute(
            """
            SELECT id, first_name, last_name, email, password_hash, role,
                   failed_login_count, locked_until, last_login_at, created_at
            FROM users
            WHERE email = ?
            """,
            (email,),
        ).fetchone()

        if user is None:
            raise AuthError("Invalid email or password.")

        locked_until = parse_timestamp(user["locked_until"])
        if locked_until and locked_until > now:
            minutes = max(1, int((locked_until - now).total_seconds() // 60) + 1)
            raise AuthError(f"Account locked. Try again in {minutes} minute(s).")

        if not check_password_hash(user["password_hash"], password):
            failed_count = int(user["failed_login_count"] or 0) + 1
            new_locked_until = None
            if failed_count >= MAX_FAILED_LOGINS:
                new_locked_until = (now + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()

            connection.execute(
                """
                UPDATE users
                SET failed_login_count = ?, locked_until = ?
                WHERE id = ?
                """,
                (failed_count, new_locked_until, user["id"]),
            )
            if new_locked_until:
                raise AuthError(f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes.")
            raise AuthError("Invalid email or password.")

        connection.execute(
            """
            UPDATE users
            SET failed_login_count = 0, locked_until = NULL, last_login_at = ?
            WHERE id = ?
            """,
            (now.isoformat(), user["id"]),
        )

    return get_user(database_path, int(user["id"]))


def authenticate_user_by_otp(database_path: Path, email: str) -> dict[str, str | int]:
    user = get_user_by_email(database_path, email)
    if user is None:
        raise AuthError("Account not found.")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE users
            SET failed_login_count = 0, locked_until = NULL, last_login_at = ?
            WHERE id = ?
            """,
            (utc_now().isoformat(), user["id"]),
        )

    return get_user(database_path, int(user["id"]))


def get_user(database_path: Path, user_id: int) -> dict[str, str | int] | None:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        user = connection.execute(
            """
            SELECT id, first_name, last_name, email, role, failed_login_count,
                   locked_until, last_login_at, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

    if user is None:
        return None

    return user_to_dict(user)


def get_user_by_email(database_path: Path, email: str) -> dict[str, str | int] | None:
    email = normalize_email(email)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        user = connection.execute(
            """
            SELECT id, first_name, last_name, email, role, failed_login_count,
                   locked_until, last_login_at, created_at
            FROM users
            WHERE email = ?
            """,
            (email,),
        ).fetchone()

    if user is None:
        return None

    return user_to_dict(user)


def list_users(database_path: Path) -> list[dict[str, str | int | bool | None]]:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, first_name, last_name, email, role, failed_login_count,
                   locked_until, last_login_at, created_at
            FROM users
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()

    return [user_to_dict(row) for row in rows]


def set_user_role(database_path: Path, user_id: int, role: str) -> None:
    if role not in ("admin", "user"):
        raise AuthError("Invalid role.")

    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def unlock_user(database_path: Path, user_id: int) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE users SET failed_login_count = 0, locked_until = NULL WHERE id = ?",
            (user_id,),
        )


def update_user_password(database_path: Path, email: str, password: str) -> None:
    email = normalize_email(email)
    validate_credentials(email, password)
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE users
            SET password_hash = ?, failed_login_count = 0, locked_until = NULL
            WHERE email = ?
            """,
            (generate_password_hash(password), email),
        )
    if cursor.rowcount == 0:
        raise AuthError("Account not found.")


def log_audit_event(
    database_path: Path,
    event_type: str,
    user_id: int | None = None,
    details: str = "",
    ip_address: str = "",
) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO audit_events (user_id, event_type, details, ip_address)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, event_type, details[:500], ip_address[:80]),
        )


def list_audit_events(database_path: Path, limit: int = 50) -> list[dict[str, str | int | None]]:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT audit_events.id, audit_events.user_id, audit_events.event_type,
                   audit_events.details, audit_events.ip_address, audit_events.created_at,
                   users.email
            FROM audit_events
            LEFT JOIN users ON users.id = audit_events.user_id
            ORDER BY audit_events.created_at DESC, audit_events.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def admin_stats(database_path: Path) -> dict[str, int]:
    with sqlite3.connect(database_path) as connection:
        total_users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        admins = connection.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
        locked_users = connection.execute(
            "SELECT COUNT(*) FROM users WHERE locked_until IS NOT NULL AND locked_until > ?",
            (utc_now().isoformat(),),
        ).fetchone()[0]
        audit_events = connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]

    return {
        "total_users": int(total_users),
        "admins": int(admins),
        "locked_users": int(locked_users),
        "audit_events": int(audit_events),
    }


def user_count(database_path: Path) -> int:
    with sqlite3.connect(database_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def user_to_dict(user: sqlite3.Row) -> dict[str, str | int | bool | None]:
    first_name = user["first_name"] or ""
    last_name = user["last_name"] or ""
    full_name = f"{first_name} {last_name}".strip()
    locked_until = user["locked_until"] if "locked_until" in user.keys() else None
    locked_until_date = parse_timestamp(locked_until)
    return {
        "id": user["id"],
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name or user["email"],
        "email": user["email"],
        "role": user["role"] if "role" in user.keys() else "user",
        "is_admin": (user["role"] if "role" in user.keys() else "user") == "admin",
        "failed_login_count": user["failed_login_count"] if "failed_login_count" in user.keys() else 0,
        "locked_until": locked_until,
        "is_locked": bool(locked_until_date and locked_until_date > utc_now()),
        "last_login_at": user["last_login_at"] if "last_login_at" in user.keys() else None,
        "created_at": user["created_at"] if "created_at" in user.keys() else None,
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

    if len(password) < 10:
        raise AuthError("Password must be at least 10 characters.")

    checks = (
        (r"[A-Z]", "one uppercase letter"),
        (r"[a-z]", "one lowercase letter"),
        (r"\d", "one number"),
        (r"[^A-Za-z0-9]", "one symbol"),
    )
    missing = [message for pattern, message in checks if not re.search(pattern, password)]
    if missing:
        raise AuthError(f"Password must include {', '.join(missing)}.")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
