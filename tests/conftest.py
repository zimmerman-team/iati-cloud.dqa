"""Pytest configuration and fixtures."""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest  # noqa: F401

from app.cache import Cache
from app.main import app
from app.models import (ActivityValidationResult, DQAResponse,
                        OrganisationSummary)
from app.solr_client import SolrClient
from app.validator import ActivityValidator

TEST_API_KEY = "ZIMMERMAN"

TITLE_NARRATIVE = "title.narrative"
DESCRIPTION_NARRATIVE = "description.narrative"
ACTIVITY_DATE_START_ACTUAL = "activity-date.start-actual"
SECTOR_CODE = "sector.code"
SECTOR_PERCENTAGE = "sector.percentage"


class AuthedTestClient:
    """Wraps Flask test client and injects X-API-Key on every request."""

    def __init__(self, client, api_key: str):
        self._client = client
        self._api_key = api_key

    def _inject_key(self, kwargs: dict) -> dict:
        headers = dict(kwargs.pop("headers", None) or {})
        headers.setdefault("X-API-Key", self._api_key)
        return {**kwargs, "headers": headers}

    def get(self, *args, **kwargs):
        return self._client.get(*args, **self._inject_key(kwargs))

    def post(self, *args, **kwargs):
        return self._client.post(*args, **self._inject_key(kwargs))

    def patch(self, *args, **kwargs):
        return self._client.patch(*args, **self._inject_key(kwargs))


@pytest.fixture
def flask_app():
    """Flask app for testing."""
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(flask_app):
    """Flask test client with X-API-Key pre-loaded."""
    return AuthedTestClient(flask_app.test_client(), TEST_API_KEY)


@pytest.fixture
def raw_client(flask_app):
    """Flask test client without API key (for testing auth failures)."""
    return flask_app.test_client()


@pytest.fixture
def mock_cache():
    """Mock cache."""
    cache = Mock(spec=Cache)
    cache.get.return_value = None
    cache.set.return_value = True
    cache.delete.return_value = True
    cache.ping.return_value = True
    return cache


@pytest.fixture
def mock_solr():
    """Mock Solr client."""
    solr = Mock(spec=SolrClient)
    return solr


@pytest.fixture
def mock_validator():
    """Mock ActivityValidator."""
    validator = Mock(spec=ActivityValidator)
    validator.validate_activity.return_value = ([], [])
    validator.calculate_budget_for_fy.return_value = 0.0
    validator.calculate_percentages.side_effect = lambda r: r
    return validator


@pytest.fixture
def validator():
    """Activity validator instance."""
    return ActivityValidator(exemptions=[])


@pytest.fixture
def validator_with_exemptions():
    """Activity validator instance."""
    return ActivityValidator(exemptions=["GB-GOV-1-EXEMPT"])


@pytest.fixture
def sample_activity():
    """Sample valid H1 activity."""
    now = datetime.now()
    two_years_ago = now - timedelta(days=730)

    return {
        "iati-identifier": "GB-GOV-1-12345",
        "hierarchy": 1,
        "activity-status.code": "2",
        TITLE_NARRATIVE: ["Sustainable Development Programme for Climate Change Adaptation in Bangladesh"],
        DESCRIPTION_NARRATIVE: [
            "This comprehensive programme aims to build resilience and adaptive capacity "
            "to climate-related hazards in Bangladesh through community-based interventions, "
            "infrastructure improvements, and capacity building initiatives."
        ],
        ACTIVITY_DATE_START_ACTUAL: [two_years_ago.isoformat() + "Z"],
        "activity-date.end-planned": [(now + timedelta(days=365)).isoformat() + "Z"],
        SECTOR_CODE: ["15170", "15110"],
        SECTOR_PERCENTAGE: [60.0, 40.0],
        "recipient-country.code": ["BD"],
        "recipient-country.percentage": [100.0],
        "participating-org.ref": ["GB-GOV-1", "BD-GOV-X"],
        "document-link.title.narrative": [
            "Business Case Published",
            "Logical Framework Published",
            "Annual Review Published",
        ],
    }


@pytest.fixture
def sample_h2_activity():
    """Sample valid H2 activity (project)."""
    now = datetime.now()
    one_year_ago = now - timedelta(days=365)

    return {
        "iati-identifier": "GB-GOV-1-12345-P1",
        "hierarchy": 2,
        "activity-status.code": "2",
        TITLE_NARRATIVE: ["Infrastructure Development Component for Climate Resilient Communities"],
        DESCRIPTION_NARRATIVE: [
            "This project component focuses on building climate-resilient infrastructure "
            "including flood protection systems, water management facilities, and sustainable "
            "agricultural infrastructure in vulnerable coastal areas."
        ],
        ACTIVITY_DATE_START_ACTUAL: [one_year_ago.isoformat() + "Z"],
        "activity-date.end-planned": [(now + timedelta(days=365)).isoformat() + "Z"],
        SECTOR_CODE: ["14010"],
        SECTOR_PERCENTAGE: [100.0],
        "recipient-country.code": ["BD"],
        "recipient-country.percentage": [100.0],
        "participating-org.ref": ["GB-GOV-1", "BD-LOCAL-1"],
    }


@pytest.fixture
def activity_with_invalid_title():
    """Activity with title that's too short."""
    return {
        "iati-identifier": "GB-GOV-1-SHORT",
        "hierarchy": 1,
        TITLE_NARRATIVE: ["Short Title"],
        DESCRIPTION_NARRATIVE: ["This is a valid description that is longer than the title."],
    }


@pytest.fixture
def activity_with_default_date():
    """Activity with a default system date."""
    return {
        "iati-identifier": "GB-GOV-1-DEFAULT",
        "hierarchy": 1,
        ACTIVITY_DATE_START_ACTUAL: ["1900-01-01T00:00:00Z"],
    }


@pytest.fixture
def activity_missing_sectors():
    """Activity missing sector information."""
    return {
        "iati-identifier": "GB-GOV-1-NOSECTOR",
        "hierarchy": 1,
        TITLE_NARRATIVE: ["Programme Without Sectors - This Title is Long Enough to Pass Validation"],
    }


@pytest.fixture
def activity_invalid_sector_percentage():
    """Activity with sector percentages not summing to 100%."""
    return {
        "iati-identifier": "GB-GOV-1-BADPCT",
        "hierarchy": 1,
        SECTOR_CODE: ["15170", "15110"],
        SECTOR_PERCENTAGE: [60.0, 30.0],  # Only 90%
    }


@pytest.fixture
def activity_transaction_sector():
    """Activity with transaction sector but no activity-level sector."""
    return {
        "iati-identifier": "GB-GOV-1-TRANSSECTOR",
        "hierarchy": 1,
        "transaction.sector.code": "15170",
    }


@pytest.fixture
def activity_no_business_case():
    """H1 activity started 6 months ago without business case."""
    six_months_ago = datetime.now() - timedelta(days=180)
    return {
        "iati-identifier": "GB-GOV-1-NOBC",
        "hierarchy": 1,
        ACTIVITY_DATE_START_ACTUAL: [six_months_ago.isoformat() + "Z"],
        "document-link.title.narrative": [],
    }


@pytest.fixture
def activity_exempt():
    """Activity that should be exempt from document checks."""
    return {
        "iati-identifier": "GB-GOV-1-EXEMPT",
        "hierarchy": 1,
        ACTIVITY_DATE_START_ACTUAL: [(datetime.now() - timedelta(days=365)).isoformat() + "Z"],
    }


@pytest.fixture
def activity_transaction_location():
    """Activity with transaction recipient country and region, no direct location with percentages."""
    return {
        "iati-identifier": "GB-GOV-1-TRANSLOC",
        "hierarchy": 1,
        "transaction.recipient-country.code": "BD",
        "transaction.recipient-region.code": "13000",
    }


@pytest.fixture
def activity_transaction_location_no_codes():
    """Activity with transaction recipient country and region, no direct location with percentages."""
    return {
        "iati-identifier": "GB-GOV-1-TRANSLOC",
        "hierarchy": 1,
    }


@pytest.fixture
def dqa_response_sample():
    """Sample DQAResponse for testing."""
    return DQAResponse(
        summary=OrganisationSummary(
            organisation="GB-GOV-1",
            financial_year="2022-2026",
            total_programmes=1,
            total_projects=1,
            total_budget=269500000.0,
        ),
        failed_activities=[
            ActivityValidationResult(
                iati_identifier="GB-GOV-3-BC",
                hierarchy=1,
                title="British Council: Official Development Assistance (ODA) support",
                activity_status="2",
                attributes=[
                    {
                        "attribute": "title",
                        "details": {"acronyms": ["ODA"], "percentage": 95.16129032258065},
                        "message": "Title contains potential acronyms that should be expanded: ODA",
                        "status": "fail",
                    },
                    {
                        "attribute": "description",
                        "details": {"length": 144, "percentage": 100.0},
                        "message": None,
                        "status": "pass",
                    },
                    {
                        "attribute": "start_date",
                        "details": {"date": "2016-04-01", "percentage": 100.0},
                        "message": None,
                        "status": "pass",
                    },
                    {
                        "attribute": "end_date",
                        "details": {"date": "2025-03-31", "percentage": 100.0},
                        "message": None,
                        "status": "pass",
                    },
                    {
                        "attribute": "sector",
                        "details": {"count": 1, "percentage": 100.0},
                        "message": None,
                        "status": "pass",
                    },
                    {
                        "attribute": "location",
                        "details": {"percentage": 100.0, "total": 100.0},
                        "message": None,
                        "status": "pass",
                    },
                    {
                        "attribute": "participating_org",
                        "details": {"count": 2, "percentage": 100.0},
                        "message": None,
                        "status": "pass",
                    },
                ],
                documents=[
                    {
                        "document_type": "business_case",
                        "exemption_reason": None,
                        "message": "Business Case document not published",
                        "published": False,
                        "status": "fail",
                    },
                    {
                        "document_type": "logical_framework",
                        "exemption_reason": None,
                        "message": "Logical Framework document not published",
                        "published": False,
                        "status": "fail",
                    },
                    {
                        "document_type": "annual_review",
                        "exemption_reason": None,
                        "message": "Annual Review document not published",
                        "published": False,
                        "status": "fail",
                    },
                ],
                overall_status="fail",
                failure_count=3,
            ),
            ActivityValidationResult(
                activity_status="2",
                attributes=[
                    {
                        "attribute": "title",
                        "details": {
                            "length": 35,
                            "percentage": 58.333333333333336,
                            "title": "British Council: budgets & payments",
                        },
                        "message": "Title is too short (35 characters, minimum 60 required)",
                        "status": "fail",
                    },
                    {
                        "attribute": "description",
                        "details": {"length": 144, "percentage": 100.0},
                        "message": None,
                        "status": "pass",
                    },
                    {
                        "attribute": "start_date",
                        "details": {"date": "2016-04-01", "percentage": 100.0},
                        "message": None,
                        "status": "pass",
                    },
                    {
                        "attribute": "end_date",
                        "details": {"date": "2025-03-31", "percentage": 100.0},
                        "message": None,
                        "status": "pass",
                    },
                    {
                        "attribute": "sector",
                        "details": {"count": 1, "percentage": 100.0},
                        "message": None,
                        "status": "pass",
                    },
                    {
                        "attribute": "location",
                        "details": {"percentage": 100.0},
                        "message": "No activity-level locations defined, only transaction-level locations",
                        "status": "not_applicable",
                    },
                    {
                        "attribute": "participating_org",
                        "details": {"count": 2, "percentage": 100.0},
                        "message": None,
                        "status": "pass",
                    },
                ],
                documents=[],
                failure_count=1,
                hierarchy=2,
                iati_identifier="GB-GOV-3-BC-101",
                overall_status="fail",
                title="British Council: budgets & payments",
            ),
        ],
        generated_at="2026-02-19T12:21:29.676151",
        not_applicable_count=1,
        pass_count=0,
    )
