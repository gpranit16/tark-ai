"""Add parsed_documents table

Revision ID: a05b38d99f12
Revises: f3278e38c273
Create Date: 2026-09-04 01:50:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a05b38d99f12'
down_revision: str | None = 'f3278e38c273'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'parsed_documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('file_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('parsed_content', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('word_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ocr_used', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_parsed_documents_created_at'), 'parsed_documents', ['created_at'], unique=False)
    op.create_index(op.f('ix_parsed_documents_file_id'), 'parsed_documents', ['file_id'], unique=True)
    op.create_index(op.f('ix_parsed_documents_status'), 'parsed_documents', ['status'], unique=False)
    op.create_index(op.f('ix_parsed_documents_user_id'), 'parsed_documents', ['user_id'], unique=False)
    op.create_index('ix_parsed_documents_user_status', 'parsed_documents', ['user_id', 'status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_parsed_documents_user_status', table_name='parsed_documents')
    op.drop_index(op.f('ix_parsed_documents_user_id'), table_name='parsed_documents')
    op.drop_index(op.f('ix_parsed_documents_status'), table_name='parsed_documents')
    op.drop_index(op.f('ix_parsed_documents_file_id'), table_name='parsed_documents')
    op.drop_index(op.f('ix_parsed_documents_created_at'), table_name='parsed_documents')
    op.drop_table('parsed_documents')
