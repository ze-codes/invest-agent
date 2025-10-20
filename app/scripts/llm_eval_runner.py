from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import time

import httpx


def read_jsonl(path: Path) -> list[dict]:
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                items.append(json.loads(s))
            except Exception:
                continue
    return items


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def run_eval(api_base: str, dataset_path: Path, out_dir: Path, horizon_default: str = "1w", limit: int | None = None, verbose: bool = False) -> Path:
    rows = read_jsonl(dataset_path)
    if limit is not None and limit > 0:
        rows = rows[:limit]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = out_dir / ts
    ensure_dir(run_dir)
    out_file = run_dir / "results.json"

    print(f"Starting eval run: {len(rows)} prompts")
    print(f"Will write JSON array to: {out_file}")

    headers = {"Accept": "text/event-stream", "Accept-Encoding": "identity"}
    records: list[dict] = []
    with httpx.Client(timeout=60.0, headers=headers, http2=False) as client:
        total = len(rows)
        for idx, row in enumerate(rows, start=1):
            q = row.get("prompt", "")
            horizon = row.get("horizon") or horizon_default
            as_of = row.get("as_of")
            params = {"question": q, "horizon": horizon}
            if as_of:
                params["as_of"] = as_of
            url = api_base.rstrip("/") + "/llm/ask_stream"

            start = time.time()
            raw_text = ""

            print(f"[{idx}/{total}] id={row.get('id')} horizon={horizon}…", end=" ", flush=True)

            with client.stream("GET", url, params=params) as r:
                r.raise_for_status()
                for chunk in r.iter_raw():
                    if not chunk:
                        continue
                    try:
                        raw_text += chunk.decode("utf-8", errors="ignore")
                    except Exception:
                        continue
                    if verbose:
                        # Print only small previews to avoid flooding
                        preview = chunk.decode("utf-8", errors="ignore")
                        if preview:
                            print(f"  CHUNK> {preview[:120].replace('\n','\\n')}")

            dur_ms = int((time.time() - start) * 1000)
            print(f"done ({dur_ms} ms)")
            raw_lines = raw_text.splitlines()
            rec = {
                "id": row.get("id"),
                "prompt": q,
                "horizon": horizon,
                "as_of": as_of,
                "raw_text": raw_text,
                "raw_lines": raw_lines,
                "duration_ms": dur_ms,
            }
            records.append(rec)
            time.sleep(0.2)

    # Write pretty JSON array once
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM eval prompts and record raw results.")
    parser.add_argument("--api-base", default=os.environ.get("EVAL_API_BASE", "http://localhost:8000"))
    parser.add_argument("--dataset", default=str(Path("docs/llm-eval-dataset.jsonl")))
    parser.add_argument("--out", default=str(Path("eval_runs")))
    parser.add_argument("--limit", type=int, default=None, help="Limit number of prompts to run")
    parser.add_argument("--verbose", action="store_true", help="Print raw SSE event/data lines for debugging")
    args = parser.parse_args()

    dataset_path = Path(args.dataset).resolve()
    out_dir = Path(args.out).resolve()
    ensure_dir(out_dir)

    out_file = run_eval(api_base=args.api_base, dataset_path=dataset_path, out_dir=out_dir, limit=args.limit, verbose=args.verbose)
    print(f"Wrote results to {out_file}")


if __name__ == "__main__":
    main()


