"""Add memories table and thread summary/temporary columns

Revision ID: d39e56f13c55
Revises: c29d45e02b44
Create Date: 2026-09-04 19:30:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd39e56f13c55'
down_revision: str | None = 'c29d45e02b44'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

memory_category = postgresql.ENUM(
    'preference', 'fact', 'goal', 'skill', 'interest', 'project_context', 'other',
    name='memory_category',
    create_type=False,
)


def upgrade() -> None:
    # 1. Create memory_category enum safely
    memory_category.create(op.get_bind(), checkfirst=True)

    # 2. Create memories table
    op.create_table(
        'memories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('category', memory_category, nullable=False, server_default='other'),
        sa.Column('key', sa.String(255), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('source', sa.String(255), nullable=False, server_default='conversation'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('importance', sa.Float(), nullable=False, server_default='0.7'),
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # 3. Create indexes for memories
    op.create_index('ix_memories_user_id', 'memories', ['user_id'])
    op.create_index('ix_memories_project_id', 'memories', ['project_id'])
    op.create_index('ix_memories_category', 'memories', ['category'])
    op.create_index('ix_memories_is_active', 'memories', ['is_active'])
    op.create_index('ix_memories_user_active_updated', 'memories', ['user_id', 'is_active', 'updated_at'])
    op.create_index('ix_memories_user_project_active', 'memories', ['user_id', 'project_id', 'is_active'])
    op.create_index('ix_memories_user_category_active', 'memories', ['user_id', 'category', 'is_active'])
    op.create_index('ix_memories_user_key', 'memories', ['user_id', 'key'])

    # 4. Add summary and temporary columns to threads
    op.add_column('threads', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('threads', sa.Column('summarized_message_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('threads', sa.Column('summary_updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('threads', sa.Column('is_temporary', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    # 1. Remove columns from threads
    op.drop_column('threads', 'is_temporary')
    op.drop_column('threads', 'summary_updated_at')
    op.drop_column('threads', 'summarized_message_id')
    op.drop_column('threads', 'summary')

    # 2. Drop memories table
    op.drop_table('memories')

    # 3. Drop memory_category enum
    memory_category.drop(op.get_bind(), checkfirst=True)
