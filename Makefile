.PHONY: dev test lint typecheck build clean migrate seed

# ── Development ──
dev:
	docker compose up -d postgres redis
	uvicorn src.api.main:app --host 0.0.0.0 --port 8080 --reload

dev-all:
	docker compose up -d

# ── Code Quality ──
lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff check --fix src/ tests/
	ruff format src/ tests/

typecheck:
	mypy src/

# ── Testing ──
test:
	pytest tests/ -v --tb=short

test-unit:
	pytest tests/unit/ -v -m unit

test-integration:
	pytest tests/integration/ -v -m integration

test-e2e:
	pytest tests/e2e/ -v -m e2e

test-cov:
	pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

# ── Database ──
migrate:
	alembic upgrade head

migrate-new:
	alembic revision --autogenerate -m "$(msg)"

seed:
	alembic upgrade head && python -m src.models.seed

# ── Build ──
build:
	docker build -t workflow-engine:latest .

build-frontend:
	cd frontend && npm run build

# ── Clean ──
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .mypy_cache .pytest_cache .ruff_cache htmlcov .coverage
