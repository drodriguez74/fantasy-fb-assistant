"""Fix stale scoringtype enum labels

Revision ID: 099d20c27ac2
Revises: f9c3eac2171a
Create Date: 2026-08-23 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '099d20c27ac2'
down_revision: Union[str, None] = 'f9c3eac2171a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Databases whose league_scoring/scoring_presets tables predate this
# migration (created via Base.metadata.create_all() and later reconciled
# with `alembic stamp head` rather than a real run of f9c3eac2171a) have a
# `scoringtype` Postgres enum type with the old member-NAME-cased labels
# (HALF_PPR, STANDARD, CUSTOM). The ORM's values_callable sends the member
# *value* ('Half_PPR', 'Standard', 'Custom'), so every non-PPR write fails
# with InvalidTextRepresentation. A genuinely fresh run of f9c3eac2171a
# already creates the type with the correct labels, so guard each rename
# with a pg_enum existence check to stay a no-op there.
_RENAMES = [
    ('HALF_PPR', 'Half_PPR'),
    ('STANDARD', 'Standard'),
    ('CUSTOM', 'Custom'),
]


def upgrade() -> None:
    for old, new in _RENAMES:
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumtypid = 'scoringtype'::regtype
                      AND enumlabel = '{old}'
                ) THEN
                    ALTER TYPE scoringtype RENAME VALUE '{old}' TO '{new}';
                END IF;
            END
            $$;
        """)


def downgrade() -> None:
    for old, new in _RENAMES:
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumtypid = 'scoringtype'::regtype
                      AND enumlabel = '{new}'
                ) THEN
                    ALTER TYPE scoringtype RENAME VALUE '{new}' TO '{old}';
                END IF;
            END
            $$;
        """)
