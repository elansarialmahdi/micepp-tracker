.PHONY: up down logs migrate bootstrap-admin test test-backend test-frontend lint

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose run --rm api alembic upgrade head

bootstrap-admin:
	docker compose run --rm api python -m app.cli.bootstrap_admin

test: test-backend test-frontend

test-backend:
	docker compose run --rm api pytest

test-frontend:
	docker compose run --rm frontend npm run test -- --run

lint:
	docker compose run --rm api ruff check app tests
	docker compose run --rm frontend npm run lint
