"""Add document_chunks table

Revision ID: b18c94e01a33
Revises: a05b38d99f12
Create Date: 2026-09-04 02:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision: str = 'b18c94e01a33'
down_revision: str | None = 'a05b38d99f12'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Ensure pgvector extension is enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table(
        'document_chunks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('file_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('parsed_document_id', sa.UUID(), nullable=True),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('embedding', Vector(1024), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parsed_document_id'], ['parsed_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index(op.f('ix_document_chunks_created_at'), 'document_chunks', ['created_at'], unique=False)
    op.create_index(op.f('ix_document_chunks_file_id'), 'document_chunks', ['file_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_user_id'), 'document_chunks', ['user_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_project_id'), 'document_chunks', ['project_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_parsed_document_id'), 'document_chunks', ['parsed_document_id'], unique=False)
    op.create_index('ix_document_chunks_user_file', 'document_chunks', ['user_id', 'file_id'], unique=False)
    op.create_index('ix_document_chunks_user_project', 'document_chunks', ['user_id', 'project_id'], unique=False)
    op.create_index('ix_document_chunks_file_chunk_idx', 'document_chunks', ['file_id', 'chunk_index'], unique=True)

    # Vector index for cosine similarity
    op.execute("CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding ON document_chunks USING hnsw (embedding vector_cosine_ops);")

    # Full-text search GIN index for PostgreSQL-native keyword search
    op.execute("CREATE INDEX IF NOT EXISTS ix_document_chunks_content_tsv ON document_chunks USING gin (to_tsvector('english', content));")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsv;")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding;")
    op.drop_index('ix_document_chunks_file_chunk_idx', table_name='document_chunks')
    op.drop_index('ix_document_chunks_user_project', table_name='document_chunks')
    op.drop_index('ix_document_chunks_user_file', table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_parsed_document_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_project_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_user_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_file_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_created_at'), table_name='document_chunks')
    op.drop_table('document_chunks')
