"""fix game_situation now() server defaults to use func.now()

The app/models/game_situation.py columns were declared with
server_default="now()" (a bare Python string) instead of
server_default=func.now(). On Postgres this happens to render to the
same DDL text (`DEFAULT now()`) as the original
469a1e42f57f_add_enhanced_game_situation_models.py migration already
used (server_default=sa.text('now()')), so there is no observable
schema drift on Postgres and this migration is a documented no-op
there. The bug was purely at the SQLAlchemy/ORM level: a bare string
server_default is handled differently than a SQL construct in some
insert-compilation paths, and on SQLite (which this project's test
suite runs against, per tests/conftest.py) it raised
`ValueError: Invalid isoformat string: 'now()'` on any insert that
didn't manually set the timestamp. This migration re-applies the
server_default explicitly via sa.text('now()') (equivalent to
func.now()) for documentation/consistency and so future
`alembic revision --autogenerate` runs don't flag drift, without
changing the actual Postgres default value.

Revision ID: 80e42eca85d0
Revises: 099d20c27ac2
Create Date: 2026-08-23 10:01:58.160791

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '80e42eca85d0'
down_revision: Union[str, None] = '099d20c27ac2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column) pairs whose server_default needs to be re-declared as
# sa.text('now()') / func.now() instead of the bare string "now()" that
# app/models/game_situation.py used to declare at the Python level.
_TIMESTAMP_COLUMNS = [
    ("game_situations", "created_at"),
    ("game_situations", "updated_at"),
    ("defensive_rankings", "created_at"),
    ("defensive_rankings", "updated_at"),
    ("venue_data", "created_at"),
    ("venue_data", "updated_at"),
    ("weather_history", "created_at"),
    ("situational_trends", "created_at"),
    ("situational_trends", "updated_at"),
    ("situational_trends", "last_updated"),
]


def upgrade() -> None:
    for table_name, column_name in _TIMESTAMP_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            existing_nullable=True,
        )


def downgrade() -> None:
    # Same server_default value ("now()"), so downgrading restores the
    # identical DDL; nothing to actually revert on the database side.
    for table_name, column_name in _TIMESTAMP_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            existing_nullable=True,
        )