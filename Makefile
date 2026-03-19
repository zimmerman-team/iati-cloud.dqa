.PHONY: help install dev test test-verbose lint format format-check security docker-up docker-down docker-logs docker-rebuild run clean redis-cli check-all

help:
	@echo "IATI Data Quality API - Make Commands"
	@echo ""
	@echo "  make install        - Install production dependencies"
	@echo "  make dev            - Install development dependencies"
	@echo "  make test           - Run tests with coverage"
	@echo "  make test-verbose   - Run tests with extra verbosity"
	@echo "  make lint           - Run linters (flake8)"
	@echo "  make format         - Format code (black + isort)"
	@echo "  make format-check   - Check formatting without modifying files"
	@echo "  make security       - Run security checks (bandit)"
	@echo "  make docker-up      - Start Docker services"
	@echo "  make docker-down    - Stop Docker services"
	@echo "  make docker-logs    - Follow Docker service logs"
	@echo "  make docker-rebuild - Rebuild and start Docker services"
	@echo "  make run            - Run Flask development server"
	@echo "  make clean          - Remove build artifacts"
	@echo "  make redis-cli      - Open Redis CLI against running container"
	@echo "  make check-all      - Run format-check, lint, security, and tests"
	@echo ""

install:
	uv sync

dev:
	uv sync --extra dev
	uv run pre-commit install

test:
	uv run pytest

test-verbose:
	uv run pytest -vv --cov=app --cov-report=term-missing

lint:
	uv run flake8 app tests

format:
	uv run black app tests
	uv run isort app tests

format-check:
	uv run black --check app tests
	uv run isort --check app tests

security:
	uv run bandit -c pyproject.toml -r app

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-rebuild:
	docker compose up -d --build

run:
	uv run flask --app app.main:app run --debug

clean:
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

redis-cli:
	docker compose exec redis redis-cli

check-all: format-check lint security test
	@echo "All checks passed!"
