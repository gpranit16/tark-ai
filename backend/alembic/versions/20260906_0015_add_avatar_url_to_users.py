"""Add avatar_url to users table

Revision ID: e1f4a9b2c3d4
Revises: d94e13f0a856
Create Date: 2026-09-06 02:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f4a9b2c3d4'
down_revision: str | None = 'd94e13f0a856'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('avatar_url', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'avatar_url')
