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


