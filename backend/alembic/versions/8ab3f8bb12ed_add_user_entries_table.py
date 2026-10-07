"""add user_entries table

Revision ID: 8ab3f8bb12ed
Revises: f79e92683ff7
Create Date: 2026-10-07 00:05:23.187582

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8ab3f8bb12ed'
down_revision: Union[str, None] = 'f79e92683ff7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("platform", sa.String(), nullable=False, server_default="prizepicks"),
        sa.Column("entry_type", sa.String(), nullable=False),
        sa.Column("stake", sa.Float(), nullable=False),
        sa.Column("to_win", sa.Float(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("legs", sa.JSON(), nullable=False),
        sa.Column("est_hit_prob", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("payout", sa.Float(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
    )
    for col in ("id", "user_id", "season", "week", "status"):
        op.create_index(f"ix_user_entries_{col}", "user_entries", [col])


def downgrade() -> None:
    for col in ("id", "user_id", "season", "week", "status"):
        op.drop_index(f"ix_user_entries_{col}", table_name="user_entries")
    op.drop_table("user_entries")
