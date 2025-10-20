## LLM Evaluation Plan — Learning-First (Manual)

Purpose: keep evaluation lightweight and fast so we can learn and iterate weekly.

### What to measure

- **Format**: required sections present; bullets count; no invented numbers. (Pass/Fail)
- **Tool use**: correct tools chosen for intent; no duplicate identical calls. (Pass/Fail)
- **Task success**: answered the actual ask (definition, trend, or both). (0–2)
- **Speed**: feel/stopwatch; under ~5–8s acceptable. (OK/Slow)

### Dataset (40 prompts)

Create and maintain a small, curated set (8 per bucket):

- Single definition (e.g., “what is bill share?”)
- Mixed: definition + trend
- Trend-only (e.g., “show recent trend of reserves_w”)
- Multi-definition (e.g., “what is bill share and what is sofr iorb?”)
- Edge/typo/ambiguous IDs

Each prompt should include notes: expected IDs; suggested tools; horizon/as_of if needed.

### How to run

1. Fix context for the session (same horizon; ideally fixed `as_of`).
2. For each prompt: ask via the widget; copy answer + tool_trace + elapsed time to the sheet.
3. Score the 4 checks; add a one‑line note if something failed.

### Rubric

- **Format (P/F)**: sections OK; bullets OK; no numbers not present in tool outputs.
- **Tool use (P/F)**: doc for definitional questions; indicator_history (preferred) or series_history for trend; no duplicate same tool+args.
- **Task success (0–2)**: 2 = nailed it; 1 = partial; 0 = missed.
- **Speed (OK/Slow)**: subjective; note big outliers.

### Weekly cadence

- Run all 40 prompts (≈30–40 minutes).
- Track pass rates and the three most common failure modes.
- Adjust prompts/instructions based on top failures; note changes.

### Acceptance bar (simple)

- Format pass ≥ 90%
- Tool use pass ≥ 90%
- Task success average ≥ 1.6/2
- “Feels fast” on ≥ 85% of prompts

### Minimal smoke test (pre-merge)

- Run 10 prompts (2 per bucket). If any Format or Tool fails, fix or revert.

### Template (sheet columns)

Prompt | Type (def/mixed/trend/multi/edge) | Horizon | Answer | Format (P/F) | Tool use (P/F) | Task (0–2) | Speed (OK/Slow) | Notes | Tool trace

### Evolve gradually

- Add 5–10 prompts weekly from real questions.
- Replace trivial prompts; keep difficult ones.
- Only add model-graded evals when/if we need more rigor.
