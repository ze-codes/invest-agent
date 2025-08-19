from __future__ import annotations

from typing import List, Dict, Any, Optional
import math


def compute_z_from_points(points: List[Dict[str, Any]], value_key: str = "value_numeric", window: int = 20) -> Optional[float]:
    if not points:
        return None
    values = [float(p[value_key]) for p in points[-window:]]
    if len(values) < 3:
        return None
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    std = math.sqrt(var)
    if std < max(1e-6, 1e-3 * abs(mean)):
        return None
    last = values[-1]
    return (last - mean) / std




