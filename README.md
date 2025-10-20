# invest-agent (Liquidity-Only MVP)

Remote-first Docker dev for use with Cursor Remote-SSH on a cloud VM. Includes a right-side chat assistant (SSE streaming) and two viz pages.

## Stack

- FastAPI (api/main.py)
- Postgres 17 (Docker service)
- Docker + docker compose
- Alembic migrations (alembic/)
- HTML/CSS/JS static viz pages (api/static)
- LLM via OpenRouter or mock provider (SSE streaming)

## Quick start (any host with Docker)

1. Copy env:
   cp env.sample .env
2. (Optional) Configure LLM:
   # For real tool-calling via OpenRouter
   echo "LLM_PROVIDER=openrouter" >> .env
   echo "OPENROUTER_API_KEY=sk-..." >> .env
   # Or keep default mock provider
3. Build & run:
   make up
4. Apply DB migrations (inside the api container):
   docker compose exec api bash -lc "alembic upgrade head"
5. Load indicator/series registry metadata:
   # Loads indicators from registry.yaml; also loads series_registry if present in the YAML
   make load-registry
   # To load a standalone series_registry YAML file instead:
   docker compose exec api bash -lc "python -m app.registry_loader series_registry.yaml"
6. Open the app:
   # Root redirects to /static/viz_indicators.html
   open http://localhost:8000/
   # Health
   open http://localhost:8000/health
7. Stop:
   make down

## Features

- Static viz pages: `viz_indicators.html`, `viz_series.html`, shared top nav.
- Right sidebar "Liquidity Assistant" chat (SSE stream): brief + ask, raw stream log, answer pane.
- Root redirect to `/static/viz_indicators.html`.
- Access logging middleware: timestamp, client IP, method, path, status, duration, user-agent.
- Unified indicator/series metadata via `registry.yaml` (+ optional `series_registry.yaml`).

## Endpoints

- GET `/` → redirects to `/static/viz_indicators.html`
- GET `/health` → basic health
- Static pages under `/static/*` (e.g., `/static/viz_indicators.html`)
- LLM SSE stream: GET `/llm/ask_stream?question=...` (optional `as_of`)
  - Example:
    curl -sS -N "http://localhost:8000/llm/ask_stream?question=what%20is%20bill%20share"

## Make targets

- `make up` — build and start API + Postgres
- `make down` — stop
- `make logs` — follow api/db logs
- `make rebuild` — rebuild api image without cache
- `make shell` — shell into api container
- `make load-registry` — load `registry.yaml` (and embedded `series_registry` if present)
- `make fetch-core` — optional data fetcher (supports FETCH_PAGES, FETCH_LIMIT)
- `make test` — run tests

## Migrations

- Run inside the container:
  docker compose exec api bash -lc "alembic upgrade head"
- Alembic scripts live in `alembic/versions/` (e.g., `add_series_registry`).

## LLM configuration

- `.env` keys:
  - `LLM_PROVIDER` — `openrouter` or `mock`
  - `OPENROUTER_API_KEY` — required when using `openrouter`
  - `LLM_MODEL` — e.g., `gpt-4o-mini`
- SSE chat widget reads `/llm/ask_stream` and displays raw events + answer.

## Evaluation runner

- Dataset: `docs/llm-eval-dataset.jsonl` (JSONL, one prompt per line)
- Run:
  python app/scripts/llm_eval_runner.py --api-base http://localhost:8000 \
   --dataset docs/llm-eval-dataset.jsonl --out eval_runs --verbose
- Output: `eval_runs/<timestamp>/results.json` (raw SSE captured in `raw_text` and `raw_lines`).

## Remote VM setup (recommended)

- Provision Ubuntu 22.04/24.04 VM (>=2 vCPU, 4GB RAM). Open port 22 only.
- Install Docker + compose:
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER && newgrp docker
- Clone repo and start:
  git clone https://github.com/your-org/invest-agent.git
  cd invest-agent
  cp env.sample .env && edit .env
  make up
- Tunnel API to your laptop:
  ssh -N -L 8000:localhost:8000 user@your-vm
  Then visit http://localhost:8000/

## Cursor Remote-SSH

- Add SSH host in Cursor → Remote-SSH: user@your-vm
- Open the repo folder on the VM and run `make up` in the terminal.

## Files

- `api/main.py` — FastAPI entrypoint
- `api/routers/*` — API routers (registry, history, llm, etc.)
- `api/static/*` — viz pages + chat widget
- `docker-compose.yml` — API + Postgres services
- `Dockerfile` — API image
- `requirements.txt` — Python deps
- `env.sample` — example environment vars
- `Makefile` — convenience targets
- `alembic/` — migrations
