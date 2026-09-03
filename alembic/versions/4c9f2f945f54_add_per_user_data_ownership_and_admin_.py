"""add per-user data ownership and admin flag

Revision ID: 4c9f2f945f54
Revises: f5301819b6e8
Create Date: 2026-09-04 00:25:36.278406

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '4c9f2f945f54'
down_revision: Union[str, None] = 'f5301819b6e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OWNED_TABLES = ("campaigns", "landing_pages", "offers", "tracking_domains", "traffic_sources")


def upgrade() -> None:
    # New column has a safe default, so it can go straight to NOT NULL.
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    # user_id columns can't have a static default (must point at a real row), so
    # add them nullable, backfill, then tighten to NOT NULL.
    for table in OWNED_TABLES:
        op.add_column(table, sa.Column("user_id", sa.Integer(), nullable=True))
        op.create_foreign_key(None, table, "users", ["user_id"], ["id"])

    conn = op.get_bind()

    # Every row that predates per-user ownership gets attributed to the env-var
    # admin account (get-or-create it here — app/routers/login.py does the same
    # get-or-create on login, so this is just making sure it exists in time to
    # own this pre-existing data too).
    from app.config import ADMIN_USERNAME
    from app.passwords import hash_password

    existing = conn.execute(
        text("SELECT id FROM users WHERE username = :u"), {"u": ADMIN_USERNAME}
    ).first()
    if existing:
        admin_id = existing[0]
        conn.execute(text("UPDATE users SET is_admin = TRUE WHERE id = :id"), {"id": admin_id})
    else:
        result = conn.execute(
            text(
                "INSERT INTO users (username, password_hash, is_admin, created_at) "
                "VALUES (:u, :p, TRUE, now()) RETURNING id"
            ),
            # This hash is never used to authenticate — the break-glass admin login
            # always checks ADMIN_PASSWORD from the environment, not this row.
            {"u": ADMIN_USERNAME, "p": hash_password(secrets.token_urlsafe(32))},
        )
        admin_id = result.scalar()

    for table in OWNED_TABLES:
        conn.execute(text(f"UPDATE {table} SET user_id = :id WHERE user_id IS NULL"), {"id": admin_id})
        op.alter_column(table, "user_id", nullable=False)

    op.alter_column("users", "is_admin", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_admin")
    for table in OWNED_TABLES:
        op.drop_constraint(None, table, type_="foreignkey")
        op.drop_column(table, "user_id")
