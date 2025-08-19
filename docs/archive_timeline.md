## Archived Execution Timeline (2 weeks)

This file preserves the original two-week timeline prior to the LLM-first reorientation.

### Day 1–2

- [x] Initialize repo, Docker, Postgres, Alembic.
- [x] Implement `indicator_registry` from YAML; migration + loader.
- [x] Implement `series_vintages` schema.
- [ ] Add pydantic I/O models (if still desired for API schemas).

### Day 3–4

- [x] FRED adapter for `WALCL`, `RESPPLLOPNWW`, `RRPONTSYD`, `SOFR`, `IORB`, `DTB3`, `DTB4WK`.
- [ ] ALFRED vintage-aware path (optional for MVP).
- [x] DTS TGA adapter.
- [x] Unit tests for adapters/parsers.
- [x] FRED adapter extension for `WSHOSHO`, `WSHOMCB` (QT components).
- [x] OFR adapter for `OFR_LIQ_IDX` (daily).
- [x] DTS adapters for `UST_REDEMPTIONS` and `UST_INTEREST` (daily cash tables).
- [x] FRED adapter for `RRP_RATE` (admin rate series).

### Day 5

- [x] Snapshot scorer (MVP): z20-based scoring, label/tilt mapping, concept-bucket aggregation, category weighting, top‑K representatives by |z|, and exclusion of missing‑data indicators.
- [ ] Threshold-based scoring and persistence:
  - [x] `sofr_iorb` (> 0 bps persistent N days), generic single‑series thresholds.
  - [x] `bill_rrp` (> +25 bps persistent N days) using `DTB3/DTB4WK` and `RRP_RATE`; mark `bill_iorb` as duplicate.
  - [ ] (deferred post-MVP) `srf_usage` (> 0 persistent), `fima_repo` (> 0 persistent), `discount_window` (> 0) as floor tightness backstops.
  - [x] `bill_share` (≥ 65%) using `UST_AUCTION_OFFERINGS` once calculator is wired.
  - [x] (Optional) `qt_pace` (@cap) once `WSHOSHO/WSHOMCB` + `qt_caps` available.
  - [x] `ofr_liq_idx` (> 80th pct) once OFR adapter is in.
- [x] Enrich provenance in responses (`published_at`, `fetched_at`, `vintage_id`) and implement `frozen_inputs_id` wiring.
- [ ] Router selection logic: quotas, de‑dup by bucket, marginal‑contribution ranking, rationale strings.
- [ ] API stubs for `/snapshot` (`full`, `k`) and `/router` (include `duplicates_note`).
- [x] Define Pydantic I/O schemas for API (series points, registry, snapshot/router skeletons).
- [x] Typed responses for `/snapshot` and `/router` when implemented.

### Day 6

- [ ] Implement pollers (daily/weekly/morning). Idempotent writes, retry/backoff.
- [ ] Wire recompute trigger to snapshot pipeline; store `frozen_inputs_id`.
- [ ] Add `as_of` support to `compute_snapshot`/`compute_indicator_status` (thread through to queries via `get_as_of_series_values`).
- [x] Persist snapshots to `snapshots` + `snapshot_indicators` (one row per indicator with provenance) via compute pipeline and manual recompute.
- [ ] Create CLI to backfill snapshot history for last N business days (db-only replay using vintages).

### Day 7

- [x] Supply calculators: derive `ust_net_settle_2w` core math (weekly net = Issues − Redemptions − Interest) using `UST_AUCTION_ISSUES`, `UST_REDEMPTIONS`, `UST_INTEREST`.
- [ ] Extend calculators for `ust_net_2w`, `bill_share`, `settle_intensity`; add morning poller 7:30–8:30 ET and manual override table.
- [ ] QT caps table + `qt_pace` calculation (UST/MBS deltas vs caps).

### Day 8

- [x] OFR adapter; [ ] optional DefiLlama stub for `stables_7d`.
- [ ] Add auth for admin endpoints.
- [x] Implement `/events/recompute` to persist a snapshot (manual admin action).
- [x] Add `GET /series/{series_id}` with `start`, `end`, `limit`, `as_of` (latest vs as-of windows), return typed models.
- [x] Enable CORS (dev) for frontend integration.
- [x] Add `GET /snapshot/history?horizon=1w&days=180[&slim=true]` → returns `{ as_of, score, label }` in slim mode.

### Day 9

- [ ] Observability: `events_log`, structured logs, p95 timers.

### Day 10–11

- [ ] Acceptance tests end-to-end.
- [ ] Fix edge cases (holidays, staleness normalization).
- [ ] Finalize flip-trigger strings.

### Day 11 (LLM)

- [ ] Implement `/brief` orchestrator: tool calls, summarizer prompt, verifier.
- [ ] Implement `/ask` with grounding rules and citations.
- [ ] Cache brief per `snapshot_id`; add banned-words and numeric-fidelity checks in CI.

### Day 12

- [ ] Hardening: error paths, rate limits, request timeouts, graceful shutdown.

### Day 13–14

- [ ] Docs: API README, runbook, example snapshot replay.
- [ ] Buffer for integration issues; optional polish on Router “why” strings.
