## Series Contracts and Data Sources (MVP)

This document fixes canonical series IDs, sources, units, transforms, and provenance needed to implement the Liquidity-Only MVP. All IDs use source-native names where possible. Point-in-time storage is required for reproducibility.

### Core series (canonical)

- `WALCL` — Fed balance sheet (Assets), weekly. Source: FRED/ALFRED. Units: USD, millions (NSA). Use ALFRED for vintages.
- `RESPPLLOPNWW` — Reserve balances, weekly. Source: FRED/ALFRED. Units: USD, millions (NSA). Use ALFRED for vintages.
- `RRPONTSYD` — ON RRP outstanding, daily. Source: FRED/ALFRED. Units: USD, millions. Use ALFRED for vintages.
- `TGA` — Treasury General Account, daily. Source: Treasury Fiscal Data (DTS) Operating Cash Balance API. Field: `close_today_bal` (USD). Keys: `record_date`, `publication_date`.
- `IORB` — Interest on Reserve Balances, daily. Source: FRED/ALFRED. Units: percent.
- `SOFR` — Secured Overnight Financing Rate, daily. Source: FRED/ALFRED. Units: percent.

### Money-market floor, repo, bills (derived)

- `sofr_iorb` — Spread = `SOFR − IORB` (bps). Persist computed values.
- `bill_iorb` — Spread = `min(DTB3, DTB4WK) − IORB` (bps). Source: FRED/ALFRED `DTB3`, `DTB4WK` (percent).
- `gc_iorb` (optional) — GC repo − IORB (bps). Note: lack of free GC index; default proxy is `sofr_iorb` for MVP.

### Treasury supply and settlements

- `ust_net_2w` — Net UST cash flow over next 2–4 weeks. Sources: Treasury Fiscal Data auction schedules/results. Fields: `security_type`, `auction_date`, `issue_date/settlement_date`, `total_accepted`. Requires redemption schedule; provide manual overrides when missing.
- `bill_share` — Bills as share of total issuance over window. Units: percent.
- `settle_intensity` — Sum of coupon settlement outflows per week. Units: USD.

### QT pace

- `qt_pace` — Weekly runoff vs caps.
  - Data: H.4.1 weekly deltas of securities held outright (UST/MBS) via FRED (e.g., UST, MBS aggregates).
  - Caps: configuration table keyed by `effective_date` with UST/MBS caps. Units: USD/week.

### Banking (H.8)

- `h8_deposits` — Bank deposits 1w Δ. Source: H.8 (FRED mirrors). Units: USD/week.
- `h8_secs` — Bank securities 1w Δ. Source: H.8 (FRED mirrors). Units: USD/week.

### Stress and credit

- `ofr_liq_idx` — OFR Treasury Market Liquidity Stress Index, daily. Source: OFR public CSV/JSON. Units: index (use percentile for trigger).
- `move_idx` (optional) — MOVE index. Licensing constraints; skip or use public proxy for MVP.

### Global (weekly)

- `ecb_bs` — ECB balance sheet total assets. Source: FRED mirror. Units: EUR (consider direction-only in local currency for MVP).
- `boj_bs` — BoJ balance sheet total assets. Source: FRED mirror. Units: JPY (direction-only for MVP).

### Crypto

- `stables_7d` — Stablecoin net issuance 7d. Source: DefiLlama stablecoins API. Units: USD change over 7 days.

### Contract details

- IDs: Prefer source-native `series_id` (FRED codes). Composite indicators list `series: [...]` in registry entries.
- Endpoints:
  - FRED/ALFRED with API key for vintages.
  - Treasury Fiscal Data (DTS) endpoints for TGA and auctions.
  - OFR public feed; DefiLlama for stablecoins.
- Field mapping:
  - FRED/ALFRED: `observation_date`, `value` (string); ALFRED adds `realtime_start`/`realtime_end`.
  - DTS (TGA): `record_date`, `publication_date`, `close_today_bal`.
  - DTS (auctions): `auction_date`, `security_type`, `total_accepted`, `issue_date`/`settlement_date`.
- Units and transforms:
  - Store currency in USD dollars (normalize FRED millions with `scale=1e6`).
  - Rates in percent; computed spreads in basis points.
  - Windows: 5d/20d on business days (daily); 20 releases (weekly).
- Publish timestamps:
  - FRED/ALFRED: use `vintage_date` (ALFRED) + `fetched_at` timestamp; maintain expected publish-time windows per series.
  - DTS: `publication_date` (date). If no time, store date and `fetched_at`.
- Staleness thresholds:
  - Daily max age: 48 hours. Weekly: 9 days. Timezone: ET. Holidays: roll to next business day.
- Error handling: Missing data marks indicator stale; do not impute. Router may exclude per policy.
- Provenance record (per observation): `series_id`, `observation_date`, `vintage_date|publication_date`, `fetched_at`, `value`, `source_url`, `source_version`.

---

## Indicator scoring examples (MVP)

Defaults: flow-like series use z20 with winsorization and variance guard; mechanical/admin use deterministic thresholds. Apply directionality; require light persistence (e.g., 2 consecutive obs) for flips.

- core_plumbing

  - `net_liq` (level): z20 → supportive if z ≥ +1; show threshold-equivalent.
  - `rrp_delta` (5d Δ, lower_is_supportive): z20 → supportive if z ≤ −1; backstop threshold: Δ ≤ −$100B/5d supportive; flip at Δ ≥ +$50B/5d.
  - `tga_delta` (5d Δ, higher_is_draining): z20 → draining if z ≥ +1; backstop: Δ ≥ +$75B/5d draining.
  - `reserves_w` (1w Δ, higher_is_supportive): z20 → supportive if z ≥ +1; backstop: Δ ≥ +$25B/w supportive.
  - `qt_pace` (mechanical): threshold → @cap = headwind (−1).

- floor

  - `sofr_iorb` (bps, higher_is_draining): threshold → persistent > 0 bps (e.g., 3 consecutive obs) = tight (−1). Optionally show z of spread.
  - `gc_iorb` (bps): threshold → > +10–15 bps = tight (−1).
  - `bill_iorb` (bps): threshold → > +25 bps = RRP drain likely (−1).

- supply

  - `ust_net_2w` (USD, higher_is_draining): z20 on 2–4w net flow → draining if z ≥ +1; backstop: > +$150B/2w draining.
  - `bill_share` (% of issuance, higher_is_supportive): threshold → ≥ 65% supportive (+1).
  - `settle_intensity` (USD/w, higher_is_draining): threshold → > +$80B/w watch (−1 or 0 per policy).

- banking (weekly)

  - `h8_deposits` (1w Δ, lower_is_draining): z20 → tight if z ≤ −1; backstop: ≤ −$50B/w.
  - `h8_secs` (1w Δ, lower_is_draining): z20 → watch if z ≤ −1; backstop: ≤ −$25B/w.

- stress

  - `ofr_liq_idx` (index): threshold → > 80th percentile = illiquid (−1).
  - `move_idx` (optional): threshold → > 120 = headwind (−1).

- global (weekly)

  - `ecb_bs` (1w Δ local, higher_is_supportive): z20 → supportive if z ≥ +1 (direction-only for MVP).
  - `boj_bs` (1w Δ local, higher_is_supportive): z20 → supportive if z ≥ +1.

- crypto
  - `stables_7d` (USD/7d, higher_is_supportive): z20 → supportive if z ≥ +1; backstop: +$2–5B/7d supportive.

Notes:

- Winsorize inputs (e.g., 2.5th/97.5th pct) before z; if `std < ε` or history < 20, set z=0 and rely on threshold backstop or neutral.
- Expose both the z value and the threshold text in the Snapshot row.

---

## Release calendar and polling windows (ET)

We detect “new data” by polling within the expected window and triggering on new vintages (ALFRED/FRED) or newer `publication_date` (DTS/OFR). SLO defaults: DAILY_N ≤ 60 min; WEEKLY_N ≤ 120 min.

### Daily sources (poll every 15m in window)

- ON RRP outstanding (`RRPONTSYD` via ALFRED)
  - Typical publish: late afternoon
  - Poll window: 3–7 pm ET (15m cadence)
  - Trigger: new observation_date or new vintage → recompute
- TGA Operating Cash Balance (DTS)
  - Typical publish: late afternoon
  - Poll window: 3–7 pm ET (15m)
  - Trigger: new row with `publication_date > last_seen`
- SOFR / EFFR (ALFRED)
  - Typical publish: next business morning (~8–9 am)
  - Poll window: 7:30–9:30 am ET (15m)
  - Trigger: new observation/vintage
- Bill yields `DTB3`, `DTB4WK` (ALFRED)
  - Typical publish: afternoon
  - Poll window: 3–7 pm ET (15m)
  - Trigger: new observation/vintage
- OFR UST Liquidity Stress Index
  - Typical publish: late day
  - Poll window: 3–7 pm ET (15m)
  - Trigger: new last date (hash/ETag or content change)
- Stablecoins (DefiLlama)
  - Availability: near‑real‑time; we sample daily
  - Poll window: 3–7 pm ET (single fetch per day is sufficient)
  - Trigger: compute 7d delta; treat as daily new print

### Weekly sources

- H.4.1 / Reserve balances `RESPPLLOPNWW` (ALFRED)
  - Typical publish: Thu ~4:30 pm ET
  - Poll window: Thu 3–6 pm ET (15m)
  - Trigger: new observation/vintage
- H.8 weekly (FRED mirror)
  - Typical publish: Fri ~4:15 pm ET
  - Poll window: Fri 3–6 pm ET (15m)
  - Trigger: new observation/vintage
- ECB / BoJ balance sheet (FRED mirrors)
  - Typical publish: weekly, local times
  - Poll window: 3–6 pm local→ET equivalent (or daily 3–6 pm ET check)
  - Trigger: new observation/vintage

### Schedule‑based (issuance/settlements/QRA)

- Treasury auction announcements/results and settlement calendars (DTS)
  - Morning consolidation: 7:30–8:30 am ET job to ingest schedules and precompute 2–4w net cash flows (`ust_net_2w`, `bill_share`, `settle_intensity`).
  - Additional triggers: known announcement times (bills typically 11:30am/1:00pm results; coupons afternoons). We can add explicit cron(s) later; MVP relies on the morning job plus next‑day catch‑up.

### Admin/policy events

- IORB, QT caps, facility changes
  - Source: FOMC statements, Fed admin releases
  - Handling: treat as event updates (manual or scraped); recompute immediately upon change

### Next‑update and staleness

- For each indicator we compute `next_update` from cadence + historical publish patterns; display it in Router/Snapshot.
- Stale if: daily > 48h since `published_at` (or last obs date), weekly > 9 days. If >2 Core are stale → abstain.
