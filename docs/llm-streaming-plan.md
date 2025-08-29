## LLM Streaming Plan (Thinking + Answer)

### Goal

Stream both the agent’s “thinking” (rationales/actions) and the final answer to the browser as the model generates output, while preserving tool-call transparency.

### Scope

- Provider-level streaming (OpenRouter first; OpenAI where supported)
- Orchestrator streaming loop (think → act → reflect → finish)
- SSE endpoint for the browser
- Frontend hooks to render streamed thinking tokens, tool events, and final answer tokens

---

### Provider-level streaming

- Use OpenRouter chat completions with `stream: true` to receive SSE-style deltas as they arrive.
- Extract text deltas from `choices[].delta.content`.
- Tool-call detection paths:
  - Function-calling: detect streamed tool_call deltas (if model supports it).
  - Text protocol fallback: instruct the model to emit explicit markers, e.g. `TOOL <name> <json>`, or `FINAL <text>`.
- Expose a streaming method in the provider that yields token deltas and structured signals (content/tool_call/final).

### Orchestrator streaming loop

- Phase 1: Thinking stream
  - Start the model stream for “planning”.
  - Forward every delta as SSE event `thinking_token` to the client.
  - Continuously scan for a tool call:
    - If function-calling: parse streamed tool_call.
    - Else (text): detect a complete line matching `TOOL <name> <json>`.
- Phase 2: Act
  - When tool_call detected:
    - Emit `decision` and `tool_call` SSE events (include tool name and JSON args).
    - Stop the current model stream.
    - Execute the tool locally; append to `tool_trace`.
    - Emit `tool_result` SSE event with a short JSON summary (truncated), and redact PII if configured.
  - Append a new message with the tool result and resume a fresh model stream (Reflect phase).
- Phase 3: Reflect (repeat)
  - Stream deltas again as `thinking_token`, detect next tool or final.
  - Bound by `max_calls` (3) to avoid loops.
- Phase 4: Finish
  - On finalization (function finish or `FINAL <text>`):
    - Switch to emitting `answer_token` deltas for the final answer stream (optional; if the provider only produces a single final message, emit it as a single block).
    - Emit `final` SSE event that includes the aggregated `tool_trace` and the final answer text.

### SSE endpoint (server → browser)

- Route: `GET /llm/ask_stream?question=...&horizon=1w`
- Event types and payloads:
  - `start`: `{horizon, as_of, regime}`
  - `thinking_token`: `{text}` (raw model thoughts as they stream)
  - `decision`: `{type: "tool"|"final"|"error", message?}`
  - `tool_call`: `{name, args}`
  - `tool_result`: `{name, summary}` (summary is truncated JSON/string)
  - `answer_token`: `{text}` (final answer as tokens)
  - `final`: `{answer, tool_trace}`
  - `error`: `{message}`
- Infra tips: disable proxy buffering for this route (e.g., Nginx `proxy_buffering off`), set `Cache-Control: no-cache`.
- Abort handling: detect client disconnect to cancel upstream provider stream and free resources.

### Frontend integration

- Use `EventSource` to subscribe to `/llm/ask_stream`.
- UI panes:
  - “Agent stream”: append `thinking_token`, `decision`, `tool_call`, and `tool_result`.
  - “Answer”: append `answer_token` as they arrive; on `final`, show the final full answer.
- Optional toggle: “Show raw thinking”. If off, suppress `thinking_token` rendering but keep other events.

### Prompting and protocol

- System/developer prompt includes ToolCatalog and strict choices:
  - Either stream free-form thinking tokens, then emit `TOOL <name> <json>` when ready.
  - Or emit `FINAL <answer>` when no tool is needed.
- For function-calling models, rely on structured tool_call deltas; for text-only models, keep the explicit `TOOL` and `FINAL` markers.
- Constraints: IDs exact; ≤ 200 words guidance; no invented numbers; keep JSON args valid.

### Guardrails and privacy

- `max_calls=3` to prevent loops.
- Timeout per stream turn (e.g., 8s provider request timeout) with graceful `error`/`final` events.
- Optional PII redaction of streamed content (emails/phones) toggled by a flag; can be disabled if full raw thinking is desired.
- Truncate `tool_result` summaries to a safe size (e.g., 400–800 chars).

### Testing

- Unit (provider shim): simulated SSE chunks produce `thinking_token`, a detected `TOOL`, then follow-on `tool_result` and resumed thinking.
- Unit (orchestrator): detect transition from thinking → tool → result → final within `max_calls`.
- Integration: curl `-N` to confirm immediate event flow and final aggregation.
- Non-streaming compatibility: ensure `/llm/ask` remains functional with the existing agent path.

### Rollout

- Phase 1: Add streaming path behind env toggles (provider + endpoint); keep existing non-streaming path by default.
- Phase 2: Enable streaming by default for `/viz/indicators` UI; retain non-streaming as fallback.
- Phase 3: Optional token streaming of the brief.

### Open questions / Options

- Do we always stream raw thinking, or gate it behind a `SHOW_THINKING` flag?
- If a provider supports native function-calling streams, should we prefer it over text markers by default?
- What truncation limits are acceptable for `tool_result` in the UI?
