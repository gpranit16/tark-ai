"""message generation metadata

Revision ID: 0002_message_generation_metadata
Revises: 0001_initial_schema
Create Date: 2026-08-31 01:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_message_generation_metadata"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


generation_status = postgresql.ENUM(
    "completed",
    "cancelled",
    "failed",
    name="generation_status",
    create_type=False,
)


def upgrade() -> None:
    generation_status.create(op.get_bind(), checkfirst=True)
    op.add_column("messages", sa.Column("provider", sa.String(length=50), nullable=True))
    op.add_column("messages", sa.Column("generation_status", generation_status, nullable=True))
    op.add_column("messages", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("messages", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("messages", sa.Column("total_tokens", sa.Integer(), nullable=True))
    op.add_column("messages", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.create_index("ix_messages_provider_created_at", "messages", ["provider", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_messages_provider_created_at", table_name="messages")
    op.drop_column("messages", "latency_ms")
    op.drop_column("messages", "total_tokens")
    op.drop_column("messages", "output_tokens")
    op.drop_column("messages", "input_tokens")
    op.drop_column("messages", "generation_status")
    op.drop_column("messages", "provider")
    generation_status.drop(op.get_bind(), checkfirst=True)
