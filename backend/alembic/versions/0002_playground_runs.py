"""Playground history: playground_runs table."""

import sqlalchemy as sa
from alembic import op

revision = "0002_playground_runs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "playground_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("profile_name", sa.String(length=200), nullable=False),
        sa.Column("client_message", sa.Text(), nullable=False),
        sa.Column("category_override", sa.String(length=100), nullable=True),
        sa.Column("detected_category", sa.String(length=100), nullable=True),
        sa.Column("category_source", sa.String(length=20), nullable=False),
        sa.Column("selected", sa.JSON(), nullable=False),
        sa.Column("reply", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_playground_runs_created_at", "playground_runs", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_playground_runs_created_at", table_name="playground_runs")
    op.drop_table("playground_runs")
