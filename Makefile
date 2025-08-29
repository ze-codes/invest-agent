up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api db

rebuild:
	docker compose build --no-cache api

shell:
	docker compose exec api bash

load-registry:
	docker compose exec api bash -lc "python -m app.registry_loader registry.yaml"

fetch-core:
	# Optional: pass FETCH_PAGES and FETCH_LIMIT to throttle fetch sizes for debugging
	docker compose exec -e FETCH_PAGES -e FETCH_LIMIT api bash -lc "python -m app.cli_fetch"

test:
	pytest -q | cat

test-api:
	docker compose exec api bash -lc "pytest -q $(TESTS) | cat"

test-up: 
	docker compose -f docker-compose.test.yml up -d

test-down:
	docker compose -f docker-compose.test.yml down -v

test-migrate:
	bash -lc "source .venv/bin/activate && DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/invest_test alembic upgrade head | cat"

test-run:
	bash -lc "source .venv/bin/activate && DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/invest_test pytest -q | cat"


