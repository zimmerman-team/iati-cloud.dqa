# Development Guide

## Setup Development Environment

### Prerequisites

- Python 3.11 or higher
- UV package manager
- Docker and Docker Compose
- Access to a Solr instance with IATI data

### Initial Setup

```bash
# Clone repository
git clone <repository-url>
cd iati-dqa-api

# Install UV if not already installed
pip install uv

# Create virtual environment and install dependencies
uv pip install -e ".[dev]"

# Copy environment file
cp .env.example .env

# Edit .env with your Solr URL and settings
nano .env

# Start Redis
docker-compose up redis -d

# Run tests to verify setup
pytest
```

## Running the Application

### Development Mode

```bash
# Using Flask CLI
python -m flask --app app.main:app run --debug

# Or using make
make run
```

### Production Mode (Docker)

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down
```

## Testing

### Run All Tests

```bash
pytest
```

### Run with Coverage Report

```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

### Run Specific Test File

```bash
pytest tests/test_validator.py -v
```

### Run Specific Test Class

```bash
pytest tests/test_validator.py::TestTitleValidation -v
```

### Run Specific Test

```bash
pytest tests/test_validator.py::TestTitleValidation::test_valid_title -v
```

### Test with Debug Output

```bash
pytest -vv -s tests/test_api.py
```

## Code Quality

### Formatting

```bash
# Format all code
black app tests
isort app tests

# Check formatting without changes
black --check app tests
isort --check-only app tests
```

### Linting

```bash
# Run flake8 linter
flake8 app tests
```

### Type Checking (Optional)

```bash
# Install mypy
uv pip install mypy

# Run type checking
mypy app
```

## Project Structure

```
iati-dqa-api/
├── app/
│   ├── __init__.py          # Package initialization
│   ├── main.py              # Flask app and routes
│   ├── config.py            # Settings and configuration
│   ├── models.py            # Pydantic data models
│   ├── cache.py             # Redis cache wrapper
│   ├── solr_client.py       # Solr query interface
│   ├── validator.py         # Activity validation logic
│   └── docs.py              # Swagger/Flasgger spec templates
├── data/
│   ├── default_dates.json               # Placeholder dates treated as missing
│   ├── document_validation_exemptions.json  # IATI IDs exempt from document checks
│   └── non_acronyms.json                # Strings excluded from acronym detection
├── tests/
│   ├── conftest.py          # Pytest fixtures
│   ├── test_api.py          # API endpoint tests
│   ├── test_cache.py        # Cache functionality tests
│   ├── test_config.py       # Configuration tests
│   ├── test_config_api.py   # Config API endpoint tests
│   ├── test_solr_client.py  # Solr client tests
│   └── test_validator.py    # Validation logic tests
├── docker-compose.yml       # Docker services (API + Redis)
├── Dockerfile               # API container
├── Makefile                 # Convenience commands
├── pyproject.toml           # Project metadata and tool configuration
├── CLAUDE.md                # Claude Code instructions
├── TECHNICAL_REQUIREMENTS.md  # Original business requirements
├── VALIDATOR_RULES.md       # Per-attribute validation rules reference
└── README.md                # Main documentation
```

See [DIAGRAMS.md](DIAGRAMS.md) for architecture and flow diagrams.

## Adding New Features

### 1. Add a New Validation Rule

**Step 1**: Add method to `app/validator.py`

```python
def validate_new_rule(self, activity: Dict[str, Any]) -> AttributeValidation:
    """Validate new rule."""
    # Implementation
    return AttributeValidation(
        attribute="new_rule",
        status=ValidationResult.PASS
    )
```

**Step 2**: Call in `validate_activity` method

```python
def validate_activity(self, activity: Dict[str, Any]):
    attr_validations.append(self.validate_new_rule(activity))
```

**Step 3**: Add tests in `tests/test_validator.py`

```python
class TestNewRuleValidation:
    def test_valid_new_rule(self, validator, sample_activity):
        result = validator.validate_new_rule(sample_activity)
        assert result.status == ValidationResult.PASS
```

**Step 4**: Run tests

```bash
pytest tests/test_validator.py::TestNewRuleValidation -v
```

### 2. Add a New API Endpoint

**Step 1**: Add route to `app/main.py`

```python
@app.route("/api/v1/new-endpoint", methods=["GET"])
def new_endpoint():
    """New endpoint description."""
    return jsonify({"message": "success"})
```

**Step 2**: Add tests in `tests/test_api.py`

```python
class TestNewEndpoint:
    def test_new_endpoint(self, client):
        response = client.get('/api/v1/new-endpoint')
        assert response.status_code == 200
```

**Step 3**: Update documentation in README.md

### 3. Add a New Configuration Option

**Step 1**: Add to `app/config.py`

```python
class Settings(BaseSettings):
    new_setting: str = "default_value"
```

**Step 2**: Use in code

```python
from app.config import settings
value = settings.new_setting
```

**Step 3**: Add to `.env.example`

```bash
NEW_SETTING=default_value
```

## Debugging

### Using Python Debugger

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use built-in breakpoint() (Python 3.7+)
breakpoint()
```

### Flask Debug Mode

```bash
export FLASK_DEBUG=1
python -m flask --app app.main:app run
```

### Redis Debugging

```bash
# Connect to Redis CLI
docker-compose exec redis redis-cli

# View all keys
KEYS *

# Get specific key
GET "dqa:GB-GOV-1"

# View key type
TYPE "dqa:GB-GOV-1"

# Get TTL
TTL "dqa:GB-GOV-1"
```

### Solr Debugging

```bash
# Test Solr query directly
curl "http://localhost:8983/solr/activity/select?q=reporting-org.ref:GB-GOV-1&rows=5"
```

### API Authentication

All API endpoints require `Authorization: <key>` header. The key is configured via `SECRET_KEY` in `.env` (default: `ZIMMERMAN`).

```bash
# Example authenticated request
curl -H "Authorization: ZIMMERMAN" http://localhost:5000/dqa/health
```

## Common Development Tasks

### Clear Cache

```bash
# Using API
curl -X POST http://localhost:5000/dqa/cache/clear -H "Authorization: ZIMMERMAN"

# Using Redis CLI
docker-compose exec redis redis-cli FLUSHALL
```

### Rebuild Docker Images

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### View Application Logs

```bash
# Docker logs
docker-compose logs -f api

# Or follow specific service
docker-compose logs -f redis
```

### Update Dependencies

```bash
# Add new dependency
uv pip install package-name

# Update pyproject.toml
# Then sync
uv pip sync
```

## Performance Profiling

### Profile API Endpoint

```python
from flask import Flask
from werkzeug.middleware.profiler import ProfilerMiddleware

app.wsgi_app = ProfilerMiddleware(app.wsgi_app)
```

### Memory Profiling

```bash
# Install memory profiler
uv pip install memory-profiler

# Decorate function
from memory_profiler import profile

@profile
def my_function():
    pass
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install uv
          uv pip install -e ".[dev]"

      - name: Run tests
        run: pytest --cov=app

      - name: Run linting
        run: |
          black --check app tests
          isort --check-only app tests
          flake8 --exit-zero app tests
```

## Troubleshooting

### Redis Connection Error

```bash
# Check if Redis is running
docker-compose ps

# Restart Redis
docker-compose restart redis

# Check Redis logs
docker-compose logs redis
```

### Solr Connection Error

```bash
# Test Solr connectivity
curl http://localhost:8983/solr/admin/ping

# Check Solr URL in .env
cat .env | grep SOLR_URL
```

### Import Errors

```bash
# Ensure in correct directory
pwd

# Reinstall package in editable mode
uv pip install -e .
```

## Best Practices

1. **Write tests first** - Follow TDD when adding features
2. **Keep functions small** - Each function should do one thing
3. **Use type hints** - Makes code more maintainable
4. **Document edge cases** - Add comments for non-obvious logic
5. **Test edge cases** - Cover boundary conditions
6. **Use fixtures** - Reuse test data across tests
7. **Mock external services** - Don't hit real Solr/Redis in tests
8. **Keep dependencies minimal** - Only add what's necessary
9. **Version control .env.example** - Never commit .env
10. **Update documentation** - Keep README in sync with code
