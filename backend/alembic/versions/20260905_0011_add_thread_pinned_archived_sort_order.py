"""Add is_pinned, is_archived, sort_order to threads table

Revision ID: a61b89c4d512
Revises: f59a78b39c77
Create Date: 2026-09-05 01:30:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'a61b89c4d512'
down_revision: str | None = 'f59a78b39c77'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('threads', sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('threads', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('threads', sa.Column('sort_order', sa.Integer(), nullable=False, server_default=sa.text('0')))
    op.create_index('ix_threads_user_archived_pinned', 'threads', ['user_id', 'is_archived', 'is_pinned', 'sort_order'])


def downgrade() -> None:
    op.drop_index('ix_threads_user_archived_pinned', table_name='threads')
    op.drop_column('threads', 'sort_order')
    op.drop_column('threads', 'is_archived')
    op.drop_column('threads', 'is_pinned')
