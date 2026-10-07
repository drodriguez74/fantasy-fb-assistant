"""add espn_projection to bet_picks

Revision ID: f79e92683ff7
Revises: 03c72f4e93d0
Create Date: 2026-10-06 20:50:16.461646

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f79e92683ff7'
down_revision: Union[str, None] = '03c72f4e93d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bet_picks", sa.Column("espn_projection", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("bet_picks", "espn_projection")