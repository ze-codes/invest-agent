"""add series_latest view

Revision ID: 0002_add_series_latest_view
Revises: 0001_init
Create Date: 2025-08-14 00:00:02

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0002_add_series_latest_view"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW series_latest AS
        SELECT DISTINCT ON (series_id, observation_date)
            series_id,
            observation_date,
            vintage_id,
            value_numeric,
            units,
            scale,
            source,
            source_url,
            source_version,
            vintage_date,
            publication_date,
            fetched_at
        FROM series_vintages
        ORDER BY series_id, observation_date,
                 COALESCE(vintage_date, publication_date::date, fetched_at::date) DESC,
                 fetched_at DESC;
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS series_latest;")


