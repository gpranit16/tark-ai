"""Enhance projects and workspace context for Phase 11

Revision ID: f59a78b39c77
Revises: e48f67a24d66
Create Date: 2026-09-04 22:50:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f59a78b39c77'
down_revision: str | None = 'e48f67a24d66'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enhance projects table
    op.add_column('projects', sa.Column('custom_instructions', sa.Text(), nullable=True))
    op.add_column('projects', sa.Column('avatar', sa.String(length=64), nullable=True))
    op.add_column('projects', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('projects', sa.Column('project_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index('ix_projects_user_archived', 'projects', ['user_id', 'is_archived'])

    # 2. Link research_sessions table to projects
    op.add_column('research_sessions', sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_research_sessions_project_id_projects',
        'research_sessions',
        'projects',
        ['project_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_research_sessions_project_id', 'research_sessions', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_research_sessions_project_id', table_name='research_sessions')
    op.drop_constraint('fk_research_sessions_project_id_projects', 'research_sessions', type_='foreignkey')
    op.drop_column('research_sessions', 'project_id')

    op.drop_index('ix_projects_user_archived', table_name='projects')
    op.drop_column('projects', 'project_metadata')
    op.drop_column('projects', 'is_archived')
    op.drop_column('projects', 'avatar')
    op.drop_column('projects', 'custom_instructions')
