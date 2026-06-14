"""Create initial application schema.

Revision ID: 20260614_0001
Revises:
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa


revision = "20260614_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("first_name", sa.Text(), nullable=False, server_default=""),
            sa.Column("last_name", sa.Text(), nullable=False, server_default=""),
            sa.Column("email", sa.Text(), nullable=False, unique=True),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("role", sa.Text(), nullable=False, server_default="FREE"),
            sa.Column("plan_type", sa.Text(), nullable=False, server_default="FREE"),
            sa.Column("status", sa.Text(), nullable=False, server_default="ACTIVE"),
            sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("locked_until", sa.Text()),
            sa.Column("last_login_at", sa.Text()),
            sa.Column("quota_reset_at", sa.Text()),
            sa.Column("weekly_usage_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("lifetime_usage_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("premium_valid_from", sa.Text()),
            sa.Column("premium_valid_until", sa.Text()),
            sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    else:
        _add_missing_columns(
            inspector,
            "users",
            {
                "first_name": sa.Column("first_name", sa.Text(), nullable=False, server_default=""),
                "last_name": sa.Column("last_name", sa.Text(), nullable=False, server_default=""),
                "role": sa.Column("role", sa.Text(), nullable=False, server_default="FREE"),
                "plan_type": sa.Column("plan_type", sa.Text(), nullable=False, server_default="FREE"),
                "status": sa.Column("status", sa.Text(), nullable=False, server_default="ACTIVE"),
                "failed_login_count": sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
                "locked_until": sa.Column("locked_until", sa.Text()),
                "last_login_at": sa.Column("last_login_at", sa.Text()),
                "quota_reset_at": sa.Column("quota_reset_at", sa.Text()),
                "weekly_usage_count": sa.Column("weekly_usage_count", sa.Integer(), nullable=False, server_default="0"),
                "lifetime_usage_count": sa.Column("lifetime_usage_count", sa.Integer(), nullable=False, server_default="0"),
                "premium_valid_from": sa.Column("premium_valid_from", sa.Text()),
                "premium_valid_until": sa.Column("premium_valid_until", sa.Text()),
            },
        )

    if "audit_events" not in tables:
        op.create_table(
            "audit_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("details", sa.Text(), nullable=False, server_default=""),
            sa.Column("ip_address", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if "usage_tracking" not in tables:
        op.create_table(
            "usage_tracking",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("anonymous_id", sa.Text()),
            sa.Column("ip_address", sa.Text(), nullable=False, server_default=""),
            sa.Column("tool_name", sa.Text(), nullable=False),
            sa.Column("usage_date", sa.Text(), nullable=False),
            sa.Column("usage_week", sa.Text(), nullable=False),
            sa.Column("execution_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_execution_at", sa.Text()),
            sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    else:
        _add_missing_columns(
            inspector,
            "usage_tracking",
            {
                "usage_date": sa.Column("usage_date", sa.Text(), nullable=False, server_default=""),
                "usage_week": sa.Column("usage_week", sa.Text(), nullable=False, server_default=""),
            },
        )

    if "user_security_questions" not in tables:
        op.create_table(
            "user_security_questions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
            sa.Column("date_of_birth_hash", sa.Text(), nullable=False),
            sa.Column("current_city_hash", sa.Text(), nullable=False),
            sa.Column("failed_reset_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reset_locked_until", sa.Text()),
            sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    else:
        _add_missing_columns(
            inspector,
            "user_security_questions",
            {
                "failed_reset_attempts": sa.Column("failed_reset_attempts", sa.Integer(), nullable=False, server_default="0"),
                "reset_locked_until": sa.Column("reset_locked_until", sa.Text()),
            },
        )

    if "user_sessions" not in tables:
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("session_token", sa.Text(), nullable=False, unique=True),
            sa.Column("user_agent", sa.Text(), nullable=False, server_default=""),
            sa.Column("ip_address", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("last_seen_at", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.Text(), nullable=False),
        )

    if "settings" not in tables:
        op.create_table(
            "settings",
            sa.Column("key", sa.Text(), primary_key=True),
            sa.Column("value", sa.Text(), nullable=False),
        )

    _drop_index_if_exists("usage_tracking", "usage_tracking_user_tool_idx")
    _drop_index_if_exists("usage_tracking", "usage_tracking_guest_tool_idx")
    _create_index_if_missing(
        "user_sessions",
        "user_sessions_user_expires_idx",
        ["user_id", "expires_at"],
    )
    _create_index_if_missing(
        "usage_tracking",
        "usage_tracking_user_tool_week_idx",
        ["user_id", "tool_name", "usage_week"],
        unique=True,
        sqlite_where=sa.text("user_id IS NOT NULL"),
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    _create_index_if_missing(
        "usage_tracking",
        "usage_tracking_guest_tool_week_idx",
        ["anonymous_id", "ip_address", "tool_name", "usage_week"],
        unique=True,
        sqlite_where=sa.text("user_id IS NULL"),
        postgresql_where=sa.text("user_id IS NULL"),
    )


def downgrade() -> None:
    _drop_index_if_exists("usage_tracking", "usage_tracking_guest_tool_week_idx")
    _drop_index_if_exists("usage_tracking", "usage_tracking_user_tool_week_idx")
    _drop_index_if_exists("user_sessions", "user_sessions_user_expires_idx")
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in (
        "settings",
        "user_sessions",
        "user_security_questions",
        "usage_tracking",
        "audit_events",
        "users",
    ):
        if table_name in tables:
            op.drop_table(table_name)


def _add_missing_columns(inspector, table_name: str, columns: dict[str, sa.Column]) -> None:
    existing = {column["name"] for column in inspector.get_columns(table_name)}
    for column_name, column in columns.items():
        if column_name not in existing:
            op.add_column(table_name, column)


def _index_names(table_name: str) -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    }


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    if index_name in _index_names(table_name):
        op.drop_index(index_name, table_name=table_name)


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], **kwargs) -> None:
    if index_name not in _index_names(table_name):
        op.create_index(index_name, table_name, columns, **kwargs)
