# Liquidity-Only MVP — Product Plan

## 1) One-liner

**“A disciplined, on-demand snapshot of USD market liquidity—curated indicators, mechanical regime label, and auditable triggers—no trade calls.”**

---

## 2) Goals & Non-Goals

**Goals (MVP)**

- Track a **canonical set of liquidity indicators**; avoid double-counting by grouping per concept.
- Produce a **Liquidity Regime Snapshot** (Positive / Neutral / Negative, with “tilt”) on-demand and whenever new data lands.
- Provide a **Relevance Router** that picks the **6–8 most relevant** indicators with reasons, thresholds, and next update times.
- Guarantee **provenance** (series IDs, publish timestamps, point-in-time values) and **reproducibility** (frozen inputs).

**Non-Goals (MVP)**

- No inflation/employment analysis, no synthesis beyond the liquidity factor.
- No instrument-specific signals, no portfolio/trade recommendations.
- No statistical prediction or backtests beyond simple z-scores/thresholds.

---

## 3) Users & Value

- **Macro PM / Analyst:** Fast, auditable read on plumbing that risk assets co-move with.
- **Trader / Execution:** A single board of **what changed in liquidity** and **what would flip** the state, without opinion drift.

**Primary value:** Reduce cognitive load and narrative bias by enforcing a small, de-duplicated indicator set with explicit thresholds and timestamps.

---

## 4) Core Features (MVP)

### A) Liquidity Indicator Registry

To avoid duplication, the complete, up-to-date registry (series, definitions, directionality, triggers, and concept buckets) is maintained in `docs/indicator-registry.md`. Please refer to that document for the catalog and details.

---

### B) Liquidity Regime Snapshot (on-demand & event-driven)

- **Output:** `regime_label ∈ {Positive, Neutral, Negative} + tilt`, evidence table (≤8 rows), and **flip triggers** per row.
- **Computation scope:** Compute hybrid contributions for every indicator in the registry. Collapse correlated signals into concept buckets via `duplicates_of` and aggregate within each bucket so a single mechanism cannot dominate. Apply category weights (Core 50%, Floor 30%, Supply 20%) to bucket aggregates.
- **Scoring (hybrid):** Each indicator contributes **−1/0/+1** using a hybrid policy:
  - **Flow-like indicators** (e.g., `rrp_delta`, `tga_delta`, `reserves_w`, `ust_net_2w` deltas): score by **z20** (20 obs) with winsorization and a minimum-variance guard. Default cutoffs: |z| ≥ 1 → ±1; otherwise 0.
  - **Mechanical/admin indicators** (e.g., **QT at caps**, **floor persistence** like `sofr_iorb > 0 bps`, **bill_share ≥ 65%`): score by **deterministic thresholds\*\*.
  - **Display both**: show current z and the active threshold/trigger for transparency.
  - **Hysteresis**: require a small margin or persistence (e.g., 2–3 consecutive observations) to change sign to reduce flip-flopping.
  - **Backstop**: if `std < ε` or insufficient history (< 20 obs), treat z as 0 and fall back to threshold or neutral.
  - Weighted vote applied to bucket aggregates (Core 50%, Floor 30%, Supply 20%).
- **Provenance:** Every row shows `series_id(s), fetched_at (ingest ts), value, window, z` and, when available, `vintage_id`/`publication_date`. For MVP we only populate `fetched_at` + `observation_date`; `publication_date`/`vintage_date` are optional.

**Example (abbrev.)**

```
Regime: Neutral → tilting positive (score +2 / max +5)
Evidence:
- RRP Δ: -$120B/5d (z -1.3) → supportive | Flip: +$50B/5d
- TGA Δ: +$90B/5d (z +1.1) → draining | Flip: -$50B/5d
- Reserves Δ: +$30B/w → supportive | Flip: < +$10B/w
- UST net 2w: +$110B (bills 68%) → neutral/supportive | Flip: > +$150B
- SOFR-iorb: 0–2 bps → neutral | Flip: > +5 bps (3d)

```

### C) Relevance Router

- **Input:** `{horizon: '1w'|'2w'|'1m'}` (risk-assets aggregate).
- **Output:** Top **6–8** indicators with **why chosen (≤25 words)**, **default trigger**, **next update time**, **duplicates_of** resolution note.
- **Policy:** Always include **3 Core plumbing**, **1–2 Floor**, **1 Supply**, optional **1 Stress**.

---

### D) Liquidity Events (auto recompute)

- **FOMC admin rates / facility changes** (IORB, ON RRP rate; QT caps/reinvestment).
- **Treasury**: QRA, weekly auction & settlement calendars, ad-hoc Cash Mgmt bills.
- **TGA drivers**: tax dates, explicit rebuild/drain guidance.
- **H.4.1 special facility usage** spikes (SRF/discount window).
- **Regulatory** changes that alter balance-sheet capacity (e.g., SLR tweaks).

---

## 5) Data & Pipeline

**Cadence**

- Daily: RRP, TGA, SOFR/EFFR, bills, repo proxy, OFR, MOVE, stables, (HY OAS lag ok).
- Weekly: Reserves / H.4.1, H.8, ECB/BoJ.
- Schedule-based: Issuance, settlements, QRA, tax dates.

**Point-in-Time**

- Store **vintages** (value, source timestamp, fetch timestamp). Snapshots freeze inputs for replay.

**Quality Gates**

- Missing >2 **Core** indicators ⇒ “insufficient fresh data.”
- Method change/outlier flag → down-weight to 0 unless acknowledged.

---

## 6) UX & Outputs

**Pages**

1. **Snapshot** — headline label + evidence table, updated timestamps, flip triggers, and a compact sparkline per indicator (20-day).
2. **Router** — the 6–8 chosen indicators with “why chosen,” next update time, and provenance.
3. **Events** — upcoming schedule (issuance, settlements, FOMC admin changes) with expected recompute times.
4. **Registry** — read-only catalog (ids, formulas, cadences).

**Interaction**

- **On-demand query** (“refresh now”) and **auto recompute** after data posts.
- Copyable **JSON** and **markdown** for the Snapshot.

---

## 7) APIs (MVP)

**GET `/snapshot`**

- **Query:** `horizon=1w|2w|1m` (required), `full=true|false` (default `false` → evidence table only), `k=6..10` (optional display cap; default `8`).
- **Response:**

```json
{
  "as_of": "2025-08-11T16:05Z",
  "regime": {
    "label": "Neutral",
    "tilt": "positive",
    "score": 2,
    "max_score": 5
  },
  "indicators": [
    {
      "id": "rrp_delta",
      "value": -120000000000,
      "window": "5d",
      "z20": -1.3,
      "status": "+1",
      "flip_trigger": "Δ >= +50B/5d",
      "provenance": {
        "series": ["RRP"],
        "fetched_at": "...",
        "vintage_id": "..."
      }
    }
  ],
  "buckets": [
    {
      "bucket": "core_plumbing/net_liq",
      "aggregate_status": "+1",
      "members": ["net_liq", "rrp_delta", "tga_delta", "reserves_w"]
    }
  ],
  "frozen_inputs_id": "snap_..."
}
```

**GET `/router`**

```json
{
  "horizon": "1m",
  "picks": [
    {
      "id": "net_liq",
      "why": "Tracks broad risk beta via BS−TGA−RRP",
      "trigger": "20d z ≥ +1",
      "next_update": "2025-08-14T20:30Z"
    }
  ]
}
```

**GET `/indicators`** → registry.

**POST `/events/recompute`** → manual refresh (admin-guarded).

**GET `/brief`** → returns `{ json, markdown, frozen_inputs_id }` summarizing the current Snapshot/Router with citations.

**POST `/ask`** → grounded Q&A over the registry and Snapshot; requires citations and in-scope guardrails.

---

## 8) Acceptance Tests (MVP)

1. **De-duplication:** Snapshot never shows two indicators from the same **sub-bucket** (e.g., RRP Δ and bill-vs-IORB without a note on overlap); Router explains the choice.
2. **Provenance:** Every indicator row exposes `series_id(s)`, `published_at`, `fetched_at`, and a **vintage key**; Snapshot can be replayed byte-for-byte via `frozen_inputs_id`.
3. **Auto-update:** Within **N minutes** of RRP/TGA postings and **H.4.1 day**, `/snapshot` recomputes; a log entry records the trigger.
4. **Abstain path:** If >2 **Core** indicators are stale (>48h for daily, >9d for weekly), Snapshot returns `"insufficient_fresh_data"`.
5. **Flip logic:** Each indicator includes a single numeric **flip trigger**; changing only that input across the threshold flips its contribution sign.
6. **Router policy:** `/router` returns **6–8** picks, includes **exactly 3 Core**, **≥1 Floor**, **≥1 Supply**, optional **1 Stress**.
7. **Latency:** P95 compute time < 2s warm cache, < 5s cold cache (MVP target).

---

## 9) Non-Functional Requirements

- **Reproducibility:** Point-in-time storage for all inputs; immutable `frozen_inputs_id`.
- **Transparency:** Plain-English “why chosen” (≤25 words) for every Router pick.
- **Reliability:** Graceful degradation when a data source is late; clear status banners.
- **Security:** Read-only public endpoints for Snapshot/Router; admin token for recompute.

---

## 10) Rollout & Timeline (solo dev, AI-copilot, ~2 weeks)

**Week 1**

- Registry + ETL for Core (RRP, TGA, H.4.1, QT caps) and Floor (SOFR/IORB).
- Point-in-time storage; Snapshot v0 (Core-only).
- Router v0 (Core-first policy).

**Week 2**

- Add Supply (issuance/settlement nets) + OFR stress.
- Snapshot vote/weights, flip triggers, provenance UI.
- Auto-recompute hooks; acceptance tests; minimal docs.

---

## 11) Risks & Mitigations

- **Issuance/settlement data quirks:** Scrape variability → add a manual override & sanity checks.
- **Repo data gaps:** Use SOFR-IORB as the default proxy; GC-IORB becomes “Should.”
- **Interpretation drift:** Keep outputs **mechanical** (scores + triggers); defer narrative.

---

## 12) Future Features (Post-MVP)

**New Factors**

- **Inflation:** CPI/PCE surprises, sticky inflation measures; link to liquidity via policy path.
- **Labor/Growth:** NFP, ISM, PMIs; recession risk composites.
- **Credit Micro:** CP spreads, bank funding detail, IG/HY primary issuance.

**Deeper Liquidity**

- **Global:** ECB/BoJ/PBoC flows with USD translation.
- **Market Micro:** Order book depth (UST futures), ETF primary flow proxies.

**From Factor to Assets (when ready)**

- **Cross-asset mapping:** Historical co-movement between the **liquidity regime** and aggregates (Equities, BTC/ETH, HY, Duration).
- **Trigger board:** Mechanical alerts when key thresholds fire (no opinions).
- **Scenario builder:** QRA/IORB/QT change “what-ifs”.

**Modeling & Evaluation**

- **Policy reaction function:** Qualitative scaffolds → light quant using OIS/term-premia.
- **Backtests:** Abstention-aware scoring of regime usefulness; stability tests.

**Product**

- **Slack/Telegram alerts**, **export to Notion/Jira**, **multi-user workspaces**, **KB links** (“Why these 8?” with book citations).

---

## 13) LLM Communication Layer (MVP)

**Purpose:** Clear, mechanical communication of liquidity state; no trade advice. Converts Snapshot/Router into a concise, verifiable brief and supports scoped Q&A.

**Tools/Inputs:** `get_snapshot(horizon)`, `get_router(horizon)`, `get_events(upcoming=true)`, optional `kb_search(query, top_k=3)`.

**Outputs:**

- JSON: `{ tldr, state, drivers, what_changed, watchlist, events, citations }`.
- Markdown: TL;DR → Drivers → What Changed → Watchlist → Events. All numbers must match `get_snapshot`.

**Style constraints:** ≤ ~180 words; no invented numbers; each numeric claim has a citation tag; abstain if ≥2 Core inputs are stale.

**Orchestration:**

1. Call Router + Snapshot.
2. Pick top-3 drivers by |z|; diff vs prior snapshot for "what changed"; add upcoming events.
3. Summarizer drafts JSON + Markdown.
4. Verifier checks numeric consistency, sections/length, banned phrases, top-3 coverage, sign-flip detection. On failure, request revision.

**APIs:**

- `GET /brief` → `{ json, markdown, frozen_inputs_id }`.
- `POST /ask` → grounded Q&A with page-level citations; out-of-scope guardrail.

**Acceptance (LLM-specific):**

1. Factuality: every number in Markdown appears in snapshot/JSON.
2. Coverage: includes top-3 drivers by |z|.
3. Change detection: sign flips noted in "What Changed".
4. Abstention on stale inputs.
5. No trade advice: fail on banned words (buy/sell/long/short, etc.).

### LLM deliverables

#### A) Liquidity Brief (auto + on-demand)

- Purpose: Turn JSON data into a concise, correct, explainable write-up.
- Inputs (tools): `get_snapshot(horizon)`, `get_router(horizon)`, `get_events(upcoming=true)`, `kb_search(query, top_k=3)`.
- Output:
  - JSON structure with `tldr`, `state`, `drivers`, `what_changed`, `watchlist`, `events`, `citations`.
  - Markdown for users: TL;DR → Drivers → What Changed → Watchlist → Events. Numbers must match `get_snapshot`.
- Style constraints:
  - ~180 words max; no invented numbers; numeric claims have citation tags; abstain if ≥2 core inputs are stale.
- Summarizer system prompt (excerpt):
  - Use only tool outputs; report exact numbers from `get_snapshot`; keep to the template; include one-line intuition per driver (≤12 words); never produce trade advice.

#### B) Ask Liquidity (Q&A)

- Purpose: Grounded answers to “Why did RRP fall matter?” or “What’s TGA?”
- Tools: `get_snapshot`, `get_registry`, `kb_search`.
- Rules: Ground in registry/KB with page citations; out-of-scope guardrail for non-liquidity questions; point to relevant indicators/triggers.

### Agent sketch (simple but agentic)

1. Call Router + Snapshot.
2. Build a plan: top 3 drivers by |z|; diff vs last snapshot for “what changed”; identify next events.
3. Ask Summarizer LLM to draft JSON + Markdown.
4. Run Verifier (programmatic):
   - Check all numbers in Markdown exist in JSON/snapshot; check length/sections; ban trade-advice phrases; ensure coverage of top-3 |z|; detect sign flips.
5. Emit final JSON + Markdown.

### Evaluation (LLM-specific)

- Factual error rate: target 0%.
- Template adherence pass rate.
- User clarity thumbs-up rate.
- Latency: P95 summarization round-trip < 2s (warm).

### Minimal schemas (for implementation)

- Router pick:
  - `{ id, why, trigger, next_update }`
- Registry entry:
  - `{ id, name, category, directionality, definition, kb_refs }`

### Example Markdown (pattern)

TL;DR: Liquidity is Neutral, tilting positive (score +2/5). Support comes from RRP outflows (−$120B/5d) and rising reserves (+$30B/w). Headwind: TGA rebuild (+$90B/5d).
Drivers:

- RRP Δ: −$120B/5d → cash exiting MMFs. [ONRRP, 2025-08-11]
- Reserves Δ: +$30B/w → easier bank plumbing. [H.4.1, 2025-08-08]
- TGA Δ: +$90B/5d → fiscal cash drain. [TGA, 2025-08-11]
  What changed: TGA flipped neutral→negative on a +$60B 5d rise.
  Watchlist: Net UST cash flow > +$150B/2w would turn liquidity negative.
  Events: H.4.1 update Thu 20:30Z; weekly issuance/settlements daily 12:00Z.

Note: All numbers must be pulled from your snapshot; above is a pattern.

### Build checklist (1–2 days for LLM bits)

- Implement tools: `get_snapshot`, `get_router`, `get_events`, `kb_search`.
- Write the summarizer system prompt and a verifier script (pure Python).
- Add `/brief` endpoint returning `{json, markdown, frozen_inputs_id}`.
- Add `/ask` endpoint with grounding rules and citations.
- Unit tests: red/green cases for factuality, abstention, and change detection.

### LLM configuration defaults (models and parameters)

- Primary: Claude 3.5 Sonnet (accuracy, long context). Fallback: GPT‑4o‑mini (cost/latency). Fast fallback: Claude 3.5 Haiku.
- Parameters (defaults): temperature 0.2, top_p 1.0, presence_penalty 0.0, max_tokens ~700 for Markdown, ~1200 for JSON.
- Modes: force JSON strict mode for the Brief JSON; stream Markdown after JSON passes verification.

### Prompts (templates)

- Summarizer system prompt (strict): “You are a macro plumbing explainer. Use only tool outputs: get_snapshot/get_router/get_events/kb_search. Do not invent numbers. Sections: TL;DR (≤25 words), Drivers, What Changed, Watchlist, Events. If ≥2 Core stale, return ‘Insufficient fresh data to summarize.’ One-line intuition per driver (≤12 words). Never produce trade advice.”
- Developer constraints: “Return both JSON and Markdown. JSON must follow the schema exactly. Markdown must contain only numbers present in JSON/snapshot. Do not reveal chain‑of‑thought.”
- Ask Liquidity system prompt: “Answer only liquidity-scoped questions using registry + snapshot + KB. Cite page-level KB and series IDs. If out of scope, say so. No trade advice.”

### Orchestration and verifier (deterministic)

1. Plan: fetch snapshot + router + events; compute top‑3 drivers by |z|; diff against prior snapshot; assemble citations.
2. Draft: call model to produce Brief JSON + Markdown in one shot (JSON mode first, then Markdown).
3. Verify (programmatic):
   - Numeric parity: every number in Markdown exists in JSON/snapshot.
   - Sections/length: all required sections present; ≤ ~180 words.
   - Coverage/change: includes top‑3 by |z|; lists sign flips since prior snapshot.
   - Safety: banned words (buy/sell/long/short) absent.
4. Remediate: if fail, call once with explicit errors; if still fail, abstain and/or serve last good from cache.
5. Cache: key by `snapshot_id` + horizon; TTL until next recompute; ETag for UI.

### Monitoring and SLOs

- Latency: p95 ≤ 2s warm cache; ≤ 5s cold (one LLM round).
- Quality: 0% factual error target; track verifier failure reasons; template adherence rate.
- Logging: prompt metadata (redacted), tool sizes, model IDs, latency; never store chain‑of‑thought.

## Appendix

### Operational assumptions (MVP defaults)

- Time and calendars

  - Baseline timezone: America/New_York (ET). “Daily” = U.S. business days using the Fed holiday calendar.
  - Holidays/early closes: publish windows shift to next business day; staleness clocks pause until then.

- Hybrid scoring parameters

  - Windows: daily z uses 20 business-day observations; weekly z uses 20 releases (no interpolation).
  - Winsorization: clip window values to the 2.5th/97.5th percentiles before computing μ, σ.
  - Variance guard: if σ < max(1e-6, 1e-3·|μ|), treat z=0 (neutral) and fall back to deterministic threshold when available.
  - Persistence/hysteresis: need 2 consecutive observations beyond cutoff to change state (floor persistence: 3 consecutive days for `sofr_iorb > 0 bps`).
  - Label thresholds: Positive if score ≥ +2, Negative if score ≤ −2, otherwise Neutral.
  - Tilt deadband: tilt is positive/negative by sign of continuous score with a deadband of ±0.25 for flat.

- Bucket aggregation and weights

  - Concept buckets: group by `duplicates_of` root. Aggregate member contributions by simple average (MVP); revisit inverse-variance later.
  - Category weights: Core 50%, Floor 30%, Supply 20%. If a category is missing, re-normalize present categories to sum to 1.

- Evidence selection (display ≤ K rows)

  - K default 8 (configurable 6–10). Quotas: 3 Core, 1–2 Floor, 1 Supply, optional 1 Stress.
  - Representative per bucket is the indicator with the largest absolute marginal contribution to the final weighted score; add `duplicates_note` listing suppressed peers.

- Staleness and abstention

  - Stale if: daily > 48h since `published_at` (or last obs date), weekly > 9 days. If > 2 Core indicators are stale → abstain with "insufficient_fresh_data".
  - Core set for this rule: `rrp_delta`, `tga_delta`, `reserves_w`, `qt_pace` (or `net_liq` if used as canonical core aggregate).

- Next-update heuristics

  - Each indicator displays `next_update` based on cadence and typical publish windows; show "late" if 30 minutes past window end without a new print (daily) or 90 minutes (weekly).

- Flip triggers (UI vs logic)

  - UI shows a single flip trigger (the nearest boundary that ends support). Under the hood, states are −1/0/+1 with a neutral band and persistence.

- Error handling
  - Source retries: exponential backoff with jitter (up to ~5 retries, max 30s), timeouts per adapter. Writes are idempotent by `(series_id, observation_date, vintage|publication_date)`.
  - Validation failures: mark indicator neutral (0), set stale reason, and log for investigation.

### Suggested SLOs (pick defaults)

| Source group                                              | Typical cadence            | Proposed polling window (ET)                  | N-minute target (auto recompute)                                       |
| --------------------------------------------------------- | -------------------------- | --------------------------------------------- | ---------------------------------------------------------------------- |
| **Daily** (RRP, TGA, SOFR/EFFR, bill yields, OFR index)   | once per U.S. business day | 3–7 pm ET (staggered, hourly)                 | **≤ 30–60 min** after publish                                          |
| **Weekly** (H.4.1 reserves/QT – Thu; H.8 bank data – Fri) | weekly                     | 3–6 pm ET on release day                      | **≤ 90 min** after publish                                             |
| **Schedule-based** (auctions/settlements/QRA)             | as posted                  | 7–8 am ET daily + on known announcement times | Refresh by **8:30 am ET** daily; manual recompute on big announcements |
| **Global weekly** (ECB/BoJ)                               | weekly                     | 3–6 pm local→ET                               | **≤ 90 min**                                                           |

If you want one number to start with: **N=60 min for daily, N=120 min for weekly**, then tighten later.

### No data contracts? Use these free sources first

(You can swap to paid later if needed.)

- **FRED/ALFRED API** (point-in-time capable):
  - Fed balance sheet: `WALCL`
  - Reserve balances: `RESPPLLOPNWW`
  - IORB: `IORB`
  - SOFR: `SOFR`
  - EFFR: `EFFR`
  - 3m bill yield: `DTB3` (and `DTB4WK` for 4-week)
- **Treasury fiscal data API** (Machine-readable):
  - **TGA / Operating Cash Balance** (Daily Treasury Statement)
  - **Auction announcements/results** (issuance & settlements to compute net cash flow)
- **Fed RRP**:
  - FRED series for ON RRP outstanding (daily). (Use your own alias; confirm series name once in code.)
- **OFR Treasury Market Liquidity Stress Index**:
  - Public daily index (use latest official feed; simple JSON/CSV).
- Optional, when ready:
  - **H.8 weekly** (bank deposits/securities) via Fed release tables (also mirrored on FRED).
  - **ECB/BoJ balance sheet** via their weekly releases (FRED mirrors common aggregates).

> Tip: for anything you pull from FRED that has revisions, also store the ALFRED vintage you used so you can replay a Snapshot exactly.

### Indicator reference

For complete, canonical definitions (series, directionality, triggers, buckets), see `docs/indicator-registry.md`. This file no longer duplicates the registry.

### Minimal implementation next steps

1. **Set SLO constants**: `DAILY_N=60m`, `WEEKLY_N=120m`.
2. **Pollers**:
   - Daily job every 15m between **3–7 pm ET** for RRP/TGA/SOFR/EFFR/bills/OFR.
   - Thursday/Friday **3–6 pm ET** pollers for H.4.1 and H.8.
   - Morning **7:30–8:30 am ET** job to ingest auction/settlement schedules and precompute net 2–4w cash flow.
3. **Freeze inputs** on recompute: store `{series_id, published_at, fetched_at, value}` per indicator + a `frozen_inputs_id`.
4. **Router/Snapshot**: score the latest values, enforce de-duplication, emit flip triggers, surface provenance.

### Starter registry

The registry is maintained in one place: `registry.yaml`. Refer to that file for the live list.
