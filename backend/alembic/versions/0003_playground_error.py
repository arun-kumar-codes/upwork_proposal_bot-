"""Playground failed-run errors: playground_runs.error."""

import sqlalchemy as sa
from alembic import op

revision = "0003_playground_error"
down_revision = "0002_playground_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("playground_runs", sa.Column("error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("playground_runs", "error")
