"""add series_registry

Revision ID: 0003_series_registry
Revises: 0002_add_series_latest_view
Create Date: 2025-09-02 00:00:03

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_series_registry"
down_revision = "0002_add_series_latest_view"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "series_registry",
        sa.Column("series_id", sa.String(), primary_key=True),
        sa.Column("cadence", sa.String(), nullable=True),
        sa.Column("units", sa.String(), nullable=True),
        sa.Column("scale", sa.Numeric(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("series_registry")


