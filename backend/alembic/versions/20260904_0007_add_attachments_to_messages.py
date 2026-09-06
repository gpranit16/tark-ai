"""Add attachments column to messages table

Revision ID: c29d45e02b44
Revises: b18c94e01a33
Create Date: 2026-09-04 17:30:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c29d45e02b44'
down_revision: str | None = 'b18c94e01a33'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('attachments', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]')
    )


def downgrade() -> None:
    op.drop_column('messages', 'attachments')
