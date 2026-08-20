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
    # Create blog_posts table
    op.create_table('blog_posts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('slug', sa.String(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('source_urls', sa.Text(), nullable=True),
    sa.Column('perspectives_count', sa.Integer(), default=5),
    sa.Column('consensus_score', sa.Integer(), nullable=True),
    sa.Column('tags', sa.String(), nullable=True),
    sa.Column('category', sa.String(), nullable=True),
    sa.Column('is_published', sa.Boolean(), default=False),
    sa.Column('featured', sa.Boolean(), default=False),
    sa.Column('publish_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('author', sa.String(), default='AI Assistant'),
    sa.Column('created_by_ai', sa.Boolean(), default=True),
    sa.Column('ai_model_used', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_blog_posts_id'), 'blog_posts', ['id'], unique=False)
    op.create_index(op.f('ix_blog_posts_slug'), 'blog_posts', ['slug'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_blog_posts_slug'), table_name='blog_posts')
    op.drop_index(op.f('ix_blog_posts_id'), table_name='blog_posts')
    op.drop_table('blog_posts')