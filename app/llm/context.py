from __future__ import annotations
from typing import Any, Dict, List


def build_brief_context(snapshot: Dict[str, Any], router: Dict[str, Any]) -> Dict[str, Any]:
    indicator_ids: List[str] = [r["id"] for r in snapshot.get("indicators", [])]
    return {
        "regime": snapshot.get("regime", {}),
        "buckets": snapshot.get("buckets", []),
        "indicator_ids": indicator_ids,
    }
