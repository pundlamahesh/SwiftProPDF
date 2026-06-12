import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash


MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
MAX_FAILED_RESET_ATTEMPTS = 5
RESET_LOCKOUT_MINUTES = 30
MAX_ACTIVE_USER_SESSIONS = 2
USER_SESSION_HOURS = 8


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
                role TEXT NOT NULL DEFAULT 'FREE',
                plan_type TEXT NOT NULL DEFAULT 'FREE',
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                failed_login_count INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                last_login_at TEXT,
                quota_reset_at TEXT,
                weekly_usage_count INTEGER NOT NULL DEFAULT 0,
                lifetime_usage_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ensure_column(connection, "users", "first_name", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "users", "last_name", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "users", "role", "TEXT NOT NULL DEFAULT 'FREE'")
        ensure_column(connection, "users", "plan_type", "TEXT NOT NULL DEFAULT 'FREE'")
        ensure_column(connection, "users", "status", "TEXT NOT NULL DEFAULT 'ACTIVE'")
        ensure_column(connection, "users", "failed_login_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "users", "locked_until", "TEXT")
        ensure_column(connection, "users", "last_login_at", "TEXT")
        ensure_column(connection, "users", "quota_reset_at", "TEXT")
        ensure_column(connection, "users", "weekly_usage_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "users", "lifetime_usage_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "users", "premium_valid_from", "TEXT")
        ensure_column(connection, "users", "premium_valid_until", "TEXT")
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                anonymous_id TEXT,
                ip_address TEXT NOT NULL DEFAULT '',
                tool_name TEXT NOT NULL,
                usage_date TEXT NOT NULL,
                usage_week TEXT NOT NULL,
                execution_count INTEGER NOT NULL DEFAULT 0,
                last_execution_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_security_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                date_of_birth_hash TEXT NOT NULL,
                current_city_hash TEXT NOT NULL,
                failed_reset_attempts INTEGER NOT NULL DEFAULT 0,
                reset_locked_until TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_token TEXT NOT NULL UNIQUE,
                user_agent TEXT NOT NULL DEFAULT '',
                ip_address TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        ensure_column(connection, "user_security_questions", "failed_reset_attempts", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "user_security_questions", "reset_locked_until", "TEXT")
        ensure_column(connection, "usage_tracking", "usage_date", "TEXT NOT NULL")
        ensure_column(connection, "usage_tracking", "usage_week", "TEXT NOT NULL")
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS user_sessions_user_expires_idx
            ON user_sessions(user_id, expires_at)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute("DROP INDEX IF EXISTS usage_tracking_user_tool_idx")
        connection.execute("DROP INDEX IF EXISTS usage_tracking_guest_tool_idx")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS usage_tracking_user_tool_week_idx
            ON usage_tracking(user_id, tool_name, usage_week)
            WHERE user_id IS NOT NULL
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS usage_tracking_guest_tool_week_idx
            ON usage_tracking(anonymous_id, ip_address, tool_name, usage_week)
            WHERE user_id IS NULL
            """
        )
        connection.execute("UPDATE users SET role = UPPER(role) WHERE role IS NOT NULL")
        connection.execute("UPDATE users SET plan_type = UPPER(plan_type) WHERE plan_type IS NOT NULL")
        connection.execute("UPDATE users SET role = 'FREE' WHERE role NOT IN ('ADMIN', 'PREMIUM', 'FREE')")
        connection.execute("UPDATE users SET plan_type = role WHERE plan_type NOT IN ('ADMIN', 'PREMIUM', 'FREE')")
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
    admin_total = connection.execute("SELECT COUNT(*) FROM users WHERE role = 'ADMIN'").fetchone()[0]
    if user_total and not admin_total:
        connection.execute(
            """
            UPDATE users
            SET role = 'ADMIN'
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
    role = "ADMIN" if user_count(database_path) == 0 else "FREE"
    plan_type = role

    try:
        with sqlite3.connect(database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (first_name, last_name, email, password_hash, role, plan_type, quota_reset_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    first_name,
                    last_name,
                    email,
                    password_hash,
                    role,
                    plan_type,
                    next_weekly_reset().isoformat(),
                ),
            )
            return int(cursor.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise AuthError("An account with this email already exists.") from exc


def set_premium_validity(database_path: Path, user_id: int, start: datetime | None = None, end: datetime | None = None) -> None:
    if start is None:
        start = utc_now()
    if end is None:
        end = start + timedelta(days=365)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE users SET premium_valid_from = ?, premium_valid_until = ? WHERE id = ?",
            (start.isoformat(), end.isoformat(), user_id),
        )


def clear_premium_validity(database_path: Path, user_id: int) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE users SET premium_valid_from = NULL, premium_valid_until = NULL WHERE id = ?",
            (user_id,),
        )


def normalize_security_answer(answer: str) -> str:
    return " ".join(answer.strip().lower().split())


def validate_security_answers(date_of_birth: str, current_city: str) -> None:
    if not date_of_birth.strip():
        raise AuthError("Date of birth is required.")
    if not current_city.strip():
        raise AuthError("Current city is required.")


def set_user_security_questions(
    database_path: Path,
    user_id: int,
    date_of_birth: str,
    current_city: str,
) -> None:
    validate_security_answers(date_of_birth, current_city)
    date_of_birth_hash = generate_password_hash(normalize_security_answer(date_of_birth))
    current_city_hash = generate_password_hash(normalize_security_answer(current_city))
    now = utc_now().isoformat()

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO user_security_questions (
                user_id, date_of_birth_hash, current_city_hash,
                failed_reset_attempts, reset_locked_until, updated_at
            )
            VALUES (?, ?, ?, 0, NULL, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                date_of_birth_hash = excluded.date_of_birth_hash,
                current_city_hash = excluded.current_city_hash,
                failed_reset_attempts = 0,
                reset_locked_until = NULL,
                updated_at = excluded.updated_at
            """,
            (user_id, date_of_birth_hash, current_city_hash, now),
        )


def has_user_security_questions(database_path: Path, user_id: int) -> bool:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT 1 FROM user_security_questions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row is not None


def verify_user_security_answers(
    database_path: Path,
    user_id: int,
    date_of_birth: str,
    current_city: str,
) -> None:
    now = utc_now()
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT date_of_birth_hash, current_city_hash, failed_reset_attempts, reset_locked_until
            FROM user_security_questions
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        if row is None:
            raise AuthError("Security questions are not configured for this account.")

        locked_until = parse_timestamp(row["reset_locked_until"])
        if locked_until and locked_until > now:
            raise AuthError("Too many failed attempts. Please try again later.")

        matches = (
            check_password_hash(row["date_of_birth_hash"], normalize_security_answer(date_of_birth))
            and check_password_hash(row["current_city_hash"], normalize_security_answer(current_city))
        )
        if matches:
            connection.execute(
                """
                UPDATE user_security_questions
                SET failed_reset_attempts = 0, reset_locked_until = NULL, updated_at = ?
                WHERE user_id = ?
                """,
                (now.isoformat(), user_id),
            )
            return

        failed_count = int(row["failed_reset_attempts"] or 0) + 1
        locked_value = None
        if failed_count >= MAX_FAILED_RESET_ATTEMPTS:
            locked_value = (now + timedelta(minutes=RESET_LOCKOUT_MINUTES)).isoformat()

        connection.execute(
            """
            UPDATE user_security_questions
            SET failed_reset_attempts = ?, reset_locked_until = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (failed_count, locked_value, now.isoformat(), user_id),
        )

    if locked_value:
        raise AuthError("Too many failed attempts. Please try again later.")
    raise AuthError("Security answers did not match.")


def create_user_with_role(
    database_path: Path,
    first_name: str,
    last_name: str,
    email: str,
    password: str,
    role: str,
    premium_valid_from: str = "",
    premium_valid_until: str = "",
) -> int:
    normalized_role = role.strip().upper()
    if normalized_role not in ("ADMIN", "PREMIUM", "FREE"):
        raise AuthError("Invalid role.")

    user_id = create_user(database_path, first_name, last_name, email, password)
    set_user_role(database_path, user_id, normalized_role)
    if normalized_role == "PREMIUM":
        start = parse_timestamp(premium_valid_from) if premium_valid_from else None
        end = parse_timestamp(premium_valid_until) if premium_valid_until else None
        if premium_valid_from and start is None:
            raise AuthError("Invalid premium valid from date.")
        if premium_valid_until and end is None:
            raise AuthError("Invalid premium valid until date.")
        set_premium_validity(database_path, user_id, start, end)
    else:
        clear_premium_validity(database_path, user_id)
    return user_id


def update_user(
    database_path: Path,
    user_id: int,
    first_name: str,
    last_name: str,
    email: str,
    role: str,
    status: str = "ACTIVE",
    password: str = "",
    premium_valid_from: str = "",
    premium_valid_until: str = "",
    clear_premium_dates: bool = False,
) -> None:
    first_name = normalize_name(first_name)
    last_name = normalize_name(last_name)
    email = normalize_email(email)
    validate_name(first_name, "First name")
    validate_name(last_name, "Last name")

    normalized_role = role.strip().upper()
    if normalized_role not in ("ADMIN", "PREMIUM", "FREE"):
        raise AuthError("Invalid role.")

    normalized_status = status.strip().upper()
    if normalized_status not in ("ACTIVE", "DISABLED"):
        raise AuthError("Invalid status.")

    if not email or "@" not in email:
        raise AuthError("Enter a valid email address.")

    if password:
        validate_credentials(email, password)

    premium_start = None
    premium_end = None
    if normalized_role == "PREMIUM" and clear_premium_dates:
        premium_start = None
        premium_end = None
    elif normalized_role == "PREMIUM":
        if premium_valid_from:
            premium_start = parse_timestamp(premium_valid_from)
            if premium_start is None:
                raise AuthError("Invalid premium valid from date.")
        else:
            premium_start = utc_now()

        if premium_valid_until:
            premium_end = parse_timestamp(premium_valid_until)
            if premium_end is None:
                raise AuthError("Invalid premium valid until date.")
        else:
            premium_end = premium_start + timedelta(days=365)

        if premium_end <= premium_start:
            raise AuthError("Premium validity end date must be after the start date.")
    else:
        premium_start = None
        premium_end = None

    try:
        with sqlite3.connect(database_path) as connection:
            if password:
                connection.execute(
                    """
                    UPDATE users
                    SET first_name = ?, last_name = ?, email = ?, role = ?, plan_type = ?, status = ?, password_hash = ?, premium_valid_from = ?, premium_valid_until = ?
                    WHERE id = ?
                    """,
                    (
                        first_name,
                        last_name,
                        email,
                        normalized_role,
                        normalized_role,
                        normalized_status,
                        generate_password_hash(password),
                        premium_start.isoformat() if premium_start else None,
                        premium_end.isoformat() if premium_end else None,
                        user_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE users
                    SET first_name = ?, last_name = ?, email = ?, role = ?, plan_type = ?, status = ?, premium_valid_from = ?, premium_valid_until = ?
                    WHERE id = ?
                    """,
                    (
                        first_name,
                        last_name,
                        email,
                        normalized_role,
                        normalized_role,
                        normalized_status,
                        premium_start.isoformat() if premium_start else None,
                        premium_end.isoformat() if premium_end else None,
                        user_id,
                    ),
                )
    except sqlite3.IntegrityError as exc:
        raise AuthError("An account with this email already exists.") from exc


def delete_user(database_path: Path, user_id: int) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute("DELETE FROM audit_events WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM user_security_questions WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))


def create_user_session(
    database_path: Path,
    user_id: int,
    session_token: str,
    user_agent: str = "",
    ip_address: str = "",
) -> None:
    now = utc_now()
    expires_at = now + timedelta(hours=USER_SESSION_HOURS)
    with sqlite3.connect(database_path) as connection:
        prune_expired_user_sessions(connection, now)
        active_count = connection.execute(
            "SELECT COUNT(*) FROM user_sessions WHERE user_id = ? AND expires_at > ?",
            (user_id, now.isoformat()),
        ).fetchone()[0]
        if int(active_count) >= MAX_ACTIVE_USER_SESSIONS:
            raise AuthError("This account is already logged in on 2 devices. Please log out from another device and try again.")

        connection.execute(
            """
            INSERT INTO user_sessions (user_id, session_token, user_agent, ip_address, created_at, last_seen_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                session_token,
                user_agent[:255],
                ip_address[:80],
                now.isoformat(),
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )


def is_user_session_active(database_path: Path, user_id: int, session_token: str) -> bool:
    now = utc_now()
    with sqlite3.connect(database_path) as connection:
        prune_expired_user_sessions(connection, now)
        row = connection.execute(
            """
            SELECT 1 FROM user_sessions
            WHERE user_id = ? AND session_token = ? AND expires_at > ?
            """,
            (user_id, session_token, now.isoformat()),
        ).fetchone()
        if row is None:
            return False

        connection.execute(
            """
            UPDATE user_sessions
            SET last_seen_at = ?, expires_at = ?
            WHERE user_id = ? AND session_token = ?
            """,
            (
                now.isoformat(),
                (now + timedelta(hours=USER_SESSION_HOURS)).isoformat(),
                user_id,
                session_token,
            ),
        )
    return True


def delete_user_session(database_path: Path, user_id: int, session_token: str) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "DELETE FROM user_sessions WHERE user_id = ? AND session_token = ?",
            (user_id, session_token),
        )


def prune_expired_user_sessions(connection: sqlite3.Connection, now: datetime | None = None) -> None:
    if now is None:
        now = utc_now()
    connection.execute("DELETE FROM user_sessions WHERE expires_at <= ?", (now.isoformat(),))


def authenticate_user(database_path: Path, email: str, password: str) -> dict[str, str | int]:
    email = normalize_email(email)
    now = utc_now()

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        user = connection.execute(
            """
            SELECT id, first_name, last_name, email, password_hash, role, plan_type, status,
                   failed_login_count, locked_until, last_login_at, quota_reset_at, weekly_usage_count,
                   lifetime_usage_count, premium_valid_from, premium_valid_until, created_at
            FROM users
            WHERE email = ?
            """,
            (email,),
        ).fetchone()

        if user is None:
            raise AuthError("Invalid email or password.")

        if user["status"] != "ACTIVE":
            raise AuthError("Account disabled. Contact an administrator.")

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


def get_user(database_path: Path, user_id: int) -> dict[str, str | int] | None:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        user = connection.execute(
            """
            SELECT id, first_name, last_name, email, role, plan_type, status,
                   failed_login_count, locked_until, last_login_at, quota_reset_at,
                   weekly_usage_count, lifetime_usage_count, premium_valid_from, premium_valid_until, created_at,
                   EXISTS (
                       SELECT 1 FROM user_security_questions
                       WHERE user_security_questions.user_id = users.id
                   ) AS security_questions_configured
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
            SELECT id, first_name, last_name, email, role, plan_type, status, failed_login_count,
                   locked_until, last_login_at, quota_reset_at, weekly_usage_count,
                   lifetime_usage_count, premium_valid_from, premium_valid_until, created_at,
                   EXISTS (
                       SELECT 1 FROM user_security_questions
                       WHERE user_security_questions.user_id = users.id
                   ) AS security_questions_configured
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
            SELECT id, first_name, last_name, email, role, plan_type, status, failed_login_count,
                   locked_until, last_login_at, quota_reset_at, weekly_usage_count,
                   lifetime_usage_count, premium_valid_from, premium_valid_until, created_at,
                   EXISTS (
                       SELECT 1 FROM user_security_questions
                       WHERE user_security_questions.user_id = users.id
                   ) AS security_questions_configured
            FROM users
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()

    return [user_to_dict(row) for row in rows]


def set_user_role(database_path: Path, user_id: int, role: str) -> None:
    normalized_role = role.strip().upper()
    if normalized_role not in ("ADMIN", "PREMIUM", "FREE"):
        raise AuthError("Invalid role.")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE users SET role = ?, plan_type = ? WHERE id = ?",
            (normalized_role, normalized_role, user_id),
        )


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


def verify_user_password(database_path: Path, user_id: int, password: str) -> None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    if row is None or not check_password_hash(row[0], password):
        raise AuthError("Current password is incorrect.")


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
        admins = connection.execute("SELECT COUNT(*) FROM users WHERE role = 'ADMIN'").fetchone()[0]
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


def usage_week_key(now: datetime | None = None) -> str:
    if now is None:
        now = utc_now()
    year, week, _ = now.isocalendar()
    return f"{year}-{week:02d}"


def next_weekly_reset(now: datetime | None = None) -> datetime:
    if now is None:
        now = utc_now()
    start_of_week = now - timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
    return start_of_week + timedelta(days=7)


def get_setting(database_path: Path, key: str, default: str | None = None) -> str | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(database_path: Path, key: str, value: str) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def ensure_default_settings(database_path: Path) -> None:
    defaults = {
        "guest_weekly_limit": "5",
        "free_weekly_limit": "10",
        "premium_weekly_limit": "0",
        "last_weekly_reset": "1970-01-01T00:00:00+00:00",
    }
    with sqlite3.connect(database_path) as connection:
        for key, value in defaults.items():
            connection.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )


def get_weekly_usage(database_path: Path, user_id: int | None = None, anonymous_id: str | None = None, ip_address: str = "") -> int:
    week_key = usage_week_key()
    with sqlite3.connect(database_path) as connection:
        if user_id is not None:
            row = connection.execute(
                "SELECT SUM(execution_count) AS total FROM usage_tracking WHERE user_id = ? AND usage_week = ?",
                (user_id, week_key),
            ).fetchone()
        elif anonymous_id:
            row = connection.execute(
                "SELECT SUM(execution_count) AS total FROM usage_tracking WHERE anonymous_id = ? AND ip_address = ? AND usage_week = ?",
                (anonymous_id, ip_address, week_key),
            ).fetchone()
        else:
            return 0
    return int(row[0] or 0)


def get_weekly_total_usage(database_path: Path) -> int:
    week_key = usage_week_key()
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT SUM(execution_count) AS total FROM usage_tracking WHERE usage_week = ?",
            (week_key,),
        ).fetchone()
    return int(row[0] or 0)


def get_lifetime_usage(database_path: Path, user_id: int | None = None, anonymous_id: str | None = None, ip_address: str = "") -> int:
    with sqlite3.connect(database_path) as connection:
        if user_id is not None:
            row = connection.execute(
                "SELECT SUM(execution_count) AS total FROM usage_tracking WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        elif anonymous_id:
            row = connection.execute(
                "SELECT SUM(execution_count) AS total FROM usage_tracking WHERE anonymous_id = ? AND ip_address = ?",
                (anonymous_id, ip_address),
            ).fetchone()
        else:
            return 0
    return int(row[0] or 0)


def get_tool_usage_breakdown(database_path: Path, user_id: int | None = None, week_key: str | None = None) -> dict[str, int]:
    if week_key is None:
        week_key = usage_week_key()
    with sqlite3.connect(database_path) as connection:
        if user_id is not None:
            rows = connection.execute(
                "SELECT tool_name, SUM(execution_count) AS total FROM usage_tracking WHERE user_id = ? AND usage_week = ? GROUP BY tool_name",
                (user_id, week_key),
            ).fetchall()
        else:
            return {}
    return {row[0]: int(row[1]) for row in rows}


def reset_user_weekly_usage(database_path: Path, user_id: int) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE users SET weekly_usage_count = 0, quota_reset_at = ? WHERE id = ?",
            (next_weekly_reset().isoformat(), user_id),
        )


def reset_all_weekly_usage(database_path: Path) -> None:
    reset_at = next_weekly_reset().isoformat()
    now = utc_now().isoformat()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE users SET weekly_usage_count = 0, quota_reset_at = ?",
            (reset_at,),
        )
        connection.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("last_weekly_reset", now),
        )


def get_total_usage(database_path: Path, user_id: int | None = None, anonymous_id: str | None = None, ip_address: str = "") -> int:
    return get_weekly_usage(database_path, user_id=user_id, anonymous_id=anonymous_id, ip_address=ip_address)


def record_tool_usage(
    database_path: Path,
    tool_name: str,
    user_id: int | None = None,
    anonymous_id: str | None = None,
    ip_address: str = "",
    count: int = 1,
) -> None:
    if user_id is None and not anonymous_id:
        raise ValueError("anonymous_id is required for guest usage tracking")

    week_key = usage_week_key()
    execution_date = utc_now().isoformat()
    with sqlite3.connect(database_path) as connection:
        if user_id is not None:
            row = connection.execute(
                "SELECT id FROM usage_tracking WHERE user_id = ? AND tool_name = ? AND usage_week = ?",
                (user_id, tool_name, week_key),
            ).fetchone()
            if row:
                connection.execute(
                    "UPDATE usage_tracking SET execution_count = execution_count + ?, last_execution_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (count, row[0]),
                )
            else:
                connection.execute(
                    "INSERT INTO usage_tracking (user_id, anonymous_id, ip_address, tool_name, usage_date, usage_week, execution_count, last_execution_at) VALUES (?, NULL, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (user_id, ip_address, tool_name, execution_date, week_key, count),
                )
            connection.execute(
                "UPDATE users SET weekly_usage_count = weekly_usage_count + ?, lifetime_usage_count = lifetime_usage_count + ? WHERE id = ?",
                (count, count, user_id),
            )
        else:
            row = connection.execute(
                "SELECT id FROM usage_tracking WHERE anonymous_id = ? AND ip_address = ? AND tool_name = ? AND usage_week = ?",
                (anonymous_id, ip_address, tool_name, week_key),
            ).fetchone()
            if row:
                connection.execute(
                    "UPDATE usage_tracking SET execution_count = execution_count + ?, last_execution_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (count, row[0]),
                )
            else:
                connection.execute(
                    "INSERT INTO usage_tracking (user_id, anonymous_id, ip_address, tool_name, usage_date, usage_week, execution_count, last_execution_at) VALUES (NULL, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (anonymous_id, ip_address, tool_name, execution_date, week_key, count),
                )


def get_usage_summary(database_path: Path, user_id: int | None = None, anonymous_id: str | None = None, ip_address: str = "") -> dict[str, int]:
    total = get_total_usage(database_path, user_id=user_id, anonymous_id=anonymous_id, ip_address=ip_address)
    return {
        "total": total,
    }


def user_to_dict(user: sqlite3.Row) -> dict[str, str | int | bool | None]:
    first_name = user["first_name"] or ""
    last_name = user["last_name"] or ""
    full_name = f"{first_name} {last_name}".strip()
    locked_until = user["locked_until"] if "locked_until" in user.keys() else None
    locked_until_date = parse_timestamp(locked_until)
    role_value = user["role"] if "role" in user.keys() else "FREE"
    status_value = user["status"] if "status" in user.keys() else "ACTIVE"
    premium_valid_from_raw = user["premium_valid_from"] if "premium_valid_from" in user.keys() else None
    premium_valid_until_raw = user["premium_valid_until"] if "premium_valid_until" in user.keys() else None
    premium_valid_from = parse_timestamp(premium_valid_from_raw)
    premium_valid_until = parse_timestamp(premium_valid_until_raw)
    now = utc_now()
    premium_is_active = bool(
        role_value == "PREMIUM" and premium_valid_until is not None and premium_valid_until >= now
    )
    if role_value == "PREMIUM" and premium_valid_until is not None:
        if premium_valid_until >= now:
            days_left = max(0, int((premium_valid_until - now).days))
            premium_status_message = (
                "Expires today" if days_left == 0 else f"Expires in {days_left} day{'s' if days_left != 1 else ''}"
            )
        else:
            premium_status_message = f"Expired on {premium_valid_until.date().isoformat()}"
    else:
        premium_status_message = ""
    return {
        "id": user["id"],
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name or user["email"],
        "email": user["email"],
        "role": role_value,
        "plan_type": user["plan_type"] if "plan_type" in user.keys() else role_value,
        "status": status_value,
        "is_admin": role_value == "ADMIN",
        "is_premium": role_value == "PREMIUM",
        "is_free": role_value == "FREE",
        "failed_login_count": user["failed_login_count"] if "failed_login_count" in user.keys() else 0,
        "locked_until": locked_until,
        "is_locked": bool(locked_until_date and locked_until_date > utc_now()),
        "last_login_at": user["last_login_at"] if "last_login_at" in user.keys() else None,
        "quota_reset_at": user["quota_reset_at"] if "quota_reset_at" in user.keys() else None,
        "premium_valid_from": premium_valid_from_raw,
        "premium_valid_until": premium_valid_until_raw,
        "premium_valid_from_display": premium_valid_from.date().isoformat() if premium_valid_from else None,
        "premium_valid_until_display": premium_valid_until.date().isoformat() if premium_valid_until else None,
        "premium_valid_until_formatted": premium_valid_until.strftime("%d-%b-%Y") if premium_valid_until else None,
        "premium_is_active": premium_is_active,
        "premium_status_message": premium_status_message,
        "security_questions_configured": bool(
            user["security_questions_configured"] if "security_questions_configured" in user.keys() else False
        ),
        "weekly_usage_count": int(user["weekly_usage_count"] or 0) if "weekly_usage_count" in user.keys() else 0,
        "lifetime_usage_count": int(user["lifetime_usage_count"] or 0) if "lifetime_usage_count" in user.keys() else 0,
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

    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters.")

    checks = (
        (r"[A-Z]", "one uppercase letter"),
        (r"[a-z]", "one lowercase letter"),
        (r"\d", "one number"),
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
