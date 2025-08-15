from typing import List, Dict, Any
import sys
import yaml
from sqlalchemy.orm import Session

from .models import IndicatorRegistry
from .db import SessionLocal


def load_registry_yaml(path: str) -> List[Dict[str, Any]]:
    with open(path, "r") as f:
        data = yaml.safe_load(f)
        if not isinstance(data, list):
            raise ValueError("Registry YAML must be a list of indicator entries")
        return data


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


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "registry.yaml"
    session = SessionLocal()
    try:
        n = upsert_registry(session, load_registry_yaml(path))
        print(f"loaded {n} entries from {path}")
    finally:
        session.close()


if __name__ == "__main__":
    main()


