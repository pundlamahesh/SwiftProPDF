"""Track browser page hits.

Revision ID: 20260619_0002
Revises: 20260614_0001
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa


revision = "20260619_0002"
down_revision = "20260614_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "browser_hits" not in tables:
        op.create_table(
            "browser_hits",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("anonymous_id", sa.Text()),
            sa.Column("ip_address", sa.Text(), nullable=False, server_default=""),
            sa.Column("path", sa.Text(), nullable=False),
            sa.Column("user_agent", sa.Text(), nullable=False, server_default=""),
            sa.Column("hit_date", sa.Text(), nullable=False),
            sa.Column("hit_week", sa.Text(), nullable=False),
            sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_hit_at", sa.Text()),
            sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    _create_index_if_missing(
        "browser_hits",
        "browser_hits_user_path_date_idx",
        ["user_id", "path", "hit_date"],
        unique=True,
        sqlite_where=sa.text("user_id IS NOT NULL"),
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    _create_index_if_missing(
        "browser_hits",
        "browser_hits_guest_path_date_idx",
        ["anonymous_id", "ip_address", "path", "hit_date"],
        unique=True,
        sqlite_where=sa.text("user_id IS NULL"),
        postgresql_where=sa.text("user_id IS NULL"),
    )


def downgrade() -> None:
    _drop_index_if_exists("browser_hits", "browser_hits_guest_path_date_idx")
    _drop_index_if_exists("browser_hits", "browser_hits_user_path_date_idx")
    if "browser_hits" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("browser_hits")


def _index_names(table_name: str) -> set[str]:
    if table_name not in set(sa.inspect(op.get_bind()).get_table_names()):
        return set()
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
