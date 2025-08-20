from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, List, Tuple
import re

from sqlalchemy.orm import Session

from app.snapshot import compute_snapshot, compute_router
from app.settings import settings
from app.llm_providers import get_provider


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_provider():
    return get_provider()


# -------------------- Prompt builders --------------------
def _build_brief_context(snap: Dict[str, Any], router: Dict[str, Any]) -> Dict[str, Any]:
    top_ids: List[str] = [r["id"] for r in snap.get("indicators", [])]
    picks: List[str] = [p.get("id") for p in router.get("picks", [])]
    return {
        "regime": snap.get("regime", {}),
        "buckets": snap.get("buckets", []),
        "top_indicator_ids": top_ids,
        "top_picks": picks[:3],
    }


def _build_brief_prompt(context: Dict[str, Any]) -> str:
    regime = context.get("regime", {})
    label = regime.get("label")
    tilt = regime.get("tilt")
    score = regime.get("score")
    max_score = regime.get("max_score")
    bucket_summ = ", ".join([f"{b['bucket']}={b['aggregate_status']}" for b in context.get("buckets", [])])
    indicators = ", ".join(context.get("top_indicator_ids", [])[:5])
    picks = ", ".join(context.get("top_picks", []))
    return (
        "Write a concise daily liquidity brief.\n"
        "Constraints: 6-10 bullet points; no financial advice; cite top-3 picks; include regime and tilt; keep under 250 words.\n"
        f"Regime: label={label}, tilt={tilt}, score={score}, max_score={max_score}.\n"
        f"Buckets: {bucket_summ}.\n"
        f"TopIndicators: {indicators}.\n"
        f"TopPicks: {picks}.\n"
        "Return markdown with bullets only."
    )


def _build_ask_prompt(question: str, snap: Dict[str, Any]) -> str:
    return (
        "Answer strictly from the provided context. If unknown, say you don't know.\n"
        f"Question: {question}\n"
        f"Context: Regime={snap.get('regime')}, Indicators={[r['id'] for r in snap.get('indicators', [])]}\n"
        "Return a concise paragraph under 200 words."
    )


# -------------------- Verifiers --------------------
_BANNED = [
    "as an ai language model",
    "cannot access the internet",
]


def _contains_banned(text: str) -> Optional[str]:
    t = text.lower()
    for w in _BANNED:
        if w in t:
            return w
    return None


def _verify_brief(markdown: str, context: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if len(markdown) > 4000:
        issues.append("too_long")
    b = _contains_banned(markdown)
    if b:
        issues.append(f"banned:{b}")
    # Must include regime label and tilt
    label = context.get("regime", {}).get("label")
    tilt = context.get("regime", {}).get("tilt")
    if label and str(label).lower() not in markdown.lower():
        issues.append("missing_regime_label")
    if tilt and str(tilt).lower() not in markdown.lower():
        issues.append("missing_tilt")
    # Include top-3 coverage
    need = [p.lower() for p in context.get("top_picks", [])]
    covered = sum(1 for nid in need if nid and nid in markdown.lower())
    if covered < min(3, len(need)):
        issues.append("missing_top3")
    return (len(issues) == 0), issues


def _fallback_brief_markdown(context: Dict[str, Any]) -> str:
    regime = context.get("regime", {})
    lines = [
        f"- Regime: {regime.get('label')} (tilt: {regime.get('tilt')}, score: {regime.get('score')}/{regime.get('max_score')})",
    ]
    if context.get("buckets"):
        lines.append("- Buckets: " + ", ".join([f"{b['bucket']}={b['aggregate_status']}" for b in context["buckets"]]))
    if context.get("top_picks"):
        lines.append("- Top-3 indicators: " + ", ".join(context["top_picks"]))
    if context.get("top_indicator_ids"):
        lines.append("- Top indicators by |z|: " + ", ".join(context["top_indicator_ids"][:5]))
    lines.append("- View details at /snapshot and /viz/indicators")
    return "\n".join(lines)


def _verify_answer(text: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if len(text) > 4000:
        issues.append("too_long")
    b = _contains_banned(text)
    if b:
        issues.append(f"banned:{b}")
    return (len(issues) == 0), issues


# -------------------- Orchestrator --------------------
def generate_brief(db: Session, horizon: str = "1w", as_of: Optional[str] = None, k: int = 8) -> Dict[str, Any]:
    snap = compute_snapshot(
        db,
        horizon=horizon,
        k=k,
        save=False,
        as_of=None if not as_of else datetime.fromisoformat(as_of),
        as_of_mode="obs",
    )
    router = compute_router(db, horizon=horizon, k=k)

    context = _build_brief_context(snap, router)
    prompt = _build_brief_prompt(context)
    provider = _get_provider()
    raw_markdown = provider.complete(prompt)

    ok, issues = _verify_brief(raw_markdown, context)
    final_markdown = raw_markdown if ok else _fallback_brief_markdown(context)

    structured_json = {
        "regime": context.get("regime"),
        "top_indicators": context.get("top_indicator_ids")[:5],
        "top_picks": context.get("top_picks"),
    }

    return {
        "horizon": horizon,
        "as_of": snap["as_of"],
        "frozen_inputs_id": snap.get("frozen_inputs_id"),
        "snapshot": snap,
        "router": router,
        "markdown": final_markdown,
        "json": structured_json,
        "verifier": {"ok": ok, "issues": issues},
    }


def answer_question(db: Session, question: str, horizon: str = "1w", as_of: Optional[str] = None) -> Dict[str, Any]:
    snap = compute_snapshot(
        db,
        horizon=horizon,
        k=8,
        save=False,
        as_of=None if not as_of else datetime.fromisoformat(as_of),
        as_of_mode="obs",
    )
    prompt = _build_ask_prompt(question, snap)
    provider = _get_provider()
    raw_answer = provider.complete(prompt)
    ok, issues = _verify_answer(raw_answer)
    final = raw_answer if ok else "I don't know from the provided data."
    return {
        "horizon": horizon,
        "as_of": snap["as_of"],
        "answer": final,
        "citations": ["snapshot"],
        "verifier": {"ok": ok, "issues": issues},
    }


