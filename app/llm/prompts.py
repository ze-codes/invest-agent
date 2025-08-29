from __future__ import annotations
from typing import Any, Dict, Optional, List


def build_brief_prompt(context: Dict[str, Any], indicator_infos: Optional[List[Dict[str, Any]]] = None) -> str:
    regime = context.get("regime", {})
    label = regime.get("label")
    tilt = regime.get("tilt")
    score = regime.get("score")
    max_score = regime.get("max_score")
    bucket_summ = ", ".join([f"{b['bucket']}={b['aggregate_status']}" for b in context.get("buckets", [])])
    indicators = ", ".join(context.get("indicator_ids", []))
    # Provide a rendering context for indicators (id, name, category, series, directionality, scoring, notes)
    ctx_lines: List[str] = []
    if indicator_infos:
        for info in indicator_infos:
            ctx_lines.append(
                f"- id={info.get('id')}; name={info.get('name')}; category={info.get('category')}; "
                f"series={info.get('series')}; directionality={info.get('directionality')}; scoring={info.get('scoring')}; "
                f"notes={info.get('notes')}; latest_value={info.get('latest_value')}; z20={info.get('z20')}; status={info.get('status')}; status_label={info.get('status_label')}; "
                f"obs_date={info.get('obs_date')}; window={info.get('window')}; flip_trigger={info.get('flip_trigger')}"
            )
    indicators_context = "\n".join(ctx_lines)

    count = len(context.get("indicator_ids", []))
    return (
        "Write a concise daily liquidity brief.\n"
        "Constraints: concise; no financial advice; under 300 words.\n"
        "CRITICAL FORMAT RULES:\n"
        "- Output exactly three parts in this order: (1) one Regime line, (2) an 'Evidence:' header followed by bullets (one per indicator), (3) a final 'Interpretation:' paragraph (2-3 sentences).\n"
        "- Regime line format: 'Regime: {label} \u2192 tilting {tilt} (score {score} / max {max_score})'.\n"
        "- Evidence bullets: For EACH id in IndicatorIDs, render ONE bullet using ONLY the provided fields, in this format: \n"
        "  - <name-or-id>: <latest_value>[/<window if present>] (z <z20 if present>) \u2192 <status_label> | Flip: <flip_trigger>\n"
        "  Use the id if name is missing. If z20 is null, omit the (z ...) segment. If window is present, append '/<window>' to the value. Do not invent units or ranges.\n"
        f"- You MUST output exactly {count} bullets under Evidence — one per id — in the SAME ORDER as IndicatorIDs. Do NOT drop or add any.\n"
        "  If any field is missing, still include the bullet and omit only the missing subparts.\n"
        "- Do NOT invent ids, values, or ranges. Use only provided fields.\n"
        f"RegimeValues: Label={label}; Tilt={tilt}; Score={score}; MaxScore={max_score}.\n"
        f"IndicatorIDs: [{indicators}].\n"
        + ("IndicatorsContext:\n" + indicators_context + "\n" if indicators_context else "")
        + "Return only these three parts in markdown.\n"
    )

def build_agent_system_prompt(known_ids_context: str, tool_catalog: str) -> str:
    """System prompt for the streaming agent.

    known_ids_context: precomputed KnownIDs block (indicator_ids and series_ids)
    tool_catalog: output of the tool catalog description
    """
    return (
        "You are a precise liquidity assistant. Use tools only when needed.\n"
        + (known_ids_context + "\n" if known_ids_context else "")
        + tool_catalog
    )


def build_agent_step_prompt(align_with_brief: bool = True) -> str:
    """Per-step decision prompt for the streaming agent."""
    base = (
        "Decide next action. If you need data, respond as: \n"
        "TOOL <name> <json_args>\n"
        "Else, respond as: \n"
        "FINAL <answer>\n"
        "Constraints: keep under 300 words; no invented numbers; cite IDs exactly.\n"
        "If the question is definitional (e.g., 'what is X', 'define X', 'meaning of X'), FIRST fetch documentation: \n"
        "- If X matches a series_id (case-insensitive) in KnownIDs and not an indicator_id, call get_series_doc {\"id\":\"X\"}.\n"
        "- Else if X matches an indicator_id (case-insensitive), call get_indicator_doc {\"id\":\"X\"}.\n"
        "- If ambiguous (both), ask for clarification once instead of guessing.\n"
        "If the documentation response is empty or missing content, respond with: \"I don't know based on registry docs. Please provide the canonical ID (indicator or series). Example: reserves_w (indicator), RESPPLLOPNWW (series).\"\n"
        "Normalize tokens when matching KnownIDs: lowercase; strip punctuation; convert spaces/hyphens to underscores; accept minor obvious variants (e.g., 'netliq' -> 'net_liq').\n"
        "HARD RULES:\n"
        # "- Do NOT call a documentation tool more than once for the same query, even with casing or minor ID variants. Use what you fetched.\n"
        "- If you suspect a typo (e.g., 'WSHOMC'), map to the closest KnownIDs match (e.g., 'WSHOMCB') ONCE, fetch docs, then FINAL."
    )
    if align_with_brief:
        base += "\nWhen discussing an indicator, align direction with the BriefContext."
    return base
