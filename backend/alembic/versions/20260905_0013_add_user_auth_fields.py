"""Add user auth fields (email, password_hash, name, is_active)

Revision ID: c83d02e9f745
Revises: b72c91d8e634
Create Date: 2026-09-05 18:30:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'c83d02e9f745'
down_revision: str | None = 'b72c91d8e634'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('email', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('name', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.create_index('ix_users_email', 'users', ['email'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_email', table_name='users')
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'name')
    op.drop_column('users', 'password_hash')
    op.drop_column('users', 'email')
