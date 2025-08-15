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
	docker compose exec api bash -lc "python -m app.cli_fetch"

test:
	pytest -q | cat


