from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional, Literal, Dict

from pydantic import BaseModel, Field


class SeriesPoint(BaseModel):
    observation_date: date
    value_numeric: float
    units: str
    scale: float
    source: str
    vintage_id: Optional[str] = None
    vintage_date: Optional[date] = None
    publication_date: Optional[datetime] = None
    fetched_at: Optional[datetime] = None


class SeriesResponse(BaseModel):
    series_id: str
    points: List[SeriesPoint]


class IndicatorRegistryEntry(BaseModel):
    id: str
    name: str
    category: str
    series: List[str]
    cadence: str
    directionality: str
    trigger_default: str
    scoring: str
    z_cutoff: Optional[float] = None
    persistence: Optional[int] = None
    duplicates_of: Optional[str] = None
    notes: Optional[str] = None


class Regime(BaseModel):
    label: Literal["Positive", "Neutral", "Negative"]
    tilt: Literal["positive", "negative", "flat"]
    score: int
    max_score: int
    score_cont: Optional[float] = None


class SnapshotIndicator(BaseModel):
    id: str
    value_numeric: float
    window: Optional[str] = None
    z20: Optional[float] = None
    status: Literal["+1", "0", "-1"]
    flip_trigger: str
    provenance: dict


class BucketMember(BaseModel):
    id: str
    status: Literal["+1", "0", "-1"]
    z20: Optional[float] = None
    is_root: bool
    is_representative: bool


class BucketDetail(BaseModel):
    bucket_id: str
    category: Optional[str] = None
    weight: float
    aggregate_status: Literal["+1", "0", "-1"]
    representative_id: Optional[str] = None
    members: List[BucketMember]


class SnapshotResponse(BaseModel):
    as_of: datetime
    horizon: Literal["1w", "2w", "1m"]
    regime: Regime
    indicators: List[SnapshotIndicator]
    bucket_details: Optional[List[BucketDetail]] = None
    bucket_weights: Optional[Dict[str, float]] = None
    frozen_inputs_id: str


class RouterPick(BaseModel):
    id: str
    why: str
    trigger: str
    next_update: Optional[datetime] = None
    duplicates_note: Optional[str] = None


class RouterResponse(BaseModel):
    horizon: Literal["1w", "2w", "1m"]
    picks: List[RouterPick]


