"""merge scoring-rules and yahoo-auth migration heads

Revision ID: f97bb25185e9
Revises: 93eaee65cd79, c2d6a8f1b3e5
Create Date: 2026-08-22 11:46:58.530233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f97bb25185e9'
down_revision: Union[str, None] = ('93eaee65cd79', 'c2d6a8f1b3e5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass