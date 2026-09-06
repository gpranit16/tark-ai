"""Add auth_tokens table and is_verified to users

Revision ID: d94e13f0a856
Revises: c83d02e9f745
Create Date: 2026-09-06 01:05:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd94e13f0a856'
down_revision: str | None = 'c83d02e9f745'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add is_verified to users
    op.add_column('users', sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.text('false')))

    # 2. Create auth_tokens table
    op.create_table(
        'auth_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('token_type', sa.String(length=50), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_used', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_auth_tokens_user_id', 'auth_tokens', ['user_id'], unique=False)
    op.create_index('ix_auth_tokens_token_hash', 'auth_tokens', ['token_hash'], unique=False)
    op.create_index('ix_auth_tokens_token_type', 'auth_tokens', ['token_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_auth_tokens_token_type', table_name='auth_tokens')
    op.drop_index('ix_auth_tokens_token_hash', table_name='auth_tokens')
    op.drop_index('ix_auth_tokens_user_id', table_name='auth_tokens')
    op.drop_table('auth_tokens')
    op.drop_column('users', 'is_verified')
