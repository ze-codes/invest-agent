from pathlib import Path
from typing import Optional
import re

from fastapi import APIRouter


router = APIRouter()


# Removed legacy /viz/series route. Use static page: /static/viz_series.html


_DOCS_CACHE: dict = {"mtime": None, "series": {}, "indicators": {}}


def _parse_registry_docs() -> tuple[dict, dict]:
    """Parse docs/indicator-registry.md to extract brief explainer text.

    Returns (series_info, indicator_info) where values are dicts keyed by id with
    fields like {"title": str, "what": str, "why": str, "trigger": str}.
    """
    global _DOCS_CACHE
    file_path = Path(__file__).resolve().parents[2] / "docs" / "indicator-registry.md"
    try:
        mtime = file_path.stat().st_mtime
    except FileNotFoundError:
        return {}, {}
    if _DOCS_CACHE["mtime"] == mtime:
        return _DOCS_CACHE["series"], _DOCS_CACHE["indicators"]

    text_md = file_path.read_text(encoding="utf-8")
    lines = text_md.splitlines()
    series_section = False
    indicators_section = False
    series_info: dict[str, dict] = {}
    ind_info: dict[str, dict] = {}

    def flush_block(kind: str, current_ids: list[str], title: str, block: list[str]):
        if not current_ids:
            return
        content = "\n".join(block).strip()
        if kind == "series":
            # Extract What/Impact/Interpretation bullets if present
            what = re.search(r"\*\*What it is\*\*:\s*(.*)", content)
            impact = re.search(r"\*\*Impact\*\*:\s*(.*)", content)
            interp = re.search(r"\*\*Interpretation[^:]*\*\*:\s*(.*)", content)
            for cid in current_ids:
                series_info[cid] = {
                    "title": title,
                    "what": what.group(1).strip() if what else "",
                    "impact": impact.group(1).strip() if impact else "",
                    "interpretation": interp.group(1).strip() if interp else "",
                }
        else:
            why = re.search(r"\*\*Why it matters\*\*:\s*(.*)", content)
            # Allow optional explanatory text (e.g., (z20)) between Scoring value and semicolon
            scoring = re.search(r"Scoring:\s*`?([a-zA-Z0-9_]+)`?(?:\s*\([^)]*\))?;\s*Trigger:\s*`?([^`\n]+)" , content)
            direction = re.search(r"Directionality:\s*`?([^`\n]+)" , content)
            for cid in current_ids:
                ind_info[cid] = {
                    "title": title,
                    "why": why.group(1).strip() if why else "",
                    "scoring": scoring.group(1).strip() if scoring else "",
                    "trigger": scoring.group(2).strip() if scoring else "",
                    "directionality": direction.group(1).strip() if direction else "",
                }

    current_kind = None
    current_ids: list[str] = []
    current_title = ""
    block: list[str] = []

    for ln in lines:
        if ln.strip().startswith("## Series glossary"):
            series_section = True
            indicators_section = False
            continue
        if ln.strip().startswith("## Indicators"):
            indicators_section = True
            series_section = False
            # flush previous series block
            flush_block("series", current_ids if current_kind == "series" else [], current_title, block)
            current_kind = None
            current_ids = []
            current_title = ""
            block = []
            continue

        # Match bullet lines and capture all backticked IDs at the start, before the em dash
        m = re.match(r"^\-\s*(.+?)\s+—\s+(.*)$", ln)
        if m and (series_section or indicators_section):
            # New item begins; flush previous
            flush_block(current_kind or ("series" if series_section else "indicator"), current_ids, current_title, block)
            current_kind = "series" if series_section else "indicator"
            ids_segment = m.group(1).strip()
            ids_found = [s.strip() for s in re.findall(r"`([^`]+)`", ids_segment)]
            current_ids = ids_found if ids_found else ([ids_segment] if ids_segment else [])
            current_title = m.group(2).strip()
            block = []
        else:
            if current_kind in ("series", "indicator"):
                block.append(ln)

    # Flush tail
    flush_block(current_kind or "", current_ids, current_title, block)

    _DOCS_CACHE = {"mtime": mtime, "series": series_info, "indicators": ind_info}
    return series_info, ind_info


@router.get("/docs/registry_explainer")
def registry_explainer(series: Optional[str] = None, indicators: Optional[str] = None):
    s_map, i_map = _parse_registry_docs()
    out = {"series": {}, "indicators": {}}
    if series:
        s_lower = {k.lower(): k for k in s_map.keys()}
        for sid in [s.strip() for s in series.split(",") if s.strip()]:
            key = sid if sid in s_map else s_lower.get(sid.lower())
            if key:
                out["series"][sid] = s_map[key]
    if indicators:
        i_lower = {k.lower(): k for k in i_map.keys()}
        for iid in [s.strip() for s in indicators.split(",") if s.strip()]:
            key = iid if iid in i_map else i_lower.get(iid.lower())
            if key:
                out["indicators"][iid] = i_map[key]
    return out


# Removed legacy /viz/indicators route. Use static page: /static/viz_indicators.html


