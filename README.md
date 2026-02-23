# IATI Data Quality API

A comprehensive Flask-based API for assessing IATI (International Aid Transparency Initiative) data quality across programmes and projects. This API validates IATI activities against defined quality standards including attribute completeness, sector/location percentages, and document publication requirements.

## Features

- **Activity Validation**: Validates H1 (programmes) and H2 (projects) activities against multiple criteria
- **Attribute Checks**: Title, description, dates, sectors, locations, and participating organizations
- **Document Publication**: Validates Business Case, Logical Framework, and Annual Review publications
- **Segmentation**: Filter by countries, regions, and sectors
- **Redis Caching**: 24-hour cache with daily refresh
- **Docker Compose**: Easy deployment with Redis and Flask API
- **Comprehensive Tests**: Full pytest suite with edge case coverage

## Architecture

See [DIAGRAMS.md](DIAGRAMS.md) for system architecture, request pipeline, Solr query construction, validation flow, data models, and cache strategy.

## Requirements

- Python 3.11+
- UV (package manager)
- Docker and Docker Compose
- Solr instance with IATI data

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd iati-dqa-api
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Solr URL and other settings
```

### 3. Run with Docker Compose

```bash
docker-compose up -d
```

The API will be available at `http://localhost:5000`

### 4. Local Development

```bash
# Install dependencies with UV
uv pip install -e ".[dev]"

# Run Redis
docker-compose up redis -d

# Run Flask app
python -m flask --app app.main:app run --debug
```

## API Endpoints

### Health Check

```bash
GET /dqa/health
```

Response:
```json
{
  "status": "healthy",
  "redis": "connected",
  "timestamp": "2024-02-12T10:30:00"
}
```

### Data Quality Assessment

```bash
POST /dqa
Content-Type: application/json

{
  "organisation": "GB-GOV-1",
  "segmentation": {
    "countries": ["AF", "BD"],
    "regions": ["298"],
    "sectors": ["151", "15170"]
  },
  "require_funding_and_accountable": false,
  "include_exemptions": true
}
```

Response:
```json
{
  "summary": {
    "organisation": "GB-GOV-1",
    "total_programmes": 45,
    "total_projects": 230,
    "total_budget": 125000000.0,
    "financial_year": "2024-2025"
  },
  "failed_activities": [
    {
      "iati_identifier": "GB-GOV-1-12345",
      "hierarchy": 1,
      "title": "Programme Title",
      "activity_status": "2",
      "attributes": [
        {
          "attribute": "title",
          "status": "fail",
          "message": "Title is too short (45 characters, minimum 60 required)",
          "details": {"length": 45}
        }
      ],
      "documents": [],
      "overall_status": "fail",
      "failure_count": 1
    }
  ],
  "pass_count": 270,
  "fail_count": 5,
  "not_applicable_count": 150,
  "generated_at": "2024-02-12T10:30:00",
  "percentages": {
    "title_percentage": 45
  }
}
```

### Clear Cache

```bash
POST /dqa/cache/clear?pattern=dqa:*
```

Response:
```json
{
  "cleared": 42,
  "pattern": "dqa:*"
}
```

### Config Lists

The `data/` directory holds JSON arrays used by the validator (default dates, document exemptions, etc.). These endpoints let you inspect and edit them at runtime without restarting the service.

**List available configs**
```bash
GET /dqa/config
```
```json
{ "configs": ["default_dates", "document_validation_exemptions", "non_acronyms"] }
```

**Get all values in a config**
```bash
GET /dqa/config/<config_name>
```
```json
{ "config_name": "default_dates", "values": ["1900-01-01", "1970-01-01"] }
```

**Edit a config** — `action` is one of `add`, `remove`, or `update`:
```bash
PATCH /dqa/config/<config_name>
Content-Type: application/json
```
```json
// Add a value
{ "action": "add", "value": "2000-01-01" }

// Remove a value
{ "action": "remove", "value": "1900-01-01" }

// Replace a value
{ "action": "update", "old_value": "1900-01-01", "new_value": "1901-06-01" }
```

Returns the full updated list on success. Error responses: `400` (bad request), `404` (config or value not found), `409` (value already exists).

> **Note**: Changes to `default_dates` are applied to the running process immediately. All other edits are persisted to disk and picked up on the next request that reads the file.

## Validation Rules

See [VALIDATOR_RULES.md](VALIDATOR_RULES.md) for the full per-attribute and per-document validation logic, including conditions, statuses, messages, and percentage calculations.

## Testing

```bash
pytest           # run all tests with coverage
pytest -v        # verbose output
```

See [DEVELOPMENT.md](DEVELOPMENT.md) for more test commands and guidance.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SOLR_URL` | Solr instance URL | `http://localhost:8983/solr/activity` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `CACHE_TTL` | Cache TTL in seconds | `86400` (24 hours) |
| `SECRET_KEY` | API authentication key (`X-API-Key` header) | `ZIMMERMAN` |
| `DEFAULT_DATES` | Comma-separated default dates | `1900-01-01,1970-01-01` |
| `BUSINESS_CASE_EXEMPTION_MONTHS` | Months before BC required | `3` |
| `LOGICAL_FRAMEWORK_EXEMPTION_MONTHS` | Months before LF required | `3` |
| `ANNUAL_REVIEW_EXEMPTION_MONTHS` | Months before AR required | `19` |
| `SECTOR_TOLERANCE` | Sector percentage tolerance | `0.02` |
| `LOCATION_TOLERANCE` | Location percentage tolerance | `0.02` |

## Project Structure

See [DEVELOPMENT.md](DEVELOPMENT.md#project-structure) for the full annotated project structure.

## Development

_This project was co-developed with AI to accelerate feature delivery. All code has been manually reviewed and tested for quality._

See [DEVELOPMENT.md](DEVELOPMENT.md) for setup, formatting, linting, adding new validations, debugging, and more.

## Deployment

### Production Considerations

1. **Monitoring**: Implement logging and metrics
2. **Scaling**: Use Redis Cluster for high availability
3. **Rate Limiting**: Add rate limiting middleware
4. **HTTPS**: Deploy behind reverse proxy with SSL

### Docker Production Build

```bash
docker build -t iati-dqa-api:latest .
docker-compose -f docker-compose.yml up -d
```

## License

[See LICENSE.MD](./LICENSE.MD)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## Support

For issues and questions:
- [GitHub Issues](https://github.com/zimmerman-team/iati-cloud.dqa/issues)
