from __future__ import annotations

from datetime import datetime, timezone, date
from typing import Dict, Any, List, Tuple, DefaultDict
from collections import defaultdict
from uuid import UUID
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import IndicatorRegistry, QTCap, Snapshot as SnapshotModel, SnapshotIndicator as SnapshotIndicatorModel, FrozenInputs as FrozenInputsModel
from app.queries import (
    get_latest_series_points,
    get_as_of_series_points,
    get_as_of_series_points_by_pub,
    get_series_points_up_to_observation_date,
)
from app.stats import compute_z_from_points


def directionality_sign(directionality: str) -> int:
    """Map registry `directionality` to a numeric sign used for status.

    Returns +1 when higher values are supportive (or default), and −1 when
    higher values are draining or lower values are supportive. This sign is
    multiplied by the z-score to derive a +1/0/−1 status contribution.
    """
    if directionality == "higher_is_supportive":
        return +1
    if directionality == "lower_is_supportive":
        return -1
    if directionality == "higher_is_draining":
        return -1
    return +1


def _json_safe(value: Any) -> Any:
    """Recursively convert common Python types (date, datetime, UUID, Decimal, set/tuple)
    into JSON-serializable equivalents. Leaves dicts/lists as-is after converting children.
    """
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime,)):
        # ensure timezone-aware datetimes are serialized
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in list(value)]
    # Fallback to string
    return str(value)


def _resolve_series_id(series_id: str) -> str:
    """Map abstract registry IDs to concrete DB series IDs when they differ.

    This lets the registry use canonical names (e.g., 'RRP') while the DB stores
    the actual series (e.g., 'RRPONTSYD'). Extend as needed.
    """
    aliases = {
        "RRP": "RRPONTSYD",
    }
    return aliases.get(series_id, series_id)


def compute_indicator_status(db: Session, reg: IndicatorRegistry, as_of: datetime | None = None, as_of_mode: str = "fetched") -> Tuple[Dict[str, Any], float]:
    """Compute the per-indicator evidence row and its numeric contribution.

    Steps (MVP):
    - If the indicator declares no series, or the DB has no points for the
      primary series, mark the indicator as not-available (status "n/a").
    - Otherwise compute a 20-observation z-score (z20) from latest points.
    - Convert z20 to a ternary status (+1/0/−1) using the registry cutoff and
      the indicator `directionality` sign.
    - Return a compact evidence row (id, value, window, z20, status, trigger,
      provenance) and a numeric contribution equal to the status.
    """
    series_ids = reg.series_json or []
    # For MVP, single-series indicators. If there is no declared series, treat as not available.
    if not series_ids:
        return (
            {
                "id": reg.indicator_id,
                "value_numeric": None,
                "window": None,
                "z20": None,
                "status": "n/a",
                "flip_trigger": reg.trigger_default or "",
                "provenance": {"series": series_ids},
            },
            0.0,
        )

    # Composite indicator: net_liq = WALCL - TGA - RRP (weekly + daily + daily)
    def _usd_value(p: Dict[str, Any]) -> float:
        try:
            return float(p["value_numeric"]) * float(p.get("scale", 1.0))
        except Exception:
            return float(p["value_numeric"])  # best effort

    def pts(series_id: str, limit: int) -> List[Dict[str, Any]]:
        if not as_of:
            return get_latest_series_points(db, series_id, limit=limit)
        if as_of_mode == "pub":
            return get_as_of_series_points_by_pub(db, series_id, as_of, limit=limit)
        if as_of_mode == "obs":
            return get_series_points_up_to_observation_date(db, series_id, as_of, limit=limit)
        return get_as_of_series_points(db, series_id, as_of, limit=limit)

    if reg.indicator_id == "net_liq" and len(series_ids) >= 3:
        walcl_pts = pts(_resolve_series_id(series_ids[0]), 60)
        tga_pts = pts(_resolve_series_id(series_ids[1]), 120)
        rrp_pts = pts(_resolve_series_id(series_ids[2]), 120)

        if not walcl_pts or not tga_pts or not rrp_pts:
            return (
                {
                    "id": reg.indicator_id,
                    "value_numeric": None,
                    "window": None,
                    "z20": None,
                    "status": "n/a",
                    "flip_trigger": reg.trigger_default or "",
                    "provenance": {"series": series_ids},
                },
                0.0,
            )

        # Build daily composite values aligning TGA and RRP dates with most recent prior WALCL
        tga_by_date = {p["observation_date"]: p for p in tga_pts}
        rrp_by_date = {p["observation_date"]: p for p in rrp_pts}
        walcl_sorted = sorted(walcl_pts, key=lambda p: p["observation_date"])  # ascending

        composite_points: List[Dict[str, Any]] = []
        for obs_date in sorted(set(tga_by_date.keys()) & set(rrp_by_date.keys())):
            walcl_val = None
            walcl_fetch = None
            for wp in reversed(walcl_sorted):
                if wp["observation_date"] <= obs_date:
                    walcl_val = _usd_value(wp)
                    walcl_fetch = wp.get("fetched_at")
                    break
            if walcl_val is None:
                continue
            tga = tga_by_date[obs_date]
            rrp = rrp_by_date[obs_date]
            net_val = walcl_val - _usd_value(tga) - _usd_value(rrp)
            fetched_at_candidates = [walcl_fetch, tga.get("fetched_at"), rrp.get("fetched_at")]
            fetched_at = max([x for x in fetched_at_candidates if x is not None]) if any(fetched_at_candidates) else None
            composite_points.append({
                "observation_date": obs_date,
                "value_numeric": net_val,
                "fetched_at": fetched_at,
                "inputs": {
                    series_ids[0]: {
                        "observation_date": wp.get("observation_date") if 'wp' in locals() else None,
                        "vintage_id": None,
                        "fetched_at": walcl_fetch,
                    },
                    series_ids[1]: {
                        "observation_date": tga.get("observation_date"),
                        "vintage_id": tga.get("vintage_id"),
                        "fetched_at": tga.get("fetched_at"),
                    },
                    series_ids[2]: {
                        "observation_date": rrp.get("observation_date"),
                        "vintage_id": rrp.get("vintage_id"),
                        "fetched_at": rrp.get("fetched_at"),
                    },
                },
            })

        points = composite_points[-40:]
        if not points:
            return (
                {
                    "id": reg.indicator_id,
                    "value_numeric": None,
                    "window": None,
                    "z20": None,
                    "status": "n/a",
                    "flip_trigger": reg.trigger_default or "",
                    "provenance": {"series": series_ids},
                },
                0.0,
            )
    else:
        # Override for derived weekly net settlements
        if reg.indicator_id == "ust_net_w":
            series_ids = ["UST_NET_SETTLE_W"]
            points = pts("UST_NET_SETTLE_W", 40)
        else:
            points = pts(_resolve_series_id(series_ids[0]), 40)
        # If no points exist for the underlying series, mark as not available
        if not points:
            return (
                {
                    "id": reg.indicator_id,
                    "value_numeric": None,
                    "window": None,
                    "z20": None,
                    "status": "n/a",
                    "flip_trigger": reg.trigger_default or "",
                    "provenance": {"series": series_ids},
                },
                0.0,
            )

    # Compute status depending on scoring policy
    if reg.scoring == "threshold":
        # QT pace vs caps: weekly runoff at/above caps => headwind
        if reg.indicator_id == "qt_pace":
            # Latest two weekly points for UST (WSHOSHO) and MBS (WSHOMCB)
            ust_pts = pts(_resolve_series_id("WSHOSHO"), 2)
            mbs_pts = pts(_resolve_series_id("WSHOMCB"), 2)
            if len(ust_pts) < 2 or len(mbs_pts) < 2:
                return (
                    {
                        "id": reg.indicator_id,
                        "value_numeric": None,
                        "window": None,
                        "z20": None,
                        "status": "n/a",
                        "flip_trigger": reg.trigger_default or "@cap => headwind",
                        "provenance": {"series": ["WSHOSHO", "WSHOMCB"]},
                    },
                    0.0,
                )

            def usd(p):
                try:
                    return float(p["value_numeric"]) * float(p.get("scale", 1.0) or 1.0)
                except Exception:
                    return float(p["value_numeric"])

            # Compute weekly runoff magnitudes (positive when holdings fall)
            ust_latest, ust_prev = ust_pts[-1], ust_pts[-2]
            mbs_latest, mbs_prev = mbs_pts[-1], mbs_pts[-2]
            ust_delta = usd(ust_latest) - usd(ust_prev)
            mbs_delta = usd(mbs_latest) - usd(mbs_prev)
            ust_runoff = max(0.0, -ust_delta)
            mbs_runoff = max(0.0, -mbs_delta)

            # Find applicable caps as of latest week
            obs_date = ust_latest["observation_date"]
            cap = (
                db.query(QTCap)
                .filter(QTCap.effective_date <= obs_date)
                .order_by(QTCap.effective_date.desc())
                .first()
            )
            if not cap:
                return (
                    {
                        "id": reg.indicator_id,
                        "value_numeric": None,
                        "window": None,
                        "z20": None,
                        "status": "n/a",
                        "flip_trigger": reg.trigger_default or "@cap => headwind",
                        "provenance": {"series": ["WSHOSHO", "WSHOMCB"]},
                    },
                    0.0,
                )

            ust_cap = float(cap.ust_cap_usd_week)
            mbs_cap = float(cap.mbs_cap_usd_week)
            at_cap = (ust_runoff >= ust_cap) or (mbs_runoff >= mbs_cap)
            status = -1 if at_cap else 0
            def _fmt_cap(x: float) -> str:
                ax = abs(x)
                if ax >= 1e12:
                    return f"${ax/1e12:.2f}T"
                if ax >= 1e9:
                    return f"${ax/1e9:.2f}B"
                if ax >= 1e6:
                    return f"${ax/1e6:.2f}M"
                if ax >= 1e3:
                    return f"${ax/1e3:.2f}K"
                return f"${ax:.2f}".rstrip("0").rstrip(".")
            result = {
                "id": reg.indicator_id,
                "value_numeric": ust_runoff + mbs_runoff,
                "window": None,
                "z20": None,
                "status": "+1" if status > 0 else ("-1" if status < 0 else "0"),
                # Explicit numeric caps for clarity in briefs
                "flip_trigger": f"UST ≥ {_fmt_cap(ust_cap)}/w or MBS ≥ {_fmt_cap(mbs_cap)}/w",
                "provenance": {
                    "series": ["WSHOSHO", "WSHOMCB"],
                    "fetched_at": max(ust_latest.get("fetched_at"), mbs_latest.get("fetched_at")) if ust_latest.get("fetched_at") and mbs_latest.get("fetched_at") else (ust_latest.get("fetched_at") or mbs_latest.get("fetched_at")),
                    "qt_caps": {
                        "effective_date": cap.effective_date,
                        "ust_cap_usd_week": ust_cap,
                        "mbs_cap_usd_week": mbs_cap,
                    },
                },
            }
            return result, float(status)

        # Threshold-based indicators may be single-series or composite (e.g., spreads)
        status = 0
        required = int(reg.persistence or 1)

        def directionally_positive() -> bool:
            # For threshold scoring, "positive" means the condition is met in the
            # direction that aligns with the indicator's directionality sign.
            # We treat a met condition as +1 before applying directionality sign mapping below.
            return True

        # Override points source for certain composites that use derived series
        if reg.indicator_id == "bill_rrp":
            # Use derived BILL_RRP_BPS series for threshold evaluation
            series_ids = ["BILL_RRP_BPS"]
            points = pts(_resolve_series_id("BILL_RRP_BPS"), 60)
            if not points:
                return (
                    {
                        "id": reg.indicator_id,
                        "value_numeric": None,
                        "window": None,
                        "z20": None,
                        "status": "n/a",
                        "flip_trigger": reg.trigger_default or "",
                        "provenance": {"series": series_ids},
                    },
                    0.0,
                )

        # Custom: OFR Liquidity Stress Index: value above its 80th percentile (history window)
        if reg.indicator_id == "ofr_liq_idx":
            import math
            # Choose a window (e.g., last 252 obs ≈ ~1Y of business days) or use all available if fewer
            window_size = 252
            vals = [float(p["value_numeric"]) for p in points[-window_size:]] if points else []
            if len(vals) < 3:
                return (
                    {
                        "id": reg.indicator_id,
                        "value_numeric": None,
                        "window": None,
                        "z20": None,
                        "status": "n/a",
                        "flip_trigger": reg.trigger_default or "> 80th pct",
                        "provenance": {"series": series_ids},
                    },
                    0.0,
                )

            def percentile(values: list[float], pct: float) -> float:
                if not values:
                    return float("nan")
                s = sorted(values)
                # nearest-rank method
                k = max(0, min(len(s) - 1, int(math.ceil(pct * len(s)) - 1)))
                return s[k]

            # Determine if the latest N observations (persistence) are above the 80th percentile threshold
            ok = 0
            latest_points = points[-required:] if points else []
            for p in latest_points:
                window_vals = vals  # reuse same window for simplicity (MVP)
                thresh_val = percentile(window_vals, 0.80)
                if float(p["value_numeric"]) > thresh_val:
                    ok += 1
            if ok >= required:
                status = 1 if directionality_sign(reg.directionality) > 0 else -1
            latest = points[-1]
            result = {
                "id": reg.indicator_id,
                "value_numeric": float(latest["value_numeric"]),
                "window": None,
                "z20": None,
                "status": "+1" if status > 0 else ("-1" if status < 0 else "0"),
                "flip_trigger": reg.trigger_default or "> 80th pct",
                "provenance": {
                    "series": series_ids,
                    "observation_date": latest.get("observation_date"),
                    "fetched_at": latest.get("fetched_at"),
                    "threshold": {
                        "type": "percentile",
                        "pct": 80.0,
                        "cutoff_value": percentile(vals, 0.80) if vals else None,
                    },
                    "streak": {"current": ok, "required": required},
                },
            }
            return result, float(status)

        # Custom: SOFR - IORB spread threshold ("persistent > 0 bps")
        if reg.indicator_id == "sofr_iorb" and len(series_ids) >= 2:
            sofr_pts = pts(_resolve_series_id(series_ids[0]), 60)
            iorb_pts = pts(_resolve_series_id(series_ids[1]), 60)
            if not sofr_pts or not iorb_pts:
                return (
                    {
                        "id": reg.indicator_id,
                        "value_numeric": None,
                        "window": None,
                        "z20": None,
                        "status": "n/a",
                        "flip_trigger": reg.trigger_default or "",
                        "provenance": {"series": series_ids},
                    },
                    0.0,
                )

            sof_by_date = {p["observation_date"]: p for p in sofr_pts}
            ior_by_date = {p["observation_date"]: p for p in iorb_pts}
            common_dates = sorted(set(sof_by_date.keys()) & set(ior_by_date.keys()))
            if not common_dates:
                return (
                    {
                        "id": reg.indicator_id,
                        "value_numeric": None,
                        "window": None,
                        "z20": None,
                        "status": "n/a",
                        "flip_trigger": reg.trigger_default or "",
                        "provenance": {"series": series_ids},
                    },
                    0.0,
                )
            # Check last `required` days have spread > 0
            ok = 0
            for d in reversed(common_dates[-required:]):
                spread = float(sof_by_date[d]["value_numeric"]) - float(ior_by_date[d]["value_numeric"])
                if spread > 0:
                    ok += 1
            if ok >= required:
                # Apply directionality sign: higher_is_draining → -1; else +1
                status = 1 if directionality_sign(reg.directionality) > 0 else -1
            z = None
            latest = sof_by_date[common_dates[-1]]
            value = float(latest["value_numeric"]) - float(ior_by_date[common_dates[-1]]["value_numeric"])
            result = {
                "id": reg.indicator_id,
                "value_numeric": value,
                "window": None,
                "z20": z,
                "status": "+1" if status > 0 else ("-1" if status < 0 else "0"),
                "flip_trigger": reg.trigger_default or "",
                "provenance": {
                    "series": series_ids,
                    "observation_date": d,
                    "fetched_at": latest.get("fetched_at"),
                    "threshold": {"op": ">", "value": 0.0},
                    "streak": {"current": ok, "required": required},
                },
            }
            return result, float(status)

        # bill_share custom: percent of bill offerings in total offerings by auction day
        if reg.indicator_id == "bill_share":
            # Pull recent totals
            total = pts(_resolve_series_id("UST_AUCTION_OFFERINGS"), 120)
            bills = pts(_resolve_series_id("UST_BILL_OFFERINGS"), 120)
            if not total or not bills:
                return (
                    {
                        "id": reg.indicator_id,
                        "value_numeric": None,
                        "window": None,
                        "z20": None,
                        "status": "n/a",
                        "flip_trigger": reg.trigger_default or ">= 65%",
                        "provenance": {"series": ["UST_BILL_OFFERINGS", "UST_AUCTION_OFFERINGS"]},
                    },
                    0.0,
                )
            by_date_total = {p["observation_date"]: float(p["value_numeric"]) for p in total}
            by_date_bills = {p["observation_date"]: float(p["value_numeric"]) for p in bills}
            common = sorted(set(by_date_total.keys()) & set(by_date_bills.keys()))
            if not common:
                return (
                    {
                        "id": reg.indicator_id,
                        "value_numeric": None,
                        "window": None,
                        "z20": None,
                        "status": "n/a",
                        "flip_trigger": reg.trigger_default or ">= 65%",
                        "provenance": {"series": ["UST_BILL_OFFERINGS", "UST_AUCTION_OFFERINGS"]},
                    },
                    0.0,
                )
            # Compute daily bill share % for recent dates
            pct_points = []
            for d in common:
                tot = by_date_total[d]
                if tot <= 0:
                    continue
                pct = 100.0 * (by_date_bills.get(d, 0.0) / tot)
                pct_points.append({"observation_date": d, "value_numeric": pct})
            pct_points.sort(key=lambda r: r["observation_date"])  # ascending
            latest = pct_points[-1] if pct_points else None
            if not latest:
                return (
                    {
                        "id": reg.indicator_id,
                        "value_numeric": None,
                        "window": None,
                        "z20": None,
                        "status": "n/a",
                        "flip_trigger": reg.trigger_default or ">= 65%",
                        "provenance": {"series": ["UST_BILL_OFFERINGS", "UST_AUCTION_OFFERINGS"]},
                    },
                    0.0,
                )
            # Apply persistence against threshold text (parse numeric, expects ">= 65")
            import re
            m = re.search(r"(>=|>|<=|<)\s*([+\-]?[0-9]+(?:\.[0-9]+)?)", reg.trigger_default or "")
            comp = m.group(1) if m else ">="
            thresh = float(m.group(2)) if m else 65.0
            required = int(reg.persistence or 1)
            ok = 0
            for p in reversed(pct_points[-required:]):
                v = float(p["value_numeric"])
                cond = (v > thresh) if comp == ">" else (v >= thresh) if comp == ">=" else (v < thresh) if comp == "<" else (v <= thresh)
                if cond:
                    ok += 1
            status = 1 if ok >= required and directionality_sign(reg.directionality) > 0 else (-1 if ok >= required else 0)
            return (
                {
                    "id": reg.indicator_id,
                    "value_numeric": float(latest["value_numeric"]),
                    "window": None,
                    "z20": None,
                    "status": "+1" if status > 0 else ("-1" if status < 0 else "0"),
                    "flip_trigger": reg.trigger_default or ">= 65%",
                    "provenance": {
                        "series": ["UST_BILL_OFFERINGS", "UST_AUCTION_OFFERINGS"],
                        "auction_date": latest["observation_date"],
                        "bill_share_pct": float(latest["value_numeric"]),
                        "threshold": {"op": comp, "value": thresh, "units": "%"},
                        "streak": {"current": ok, "required": required},
                    },
                },
                float(status),
            )

        # Generic single-series threshold: check latest N observations against a parsed threshold
        # Parse numeric threshold from trigger_default (best effort)
        import re

        thresh = None
        comp = None  # '>' or '>=' or '<' or '<='
        if reg.trigger_default:
            m = re.search(r"(>=|>|<=|<)\s*([+\-]?[0-9]+(?:\.[0-9]+)?(?:e[+\-]?[0-9]+)?)", reg.trigger_default, re.IGNORECASE)
            if m:
                comp = m.group(1)
                try:
                    thresh = float(m.group(2))
                except Exception:
                    thresh = None

        latest = points[-1] if points else None
        def cmp(v: float) -> bool:
            if thresh is None or comp is None:
                return False
            if comp == ">":
                return v > thresh
            if comp == ">=":
                return v >= thresh
            if comp == "<":
                return v < thresh
            if comp == "<=":
                return v <= thresh
            return False

        ok = 0
        for p in reversed(points[-required:]):
            v = float(p["value_numeric"])
            if cmp(v):
                ok += 1
        if ok >= required:
            # Map to status sign via directionality
            status = 1 if directionality_sign(reg.directionality) > 0 else -1

        status_str = "+1" if status > 0 else ("-1" if status < 0 else "0")
        value = float(latest["value_numeric"]) if latest else None
        result = {
            "id": reg.indicator_id,
            "value_numeric": value,
            "window": None,
            "z20": None,
            "status": status_str,
            "flip_trigger": reg.trigger_default or "",
            "provenance": {
                "series": series_ids,
                "observation_date": latest.get("observation_date") if latest else None,
                "publication_date": latest.get("publication_date") if latest else None,
                "vintage_date": latest.get("vintage_date") if latest else None,
                "fetched_at": latest.get("fetched_at") if latest else None,
                "vintage_id": latest.get("vintage_id") if latest else None,
                "source": latest.get("source") if latest else None,
                "source_url": latest.get("source_url") if latest else None,
                "threshold": {"op": comp or "", "value": thresh},
                "streak": {"current": ok, "required": required},
            },
        }
        return result, float(status)

    # Helper: derive the measurement window for the value (not the z lookback)
    def _derive_measurement_window() -> str | None:
        import re
        trig = reg.trigger_default or ""
        # Prefer explicit "/<token>" suffixes (e.g., "/w", "/5d", "/2w")
        m = re.search(r"/\s*([0-9]+[dw]|[dw])\b", trig, re.IGNORECASE)
        if m:
            return m.group(1).lower()
        # Also accept phrases like "over 5d" or "over 2w"
        m = re.search(r"over\s+([0-9]+[dw])\b", trig, re.IGNORECASE)
        if m:
            return m.group(1).lower()
        # Fallback from cadence
        cad = (reg.cadence or "").lower()
        if cad == "weekly":
            return "w"
        # For daily/level/sched/weekly_daily leave unspecified to avoid confusion
        return None

    # Compute z for the latest point(s) for z-scored indicators
    z = compute_z_from_points(points, window=20)
    status = 0
    if z is not None:
        cutoff = float(reg.z_cutoff or 1.0)
        # Apply persistence/hysteresis if configured: need N consecutive qualifying observations
        required = int(reg.persistence or 1)
        qualifies = 0
        # Walk back over last `required` observations, recomputing z20 at each step
        # by truncating the tail of points.
        for back in range(0, required):
            # Need at least window points to compute z; fall back to latest z-only if insufficient
            if len(points) - back < 3:
                break
            z_i = compute_z_from_points(points[: len(points) - back], window=20)
            if z_i is None or abs(z_i) < cutoff:
                break
            # Check sign after applying directionality
            if z_i * directionality_sign(reg.directionality) > 0:
                qualifies += 1
            else:
                break
        if qualifies >= required:
            status = 1
        else:
            # Check if it qualifies in the negative direction consistently
            qualifies_neg = 0
            for back in range(0, required):
                if len(points) - back < 3:
                    break
                z_i = compute_z_from_points(points[: len(points) - back], window=20)
                if z_i is None or abs(z_i) < cutoff:
                    break
                if z_i * directionality_sign(reg.directionality) < 0:
                    qualifies_neg += 1
                else:
                    break
            if qualifies_neg >= required:
                status = -1

    status_str = "+1" if status > 0 else ("-1" if status < 0 else "0")
    latest = points[-1] if points else None
    # Use scaled value where applicable for single-series; composite points have no scale
    value = _usd_value(latest) if latest else None
    measurement_window = _derive_measurement_window()
    result = {
        "id": reg.indicator_id,
        "value_numeric": value,
        # window reflects the measurement window, not the z lookback
        "window": measurement_window,
        "z20": z,
        "status": status_str,
        "flip_trigger": reg.trigger_default or "",
        "provenance": {
            "series": series_ids,
            "observation_date": latest.get("observation_date") if latest else None,
            "publication_date": latest.get("publication_date") if latest else None,
            "vintage_date": latest.get("vintage_date") if latest else None,
            "fetched_at": latest.get("fetched_at") if latest else None,
            "vintage_id": latest.get("vintage_id") if latest else None,
            "source": latest.get("source") if latest else None,
            "source_url": latest.get("source_url") if latest else None,
            "inputs": latest.get("inputs") if latest else None,
            # record z lookback for transparency
            "z_window": 20,
        },
    }
    # Contribution used for weights later
    contribution = float(status)
    return result, contribution


def compute_snapshot(db: Session, horizon: str = "1w", k: int = 8, save: bool = False, as_of: datetime | None = None, as_of_mode: str = "fetched") -> Dict[str, Any]:
    """Build the Liquidity Snapshot response (MVP).

    Pipeline:
    1) Evaluate each indicator from the registry via `compute_indicator_status`.
       Exclude indicators with status "n/a" (no underlying data).
    2) Group remaining indicators into concept buckets using `duplicates_of`.
       Aggregate member contributions per bucket by simple average (MVP).
    3) Apply category weights to bucket aggregates (Core 50%, Floor 30%, Supply 20%)
       to form a continuous score; map to regime label (±2 thresholds) and tilt.
    4) Choose one representative per bucket (member with largest |z|), then sort
       representatives by |z| and truncate to top K for the evidence table.
    5) Return regime, top‑K evidence rows, and a `buckets` section listing each
       bucket’s aggregate status and members.
    """
    regs: List[IndicatorRegistry] = db.query(IndicatorRegistry).order_by(IndicatorRegistry.indicator_id).all()
    reg_by_id: Dict[str, IndicatorRegistry] = {r.indicator_id: r for r in regs}
    indicators: List[Dict[str, Any]] = []
    contributions: Dict[str, float] = {}

    for reg in regs:
        row, contrib = compute_indicator_status(db, reg, as_of=as_of, as_of_mode=as_of_mode)
        # Skip indicators with no underlying data (status == 'n/a') to avoid misleading zeros
        if row.get("status") == "n/a":
            continue
        indicators.append(row)
        contributions[reg.indicator_id] = contrib

    # Build concept buckets using duplicates_of graph (root = duplicates_of or self)
    def root_id(indicator_id: str) -> str:
        r = reg_by_id.get(indicator_id)
        if r is None:
            return indicator_id
        return r.duplicates_of or indicator_id

    members_by_bucket: DefaultDict[str, List[str]] = defaultdict(list)
    for ind_id in contributions.keys():
        rid = root_id(ind_id)
        members_by_bucket[rid].append(ind_id)

    # Aggregate contributions within each bucket (simple average, MVP)
    bucket_aggregate: Dict[str, float] = {}
    for rid, members in members_by_bucket.items():
        vals = [contributions[m] for m in members]
        bucket_aggregate[rid] = sum(vals) / len(vals) if vals else 0.0

    # Category weights (apply only to the main three categories per MVP)
    WEIGHTS: Dict[str, float] = {
        "core_plumbing": 0.50,
        "floor": 0.30,
        "supply": 0.20,
    }

    # Compute weighted continuous score over buckets using root category; others get 0 weight
    weighted_sum = 0.0
    total_weight = 0.0
    for rid, agg in bucket_aggregate.items():
        root_reg = reg_by_id.get(rid)
        if not root_reg:
            continue
        w = WEIGHTS.get(root_reg.category, 0.0)
        if w == 0.0:
            continue
        weighted_sum += w * agg
        total_weight += w

    # Map to label/tilt
    # Use integer score by rounding weighted_sum to nearest integer; max_score approximated by number of weighted buckets
    score_cont = weighted_sum if total_weight > 0 else sum(contributions.values())
    score = int(round(score_cont))
    max_score = max(1, len([rid for rid in bucket_aggregate.keys() if reg_by_id.get(rid) and WEIGHTS.get(reg_by_id[rid].category, 0.0) > 0]))
    label = "Positive" if score >= 2 else ("Negative" if score <= -2 else "Neutral")
    tilt = "positive" if score_cont > 0 else ("negative" if score_cont < 0 else "flat")

    # Choose one representative per bucket (max |z|), then take top-k by |z|
    z_by_id: Dict[str, float] = {}
    row_by_id: Dict[str, Dict[str, Any]] = {row["id"]: row for row in indicators}
    for row in indicators:
        z = row.get("z20")
        z_by_id[row["id"]] = abs(float(z)) if z is not None else 0.0

    reps: List[Dict[str, Any]] = []
    representative_by_bucket: Dict[str, str] = {}
    for rid, members in members_by_bucket.items():
        # Pick member with largest |z|
        best_id = max(members, key=lambda mid: z_by_id.get(mid, 0.0))
        representative_by_bucket[rid] = best_id
        reps.append(row_by_id[best_id])

    def z_abs(row: Dict[str, Any]) -> float:
        z = row.get("z20")
        return abs(float(z)) if z is not None else 0.0

    indicators_sorted = sorted(reps, key=z_abs, reverse=True)[:k]

    # Build bucket_details section for response
    bucket_details: List[Dict[str, Any]] = []
    for rid, agg in bucket_aggregate.items():
        root_reg = reg_by_id.get(rid)
        members = members_by_bucket.get(rid, [])
        agg_status = "+1" if agg > 0 else ("-1" if agg < 0 else "0")
        rep_id = representative_by_bucket.get(rid)
        member_objs: List[Dict[str, Any]] = []
        for mid in members:
            r = row_by_id.get(mid)
            member_objs.append(
                {
                    "id": mid,
                    "status": "+1" if contributions.get(mid, 0.0) > 0 else ("-1" if contributions.get(mid, 0.0) < 0 else "0"),
                    "z20": (None if not r else r.get("z20")),
                    "is_root": (mid == rid),
                    "is_representative": (mid == rep_id),
                }
            )
        bucket_details.append(
            {
                "bucket_id": rid,
                "category": root_reg.category if root_reg else None,
                "weight": WEIGHTS.get(root_reg.category, 0.0) if root_reg else 0.0,
                "aggregate_status": agg_status,
                "representative_id": rep_id,
                "members": member_objs,
            }
        )

    as_of_now = as_of or datetime.now(timezone.utc)
    frozen_id_str = "temp"
    if save:
        # Build frozen inputs list
        frozen_items: List[Dict[str, Any]] = []
        for row in indicators_sorted:
            prov = row.get("provenance", {})
            series_list = prov.get("series", [])
            inputs_map = prov.get("inputs")
            if isinstance(inputs_map, dict):
                for sid, meta in inputs_map.items():
                    obs = meta.get("observation_date")
                    vid = meta.get("vintage_id")
                    frozen_items.append({
                        "indicator_id": row["id"],
                        "series_id": sid,
                        "vintage_id": str(vid) if vid is not None else None,
                        "observation_date": obs.isoformat() if hasattr(obs, "isoformat") else obs,
                    })
            else:
                obs = prov.get("observation_date")
                vid = prov.get("vintage_id")
                for sid in series_list:
                    frozen_items.append({
                        "indicator_id": row["id"],
                        "series_id": sid,
                        "vintage_id": str(vid) if vid is not None else None,
                        "observation_date": obs.isoformat() if hasattr(obs, "isoformat") else obs,
                    })

        frozen = FrozenInputsModel(inputs_json=_json_safe(frozen_items))
        db.add(frozen)
        db.flush()  # assign ID
        snap = SnapshotModel(
            as_of=as_of_now,
            horizon=horizon,
            frozen_inputs_id=frozen.frozen_inputs_id,
            regime_label=label,
            tilt=tilt,
            score=score,
            max_score=max_score,
        )
        db.add(snap)
        db.flush()
        for row in indicators:
            db.add(
                SnapshotIndicatorModel(
                    snapshot_id=snap.snapshot_id,
                    indicator_id=row["id"],
                    value_numeric=row.get("value_numeric"),
                    window=row.get("window"),
                    z20=row.get("z20"),
                    status=row.get("status"),
                    flip_trigger=row.get("flip_trigger", ""),
                    provenance_json=_json_safe(row.get("provenance", {})),
                )
            )
        db.commit()
        frozen_id_str = str(frozen.frozen_inputs_id)

    return {
        "as_of": as_of_now.isoformat(),
        "regime": {"label": label, "tilt": tilt, "score": score, "max_score": max_score, "score_cont": round(score_cont, 2)},
        "indicators": indicators_sorted,
        "bucket_details": bucket_details,
        "bucket_weights": WEIGHTS,
        "frozen_inputs_id": frozen_id_str,
        "horizon": horizon,
    }


def compute_router(db: Session, horizon: str = "1w", k: int = 8) -> Dict[str, Any]:
    """Return top‑K relevant indicators for the Router endpoint (MVP).

    Logic:
    - Skip indicators with no declared series or no points (missing data).
    - Compute z20 for each remaining indicator and rank by absolute z as a
      proxy for near-term relevance.
    - Emit `{id, why, trigger, next_update}` picks (duplicates resolution and
      quotas to be added in a later step).
    """
    regs: List[IndicatorRegistry] = db.query(IndicatorRegistry).order_by(IndicatorRegistry.indicator_id).all()
    # Rank by absolute z as proxy for relevance
    rows: List[Tuple[IndicatorRegistry, float]] = []
    for reg in regs:
        series_ids = reg.series_json or []
        if not series_ids:
            continue
        points = get_latest_series_points(db, series_ids[0], limit=40)
        if not points:
            # Skip indicators with no underlying data
            continue
        z = compute_z_from_points(points, window=20)
        rows.append((reg, abs(float(z)) if z is not None else 0.0))

    rows.sort(key=lambda t: t[1], reverse=True)
    picks = []
    for reg, _ in rows[:k]:
        picks.append({
            "id": reg.indicator_id,
            "why": reg.notes or reg.name,
            "trigger": reg.trigger_default or "",
            "next_update": None,
        })

    return {"horizon": horizon, "picks": picks}




