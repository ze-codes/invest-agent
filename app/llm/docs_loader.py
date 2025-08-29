from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
import re


_CACHE: Dict[str, object] = {"mtime": None, "blocks": {}, "series": {}}


def _load_md_text() -> tuple[str, float]:
    md_path = Path(__file__).resolve().parents[2] / "docs" / "indicator-registry.md"
    txt = md_path.read_text(encoding="utf-8")
    mtime = md_path.stat().st_mtime
    return txt, mtime


def _load_md_blocks() -> Dict[str, str]:
    """Load full markdown blocks per indicator id from docs/indicator-registry.md with mtime cache."""
    try:
        txt, mtime = _load_md_text()
    except FileNotFoundError:
        return {}

    global _CACHE
    if _CACHE.get("mtime") == mtime and _CACHE.get("blocks"):
        return _CACHE.get("blocks", {})  # type: ignore

    lines = txt.splitlines()
    blocks_list: Dict[str, List[str]] = {}
    current_id: Optional[str] = None
    pat = re.compile(r"^\-\s*`([^`]+)`\s+—\s+(.*)$")
    for ln in lines:
        m = pat.match(ln)
        if m:
            current_id = m.group(1).strip()
            blocks_list.setdefault(current_id, [])
            continue
        if current_id:
            blocks_list[current_id].append(ln)

    blocks: Dict[str, str] = {k: "\n".join(v).strip() for k, v in blocks_list.items()}
    _CACHE["mtime"] = mtime
    _CACHE["blocks"] = blocks
    return blocks


def _load_series_docs() -> Dict[str, Dict[str, str]]:
    """Parse 'Series glossary (raw inputs)' into id -> {title, what, impact, interpretation}."""
    try:
        txt, mtime = _load_md_text()
    except FileNotFoundError:
        return {}

    global _CACHE
    if _CACHE.get("mtime") == mtime and _CACHE.get("series"):
        return _CACHE.get("series", {})  # type: ignore

    lines = txt.splitlines()
    out: Dict[str, Dict[str, str]] = {}
    in_series = False
    current_id: Optional[str] = None
    current_title = ""
    buf: List[str] = []

    def flush():
        nonlocal current_id, current_title, buf
        if not current_id:
            return
        content = "\n".join(buf)
        what = re.search(r"\*\*What it is\*\*:\s*(.*)", content)
        impact = re.search(r"\*\*Impact\*\*:\s*(.*)", content)
        interp = re.search(r"\*\*Interpretation[^:]*\*\*:\s*(.*)", content)
        out[current_id] = {
            "title": current_title,
            "what": what.group(1).strip() if what else "",
            "impact": impact.group(1).strip() if impact else "",
            "interpretation": interp.group(1).strip() if interp else "",
        }

    for ln in lines:
        if ln.strip().startswith("## Series glossary"):
            in_series = True
            current_id = None
            current_title = ""
            buf = []
            continue
        if ln.strip().startswith("## Indicators"):
            # end of series section
            flush()
            in_series = False
            break
        if not in_series:
            continue
        m = re.match(r"^\-\s*`([^`]+)`\s+—\s+(.*)$", ln)
        if m:
            # new item
            flush()
            current_id = m.group(1).strip()
            current_title = m.group(2).strip()
            buf = []
        else:
            if current_id:
                buf.append(ln)
    # flush tail
    flush()

    _CACHE["mtime"] = mtime
    _CACHE["series"] = out
    return out


def get_indicator_doc(indicator_id: str, *, truncate_chars: Optional[int] = None) -> str:
    """Return the full markdown block for a given indicator id (empty string if missing)."""
    blocks = _load_md_blocks()
    doc = blocks.get(indicator_id, "")
    if truncate_chars and truncate_chars > 0 and len(doc) > truncate_chars:
        return doc[:truncate_chars]
    return doc


def get_series_doc(series_id: str) -> Dict[str, str]:
    series_map = _load_series_docs()
    return series_map.get(series_id, {})


