from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
import re
import time

from sqlalchemy.orm import Session

from app.snapshot import compute_snapshot, compute_router
from app.queries import get_latest_series_points
from app.models import IndicatorRegistry, SeriesVintage
from .context import build_brief_context
from .prompts import build_brief_prompt, build_agent_system_prompt, build_agent_step_prompt
from .providers import get_provider
from .docs_loader import get_indicator_doc, get_series_doc
from app.settings import settings


def _normalize_numeric_tokens(text: str) -> list[str]:
    if not text:
        return []
    import re as _re
    # Capture numbers like -120, 120.5, 0–2 as 0 and 2, and 1,200 as 1200
    cleaned = text.replace(",", "")
    # Split ranges like "0–2" or "0-2"
    cleaned = cleaned.replace("–", "-")
    tokens = _re.findall(r"-?\d+(?:\.\d+)?", cleaned)
    return tokens


def _verify_brief(markdown: str, indicator_infos: list[dict[str, Any]], regimen: dict[str, Any]) -> dict:
    issues: list[str] = []
    ok = True
    text = markdown or ""
    lower = text.lower()

    # Sections
    if "regime:" not in lower:
        ok = False
        issues.append("missing Regime line")
    if "evidence:" not in lower:
        ok = False
        issues.append("missing Evidence section")
    if "interpretation" not in lower:
        ok = False
        issues.append("missing Interpretation section")

    # Length (words)
    words = len(text.split())
    if words > 320:
        ok = False
        issues.append(f"too long: {words} words > 320")

    # Bullet count (after 'Evidence:')
    try:
        evid_part = text.split("Evidence:", 1)[1]
        bullets = [ln for ln in evid_part.splitlines() if ln.strip().startswith("-")]
        expected = min(len(indicator_infos), 12) if indicator_infos else 0
        if expected and len(bullets) < max(3, min(expected, 12)):
            ok = False
            issues.append(f"too few evidence bullets: {len(bullets)} < {max(3, min(expected, 12))}")
    except Exception:
        pass

    # Numeric parity (light): All numbers in markdown must come from allowed fields
    allowed_nums: set[str] = set()
    # Regime numbers
    try:
        if regimen:
            for key in ("score", "max_score"):
                val = regimen.get(key)
                if val is not None:
                    allowed_nums.add(str(val))
    except Exception:
        pass
    # Indicator numbers: latest_value, z20, and numbers inside flip_trigger
    for info in indicator_infos or []:
        try:
            if info.get("latest_value") is not None:
                # Allow numbers present inside formatted latest_value strings (e.g., "$239.9B")
                for tok in _normalize_numeric_tokens(str(info.get("latest_value"))):
                    allowed_nums.add(tok)
            if info.get("z20") is not None:
                allowed_nums.add(str(info.get("z20")))
            flip = info.get("flip_trigger") or ""
            for tok in _normalize_numeric_tokens(flip):
                allowed_nums.add(tok)
        except Exception:
            continue

    found_nums = _normalize_numeric_tokens(text)
    # Allow small numeric formatting differences by comparing as floats when possible
    def _as_float(s: str) -> float | None:
        try:
            return float(s)
        except Exception:
            return None
    allowed_floats = {f for s in allowed_nums if (f := _as_float(s)) is not None}
    for num in found_nums:
        f = _as_float(num)
        if f is None:
            continue
        # accept if within small epsilon of some allowed number
        if not any(abs(f - af) <= 1e-6 for af in allowed_floats):
            ok = False
            issues.append(f"number not in snapshot context: {num}")
            # don't flood
            if len([i for i in issues if i.startswith("number not in snapshot")]) > 5:
                break

    return {"ok": ok, "issues": issues}


def _redact_pii(text: Any) -> str:
    """Redact basic PII like emails and phone numbers from text blocks."""
    if text is None:
        return ""
    s = str(text)
    try:
        s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted_email]", s)
        s = re.sub(r"\b(\+?\d[\d\-\s()]{9,}\d)\b", "[redacted_phone]", s)
        return s
    except Exception:
        return str(text)


def _complete_with_timeout(provider, prompt: str, timeout_s: float = 8.0) -> str:
    """Run provider.complete with a hard timeout in a worker thread."""
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as _TO
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(provider.complete, prompt)
            return fut.result(timeout=timeout_s)
    except Exception as e:  # includes TimeoutError
        raise TimeoutError(str(e))


def _get_indicator_history(
    db: Session,
    indicator_id: str,
    *,
    horizon: str = "1w",
    days: int = 90,
    max_points: int = 20,
) -> list[dict[str, Any]]:
    """Fetch recent indicator history points from snapshots for LLM use."""
    from sqlalchemy import text as _text
    cutoff_clause = " AND s.as_of >= :cut" if (days and days > 0) else ""
    q = _text(
        f"""
        SELECT s.as_of, si.value_numeric, si.z20, si.status
        FROM snapshots s
        JOIN snapshot_indicators si ON si.snapshot_id = s.snapshot_id
        WHERE si.indicator_id = :iid AND s.horizon = :h{cutoff_clause}
        ORDER BY s.as_of ASC
        """
    )
    params: dict[str, Any] = {"iid": indicator_id, "h": horizon}
    if days and days > 0:
        from datetime import datetime, timezone, timedelta

        params["cut"] = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(q, params).mappings().all()
    items = [
        {
            "as_of": r["as_of"],
            "value_numeric": float(r["value_numeric"]) if r["value_numeric"] is not None else None,
            "z20": float(r["z20"]) if r["z20"] is not None else None,
            "status": r["status"],
        }
        for r in rows
    ]
    if max_points and len(items) > max_points:
        items = items[-max_points:]
    return items


def _get_series_history(
    db: Session,
    series_id: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Fetch recent series points (best-known per observation date).

    Returns ascending by observation_date with numeric values.
    """
    try:
        capped = max(6, min(int(limit or 20), 60))
    except Exception:
        capped = 20
    rows = get_latest_series_points(db, series_id, limit=capped)
    items = [
        {
            "observation_date": r.get("observation_date"),
            "value_numeric": float(r.get("value_numeric")) if r.get("value_numeric") is not None else None,
            "units": r.get("units"),
            "scale": float(r.get("scale") or 1) if r.get("scale") is not None else 1.0,
        }
        for r in rows
    ]
    return items

def _clean_flip_trigger(flip: Any) -> str:
    """Remove commentary after '=>', keeping the trigger expression only."""
    if not flip:
        return ""
    try:
        s = str(flip)
        return s.split("=>", 1)[0].strip()
    except Exception:
        return str(flip)


def _format_compact_value(indicator_id: str, value: Any) -> str:
    """Format numeric values compactly with units where obvious.

    Heuristics:
    - If abs(value) >= 1e6, assume USD and use $ with K/M/B/T suffix.
    - If indicator id contains 'iorb', append ' bps'.
    - Otherwise, return plain number string.
    """
    if value is None:
        return ""
    try:
        v = float(value)
    except Exception:
        return str(value)

    sign = "-" if v < 0 else ""
    av = abs(v)

    def with_suffix(x: float) -> str:
        if x >= 1e12:
            return f"${x/1e12:.1f}T"
        if x >= 1e9:
            return f"${x/1e9:.1f}B"
        if x >= 1e6:
            return f"${x/1e6:.1f}M"
        if x >= 1e3:
            return f"${x/1e3:.1f}K"
        # small numbers: print raw with up to 3 decimals if needed
        return f"${x:.3f}".rstrip("0").rstrip(".")

    # Dollars formatting if obviously a dollar magnitude
    if av >= 1e6:
        core = with_suffix(av)
        out = f"{sign}{core}"
    else:
        # keep as plain number with up to 3 decimals
        out = f"{v:.3f}".rstrip("0").rstrip(".")

    # Add bps for IORB spread indicators
    if "iorb" in (indicator_id or "").lower():
        out = f"{out} bps"

    return out

def generate_brief(db: Session, horizon: str = "1w", as_of: Optional[str] = None, k: int = 12) -> Dict[str, Any]:
    snap = compute_snapshot(
        db,
        horizon=horizon,
        k=k,
        save=False,
        as_of=None if not as_of else datetime.fromisoformat(as_of),
        as_of_mode="obs",
    )
    router = compute_router(db, horizon=horizon, k=k)

    context = build_brief_context(snap, router)

    # Supply registry-backed metadata for indicators to prevent the model from inventing fields
    indicator_ids: List[str] = [r.get("id") for r in snap.get("indicators", []) if r.get("id")]
    indicator_infos: List[Dict[str, Any]] = []
    # Build a quick lookup of snapshot values by id
    snap_by_id: Dict[str, Dict[str, Any]] = {r.get("id"): r for r in snap.get("indicators", []) if r.get("id")}
    if indicator_ids:
        rows = (
            db.query(IndicatorRegistry)
            .filter(IndicatorRegistry.indicator_id.in_(indicator_ids))
            .all()
        )
        by_id = {r.indicator_id: r for r in rows}
        for iid in indicator_ids:
            r = by_id.get(iid)
            if not r:
                continue
            s = snap_by_id.get(iid, {})
            prov = s.get("provenance", {}) if isinstance(s, dict) else {}
            st = s.get("status")
            if st == "+1":
                status_label = "supportive"
            elif st == "-1":
                status_label = "draining"
            else:
                status_label = "neutral"
            formatted_value = _format_compact_value(iid, s.get("value_numeric"))
            cleaned_flip = _clean_flip_trigger(s.get("flip_trigger"))
            indicator_infos.append(
                {
                    "id": r.indicator_id,
                    "name": r.name,
                    # Snapshot-attached fields
                    "latest_value": formatted_value,
                    "z20": s.get("z20"),
                    "status": s.get("status"),
                    "status_label": status_label,
                    "obs_date": prov.get("observation_date"),
                    "window": s.get("window"),
                    "flip_trigger": cleaned_flip,
                }
            )
    # Avoid noisy logs in production

    prompt = build_brief_prompt(context, indicator_infos=indicator_infos)
    provider = get_provider()
    # Guard LLM call with a hard timeout so brief generation cannot hang
    try:
        raw_markdown = _complete_with_timeout(provider, prompt, timeout_s=20.0)
    except TimeoutError:
        raw_markdown = ""

    verifier = _verify_brief(raw_markdown, indicator_infos, context.get("regime", {}))

    # Populate in-process brief cache so other flows (e.g., ask_stream) can reuse without recompute
    try:
        _BRIEF_CACHE[(horizon, k)] = {"md": raw_markdown or "", "exp": time.time() + _BRIEF_TTL_SECONDS}
        # Also cache snapshot/router to reuse in streaming agent
        _SNAPSHOT_CACHE[horizon] = {"snap": {"snapshot": snap, "router": router, "as_of": snap.get("as_of")}, "exp": time.time() + _SNAPSHOT_TTL_SECONDS}
    except Exception:
        pass

    return {
        "horizon": horizon,
        "as_of": snap["as_of"],
        "frozen_inputs_id": snap.get("frozen_inputs_id"),
        "snapshot": snap,
        "router": router,
        "markdown": raw_markdown,
        "json": {
            "regime": context.get("regime"),
            "top_indicators": context.get("indicator_ids", [])[:5],
            "top_picks": [],
        },
        "verifier": verifier,
    }

# ------------------------
# Lightweight in-memory TTL cache for tools
# ------------------------
_TOOL_CACHE: Dict[str, Dict[Any, Dict[str, Any]]] = {
    "indicator_history": {},
}
_TTL_SECONDS: Dict[str, int] = {"indicator_history": 60}


def _cache_get(namespace: str, key: Any) -> Any:
    now = time.time()
    bucket = _TOOL_CACHE.get(namespace, {})
    ent = bucket.get(key)
    if not ent:
        return None
    if ent.get("exp", 0) <= now:
        try:
            del bucket[key]
        except Exception:
            pass
        return None
    return ent.get("val")


def _cache_set(namespace: str, key: Any, value: Any, ttl_seconds: Optional[int] = None) -> None:
    ttl = ttl_seconds if ttl_seconds is not None else _TTL_SECONDS.get(namespace, 30)
    bucket = _TOOL_CACHE.setdefault(namespace, {})
    bucket[key] = {"val": value, "exp": time.time() + ttl}


# Cached brief (markdown) per horizon/k to avoid recompute on each ask
_BRIEF_CACHE: Dict[Any, Dict[str, Any]] = {}
_BRIEF_TTL_SECONDS = 300

# Cache for snapshots/routers by horizon for reuse across LLM flows
_SNAPSHOT_CACHE: Dict[str, Dict[str, Any]] = {}
_SNAPSHOT_TTL_SECONDS = 300


def _get_cached_brief(db: Session, horizon: str, as_of: Optional[str], k: int = 12) -> str:
    key = (horizon, k)
    now = time.time()
    ent = _BRIEF_CACHE.get(key)
    if ent and ent.get("exp", 0) > now:
        return ent.get("md", "")
    try:
        from .orchestrator import generate_brief as _gen  # local import to avoid cycles
    except Exception:
        from app.llm.orchestrator import generate_brief as _gen  # type: ignore
    try:
        br = _gen(db, horizon=horizon, as_of=as_of, k=k)
        md = (br or {}).get("markdown") or ""
    except Exception:
        md = ""
    _BRIEF_CACHE[key] = {"md": md, "exp": now + _BRIEF_TTL_SECONDS}
    return md

def _get_cached_snapshot(horizon: str) -> Optional[Dict[str, Any]]:
    ent = _SNAPSHOT_CACHE.get(horizon)
    if not ent:
        return None
    if ent.get("exp", 0) <= time.time():
        try:
            del _SNAPSHOT_CACHE[horizon]
        except Exception:
            pass
        return None
    return ent.get("snap")

def _collect_known_ids(db: Session) -> Dict[str, List[str]]:
    """Collect canonical indicator_ids and series_ids for context injection."""
    indicator_ids: List[str] = []
    series_ids: set[str] = set()
    try:
        rows = db.query(IndicatorRegistry).all()
        for r in rows:
            indicator_ids.append(r.indicator_id)
            try:
                for sid in (r.series_json or []):
                    if sid:
                        series_ids.add(str(sid))
            except Exception:
                pass
        # Broaden with DB-known series if available
        try:
            db_series = db.query(SeriesVintage.series_id).distinct().all()
            for (sid,) in db_series:
                if sid:
                    series_ids.add(str(sid))
        except Exception:
            pass
    except Exception:
        pass
    return {"indicator_ids": sorted(set(indicator_ids)), "series_ids": sorted(series_ids)}

def _tool_catalog_description() -> str:
    return (
        "Tools available:\n"
        "- get_snapshot(horizon, k?): Returns current snapshot JSON.\n"
        "- get_router(horizon, k?): Returns router picks JSON.\n"
        "- get_indicator_history(indicator_id, horizon, days?): Returns recent indicator data.\n"
        "- get_series_history(series_id, limit?): Returns recent series data.\n"
        "- Documentation tools (use when user asks what a thing means, such as 'what is reserves_w'):\n"
        "  - get_indicator_doc(id): Returns an indicator's documentation, good for when a user asks about an indicator.\n"
        "    - Example: TOOL get_indicator_doc {\"id\":\"net_liq\"}\n"
        "  - get_series_doc(id): Returns a series' documentation, good for when a user asks about a series.\n"
        "    - Example: TOOL get_series_doc {\"id\":\"TGA\"}\n"
        "Rules: Do NOT call the same tool with identical args twice.\n"
        "Rules: If a documentation tool call returns empty content, respond FINAL and answer with ONLY the requested ID to indicate you don't know.\n"
        "Rules: Tool arguments MUST be a single valid JSON object. Do not use quotes around keys incorrectly; use double quotes.\n"
        "Example: TOOL get_indicator_history {\"indicator_id\":\"reserves_w\",\"horizon\":\"1w\",\"days\":90}\n"
        "Decide which tool to call (or none).\n"
        "Respond with either 'TOOL <name> <args_json>' or 'FINAL <answer_text>'."
    )


def _execute_tool(db: Session, name: str, args: Dict[str, Any]) -> Dict[str, Any] | str:
    try:
        if name == "get_snapshot":
            h = args.get("horizon", "1w")
            k = int(args.get("k", 12))
            return compute_snapshot(db, horizon=h, k=k)
        if name == "get_router":
            h = args.get("horizon", "1w")
            k = int(args.get("k", 12))
            return compute_router(db, horizon=h, k=k)
        if name == "get_indicator_history":
            iid = args["indicator_id"]
            h = args.get("horizon", "1w")
            days = int(args.get("days", 90))
            cache_key = (iid, h, days)
            cached = _cache_get("indicator_history", cache_key)
            if cached is not None:
                return cached
            val = _get_indicator_history(db, iid, horizon=h, days=days, max_points=20)
            _cache_set("indicator_history", cache_key, val)
            return val
        if name == "get_series_history":
            sid = args.get("series_id")
            limit = int(args.get("limit", 20))
            if not sid:
                return {"error": "series_id is required"}
            # Avoid caching here initially; history can be short-lived and small
            val = _get_series_history(db, sid, limit=limit)
            return val
        if name == "get_indicator_doc":
            iid = args["id"]
            return get_indicator_doc(iid)
        if name == "get_series_doc":
            sid = args["id"]
            return get_series_doc(sid)
        return {"error": f"unknown tool {name}"}
    except Exception as e:
        return {"error": str(e)}

def agent_answer_question_events(
    db: Session, question: str, horizon: str = "1w", as_of: Optional[str] = None
):
    """Generator yielding agent events for streaming (SSE-friendly).

    Events yielded as dicts with keys: event, data.
    event values: start, decision, tool_call, tool_result, final.
    """
    # Use cached brief as primary context; avoid recompute here
    brief_md = _get_cached_brief(db, horizon=horizon, as_of=as_of, k=6)
    # After ensuring brief, try to read cached snapshot metadata for start event
    cached = _get_cached_snapshot(horizon)
    snap = cached.get("snapshot") if cached else None
    provider = get_provider()
    messages: List[Dict[str, str]] = []
    # Inject KnownIDs context so the model can classify tokens without extra tool calls
    known = _collect_known_ids(db)
    known_ids_context = (
        "KnownIDs:\n"
        + "indicators=" + ",".join(known.get("indicator_ids", [])[:200]) + "\n"
        + "series=" + ",".join(known.get("series_ids", [])[:400])
    )
    system = build_agent_system_prompt(known_ids_context, _tool_catalog_description())
    messages.append({"role": "system", "content": system})
    redacted_q = _redact_pii(question)
    messages.append({"role": "user", "content": f"Question: {redacted_q}"})
    # Attach brief markdown and require alignment
    if brief_md:
        messages.append({
            "role": "assistant",
            "content": (
                "BriefContext (you MUST align with this; if conflict, prefer this):\n" + brief_md
            ),
        })

    start_payload: Dict[str, Any] = {"horizon": horizon}
    try:
        if isinstance(snap, dict):
            start_payload.update({"as_of": snap.get("as_of"), "regime": snap.get("regime")})
    except Exception:
        pass
    yield {"event": "start", "data": start_payload}
    tool_trace: List[Dict[str, Any]] = []

    answer_text: Optional[str] = None
    for _ in range(4):
        prompt = build_agent_step_prompt(align_with_brief=True)
        trimmed = messages[-6:] if len(messages) > 6 else messages
        model_input = trimmed + [{"role": "user", "content": prompt}]

        buffer = ""
        detected_final = False
        detected_tool = False
        tool_name = ""
        tool_json_buf = ""
        last_ping = time.time()
        # stream model output tokens
        try:
            for chunk in provider.stream(str(model_input)):
                token = str(chunk)
                # keepalive ping every ~15s
                now = time.time()
                if now - last_ping >= 15:
                    yield {"event": "ping", "data": {"t": int(now)}}
                    last_ping = now
                # Append to buffers first to allow marker detection before echoing
                if detected_tool:
                    # Accumulate tool JSON until parseable
                    tool_json_buf += token
                else:
                    buffer += token

                if detected_final:
                    # Forward answer tokens once FINAL detected
                    yield {"event": "answer_token", "data": {"text": token}}
                    answer_text = (answer_text or "") + token
                    continue
                if detected_tool:
                    import json as _json
                    try:
                        args = _json.loads(tool_json_buf)
                        # Loop guard: if repeating same tool+args, nudge and move to next decision step (no user-facing leak)
                        if tool_trace and tool_trace[-1].get("tool") == tool_name and tool_trace[-1].get("args") == args:
                            messages.append({
                                "role": "assistant",
                                "content": (
                                    "You already have the requested data. Respond as FINAL with a concise answer now."
                                ),
                            })
                            # Move to next decision step
                            break
                        yield {"event": "tool_call", "data": {"name": tool_name, "args": args}}
                        result = _execute_tool(db, tool_name, args)
                        tool_trace.append({"tool": tool_name, "args": args, "result": result})
                        try:
                            brief = _json.dumps(result, default=str)
                        except Exception:
                            brief = str(result)
                        messages.append({"role": "assistant", "content": _redact_pii(f"ToolResult({tool_name}): {brief[:800]}")})
                        yield {"event": "tool_result", "data": {"name": tool_name, "summary": brief}}
                        # Nudge: encourage FINAL in next step
                        messages.append({
                            "role": "assistant",
                            "content": (
                                "You now have the requested data. Respond as FINAL with a concise answer now."
                            ),
                        })
                        # Move to next decision step
                        break
                    except Exception:
                        # keep buffering until JSON completes
                        continue
                # Detect markers in buffer (only when not already in tool/final modes)
                # Detect markers in buffer
                if "FINAL " in buffer:
                    # Begin final answer streaming; include remainder after first FINAL
                    idx = buffer.find("FINAL ")
                    remainder = buffer[idx + len("FINAL ") :]
                    yield {"event": "decision", "data": {"type": "final"}}
                    if remainder:
                        yield {"event": "answer_token", "data": {"text": remainder}}
                        answer_text = (answer_text or "") + remainder
                    detected_final = True
                    continue
                if "TOOL " in buffer:
                    # Attempt to parse TOOL name and start capturing JSON args
                    try:
                        after = buffer.split("TOOL ", 1)[1]
                        parts = after.split(" ", 1)
                        if len(parts) == 2:
                            tool_name = parts[0].strip()
                            tool_json_buf = parts[1].strip()
                            yield {"event": "decision", "data": {"type": "tool", "name": tool_name}}
                            detected_tool = True
                            continue
                    except Exception:
                        pass
                # Not yet detected tool or final: forward thinking tokens (excluding already consumed markers)
                yield {"event": "thinking_token", "data": {"text": token}}
            else:
                # stream ended without an explicit decision; finalize
                if not answer_text:
                    answer_text = buffer.strip()
                yield {"event": "decision", "data": {"type": "final"}}
                break
        except Exception:
            answer_text = "Streaming failed while consulting the model."
            yield {"event": "error", "data": {"message": answer_text}}
            break

    if not answer_text:
        answer_text = "I don't know based on the available tools."
    yield {"event": "final", "data": {"answer": _redact_pii(answer_text), "tool_trace": tool_trace}}
