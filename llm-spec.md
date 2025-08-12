## LLM Specification — Liquidity-Only MVP

This document provides engineering-level detail for the LLM layer used by the MVP’s Brief and Ask endpoints.

### Model matrix

- Primary: Claude 3.5 Sonnet (accuracy, long context)
- Balanced: GPT‑4o‑mini (cost/latency)
- Fast fallback: Claude 3.5 Haiku

Parameters (defaults):

- temperature 0.2, top_p 1.0, presence_penalty 0.0
- max_tokens: JSON ~1200, Markdown ~700
- JSON mode for Brief JSON; stream Markdown

### Brief JSON schema

```
{
  "tldr": string,
  "state": { "label": string, "tilt": string, "score": number, "max_score": number },
  "drivers": [ { "id": string, "status": "+1"|"0"|"-1", "why": string, "evidence": string } ],
  "what_changed": [ { "id": string, "from": string, "to": string, "delta": string } ],
  "watchlist": [ { "id": string, "trigger": string, "meaning": string } ],
  "events": [ { "name": string, "when": string } ],
  "citations": [ { "indicator": string, "series": string, "published_at": string, "vintage_id": string } ]
}
```

### Prompts

Summarizer system prompt (strict):
“You are a macro plumbing explainer. Use only tool outputs: get_snapshot/get_router/get_events/kb_search. Do not invent numbers. Report exact numbers from snapshot. Template: TL;DR (≤25 words), Drivers, What Changed, Watchlist, Events. If ≥2 Core stale, return ‘Insufficient fresh data to summarize.’ One-line intuition per driver (≤12 words). Never produce trade advice.”

Developer constraints:
“Return both JSON and Markdown. JSON must follow the schema exactly. Markdown must contain only numbers present in JSON/snapshot. Do not reveal chain‑of‑thought.”

Ask Liquidity system prompt:
“Answer only liquidity-scoped questions using registry + snapshot + KB. Cite page-level KB and series IDs. If out of scope, say so. No trade advice.”

### Orchestration pseudocode

```
def generate_brief(horizon):
    snap = get_snapshot(horizon)
    router = get_router(horizon)
    events = get_events(upcoming=True)
    prev = get_previous_snapshot(horizon)

    top3 = select_top3_by_abs_z(snap)
    changes = diff_snapshots(prev, snap)
    citations = build_citations(snap)

    json_out, md_out = call_model(snap, router, events, top3, changes, citations)

    verify_markdown_numbers(md_out, json_out, snap)
    verify_sections_and_length(md_out)
    verify_top3_coverage(json_out, top3)
    verify_sign_flips(json_out, changes)
    verify_banned_words(md_out)

    cache_brief(snap.snapshot_id, horizon, json_out, md_out)
    return { 'json': json_out, 'markdown': md_out, 'frozen_inputs_id': snap.frozen_inputs_id }
```

### Verifier contract

- Numeric parity: regex extract all numerics from Markdown; every numeric must appear in JSON or snapshot.
- Sections: TL;DR, Drivers, What Changed, Watchlist, Events present.
- Length: ≤ ~180 words.
- Coverage: top‑3 by |z| included as drivers.
- Change detection: any sign flips present in What Changed.
- Safety: banned words disallowed (buy/sell/long/short/etc.).

### Monitoring & logging

- Metrics: p50/p95 latency, failures by reason, adherence rate.
- Logs: model name, token counts, tool sizes, verifier outcomes; redact prompts; no chain‑of‑thought storage.

### Testing

- Unit: numeric parity parser, section/length checks, banned-words filter, top3 coverage.
- Integration: golden snapshot/router fixtures → stable JSON + Markdown.
- Regression: staleness → abstention; extreme values; zero-variance z.
