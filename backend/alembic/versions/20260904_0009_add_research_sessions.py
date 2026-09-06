"""Add research_sessions table for Phase 10 Deep Research

Revision ID: e48f67a24d66
Revises: d39e56f13c55
Create Date: 2026-09-04 21:35:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e48f67a24d66'
down_revision: str | None = 'd39e56f13c55'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'research_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('thread_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('threads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('plan', postgresql.JSONB(), nullable=True),
        sa.Column('task_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('duration_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('research_metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_research_sessions_thread_id', 'research_sessions', ['thread_id'])
    op.create_index('ix_research_sessions_user_id', 'research_sessions', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_research_sessions_user_id', 'research_sessions')
    op.drop_index('ix_research_sessions_thread_id', 'research_sessions')
    op.drop_table('research_sessions')
