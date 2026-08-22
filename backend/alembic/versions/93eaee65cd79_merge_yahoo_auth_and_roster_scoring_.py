"""merge yahoo auth and roster/scoring settings migration heads

Revision ID: 93eaee65cd79
Revises: 4f785f034efe, 9c1a2f6b3d47
Create Date: 2026-08-22 11:36:50.751181

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '93eaee65cd79'
down_revision: Union[str, None] = ('4f785f034efe', '9c1a2f6b3d47')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass