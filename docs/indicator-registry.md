## Indicator Registry — Explainer

This document explains each series (raw data) and each indicator in `registry.yaml`: definition, why it matters, directionality, cadence, and default trigger. It also describes concept buckets (via `duplicates_of`).

Note on canonical source of truth

- `registry.yaml` is the authoritative source for series/indicator IDs and metadata used by the app.
- This document is the maintained explainer that describes the semantics, scoring, and operations for those entries.
- The older `series-contracts.md` has been consolidated into this document.

### How to read the registry

- **id**: canonical indicator ID used in code and APIs
- **series**: source series IDs (raw data inputs)
- **cadence**: expected update frequency (daily, weekly, sched, or weekly_daily)
- **directionality**:
  - `higher_is_supportive`: higher values add liquidity (supportive)
  - `higher_is_draining`: higher values drain liquidity (headwind)
  - `lower_is_supportive`: lower values add liquidity (supportive)
- **scoring**: `z` (z20 window) or `threshold` (deterministic)
- **trigger_default**: default flip condition used for status/sign
- **duplicates_of**: concept bucket root to avoid double-counting

---

## Series glossary (raw inputs)

- `WALCL` — Federal Reserve total assets (Fed balance sheet), weekly. Units: USD (millions on FRED; scaled in app).

  - **What it is**: The total value of assets held by the Federal Reserve, including Treasury securities, mortgage-backed securities, and loans to banks. It's the broadest measure of the Fed's balance sheet size.
  - **Impact**: High. This is a primary driver of base money. When the Fed engages in quantitative easing (QE), it buys assets, and `WALCL` increases, which expands the money supply and bank reserves. During quantitative tightening (QT), the balance sheet shrinks, draining liquidity.
  - **Interpretation for risk assets**: An expanding balance sheet (`WALCL` ↑) is generally supportive for risk assets, as it implies lower interest rates, abundant liquidity, and encourages investment in higher-yield assets. A contracting balance sheet (`WALCL` ↓) is a headwind, tightening financial conditions.

- `RESPPLLOPNWW` — Reserve balances with Federal Reserve Banks (H.4.1), weekly. Units: USD (millions).

  - **What it is**: Deposits held by commercial banks at the Federal Reserve. This is the most direct measure of the aggregate liquidity available to the banking system.
  - **Impact**: High. Reserves are the ultimate settlement asset. Changes directly impact banks' capacity to lend, absorb Treasury issuance, and make markets.
  - **Interpretation for risk assets**: Rising reserves signal easier funding conditions, which is supportive for risk assets. Falling reserves signal tightening and can become a significant headwind if they become scarce.

- `RRPONTSYD` — ON RRP facility outstanding, daily. Units: USD (millions).

  - **What it is**: The amount of cash that money market funds (MMFs) and other eligible institutions lend to the Fed overnight, earning a fixed rate. It's a safe, cash-equivalent investment that represents liquidity _drained_ from the private sector.
  - **Impact**: High. A high RRP balance means a large pool of cash is sitting on the sidelines. A sustained decline in RRP implies that cash is being deployed into other assets (typically T-bills first, then other securities), adding liquidity to the market.
  - **Interpretation for risk assets**: A falling RRP balance is supportive for risk assets. A rising RRP balance signals risk aversion and drains liquidity.

- `TGA` — Treasury General Account (Operating Cash Balance), daily (DTS). Units: USD (millions).

  - **What it is**: The U.S. Treasury's primary checking account, held at the Federal Reserve.
  - **Impact**: High. When the Treasury collects taxes or issues bonds, the TGA balance rises by pulling cash out of the banking system (draining reserves). When it spends (e.g., on Social Security), the TGA balance falls, injecting cash back into the system.
  - **Interpretation for risk assets**: A rising TGA is a direct liquidity drain and a headwind for risk assets. A falling TGA is a liquidity injection and is supportive.

- `SOFR` — Secured Overnight Financing Rate, daily. Units: percent.

  - **What it is**: A broad measure of the cost for banks to borrow cash overnight when collateralized by Treasury securities. It is the primary U.S. interest rate benchmark.
  - **Impact**: Medium. Its level relative to the Fed's administered rates (like IORB) is a key indicator of money market stress.
  - **Interpretation for risk assets**: If SOFR trades persistently above IORB, it signals stress in the critical repo market, indicating a shortage of cash or collateral. This tightness is a headwind for risk assets.

- `IORB` — Interest on Reserve Balances (admin rate), daily/stepwise. Units: percent.

  - **What it is**: The interest rate the Fed pays commercial banks for holding reserves. It is a primary tool of monetary policy used to control the federal funds rate and acts as a floor for overnight rates.
  - **Impact**: High (as a policy tool). Changes in IORB directly reflect changes in Fed policy.
  - **Interpretation for risk assets**: While the absolute level matters, the _spreads_ of other rates against IORB are more telling for liquidity conditions.

- `RRP_RATE` — ON RRP administered rate, daily/stepwise. Units: percent.

  - **What it is**: The fixed rate paid by the Fed on the Overnight Reverse Repo Facility (ON RRP). It serves as the arbitrage anchor for money market funds.
  - **Impact**: High for floor dynamics. The spread between bill yields and `RRP_RATE` drives cash allocation between RRP and bills.
  - **Interpretation for risk assets**: When bill yields rise well above `RRP_RATE`, cash leaves the floor into bills, easing tightness and often supporting broader risk appetite.

- `DTB3` — 3‑month Treasury bill secondary market rate, daily. Units: percent.
- `DTB4WK` — 4‑week Treasury bill secondary market rate, daily. Units: percent.

  - **What it is**: The yield on short-term government debt.
  - **Impact**: Medium. Bill yields relative to the RRP rate and IORB drive MMF asset allocation.
  - **Interpretation for risk assets**: When bill yields rise significantly above the RRP rate, they incentivize MMFs to move cash out of the RRP facility and into T-bills. This is supportive for risk assets because it can kickstart a "cash out of the sidelines" dynamic, even if the cash only moves into government debt initially.

- `WSHOSHO` / `WSHOMCB` — UST/MBS holdings/runoff proxies for QT/QE (weekly or H.4.1 components). Units: USD (millions).

  - **What it is**: These series track the Fed's holdings of Treasury securities and Mortgage-Backed Securities. The weekly change reflects the pace of QT (runoff) or QE (purchases).
  - **Impact**: High. This is the mechanical implementation of QE/QT. Runoff at the announced caps is a steady, persistent drain on liquidity.
  - **Interpretation for risk assets**: “Runoff” means the Fed allows holdings to mature without reinvestment, so the level of `WSHOSHO`/`WSHOMCB` trends down and the weekly change is negative. Faster/more negative weekly changes (close to the caps) = stronger headwind. A slowdown (smaller negatives), a flat profile (near zero change), or increases (positive change, i.e., purchases/reinvestments) are progressively more supportive.

- `UST_AUCTION_OFFERINGS` — Total offering amount per auction date (DTS `auctions_query`). Units: USD.

  - **What it is**: For each `auction_date`, we sum `offering_amt` across all announced securities (bills and coupons). This is the face amount Treasury plans to sell on that day.
  - **Impact**: High (supply pressure). Larger offerings signal near‑term cash needs that the market must fund; they are the first leg of the issuance pipeline.
  - **Interpretation for risk assets**: A week with unusually large offerings (especially coupons) foreshadows a heavier liquidity drain as those auctions settle. Used as an input to `ust_net_2w`, `bill_share`, and `settle_intensity`.

- `UST_AUCTION_ISSUES` — Total issuance amount per issue date (proxy for settlement day). Units: USD.

  - **What it is**: Using `issue_date` from `auctions_query` as an operational proxy for settlement timing, we sum `total_accepted` by `issue_date` (fallback to `offering_amt` if missing). This tracks the realized cash call when auctions complete.
  - **Impact**: High (cash drain timing). Clusters of large `issue_date`s concentrate settlement cash needs, tightening funding around those days.
  - **Interpretation for risk assets**: Spikes in `UST_AUCTION_ISSUES` flag weeks where Treasury cash calls are lumpy; these periods can coincide with tighter liquidity and risk‑off tone. Also used for `settle_intensity` and contributes to net‑settlement calculations alongside redemptions and interest.

- `UST_REDEMPTIONS` — Public debt cash redemptions (maturities), daily (DTS). Units: USD.

  - **What it is**: The daily cash outflows from the Treasury as securities mature and are redeemed.
  - **Impact**: High (supportive). Redemptions return cash to holders and reduce the TGA balance, injecting liquidity back into the system.
  - **Interpretation for risk assets**: Elevated or clustered redemptions are supportive of liquidity and can offset issuance drains around the same window. Used directly as an indicator and in net settlement calculations.
  - **Scope (filtered)**: Includes marketable securities and nonmarketable United States Savings Securities. Excludes intragovernmental/non‑public categories such as Government Account Series (GAS), Federal Financing Bank (FFB), SLGS, and similar, which do not inject cash into the private sector.

- `UST_INTEREST` — Interest/coupon outlays on Treasury securities, daily (DTS). Units: USD.

  - **What it is**: The daily coupon and interest payments made by the Treasury to security holders.
  - **Impact**: Medium-High (supportive). These payments reduce the TGA and inject cash into the private sector.
  - **Interpretation for risk assets**: Higher interest outlays are supportive for liquidity conditions on payment days and can cushion issuance-related drains.

- `UST_NET_SETTLE_W` — Net Treasury settlements by week (Issues − Redemptions − Interest), weekly. Units: USD.

  - **What it is**: A derived weekly series that nets Treasury cash outflows/inflows by settlement week: auction Issues minus Redemptions of maturing debt minus Interest outlays.
  - **Impact**: High (cash call timing). Captures the lumpy, week-clustered funding impact that tightens or eases liquidity conditions.
  - **Interpretation for risk assets**: Large positive weekly nets (heavy issuance relative to returns) are draining; negative nets are supportive.
  - **How it’s calculated (code-backed)**:
    - Weekly buckets are ISO weeks anchored to Monday. Each daily observation is assigned to `week = Monday(observation_date)`.
    - Inputs and sources:
      - Issues: `UST_AUCTION_ISSUES` (Treasury Auctions; sum of `accepted_amount` by issue_date; fallback to `offering_amount` if accepted missing). Source: DTS `auctions_query` (units USD).
      - Redemptions: `UST_REDEMPTIONS` (Public Debt Transactions; filtered to marketable + savings only; sum of `transaction_today_amt` where `transaction_type = "Redemptions"`). Source: DTS (units USD, stored with `scale=1e6`).
      - Interest: `UST_INTEREST` (Deposits and Withdrawals of the Operating Cash; withdrawals where category starts with “Interest on Treasury…” preferring Gross). Source: DTS (units USD, stored with `scale=1e6`).
    - Scaling: Each row is converted to USD via its `scale` column; weekly sums use `value_numeric * scale`.
    - Weekly net formula: `Net = Issues − Redemptions − Interest` for each Monday week bucket.
    - Persistence: Saved as series `UST_NET_SETTLE_W` with `units="USD"`, `scale=1.0`, `source="DERIVED"`.
    - Reference implementation: see `app/supply.py` functions `compute_weekly_net_settlements` and `upsert_weekly_net_settlements`.

- `H8_DEPOSITS` — Bank deposits (H.8), weekly. Units: USD.

  - **What it is**: The total amount of deposits in the commercial banking system.
  - **Impact**: Medium. A rapid decline in deposits can signal funding stress for banks, potentially leading them to reduce lending and market-making activities.
  - **Interpretation for risk assets**: Stable or growing deposits are neutral-to-supportive. A sustained, sharp decline is a warning sign of tightening financial conditions and a headwind for risk assets.

- `H8_SECURITIES` — Bank securities (H.8), weekly. Units: USD.

  - **What it is**: The total value of securities held by commercial banks.
  - **Impact**: Medium. Banks selling securities (especially under duress) tightens financial conditions. This can indicate they are facing funding shortfalls or re-managing duration risk.
  - **Interpretation for risk assets**: A decline in bank security holdings is a potential headwind, as it suggests banks are reducing their risk appetite or capacity.

- `SRF_USAGE` — Standing Repo Facility usage, daily. Units: USD.

  - **What it is**: Aggregate daily take-up of the Fed's Standing Repo Facility.
  - **Impact**: Medium-High (tightness signal). Persistent usage indicates elevated funding tightness.
  - **Interpretation for risk assets**: Sustained, non-idiosyncratic usage is a warning sign of stress in money markets and a headwind for risk assets.

- `FIMA_REPO` — FIMA repo usage, daily. Units: USD.

  - **What it is**: Daily usage of the Fed's FIMA repo facility by foreign official institutions.
  - **Impact**: Medium-High (tightness signal). Usage tends to increase when dollar funding tightens globally.
  - **Interpretation for risk assets**: Persistent elevations are consistent with stress that can spill into broader markets.

- `DISCOUNT_WINDOW` — Primary credit outstanding, weekly. Units: USD.

  - **What it is**: Outstanding balances at the Fed's primary credit facility (discount window).
  - **Impact**: Medium-High (stress signal). Non-zero balances outside of idiosyncratic events indicate bank funding stress.
  - **Interpretation for risk assets**: Usage is a cautionary signal for tightening financial conditions.

- `OFR_LIQ_IDX` — OFR U.S. Treasury Market Liquidity Stress Index, daily (unitless index).

  - **What it is**: An index from the Office of Financial Research that measures stress in the U.S. Treasury market, arguably the most important market in the world.
  - **Impact**: High (as a signal). A high reading indicates poor market functioning (e.g., wide bid-ask spreads, low depth), which can have spillover effects.
  - **Interpretation for risk assets**: Rising stress in the Treasury market signals systemic illiquidity and is a major headwind for all risk assets.

- `MOVE` — ICE BofA MOVE Index (rates volatility), daily (index level). Licensing constraints.

  - **What it is**: A measure of implied volatility in the U.S. Treasury market, akin to the VIX for stocks.
  - **Impact**: Medium-High. High rates volatility makes it difficult for investors to hedge and value other assets, leading to a general reduction in risk-taking.
  - **Interpretation for risk assets**: A high MOVE index reading (> 120-130) typically corresponds to tightening financial conditions and is a headwind for risk assets.
  - **Status**: Not yet ingested.

- `ECB_ASSETS` — ECB balance sheet aggregate (local currency), weekly. Units: local.
- `BOJ_ASSETS` — BoJ balance sheet aggregate (local currency), weekly. Units: local.

  - **What it is**: The balance sheets of the European Central Bank and Bank of Japan.
  - **Impact**: Medium. These central banks are major sources of global liquidity. Their policy actions can have spillover effects on USD liquidity through currency and interest rate differentials.
  - **Interpretation for risk assets**: Expansionary policy from the ECB or BoJ is generally supportive for global risk assets, including those priced in USD.
  - **Status**: Not yet ingested.

- `DEFI_LLAMA_STABLES` — Stablecoin circulating supply (summed), daily. Units: USD.
  - **What it is**: The total market capitalization of major USD-pegged stablecoins.
  - **Impact**: Low-Medium (for traditional markets). It's a direct proxy for the amount of USD-equivalent liquidity available on-chain for crypto assets.
  - **Interpretation for risk assets**: While primarily relevant to crypto, a strong inflow into stablecoins can be a leading indicator of speculative appetite and represents a pool of liquidity at the edge of the traditional financial system.
  - **Status**: Not yet ingested.

Notes:

- Some series are mirrored by FRED (often in millions); the app stores a `scale` so `value_numeric * scale` yields USD.
- For DTS (TGA, auctions), publication is treated as non‑revising; ordering uses `fetched_at`. For auctions, we currently use `offering_amt` and `issue_date` as a settlement proxy; this can be upgraded to awarded/settlement amounts if a better DTS dataset is integrated.

---

## Indicators (catalog)

### Core plumbing

- `net_liq` — Net Liquidity (WALCL − TGA − RRP)

  - **Why it matters**: This is the most comprehensive top-down measure of liquidity available to the private sector from the Fed's balance sheet. It acts as a high-level "tide" that influences all risk assets. By subtracting the Treasury's and money market funds' cash parked at the Fed (`TGA`, `RRP`) from the Fed's total assets (`WALCL`), it estimates the liquidity that is actually circulating in the financial system and available to support economic activity and asset prices.
  - **Series chosen**: `WALCL` (Fed balance sheet total assets) is the ultimate source of base liquidity from the central bank. `TGA` and `RRP` (`RRPONTSYD`) represent the two largest non-reserve liabilities that effectively "lock up" or remove this liquidity from private sector hands. Combining them provides a robust net measure.
  - **Status**: Ingested (`WALCL`, `TGA`, `RRPONTSYD`).
  - Directionality: `higher_is_supportive`
  - Scoring: `z` (z20); Trigger: `z20 >= +1 => supportive`
  - Bucket: root (avoid stacking with its components)

- `rrp_delta` — ON RRP 5d Δ

  - **Why it matters**: While the absolute level of the RRP is important, the _rate of change_ (`delta`) often has a more immediate market impact. A rapid fall in the RRP balance is a powerful signal that a large pool of cash is moving off the sidelines and being deployed into the market, typically starting with T-bills. This dynamic adds liquidity and can fuel demand for riskier assets. It's a key high-frequency signal of changing risk appetite.
  - **Series chosen**: Uses only `RRP` (`RRPONTSYD`), as it's the direct measure of the facility's outstanding balance, from which the change is calculated.
  - **Status**: Ingested (`RRPONTSYD`).
  - Directionality: `lower_is_supportive`
  - Scoring: `z`; Trigger: `Δ <= -100e9/5d => supportive`
  - Bucket: `duplicates_of: net_liq`

- `tga_delta` — TGA 5d Δ

  - **Why it matters**: Similar to RRP, the change in the TGA balance is a direct, high-frequency driver of banking system reserves. A rapid increase in the TGA (e.g., around tax deadlines or large bond auctions) can quickly drain tens or hundreds of billions in liquidity, tightening financial conditions. Conversely, a rapid drawdown injects cash. Monitoring the 5-day delta captures these impactful flows.
  - **Series chosen**: Uses `TGA` data, which directly tracks the Treasury's cash balance at the Fed.
  - **Status**: Ingested (`TGA`).
  - Directionality: `higher_is_draining`
  - Scoring: `z`; Trigger: `+75e9/5d => draining`
  - Bucket: `duplicates_of: net_liq`

- `reserves_w` — Reserve Balances 1w Δ

  - **Why it matters**: Bank reserves are the lifeblood of the financial plumbing. An increase in reserves makes it easier for banks to lend, settle payments, and absorb Treasury issuance. The weekly change is a direct read on the liquidity position of the banking system, which underpins the stability of broader markets.
  - **Series chosen**: Uses `RESPPLLOPNWW`, the definitive weekly data on reserve balances from the Fed's H.4.1 release.
  - **Status**: Ingested (`RESPPLLOPNWW`).
  - Directionality: `higher_is_supportive`
  - Scoring: `z`; Trigger: `+25e9/w => supportive`
  - Bucket: `duplicates_of: net_liq`

- `qt_pace` — UST/MBS runoff vs caps (QT/QE)
  - **Why it matters**: Quantitative Tightening (QT) is a persistent, mechanical drain on liquidity. When the Fed's holdings of securities mature, the principal repayment is extinguished, removing money from the system. Tracking the pace of this runoff relative to the Fed's announced caps confirms whether this structural headwind is operating as expected.
  - **Series chosen**: `WSHOSHO` (Treasuries) and `WSHOMCB` (MBS) are direct line items on the Fed's balance sheet that track its holdings, allowing for calculation of the weekly change/runoff.
  - **Status**: Ingested (`WSHOSHO`, `WSHOMCB`).
  - Directionality: `higher_is_draining`
  - Scoring: `threshold`; Trigger: `@cap => headwind`
  - Bucket: `duplicates_of: reserves_w`

### Money market floor / rates spreads

- `sofr_iorb` — SOFR − IORB (bps)

  - **Why it matters**: This spread is a key proxy for money market tightness. IORB is a Fed-administered rate, acting as a floor. SOFR reflects the market-determined cost of borrowing cash against Treasury collateral. If SOFR trades consistently above IORB, it indicates that demand for cash is outstripping supply in the critical repo market, a clear sign of funding stress and tightening conditions.
  - **Series chosen**: `SOFR` and `IORB` are the two components of the spread. SOFR is the market benchmark, and IORB is the policy benchmark, making their relationship a clean signal.
  - **Status**: Ingested (`SOFR`, `IORB`).
  - Directionality: `higher_is_draining`
  - Scoring: `threshold`; Trigger: `> 0 bps persistent => tight`
  - Bucket: root for floor concept

- `gc_iorb` — GC repo − IORB (bps)

  - **Why it matters**: Conceptually similar to `sofr_iorb`, using a General Collateral (GC) repo rate. It's another measure of funding tightness, where a positive spread signals stress.
  - **Series chosen**: (empty in MVP due to licensing). If data were available, a benchmark GC repo rate would be used alongside `IORB`.
  - Directionality: `higher_is_draining`
  - Scoring: `threshold`; Trigger: `> +10–15 bps => tight`
  - Bucket: `duplicates_of: sofr_iorb`

- `bill_rrp` — 1–3m bill − RRP (bps)

  - **Why it matters**: MMFs arbitrage vs the RRP admin rate directly. When bill yields exceed RRP materially, cash exits RRP into bills, reducing floor usage and supporting risk appetite.
  - **Series chosen**: `DTB3`/`DTB4WK` vs admin `RRP_RATE`. Derived series: `BILL_RRP_BPS` (bps).
  - **Status**: Ingested (`DTB3`, `DTB4WK`, `RRP_RATE`, `BILL_RRP_BPS`).
  - Directionality: `higher_is_supportive`
  - Scoring: `threshold`; Trigger: `> +25 bps => RRP drain likely`
  - Bucket: root for floor concept

- `bill_iorb` — 1–3m bill − IORB (bps)

  - **Role**: Secondary variant; duplicates `bill_rrp` concept.
  - Directionality: `higher_is_supportive`
  - Bucket: `duplicates_of: bill_rrp`

- `srf_usage` — Standing Repo Facility usage (daily)

  - **Why it matters**: Persistent usage of the SRF is a classic tightness tell, signaling that dealers and banks are tapping the Fed for funding against Treasuries.
  - **Series chosen**: `SRF_USAGE`.
  - Directionality: `higher_is_draining`
  - Scoring: `threshold`; Trigger: `> 0 persistent => tight`
  - Bucket: `duplicates_of: sofr_iorb`

- `fima_repo` — FIMA repo usage (daily)

  - **Why it matters**: Elevated usage by foreign official institutions often corresponds to global dollar funding stress.
  - **Series chosen**: `FIMA_REPO`.
  - Directionality: `higher_is_draining`
  - Scoring: `threshold`; Trigger: `> 0 persistent => tight`
  - Bucket: `duplicates_of: sofr_iorb`

- `discount_window` — Discount window primary credit (weekly)

  - **Why it matters**: Non‑zero balances outside idiosyncratic events indicate bank funding stress.
  - **Series chosen**: `DISCOUNT_WINDOW`.
  - Directionality: `higher_is_draining`
  - Scoring: `threshold`; Trigger: `> 0 => stress`
  - Bucket: `duplicates_of: sofr_iorb`

### Treasury supply

- `ust_net_w` — Net UST settlements (weekly)

  - **Why it matters**: Consolidates Treasury cash flows into a weekly net of Issues − Redemptions − Interest, aligning to the actual, lumpy settlement cadence that drives funding conditions.
  - **Series chosen**: `UST_NET_SETTLE_W` (derived weekly series).
  - **Status**: Ingested (`UST_NET_SETTLE_W`).
  - Directionality: `higher_is_draining`
  - Scoring: `z`; Trigger: `> +80–100e9/w => drain`

- `bill_share` — Bill share of issuance (%)

  - **Why it matters**: Not all issuance is created equal. Short-term T-bills are often bought by money market funds with excess cash, so they are less draining on overall liquidity than long-term coupon bonds, which require duration-taking investors to sell other assets to make room. A higher share of bills in total issuance is therefore less of a headwind for markets.
  - **Series chosen**: `UST_AUCTION_OFFERINGS` (sum of bills vs coupons by auction date) to calculate the proportion of bills in issuance.
  - **Status**: Ingested (`UST_AUCTION_OFFERINGS`); bill-only variant stored as `UST_BILL_OFFERINGS`.
  - Directionality: `higher_is_supportive`
  - Scoring: `threshold`; Trigger: `>= 65% => less drain`
  - Bucket: `duplicates_of: ust_net_2w`

- `settle_intensity` — Coupon settlement intensity (weekly $)

  - **Why it matters**: Large, concentrated settlements of Treasury coupon auctions can cause temporary but acute liquidity drains on specific days. Monitoring the weekly intensity helps identify periods where this "lumpy" demand for cash could tighten funding conditions.
  - **Series chosen**: `UST_AUCTION_ISSUES` provides the proxy settlement timing and amounts for coupon-bearing securities. This can be upgraded when a more explicit settlement dataset is integrated.
  - **Status**: Ingested (`UST_AUCTION_ISSUES`).
  - Directionality: `higher_is_draining`
  - Scoring: `threshold`; Trigger: `> +80e9/w => watch`
  - Bucket: `duplicates_of: ust_net_2w`

- `ust_redemptions` — Treasury redemptions (daily)

  - **Why it matters**: Redemptions reduce the TGA and inject cash back into the system, supporting liquidity, especially when clustered.
  - **Series chosen**: `UST_REDEMPTIONS`.
  - **Status**: Ingested (`UST_REDEMPTIONS`).
  - Directionality: `higher_is_supportive`
  - Scoring: `z`; Trigger: `higher daily redemptions => supportive`
  - Bucket: `duplicates_of: ust_net_2w`

- `ust_interest` — Treasury interest/coupon outlays (daily)

  - **Why it matters**: Coupon and interest payments are direct cash injections from the Treasury to the private sector.
  - **Series chosen**: `UST_INTEREST`.
  - **Status**: Ingested (`UST_INTEREST`).
  - Directionality: `higher_is_supportive`
  - Scoring: `z`; Trigger: `higher coupon/interest outlays => supportive`
  - Bucket: `duplicates_of: ust_net_2w`

### Banking (H.8) — deferred post‑MVP

- `h8_deposits` — H.8 Deposits 1w Δ

  - **Why it matters**: Deposit flows are a core indicator of banking system health and funding stability. A significant, sustained outflow of deposits can force banks to shrink their balance sheets by selling assets or reducing lending, which constitutes a major tightening of financial conditions.
  - **Series chosen**: `H8_DEPOSITS` is the aggregate weekly data on commercial bank deposits from the Fed's H.8 release.
  - Directionality: `lower_is_draining`
  - Scoring: `z`; Trigger: `<= -50e9/w => tight`

- `h8_secs` — H.8 Securities 1w Δ
  - **Why it matters**: This indicator tracks whether banks are net buyers or sellers of securities. If banks are selling securities, it can be a sign of stress, as they may be forced to raise liquidity or reduce duration risk. This selling pressure directly tightens financial conditions.
  - **Series chosen**: `H8_SECURITIES` from the H.8 release provides the data on banks' holdings.
  - Directionality: `lower_is_draining`
  - Scoring: `z`; Trigger: `<= -25e9/w => watch`
  - Bucket: `duplicates_of: h8_deposits`

### Stress

- `ofr_liq_idx` — OFR UST Liquidity Stress Index

  - **Why it matters**: The Treasury market is the bedrock of the global financial system. If it is illiquid or stressed, it has severe negative consequences for all other markets. This index aggregates multiple measures of market functioning (like bid-ask spreads, order depth) into a single, reliable indicator of systemic stress.
  - **Series chosen**: `OFR_LIQ_IDX` is the official index published by the Office of Financial Research.
  - Directionality: `higher_is_draining`
  - Scoring: `threshold`; Trigger: `> 80th pct => illiquid`

- `move_idx` — MOVE index (deferred post‑MVP)
  - **Why it matters**: The MOVE index is the bond market's "fear gauge." High volatility in Treasury yields makes it more expensive and difficult to hedge interest rate risk, causing lenders and market makers to pull back on providing liquidity across the board. It's a key measure of uncertainty that can freeze up markets.
  - **Series chosen**: `MOVE` is the standard market index for Treasury volatility.
  - Directionality: `higher_is_draining`
  - Scoring: `threshold`; Trigger: `> 120 => headwind`
  - Bucket: `duplicates_of: ofr_liq_idx`

### Global — deferred post‑MVP

- `ecb_bs` — ECB balance sheet 1w Δ (local)

  - **Why it matters**: The ECB is the second most important central bank. Its policy actions (QE/QT) affect global liquidity flows. A more accommodative ECB can lead to capital flowing into USD assets, indirectly supporting USD liquidity.
  - **Series chosen**: `ECB_ASSETS` provides the raw data on the ECB's balance sheet size.
  - Directionality: `higher_is_supportive`
  - Scoring: `z`; Trigger: `sustained increase => supportive`

- `boj_bs` — BoJ balance sheet 1w Δ (local)
  - **Why it matters**: The Bank of Japan's historically ultra-loose monetary policy has been a major source of global liquidity via the "yen carry trade." Changes in BoJ policy can therefore influence global capital flows and risk appetite.
  - **Series chosen**: `BOJ_ASSETS` provides the raw data on the BoJ's balance sheet size.
  - Directionality: `higher_is_supportive`
  - Scoring: `z`; Trigger: `acceleration => supportive`
  - Bucket: `duplicates_of: ecb_bs`

### Crypto (optional, deferred post‑MVP)

- `stables_7d` — Stablecoin net issuance (7d)
  - **Why it matters**: This indicator measures the flow of capital into the crypto ecosystem's primary on-chain liquidity source. Strong inflows (positive issuance) suggest a "risk-on" sentiment within crypto and represent a pool of USD-denominated liquidity ready to be deployed into digital assets.
  - **Series chosen**: `DEFI_LLAMA_STABLES` is a reliable public data source for aggregated stablecoin market caps.
  - Directionality: `higher_is_supportive`
  - Scoring: `z`; Trigger: `+2–5e9/7d => supportive`

---

## Concept buckets (de‑duplication)

Indicators with `duplicates_of` roll into the same concept bucket as their root. Only one representative per bucket should be shown in the Snapshot evidence table to avoid double-counting similar mechanisms. Examples:

- Core plumbing bucket: `net_liq` (root) with `rrp_delta`, `tga_delta`, `reserves_w` as members.
- Floor tightness bucket: `sofr_iorb` (root) with `gc_iorb`, `srf_usage`, `fima_repo`, `discount_window` as members.
- Floor bills bucket: `bill_rrp` (root) with `bill_iorb` as member.
- Supply bucket: `ust_net_w` (root) with `bill_share`, `settle_intensity`, `ust_redemptions`, `ust_interest` as members.
- Banking bucket: `h8_deposits` (root) with `h8_secs` as member.
- Stress bucket: `ofr_liq_idx` (root) with `move_idx` as member.
- Global bucket: `ecb_bs` (root) with `boj_bs` as member.

---

## Cadence, staleness, and scoring

### What is a Z-Score (z20)?

A **z-score** measures how far a data point is from the average of a dataset, in units of standard deviation. The `z20` used here is a z-score calculated over a rolling **20-observation window** (e.g., 20 business days for daily data).

- **Why use it?** It automatically standardizes different indicators, allowing them to be compared on a like-for-like basis. For example, a $50 billion move in reserves can be compared to a $100 billion move in RRP. By converting them to z-scores, we can see which move is more statistically significant relative to its own recent history.
- **How to interpret it**:
  - `z = 0`: The latest data point is exactly equal to the 20-period average.
  - `z = +1.0`: The data point is 1 standard deviation _above_ the average. This is often used as a threshold for a "significant" move.
  - `z = -1.0`: The data point is 1 standard deviation _below_ the average.
- **Purpose**: It provides a dynamic, adaptive way to score "flow-like" indicators. Instead of relying on a fixed threshold (e.g., "a change of >$X is significant"), which can become outdated as market conditions change, the z-score adapts to recent volatility.

- Daily series: evaluated with 20 business‑day z‑windows for `z` indicators; thresholds for `threshold` indicators.
- Weekly series: evaluated on 20 releases (no interpolation).
- Staleness defaults (MVP): daily >48h, weekly >9 days → considered stale; abstain if >2 core stale.
- Directionality flips sign mapping for status: z > cutoff → `+1` if supportive by direction; else `-1`; within band → `0`.

---

## Why these indicators

- The set aims to cover the core U.S. USD liquidity mechanisms without double‑counting: central bank balance sheet (WALCL/reserves), money‑market floor tightness (SOFR/IORB and proxies), fiscal cash (TGA), Treasury supply (net cash flow, bill share, settlements), bank plumbing (H.8), and market stress (OFR/MOVE), with optional global/crypto spillovers.
- Concept buckets ensure a single mechanism doesn’t dominate the vote.
