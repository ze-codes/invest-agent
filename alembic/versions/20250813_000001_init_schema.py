"""init schema

Revision ID: 0001_init
Revises: 
Create Date: 2025-08-13 00:00:01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "series_vintages",
        sa.Column("vintage_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("vintage_date", sa.Date()),
        sa.Column("publication_date", sa.DateTime()),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("value_numeric", sa.Numeric(), nullable=False),
        sa.Column("units", sa.String(), nullable=False),
        sa.Column("scale", sa.Numeric(), nullable=False, server_default=sa.text("1")),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("source_version", sa.Text()),
        sa.UniqueConstraint(
            "series_id", "observation_date", "vintage_date", "publication_date",
            name="uq_series_observation_vintage_publication",
        ),
    )

    op.create_index("ix_series_vintages_series_id", "series_vintages", ["series_id"]) 
    op.create_index("ix_series_vintages_observation_date", "series_vintages", ["observation_date"]) 

    op.create_table(
        "indicator_registry",
        sa.Column("indicator_id", sa.String(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("series_json", sa.JSON(), nullable=False),
        sa.Column("cadence", sa.String(), nullable=False),
        sa.Column("directionality", sa.String(), nullable=False),
        sa.Column("trigger_default", sa.Text(), nullable=False),
        sa.Column("scoring", sa.String(), nullable=False),
        sa.Column("z_cutoff", sa.Numeric()),
        sa.Column("persistence", sa.Integer()),
        sa.Column("duplicates_of", sa.String()),
        sa.Column("poll_window_et", sa.String()),
        sa.Column("slo_minutes", sa.Integer()),
        sa.Column("notes", sa.Text()),
    )

    op.create_table(
        "qt_caps",
        sa.Column("effective_date", sa.Date(), primary_key=True),
        sa.Column("ust_cap_usd_week", sa.Numeric(), nullable=False),
        sa.Column("mbs_cap_usd_week", sa.Numeric(), nullable=False),
    )

    op.create_table(
        "snapshots",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("horizon", sa.String(), nullable=False),
        sa.Column("frozen_inputs_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("regime_label", sa.String(), nullable=False),
        sa.Column("tilt", sa.String(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False),
    )

    op.create_table(
        "frozen_inputs",
        sa.Column("frozen_inputs_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("inputs_json", sa.JSON(), nullable=False),
    )

    op.create_table(
        "snapshot_indicators",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snapshots.snapshot_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("indicator_id", sa.String(), sa.ForeignKey("indicator_registry.indicator_id"), primary_key=True),
        sa.Column("value_numeric", sa.Numeric(), nullable=False),
        sa.Column("window", sa.String()),
        sa.Column("z20", sa.Numeric()),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("flip_trigger", sa.Text(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
    )

    op.create_table(
        "events_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("series_or_indicator", sa.String()),
        sa.Column("scheduled_for", sa.DateTime()),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("details", sa.JSON()),
    )

    op.create_table(
        "briefs_cache",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snapshots.snapshot_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("json_payload", sa.JSON(), nullable=False),
        sa.Column("markdown_payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # View for latest-by-observation (uses COALESCE over vintage/publication/fetched_at recency)
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
    op.drop_table("briefs_cache")
    op.drop_table("events_log")
    op.drop_table("snapshot_indicators")
    op.drop_table("frozen_inputs")
    op.drop_table("snapshots")
    op.drop_table("qt_caps")
    op.drop_table("indicator_registry")
    op.drop_index("ix_series_vintages_observation_date", table_name="series_vintages")
    op.drop_index("ix_series_vintages_series_id", table_name="series_vintages")
    op.drop_table("series_vintages")


