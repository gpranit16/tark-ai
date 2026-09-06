"""Add user_settings table

Revision ID: b72c91d8e634
Revises: a61b89c4d512
Create Date: 2026-09-05 14:20:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b72c91d8e634'
down_revision: str | None = 'a61b89c4d512'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

conversation_mode = postgresql.ENUM(
    'fast',
    'normal',
    'reasoning',
    'rag',
    'deep_research',
    'coding',
    name='conversation_mode',
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        'user_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False, server_default='Developer'),
        sa.Column('theme', sa.String(length=20), nullable=False, server_default='dark'),
        sa.Column('language', sa.String(length=20), nullable=False, server_default='en'),
        sa.Column('default_mode', conversation_mode, nullable=False, server_default='normal'),
        sa.Column('chat_density', sa.String(length=20), nullable=False, server_default='comfortable'),
        sa.Column('animations_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('enter_to_send', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('streaming_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('show_timestamps', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('auto_scroll', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('compact_messages', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('show_citations', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('show_attachment_previews', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('smart_memory_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('explicit_memory_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('default_retrieval_mode', sa.String(length=20), nullable=False, server_default='hybrid'),
        sa.Column('rag_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('document_context_scope', sa.String(length=20), nullable=False, server_default='project'),
        sa.Column('tool_preferences', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('crag_debug_mode', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('show_crag_pipeline', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('detailed_streaming_events', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index('ix_user_settings_user_id', 'user_settings', ['user_id'], unique=True)
    op.create_index(op.f('ix_user_settings_created_at'), 'user_settings', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_settings_created_at'), table_name='user_settings')
    op.drop_index('ix_user_settings_user_id', table_name='user_settings')
    op.drop_table('user_settings')
