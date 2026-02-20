.PHONY: help install dev test lint format docker-up docker-down clean

help:
	@echo "IATI Data Quality API - Make Commands"
	@echo ""
	@echo "  make install     - Install production dependencies"
	@echo "  make dev         - Install development dependencies"
	@echo "  make test        - Run tests with coverage"
	@echo "  make lint        - Run linters (flake8)"
	@echo "  make format      - Format code (black + isort)"
	@echo "  make docker-up   - Start Docker services"
	@echo "  make docker-down - Stop Docker services"
	@echo "  make clean       - Remove build artifacts"
	@echo "  make run         - Run Flask development server"
	@echo "  make check-all   - Run format, lint, and tests"
	@echo ""

install:
	uv pip install -e .

dev:
	uv pip install -e ".[dev]"

test:
	pytest --cov=app --cov-report=term-missing --cov-report=html

test-verbose:
	pytest -vv --cov=app --cov-report=term-missing

lint:
	flake8 app tests

format:
	black app tests
	isort app tests

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-rebuild:
	docker compose up -d --build

run:
	python -m flask --app app.main:app run --debug

clean:
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

redis-cli:
	docker compose exec redis redis-cli

check-all: format lint test
	@echo "All checks passed!"
