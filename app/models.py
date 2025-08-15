from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Numeric,
    Date,
    DateTime,
    JSON,
    ForeignKey,
    UniqueConstraint,
    UUID as SAUUID,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from .db import Base


class SeriesVintage(Base):
    __tablename__ = "series_vintages"

    vintage_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    series_id = Column(String, nullable=False, index=True)
    observation_date = Column(Date, nullable=False, index=True)
    vintage_date = Column(Date)
    publication_date = Column(DateTime)
    fetched_at = Column(DateTime, nullable=False)
    value_numeric = Column(Numeric, nullable=False)
    units = Column(String, nullable=False)
    scale = Column(Numeric, nullable=False, default=1)
    source = Column(String, nullable=False)
    source_url = Column(Text)
    source_version = Column(Text)

    __table_args__ = (
        UniqueConstraint(
            "series_id",
            "observation_date",
            "vintage_date",
            "publication_date",
            name="uq_series_observation_vintage_publication",
        ),
    )


class IndicatorRegistry(Base):
    __tablename__ = "indicator_registry"

    indicator_id = Column(String, primary_key=True)
    name = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    series_json = Column(JSON, nullable=False)
    cadence = Column(String, nullable=False)
    directionality = Column(String, nullable=False)
    trigger_default = Column(Text, nullable=False)
    scoring = Column(String, nullable=False)
    z_cutoff = Column(Numeric)
    persistence = Column(Integer)
    duplicates_of = Column(String)
    poll_window_et = Column(String)
    slo_minutes = Column(Integer)
    notes = Column(Text)


class QTCap(Base):
    __tablename__ = "qt_caps"

    effective_date = Column(Date, primary_key=True)
    ust_cap_usd_week = Column(Numeric, nullable=False)
    mbs_cap_usd_week = Column(Numeric, nullable=False)


class Snapshot(Base):
    __tablename__ = "snapshots"

    snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    as_of = Column(DateTime, nullable=False)
    horizon = Column(String, nullable=False)
    frozen_inputs_id = Column(UUID(as_uuid=True), nullable=False)
    regime_label = Column(String, nullable=False)
    tilt = Column(String, nullable=False)
    score = Column(Integer, nullable=False)
    max_score = Column(Integer, nullable=False)

    indicators = relationship("SnapshotIndicator", back_populates="snapshot", cascade="all, delete-orphan")


class FrozenInputs(Base):
    __tablename__ = "frozen_inputs"

    frozen_inputs_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inputs_json = Column(JSON, nullable=False)


class SnapshotIndicator(Base):
    __tablename__ = "snapshot_indicators"

    snapshot_id = Column(UUID(as_uuid=True), ForeignKey("snapshots.snapshot_id", ondelete="CASCADE"), primary_key=True)
    indicator_id = Column(String, ForeignKey("indicator_registry.indicator_id"), primary_key=True)
    value_numeric = Column(Numeric, nullable=False)
    window = Column(String)
    z20 = Column(Numeric)
    status = Column(String, nullable=False)
    flip_trigger = Column(Text, nullable=False)
    provenance_json = Column(JSON, nullable=False)

    snapshot = relationship("Snapshot", back_populates="indicators")


class EventsLog(Base):
    __tablename__ = "events_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String, nullable=False)
    series_or_indicator = Column(String)
    scheduled_for = Column(DateTime)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime)
    status = Column(String, nullable=False)
    details = Column(JSON)


class BriefsCache(Base):
    __tablename__ = "briefs_cache"

    snapshot_id = Column(UUID(as_uuid=True), ForeignKey("snapshots.snapshot_id", ondelete="CASCADE"), primary_key=True)
    json_payload = Column(JSON, nullable=False)
    markdown_payload = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)


