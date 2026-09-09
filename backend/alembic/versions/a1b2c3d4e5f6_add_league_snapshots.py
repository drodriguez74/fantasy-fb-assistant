"""add league_snapshots (stale-while-revalidate cache for slow ESPN/Yahoo reads)

One row per (user_league_id, kind) holding the last-computed JSON response
body for an expensive per-league endpoint (This Week, roster analysis,
standings). See app/services/snapshot_cache.py.

Revision ID: a1b2c3d4e5f6
Revises: 80e42eca85d0
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '80e42eca85d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "league_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_league_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_league_id"], ["user_leagues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_league_id", "kind", name="uq_league_snapshot_league_kind"),
    )
    op.create_index(
        op.f("ix_league_snapshots_user_league_id"),
        "league_snapshots",
        ["user_league_id"],
        unique=False,
    )
    op.create_index(op.f("ix_league_snapshots_id"), "league_snapshots", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_league_snapshots_id"), table_name="league_snapshots")
    op.drop_index(op.f("ix_league_snapshots_user_league_id"), table_name="league_snapshots")
    op.drop_table("league_snapshots")
