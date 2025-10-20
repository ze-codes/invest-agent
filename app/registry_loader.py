from typing import List, Dict, Any, Tuple
import sys
import yaml
from sqlalchemy.orm import Session

from .models import IndicatorRegistry, SeriesRegistry
from .db import SessionLocal


def load_registry_yaml(path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Load indicators and optional series_registry from registry.yaml.

    Supports either:
    - single-document YAML as a list (indicators only), or
    - multi-document YAML with an additional mapping that includes 'series_registry'.
    """
    indicators: List[Dict[str, Any]] = []
    series_meta: Dict[str, Dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
    if not docs:
        return indicators, series_meta
    # First doc often is the indicator list
    for doc in docs:
        if isinstance(doc, list):
            indicators.extend(doc)
        elif isinstance(doc, dict):
            # Accept either top-level series_registry key or nested indicators key
            if "indicators" in doc and isinstance(doc["indicators"], list):
                indicators.extend(doc["indicators"])  # type: ignore[arg-type]
            if "series_registry" in doc and isinstance(doc["series_registry"], dict):
                series_meta.update(doc["series_registry"])  # type: ignore[arg-type]
    if not indicators and not series_meta:
        raise ValueError("registry.yaml does not contain indicator or series entries")
    return indicators, series_meta


def upsert_registry(db: Session, entries: List[Dict[str, Any]]) -> int:
    count = 0
    for e in entries:
        indicator_id = e["id"]
        rec = db.get(IndicatorRegistry, indicator_id)
        payload = {
            "indicator_id": indicator_id,
            "name": e.get("name"),
            "category": e.get("category"),
            "series_json": e.get("series", []),
            "cadence": e.get("cadence"),
            "directionality": e.get("directionality"),
            "trigger_default": e.get("trigger_default", ""),
            "scoring": e.get("scoring", "z"),
            "z_cutoff": e.get("z_cutoff"),
            "persistence": e.get("persistence"),
            "duplicates_of": e.get("duplicates_of"),
            "poll_window_et": e.get("poll_window_et"),
            "slo_minutes": e.get("slo_minutes"),
            "notes": e.get("notes"),
        }
        if rec:
            for k, v in payload.items():
                setattr(rec, k, v)
        else:
            rec = IndicatorRegistry(**payload)
            db.add(rec)
        count += 1
    db.commit()
    return count


def upsert_series_registry(db: Session, entries: Dict[str, Dict[str, Any]]) -> int:
    count = 0
    for sid, meta in entries.items():
        rec = db.get(SeriesRegistry, sid)
        payload = {
            "series_id": sid,
            "cadence": meta.get("cadence"),
            "units": meta.get("units"),
            "scale": meta.get("scale"),
            "source": meta.get("source"),
            "notes": meta.get("notes"),
        }
        if rec:
            for k, v in payload.items():
                setattr(rec, k, v)
        else:
            rec = SeriesRegistry(**payload)
            db.add(rec)
        count += 1
    db.commit()
    return count

def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "registry.yaml"
    session = SessionLocal()
    try:
        ind, series_meta = load_registry_yaml(path)
        n = upsert_registry(session, ind)
        print(f"loaded {n} indicators from {path}")
        if series_meta:
            m = upsert_series_registry(session, series_meta)
            print(f"loaded {m} series into series_registry")
    finally:
        session.close()


if __name__ == "__main__":
    main()


