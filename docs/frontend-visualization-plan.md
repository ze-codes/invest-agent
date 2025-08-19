## Frontend Visualization Plan — Thresholds, Persistence, and History

### Goals

- Visualize threshold-based scoring with persistence (streaks) clearly.
- Provide both point-in-time and historical context for regime, buckets, and indicators.
- Keep first iteration lightweight; use API-provided streak metadata where possible.

### Views

1. Indicator tiles (overview)

- Status color (+1/0/−1), current value, threshold text, and a small streak meter (e.g., "2/3 days").
- Missing data → gray.

2. Indicator detail (sparkline)

- 60-day sparkline with a horizontal threshold line/band.
- Shaded spans where condition is met; annotate current consecutive streak and last flip.

3. Status heatmap (persistence)

- Rows = indicators (or bucket representatives), columns = days; cells colored by status (+1/0/−1).
- Ideal to scan persistence clusters and flip timing.

4. Bucket roll-up

- Gauges/bars for Core/Floor/Supply: aggregate status and fraction of members meeting thresholds.
- Optional stacked area over time for contributions to the overall score.

5. Contributions waterfall

- Sorted bars for each indicator’s contribution (+1/0/−1). Hover shows streak, trigger, last update.

### Time series (history)

- Persist daily snapshots and expose `GET /snapshot/history?horizon=1w&days=180[&slim=true]`.
- Charts:
  - Regime score timeline with bands (Positive/Neutral/Negative) and flip markers.
  - Stacked area of bucket contributions.
  - Heatmap of indicator status (+1/0/−1) by day.

### API niceties (optional but helpful)

- Include per-indicator: `streak_count`, `required`, `met_dates[]` or `recent_statuses[]` to avoid client-side recomputation.
- Provide each indicator’s human-readable `trigger_default` and units.

### Tech choices (first pass)

- React + Plotly or Vega-Lite/Altair via a simple wrapper; light CSS grid for tiles.
- Color map: green (+1), gray (0), red (−1); consistent across all charts.

### Minimal milestones

1. Tiles grid + sparkline with threshold band for top-K indicators
2. Regime timeline chart from `/snapshot/history`
3. Bucket gauges and contributions waterfall
4. Status heatmap for persistence

### Notes

- No extra fetches are required for history; reuses stored vintages and snapshot rows.
- Start with slim history payload (score + buckets). Expand to include indicator streaks as needed.
