"""Add blog posts table

Revision ID: 8f2a4c5d6e91
Revises: 7a4b2d1e5f89
Create Date: 2025-08-14 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8f2a4c5d6e91'
down_revision = '7a4b2d1e5f89'
branch_labels = None
depends_on = None


def upgrade():
    # blog_posts was already created by the initial migration (0b92d89d8227).
    # This migration originally re-issued a full create_table for it, which
    # is a guaranteed "relation already exists" failure on a fresh database.
    # The only real, new-to-this-migration difference vs. the initial schema
    # is two columns (`featured`, `author`) that the BlogPost model has but
    # 0b92d89d8227 never created -- add just those instead of recreating the
    # whole table.
    op.add_column('blog_posts', sa.Column('featured', sa.Boolean(), nullable=True, server_default=sa.false()))
    op.add_column('blog_posts', sa.Column('author', sa.String(), nullable=True, server_default='AI Assistant'))


def downgrade():
    op.drop_column('blog_posts', 'author')
    op.drop_column('blog_posts', 'featured')