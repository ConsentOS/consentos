.PHONY: up down restart logs migrate seed bootstrap test lint fmt check clean test-infra-up test-infra-down

# ── Development environment ──────────────────────────────────────────

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

logs-api:
	docker compose logs -f api

# ── Database ─────────────────────────────────────────────────────────

migrate:
	docker compose exec api alembic upgrade head

migrate-offline:
	cd apps/api && DATABASE_URL=postgresql+asyncpg://consentos:consentos@localhost:5432/consentos alembic upgrade head

bootstrap:
	docker compose exec api python -m src.cli.bootstrap_admin

seed: migrate bootstrap
	docker compose exec api python -m src.cli.seed_known_cookies --clear

rollback:
	docker compose exec api alembic downgrade -1

# ── Testing ──────────────────────────────────────────────────────────

test-infra-up:
	docker compose -f docker-compose.test.yml up -d
	docker compose -f docker-compose.test.yml exec -T postgres-test sh -c 'until pg_isready -U consentos_test; do sleep 1; done'

test-infra-down:
	docker compose -f docker-compose.test.yml down -v

test:
	cd apps/api && python -m pytest tests/ -v --tb=short

test-cov:
	cd apps/api && python -m pytest tests/ -v --cov=src --cov-report=term-missing --tb=short

# ── Code quality ─────────────────────────────────────────────────────

lint:
	cd apps/api && ruff check src/ tests/ alembic/

fmt:
	cd apps/api && ruff check --fix src/ tests/ alembic/
	cd apps/api && ruff format src/ tests/

check: lint test

# ── Cleanup ──────────────────────────────────────────────────────────

clean:
	docker compose down -v
	docker compose -f docker-compose.test.yml down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
