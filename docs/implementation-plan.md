## Liquidity-Only MVP — Implementation Plan

This plan describes how to build the Liquidity-Only MVP end-to-end: architecture, data model, ETL/pollers, scoring, APIs, observability, testing, and a two-week execution timeline.

### Objectives (from product plan)

- Compute a mechanical Liquidity Snapshot (Positive/Neutral/Negative + tilt) with ≤8 evidence rows, flip triggers, and full provenance.
- Provide a Relevance Router that returns the 6–8 most relevant indicators with reasons and next-update times, de-duplicated by concept.
- Guarantee reproducibility via point-in-time storage and a `frozen_inputs_id` for snapshots.
- Auto-recompute within SLOs after new data lands (N-minute targets).

### Non-Goals (MVP)

- No portfolio signals or trade advice. No broader macro synthesis beyond liquidity factor. No heavy backtests.

---

## Architecture

### Stack

- API: FastAPI (Python 3.11+)
- Storage: Postgres 15 (Timescale optional later)
- Background jobs: APScheduler (in-process) or Celery/Redis (if we need distributed later). Start with APScheduler.
- HTTP: httpx with retry/backoff
- Config/secrets: pydantic-settings + environment variables
- Containerization: Docker + docker-compose for local (api + db)
- LLM: hosted model provider (OpenAI-compatible API or self-host), with a small orchestrator and a programmatic verifier

### Services

- Source adapters: FRED/ALFRED, Treasury Fiscal Data (DTS), OFR, DefiLlama
- Ingestion/pollers: scheduled fetchers writing point-in-time observations using publish windows and new-vintage detection
- Compute: hybrid scorer (z + deterministic thresholds), concept-bucket aggregator, regime label/tilt mapper
- Router: marginal-contribution ranking with quotas and de-dup by bucket; evidence table builder (≤K rows)
- API layer: `/snapshot` (supports `full` and `k`), `/router`, `/indicators`, `/events/recompute`, `/health`, `/brief`, `/ask`
- Observability: structured logs, recompute audit log, simple metrics (latency; brief verifier outcomes)

---

## Data model (Postgres)

```
table series_vintages (
  vintage_id          uuid primary key,
  series_id           text not null,
  observation_date    date not null,
  vintage_date        date,          -- ALFRED realtime_start; null for non-ALFRED
  publication_date    timestamptz,   -- optional; MVP uses fetched_at for point-in-time
  fetched_at          timestamptz not null default now(),
  value_numeric       numeric not null,
  units               text not null, -- 'USD', 'percent', 'bps', etc.
  scale               numeric not null default 1, -- multiply raw by scale to get USD, etc.
  source              text not null, -- 'FRED', 'ALFRED', 'DTS', 'OFR', 'DEFI_LLAMA'
  source_url          text,
  source_version      text
);

table indicator_registry (
  indicator_id        text primary key,
  name                text not null,
  category            text not null,  -- core_plumbing, floor, supply, stress
  series_json         jsonb not null, -- list of source series IDs
  cadence             text not null,  -- daily | weekly | sched | weekly_daily
  directionality      text not null,  -- higher_is_supportive | higher_is_draining | lower_is_supportive
  trigger_default     text not null,
  scoring             text not null,  -- 'z' | 'threshold'
  z_cutoff            numeric,        -- default |z| >= 1 for z-based; nullable for threshold-based
  persistence         integer,        -- consecutive obs beyond boundary to change state (e.g., 2; floor spread 3)
  duplicates_of       text,           -- nullable link to canonical id
  poll_window_et      text,           -- optional operational hint, e.g., '15:00-19:00'
  slo_minutes         integer,        -- optional N-minute SLO target (e.g., 60 or 120)
  notes               text
);

table qt_caps (
  effective_date      date primary key,
  ust_cap_usd_week    numeric not null,
  mbs_cap_usd_week    numeric not null
);

table snapshots (
  snapshot_id         uuid primary key,
  as_of               timestamptz not null,
  horizon             text not null, -- '1w'|'2w'|'1m'
  frozen_inputs_id    uuid not null, -- groups the vintage_ids used
  regime_label        text not null, -- Positive|Neutral|Negative
  tilt                text not null, -- positive|negative|flat
  score               integer not null,
  max_score           integer not null
);

table frozen_inputs (
  frozen_inputs_id    uuid primary key,
  inputs_json         jsonb not null  -- [{indicator_id, series_id, vintage_id}] for replay
);

table snapshot_indicators (
  snapshot_id         uuid references snapshots(snapshot_id) on delete cascade,
  indicator_id        text references indicator_registry(indicator_id),
  value_numeric       numeric not null,
  window              text,         -- '5d'|'20d'|'1w' etc.
  z20                 numeric,      -- n/a if not used
  status              text not null, -- '+1'|'0'|'-1'
  flip_trigger        text not null,
  provenance_json     jsonb not null, -- {series:[...], published_at, fetched_at, vintage_id}
  primary key (snapshot_id, indicator_id)
);

table events_log (
  id                  bigserial primary key,
  event_type          text not null, -- 'poll', 'recompute', 'abstain'
  series_or_indicator text,
  scheduled_for       timestamptz,
  started_at          timestamptz not null default now(),
  finished_at         timestamptz,
  status              text not null, -- 'success'|'error'
  details             jsonb
);

-- Optional (LLM cache): store last successful brief per snapshot for reuse
table briefs_cache (
  snapshot_id         uuid primary key references snapshots(snapshot_id) on delete cascade,
  json_payload        jsonb not null,
  markdown_payload    text not null,
  created_at          timestamptz not null default now()
);
```

Migration tool: Alembic.

---

## Source adapters

### FRED/ALFRED

- Endpoints: FRED/ALFRED JSON; require API key. Use ALFRED for vintage-aware series.
- Series: `WALCL`, `RESPPLLOPNWW`, `RRPONTSYD`, `RRP_RATE`, `IORB`, `SOFR`, `DTB3`, `DTB4WK`.
- Extensions (DONE): `WSHOSHO`, `WSHOMCB` (QT/QE components for `qt_pace`).
- Transform: parse value, normalize to USD dollars if series is in millions (`scale=1e6`).
- Provenance: store `vintage_date` (ALFRED `realtime_start`), `observation_date`, `fetched_at`.

### Treasury Fiscal Data (DTS)

- TGA: Operating Cash Balance. Fields `record_date`, `publication_date`, `close_today_bal`.
- Auctions (DONE baseline): using `auctions_query` with fields `auction_date`, `issue_date`, `security_type`, `security_term`, `offering_amt`. We aggregate to two raw series: `UST_AUCTION_OFFERINGS` (by auction date) and `UST_AUCTION_ISSUES` (by issue date proxy).
- Provenance: use `fetched_at` (ingest time). `publication_date` may be null in MVP.

- Redemptions (DONE): public debt cash redemptions/maturities. Daily series `UST_REDEMPTIONS` from DTS Public Debt Transactions (sums `transaction_today_amt` where `transaction_type = "Redemptions"`).
- Interest (DONE): coupon/interest outlays. Daily series `UST_INTEREST` from DTS Deposits and Withdrawals of Operating Cash (Withdrawals where transaction category starts with “Interest on Treasury…”; prefer Gross when present).
  - Notes: Buybacks support is optional and can be added later when a reliable dataset is integrated.

### OFR / DefiLlama

- OFR Liquidity Stress Index (DONE): daily CSV (`fsi.csv`); ingested as `OFR_LIQ_IDX` with units `index`. Percentile trigger ("> 80th pct") to be wired in scoring.
- Stablecoins (DefiLlama): sum circulation; compute 7d net change.

### Fed facilities / H.4.1

- Standing Repo Facility usage (NEW): daily take-up ingested as `SRF_USAGE`.
- FIMA repo usage (NEW): daily usage ingested as `FIMA_REPO`.
- Discount window primary credit (NEW): weekly outstanding ingested as `DISCOUNT_WINDOW`.
  - Source: Board of Governors H.4.1 tables / FRBNY operations releases as applicable; persist `publication_date` and `fetched_at`.

---

## Computation layer

### Windows and z-scores (hybrid scoring)

- Daily indicators: 5d and 20d rolling on business days.
- Weekly indicators: 20 releases window (20 observations).
- Winsorize inputs (clip to 2.5th/97.5th percentiles) before z; require `std >= ε` (configurable). If not, set z=0.
- No interpolation; for `net_liq`, use latest weekly `WALCL` with latest daily `TGA`/`RRP`.

### Status contribution per indicator (hybrid)

- Flow-like indicators (deltas/spreads): use z-based rule with default cutoffs |z| ≥ 1 → ±1, else 0; apply directionality and optional persistence (e.g., require 2 consecutive observations beyond cutoff).
- Mechanical/admin indicators (QT caps, floor persistence, bill_share): use deterministic thresholds and optional persistence windows.
  - Implemented: `sofr_iorb` (> 0 bps persistent N days), generic single‑series thresholds.
  - Implemented: `bill_rrp` via derived `BILL_RRP_BPS` (min(DTB3, DTB4WK) − `RRP_RATE`) in bps; apply > +25 bps persistent N days; `bill_iorb` remains `duplicates_of: bill_rrp`.
    - Backstops: `srf_usage` (> 0 persistent), `fima_repo` (> 0 persistent), `discount_window` (> 0) under floor tightness bucket.
    - Supply mods: `bill_share` (≥ 65%).
    - QT: `qt_pace` (@cap) once `qt_caps` available.
    - Stress: `ofr_liq_idx` (> 80th pct).
- Always display both z and the active threshold when available; if z is suppressed (low variance/short history), mark as "threshold-backstop" in provenance.

### Concept buckets and aggregation

- Build buckets using `duplicates_of` links (each canonical indicator defines a bucket).
- For scoring the final regime, compute contributions for all indicators, then aggregate within each bucket (e.g., mean of member contributions, or inverse-variance weighted). Persist both member and bucket scores.
- Apply category weights to bucket aggregates (Core 50%, Floor 30%, Supply 20%).

### Evidence table selection (≤K rows)

- Compute marginal contribution of each indicator to the final weighted score (difference vs bucket aggregate without the indicator).
- Within each bucket, choose the representative with the largest absolute marginal contribution; include a `duplicates_note` listing suppressed peers.
- Enforce quotas (3 Core, 1–2 Floor, 1 Supply, optional 1 Stress) and cap K (default 8, configurable 6–10). Provide full JSON including all bucket/member scores. `/snapshot` supports `full=true` to return all members in addition to representative rows.

### Category weights and regime label

- Weights: Core 50%, Floor 30%, Supply 20%. Normalize if a category is missing due to staleness.
- Score = weighted sum of included indicators (rounded to integer). Map to label:
  - score ≥ +2 → Positive
  - score ≤ −2 → Negative
  - else → Neutral
- Tilt: sign of unrounded weighted sum (positive/negative/flat). Fine-tune thresholds during testing.

### De-duplication policy

- Use `duplicates_of` graph in registry. Selection keeps one representative per concept; Router includes note on resolution choice.

### Missing-data handling (added)

- Indicators with no underlying series points at compute time are treated as not available.
- Behavior:
  - Internally marked as `status = "n/a"` (no `value_numeric`, `z20`, or `window`).
  - Excluded from `/snapshot` evidence and `/router` picks to avoid misleading zeros.
  - This rule applies per indicator (e.g., `boj_bs` is omitted if `BOJ_ASSETS` has no data).

### Flip triggers

- Single numeric trigger per indicator in human-readable text (units explicit). Changing only that input across the threshold flips sign.

---

## LLM orchestration

### Components

- Orchestrator: fetches Router + Snapshot, plans sections, calls summarizer, runs verifier, caches result per `snapshot_id`.
- Summarizer: hosted LLM with a strict system prompt; only uses tool outputs; never invents numbers.
- Verifier: programmatic checks for numeric fidelity, length/sections, banned phrases, top-3 |z| coverage, sign-flip detection.

### Flow

1. Retrieve latest `snapshot` (by horizon) and `router` picks.
2. Select top-3 drivers by absolute z-score from included indicators; compute deltas vs prior snapshot for "what changed"; fetch upcoming events.
3. Call summarizer to produce JSON + Markdown.
4. Run verifier:
   - Every number in Markdown must appear in JSON/snapshot.
   - Enforce ≤ ~180 words, required sections.
   - Reject on banned words: buy/sell/long/short, etc.
   - Ensure top-3 |z| are represented; detect sign flips.
5. On success: persist to `briefs_cache` keyed by `snapshot_id`; on failure: request one retry with explicit errors; if still failing, return abstention.

### Endpoints

- GET `/brief?horizon=1w|2w|1m` → returns `{ json, markdown, frozen_inputs_id }`, cached by `snapshot_id`.
- POST `/ask` → `{ question, horizon? }` grounded in registry + snapshot with citations; out-of-scope guardrail.

### Latency targets

- Brief generation: p95 < 2s warm cache; < 5s cold (including one LLM round).

---

## Polling and recompute

### SLO defaults

- DAILY_N = 60 minutes; WEEKLY_N = 120 minutes.

### Schedules (ET)

- Daily pollers (every 15 min between 3–7 pm ET): RRP, RRP_RATE, TGA, SOFR/EFFR, bills, OFR, SRF/FIMA usage.
- Weekly pollers: Thu 3–6 pm ET (H.4.1 reserves/QT and discount window), Fri 3–6 pm ET (H.8).
- Morning job 7:30–8:30 am ET: ingest auction/settlement schedules plus redemptions/interest; precompute 2–4w net cash flow.

### Triggers

- When new observations arrive (new `fetched_at` for same observation_date), enqueue recompute. `publication_date`/`vintage_date` are optional.
- Recompute abstains if >2 Core indicators are stale (daily >48h, weekly >9d).

### Reliability

- Exponential backoff with jitter; circuit-breaker after consecutive failures.
- Idempotent writes keyed by `(series_id, observation_date, publication_date|fetched_at)` in MVP.

---

## APIs

- GET `/health` → liveness/DB check
- GET `/indicators` → registry (read-only)
- GET `/router?horizon=1w|2w|1m` → 6–8 picks with `why`, `trigger`, `next_update`, `duplicates_note`
- GET `/snapshot?horizon=1w|2w|1m[&full=true][&k=6..10]` → regime + ≤K evidence rows and the full bucket/member structure (if `full=true`), with provenance and `frozen_inputs_id`
- POST `/events/recompute` (admin) → manual refresh
- Versioning: add `X-App-Version` header and `/version` endpoint

Response formats follow the product plan examples.

### Data presence checklist (current vs TODO)

- Present (ingested): `WALCL`, `RESPPLLOPNWW`, `RRPONTSYD`, `TGA`, `SOFR`, `IORB`, `DTB3`, `DTB4WK`, `WSHOSHO`, `WSHOMCB`, `OFR_LIQ_IDX`, `UST_AUCTION_OFFERINGS`, `UST_AUCTION_ISSUES`, `UST_REDEMPTIONS`, `UST_INTEREST`.
- Missing (plan to ingest):
  - Admin rate: `RRP_RATE` (DONE).
  - Facilities/backstops: `SRF_USAGE`, `FIMA_REPO`, `DISCOUNT_WINDOW`.
  - Optional later: buybacks dataset for netting; `MOVE`, `ECB_ASSETS`, `BOJ_ASSETS`.

### API behavior updates (added)

- `/snapshot` and `/router` exclude indicators that lack series data (no points). This prevents rows like `value_numeric: 0` for unavailable inputs.
- `/snapshot` returns a `buckets` array with concept-bucket aggregates and members. Representatives are chosen as the member with the largest absolute z-score within each bucket, then globally limited to `k` by |z|.

---

## Observability

- Structured logs (JSON): polling, recompute decisions, abstentions, errors, durations.
- `events_log` row for each poll/recompute with timings and outcomes.
- Basic metrics endpoints (counts, p95 durations) for later Prometheus integration.

---

## Testing strategy

### Unit

- Adapters: parse/normalize values, handle missing fields, scaling to dollars.
- Z-score/window math: deterministic fixtures.
- De-dup resolver and category weighting.

### Integration

- Golden-sample datasets (small CSV/JSON) to run end-to-end recompute and assert snapshot JSON structure and provenance.

### Acceptance (mapped to plan)

1. De-duplication: no duplicate sub-buckets in snapshot; Router explains choice.
2. Provenance: every indicator row exposes series IDs, `published_at`, `fetched_at`, and vintage key; snapshot replay via `frozen_inputs_id` yields identical JSON.
3. Auto-update: within SLO windows after daily/weekly postings, recompute runs and audit line recorded.
4. Abstain path: stale core inputs trigger `insufficient_fresh_data`.
5. Flip logic: toggling only the flip input across threshold flips sign in tests.
6. Router policy: returns 6–8 picks with exact category quotas.
7. Latency: p95 < 2s warm, < 5s cold with caching of recent computations.
8. LLM: brief ≤ ~180 words; numeric claims match snapshot; banned-words check; includes top-3 |z|; detects sign flips.

### Added tests (implemented)

- Exclusion of missing-data indicators: ensure `/snapshot` and `/router` omit indicators whose underlying series have no points; only populated indicators appear (see `tests/test_exclude_missing_data.py`).
- DTS parsers: `tests/test_treasury_interest_parser.py`, `tests/test_treasury_redemptions_parser.py`.
- Weekly net settlements: `tests/test_supply_weekly_net_settlements.py`.

### Config defaults (operational)

- Timezone: America/New_York (ET); business-day calendar = Fed holidays.
- Z windows: daily=20 business obs; weekly=20 releases; no interpolation.
- Winsorization: 2.5th/97.5th pct on window values before μ, σ.
- Variance guard ε: treat z=0 if σ < max(1e-6, 1e-3·|μ|).
- Persistence: 2 consecutive obs to change state; floor `sofr_iorb` persistence=3 days.
- Category weights: Core 0.50, Floor 0.30, Supply 0.20; re-normalize if missing categories.
- Tilt deadband: ±0.25 of continuous weighted score for "flat".
- Staleness: daily > 48h; weekly > 9d; abstain if >2 Core stale.
- K (evidence rows): default 8, allowed range 6–10.
- Backoff: exp backoff with jitter, max ~5 retries (cap 30s); HTTP timeouts per adapter.

---

## Deployment

- Local: docker-compose (api + postgres). Makefile targets: `make up`, `make down`, `make test`.
- Env: `FRED_API_KEY`, `DATABASE_URL`, admin token, timezone set to `America/New_York` for scheduler.
- CI: run linters, unit/integration tests; fail on acceptance-test violations.

---

## Execution timeline

See `timeline_v2.md` for the current LLM‑first plan. The original two‑week plan is preserved in `archive_timeline.md` for reference.

## Risks & mitigations

- Treasury schedule quirks: add manual override table and validations.
- Revisions/vintage gaps: use ALFRED where available; otherwise store `fetched_at` with source date to approximate.
- Floor overlap: keep de-dup matrix opinionated; Router explains rationale.
- Licensing (MOVE, GC): exclude from MVP; rely on `sofr_iorb` and documented limitations.

---

## Open items (minor)

- Confirm final label/tilt thresholds after initial data dry-run.
- Decide ECB/BoJ unit policy (local-currency direction vs USD-converted) — default to local-direction only in MVP.
