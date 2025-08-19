from pathlib import Path
from typing import Optional
import re

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse


router = APIRouter()


@router.get("/viz/series", response_class=HTMLResponse)
def viz_series(ids: Optional[str] = None, as_of: Optional[str] = None, limit: int = 1000):
    # Lightweight HTML/JS page using Plotly; pulls data from /series/{id}
    default_ids = [
        "WALCL", "RESPPLLOPNWW", "RRPONTSYD", "TGA", "SOFR", "IORB", "DTB3", "DTB4WK",
    ]
    series_ids = ids.split(",") if (ids and ids.strip()) else default_ids
    file_path = Path(__file__).resolve().parents[2] / "api" / "static" / "viz_series.html"
    return FileResponse(str(file_path))


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

    def flush_block(kind: str, current_id: Optional[str], title: str, block: list[str]):
        if not current_id:
            return
        content = "\n".join(block).strip()
        if kind == "series":
            # Extract What/Impact/Interpretation bullets if present
            what = re.search(r"\*\*What it is\*\*:\s*(.*)", content)
            impact = re.search(r"\*\*Impact\*\*:\s*(.*)", content)
            interp = re.search(r"\*\*Interpretation[^:]*\*\*:\s*(.*)", content)
            series_info[current_id] = {
                "title": title,
                "what": what.group(1).strip() if what else "",
                "impact": impact.group(1).strip() if impact else "",
                "interpretation": interp.group(1).strip() if interp else "",
            }
        else:
            why = re.search(r"\*\*Why it matters\*\*:\s*(.*)", content)
            scoring = re.search(r"Scoring:\s*`?([a-zA-Z0-9_]+)`?;\s*Trigger:\s*`?([^`\n]+)" , content)
            direction = re.search(r"Directionality:\s*`?([^`\n]+)" , content)
            ind_info[current_id] = {
                "title": title,
                "why": why.group(1).strip() if why else "",
                "scoring": scoring.group(1).strip() if scoring else "",
                "trigger": scoring.group(2).strip() if scoring else "",
                "directionality": direction.group(1).strip() if direction else "",
            }

    current_kind = None
    current_id = None
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
            flush_block("series", current_id if current_kind == "series" else None, current_title, block)
            current_kind = None
            current_id = None
            current_title = ""
            block = []
            continue

        m = re.match(r"^\-\s*`([^`]+)`\s+—\s+(.*)$", ln)
        if m and (series_section or indicators_section):
            # New item begins; flush previous
            flush_block(current_kind or ("series" if series_section else "indicator"), current_id, current_title, block)
            current_kind = "series" if series_section else "indicator"
            current_id = m.group(1).strip()
            current_title = m.group(2).strip()
            block = []
        else:
            if current_kind in ("series", "indicator"):
                block.append(ln)

    # Flush tail
    flush_block(current_kind or "", current_id, current_title, block)

    _DOCS_CACHE = {"mtime": mtime, "series": series_info, "indicators": ind_info}
    return series_info, ind_info


@router.get("/docs/registry_explainer")
def registry_explainer(series: Optional[str] = None, indicators: Optional[str] = None):
    s_map, i_map = _parse_registry_docs()
    out = {"series": {}, "indicators": {}}
    if series:
        for sid in [s.strip() for s in series.split(",") if s.strip()]:
            if sid in s_map:
                out["series"][sid] = s_map[sid]
    if indicators:
        for iid in [s.strip() for s in indicators.split(",") if s.strip()]:
            if iid in i_map:
                out["indicators"][iid] = i_map[iid]
    return out


@router.get("/viz/indicators")
def viz_indicators(ids: Optional[str] = None, horizon: str = "1w", days: int = 180):
    file_path = Path(__file__).resolve().parents[2] / "api" / "static" / "viz_indicators.html"
    return FileResponse(str(file_path))


