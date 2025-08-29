## Execution Timeline v2 (LLM-first, comprehensive)

This reorganized plan prioritizes the LLM layer in the next few days while retaining the full scope from the original plan (see `archive_timeline.md`). Items already completed remain checked.

References: `implementation-plan.md` (architecture/data model) and `llm-spec.md` (LLM prompts, verifier, tests).

### Phase A (Days 1–3): LLM endpoints and mockable orchestration

- [x] Router `api/routers/llm.py`:
  - [x] POST `/brief` { horizon, as_of?, k? } → { json, markdown, frozen_inputs_id }
  - [x] POST `/ask` { question, horizon?, as_of? } → { answer, citations }
- [x] Orchestrator `app/llm`:
  - [x] Retrieval tools: snapshot, router, indicator history, series values, registry docs
  - [x] Prompts per `llm-spec.md` (summarizer, ask)
  - [x] Verifier: numeric parity, section/length, banned words, top‑3 coverage, sign‑flip detection
  - [x] Provider interface + mock provider for tests
- [x] Config/env: `LLM_PROVIDER`, provider keys in `env.sample`, wire in `app/settings.py`
- [x] Tests: golden fixtures for `/brief` and `/ask` using mock provider

### Phase B (Days 4–5): Provider integration, tools-agent, and caching

- [ ] Integrate hosted provider (OpenAI/Anthropic) behind env flags
- [x] Add tool-using agent for `/llm/ask` (plan → tool call(s) → final answer)
  - [x] Define ToolCatalog (names, args, outputs) and selection rules
  - [x] Expose tools: get_snapshot, get_router, get_indicator_history, get_series_latest, get_indicator_doc, get_series_doc
  - [x] Orchestrator loop (max 3 steps), ToolCall → execute → ToolResult → FinalAnswer
  - [ ] Bugfix: for definitional questions, never call `get_series_doc` for indicator ids; ensure `get_indicator_doc` is used when token ∈ indicator_ids
  - [ ] Mock provider tool-calls; golden tests for tool selection (history vs series)
- [ ] Read‑through cache for `/brief` keyed by `snapshot_id` via `briefs_cache` (deferred)
- [ ] Basic logging/metrics: p50/p95 latency, verifier results

### Phase C (Days 6–7): Router rationales and scoring polish

- [ ] Add rationale strings and `duplicates_note` to `/router`
- [ ] Quality‑weighted bucket aggregation default switch (simple toggle)
- [ ] Finalize flip‑trigger strings from registry

### Phase D (Days 8–10): Pollers, automation, observability

- [ ] Implement pollers (daily/weekly/morning) with retry/backoff; idempotent writes
- [ ] Wire recompute trigger → compute pipeline; abstain on stale core inputs
- [ ] Observability: `events_log`, structured logs; simple counters/latency metrics

### Phase E (Days 11–12): Hardening and auth

- [ ] Admin auth for `/events/*`, `/brief`, `/ask`
- [ ] Rate limits and request timeouts on LLM calls; graceful shutdown

### Phase F (Days 13–14): Docs, acceptance tests, buffer

- [ ] Acceptance tests end‑to‑end; regression tests for LLM verifier
- [ ] Docs: API README, runbook, example snapshot replay
- [ ] Buffer for integration/polish on Router “why” strings

---

## Completed and carry‑over items from original plan

These remain part of the product scope and are considered done unless noted.

### Data ingestion and models

- [x] Alembic migrations; `indicator_registry` loader; `series_vintages`
- [x] FRED: `WALCL`, `RESPPLLOPNWW`, `RRPONTSYD`, `SOFR`, `IORB`, `DTB3`, `DTB4WK`, `WSHOSHO`, `WSHOMCB`, `RRP_RATE`
- [x] DTS: `TGA`, `UST_AUCTION_OFFERINGS`, `UST_AUCTION_ISSUES`, `UST_REDEMPTIONS`, `UST_INTEREST`
- [x] OFR: `OFR_LIQ_IDX`
- [ ] ALFRED vintage path (optional)

### Compute and persistence

- [x] Snapshot scorer (hybrid), concept buckets, missing‑data exclusion
- [x] Threshold indicators: `sofr_iorb`, `bill_rrp` (via `BILL_RRP_BPS`), `bill_share`, `qt_pace`, `ofr_liq_idx`
- [x] Provenance enrichment; `frozen_inputs_id`
- [x] Persist snapshots + all indicator rows; history de‑dup/upsert
- [x] As‑of modes: fetched/pub/obs; queries implemented
- [ ] Router selection: quotas, marginal contribution, rationale strings (in Phase C)

### APIs and tooling

- [x] `/events/recompute`, `/events/backfill_history`
- [x] `/snapshot`, `/router`, `/snapshot/history`, `/indicators/{indicator}/history`, `/series/{id}`
- [x] Static viz pages for series and indicators with docs explainer
- [ ] Admin auth for admin/LLM endpoints (Phase E)

### Supply/QT extensions (carry‑over)

- [x] QT caps table + `qt_pace` calculation
- [ ] Extend calculators: `ust_net_2w`, `settle_intensity`; morning poller and manual overrides (post‑LLM)

### Observability and hardening (carry‑over)

- [ ] `events_log`, structured logs, p95 timers (Phase D)
- [ ] Hardening, rate limits, timeouts (Phase E)
