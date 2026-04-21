import json
from unittest.mock import Mock, patch  # noqa: F401

import pytest  # noqa: F401


class TestAuthentication:
    """Tests for API key authentication."""

    def test_missing_api_key_returns_401(self, raw_client):
        """Test that requests without Authorization are rejected."""
        response = raw_client.get("/dqa/health")
        assert response.status_code == 401
        data = json.loads(response.data)
        assert "error" in data

    def test_wrong_api_key_returns_401(self, raw_client):
        """Test that requests with an incorrect Authorization are rejected."""
        response = raw_client.get("/dqa/health", headers={"Authorization": "WRONG_KEY"})
        assert response.status_code == 401

    def test_correct_api_key_is_accepted(self, raw_client):
        """Test that the correct Authorization passes authentication."""
        with patch("app.main.cache") as mock_cache:
            mock_cache.ping.return_value = True
            response = raw_client.get("/dqa/health", headers={"Authorization": "ZIMMERMAN"})
        assert response.status_code == 200

    def test_swagger_ui_exempt_from_auth(self, raw_client):
        """Test that the Swagger UI is accessible without an API key."""
        response = raw_client.get("/dqa/docs/")
        assert response.status_code != 401

    def test_openapi_spec_exempt_from_auth(self, raw_client):
        """Test that the OpenAPI spec endpoint is accessible without an API key."""
        response = raw_client.get("/dqa/apispec.json")
        assert response.status_code != 401


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check_redis_connected(self, client, mock_cache):
        """Test health check when Redis is connected."""
        with patch("app.main.cache", mock_cache):
            response = client.get("/dqa/health")
            data = json.loads(response.data)

            assert response.status_code == 200
            assert data["status"] == "healthy"
            assert data["redis"] == "connected"
            assert "timestamp" in data

    def test_health_check_redis_disconnected(self, client, mock_cache):
        """Test health check when Redis is disconnected."""
        mock_cache.ping.return_value = False

        with patch("app.main.cache", mock_cache):
            response = client.get("/dqa/health")
            data = json.loads(response.data)

            assert response.status_code == 200
            assert data["status"] == "degraded"
            assert data["redis"] == "disconnected"


class TestDQAEndpoint:
    """Tests for DQA endpoint."""

    def test_dqa_endpoint_basic_request(self, client, mock_cache, mock_solr, mock_validator):
        """Test basic DQA request."""
        # Setup mocks
        mock_cache.get.return_value = None

        mock_solr.get_h1_activities.return_value = []
        mock_solr.get_h2_activities.return_value = []
        mock_validator.calculate_budget_for_fy.return_value = 0.0
        with (
            patch("app.main.cache", mock_cache),
            patch("app.main.solr_client", mock_solr),
            patch("app.main.ActivityValidator", return_value=mock_validator),
        ):
            request_data = {"organisation": "GB-GOV-1"}
            response = client.post("/dqa", data=json.dumps(request_data), content_type="application/json")
            data = json.loads(response.data)
            assert response.status_code == 200
            assert "summary" in data
            assert data["summary"]["organisation"] == "GB-GOV-1"
            assert "failed_activities" in data
            assert "pass_count" in data
            assert "fail_count" in data

    def test_dqa_endpoint_with_segmentation(self, client, mock_cache, mock_solr, mock_validator):
        """Test DQA request with segmentation filters."""
        mock_cache.get.return_value = None
        mock_solr.get_h1_activities.return_value = []
        mock_solr.get_h2_activities.return_value = []
        mock_validator.calculate_budget_for_fy.return_value = 0.0

        with (
            patch("app.main.cache", mock_cache),
            patch("app.main.solr_client", mock_solr),
            patch("app.main.ActivityValidator", return_value=mock_validator),
        ):
            request_data = {
                "organisation": "GB-GOV-1",
                "segmentation": {"countries": ["AF", "BD"], "sectors": ["151", "15170"]},
                "require_funding_and_accountable": True,
            }

            response = client.post("/dqa", data=json.dumps(request_data), content_type="application/json")

            assert response.status_code == 200

            # Verify filters were passed to Solr
            mock_solr.get_h1_activities.assert_called_once()
            call_kwargs = mock_solr.get_h1_activities.call_args[1]
            assert "countries" in call_kwargs
            assert call_kwargs["countries"] == ["AF", "BD"]
            assert "sectors" in call_kwargs
            assert call_kwargs["sectors"] == ["151", "15170"]

    def test_dqa_endpoint_returns_cached_result(self, client, mock_cache):
        """Test that cached results are returned."""
        cached_data = {
            "summary": {
                "organisation": "GB-GOV-1",
                "total_programmes": 10,
                "total_projects": 50,
                "total_budget": 1000000.0,
                "financial_year": "2024-2025",
            },
            "failed_activities": [],
            "pass_count": 60,
            "fail_count": 0,
            "not_applicable_count": 0,
            "generated_at": "2024-01-01T00:00:00",
        }
        mock_cache.get.return_value = cached_data

        with patch("app.main.cache", mock_cache):
            request_data = {"organisation": "GB-GOV-1"}

            response = client.post("/dqa", data=json.dumps(request_data), content_type="application/json")

            data = json.loads(response.data)

            assert response.status_code == 200
            assert data["summary"]["total_programmes"] == 10
            # Cache.set should not be called since we got cached data
            mock_cache.set.assert_not_called()

    def test_dqa_endpoint_invalid_request(self, client):
        """Test DQA endpoint with invalid request data."""
        response = client.post("/dqa", data=json.dumps({"invalid": "data"}), content_type="application/json")

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data

    def test_dqa_endpoint_with_failed_activities(self, client, mock_cache, mock_solr):
        """Test DQA endpoint with activities that fail validation."""
        mock_cache.get.return_value = None

        # Activity with invalid title (too short)
        failed_activity = {
            "iati-identifier": "GB-GOV-1-FAIL",
            "hierarchy": 1,
            "title.narrative": ["Too Short"],
            "description.narrative": ["This description is longer than the title."],
            "activity-status.code": "2",
        }

        mock_solr.get_h1_activities.return_value = [failed_activity]
        mock_solr.get_h2_activities.return_value = []
        mock_solr.get_all_downstream_partners_for_h1_and_h2.return_value = set()

        with patch("app.main.cache", mock_cache), patch("app.main.solr_client", mock_solr):
            request_data = {"organisation": "GB-GOV-1"}
            response = client.post("/dqa", data=json.dumps(request_data), content_type="application/json")
            data = json.loads(response.data)

            assert response.status_code == 200
            assert data["fail_count"] > 0
            assert len(data["failed_activities"]) > 0
            assert data["failed_activities"][0]["iati_identifier"] == "GB-GOV-1-FAIL"

    def test_dqa_endpoint_with_regions(self, client, mock_cache, mock_solr, mock_validator):
        """Test DQA request with regions filter."""
        mock_cache.get.return_value = None
        mock_solr.get_h1_activities.return_value = []
        mock_solr.get_h2_activities.return_value = []
        mock_validator.calculate_budget_for_fy.return_value = 0.0

        with (
            patch("app.main.cache", mock_cache),
            patch("app.main.solr_client", mock_solr),
            patch("app.main.ActivityValidator", return_value=mock_validator),
        ):
            request_data = {"organisation": "GB-GOV-1", "segmentation": {"regions": ["298", "299"]}}

            response = client.post("/dqa", data=json.dumps(request_data), content_type="application/json")

            assert response.status_code == 200
            mock_solr.get_h1_activities.assert_called_once()
            call_kwargs = mock_solr.get_h1_activities.call_args[1]
            assert "regions" in call_kwargs
            assert call_kwargs["regions"] == ["298", "299"]

    def test_dqa_endpoint_failed_activities_false_omits_list(self, client, mock_cache, mock_solr):
        """Test that failed_activities=false returns an empty list even when failures exist."""
        mock_cache.get.return_value = None

        failed_activity = {
            "iati-identifier": "GB-GOV-1-FAIL",
            "hierarchy": 1,
            "title.narrative": ["Too Short"],
            "description.narrative": ["This description is longer than the title."],
            "activity-status.code": "2",
        }
        mock_solr.get_h1_activities.return_value = [failed_activity]
        mock_solr.get_h2_activities.return_value = []
        mock_solr.get_all_downstream_partners_for_h1_and_h2.return_value = set()

        with patch("app.main.cache", mock_cache), patch("app.main.solr_client", mock_solr):
            request_data = {"organisation": "GB-GOV-1", "failed_activities": False}
            response = client.post("/dqa", data=json.dumps(request_data), content_type="application/json")
            data = json.loads(response.data)

            assert response.status_code == 200
            assert data["fail_count"] > 0
            assert data["failed_activities"] == []

    def test_dqa_endpoint_failed_activities_false_with_cache_hit(self, client, mock_cache):
        """Test that failed_activities=false strips the list from a cached response."""
        cached_data = {
            "summary": {
                "organisation": "GB-GOV-1",
                "total_programmes": 1,
                "total_projects": 0,
                "total_budget": 0.0,
                "financial_year": "2024-2025",
            },
            "failed_activities": [{"iati_identifier": "GB-GOV-1-FAIL"}],
            "pass_count": 0,
            "fail_count": 1,
            "not_applicable_count": 0,
            "generated_at": "2024-01-01T00:00:00",
        }
        mock_cache.get.return_value = cached_data

        with patch("app.main.cache", mock_cache):
            request_data = {"organisation": "GB-GOV-1", "failed_activities": False}
            response = client.post("/dqa", data=json.dumps(request_data), content_type="application/json")
            data = json.loads(response.data)

            assert response.status_code == 200
            assert data["fail_count"] == 1
            assert data["failed_activities"] == []

    def test_dqa_endpoint_pass_count(self, client, mock_cache, mock_solr, mock_validator):
        """Test DQA endpoint returns correct pass_count when all activities pass validation."""
        mock_cache.get.return_value = None
        # Activities that will pass validation (simulate validator always passing)
        passing_activity = {
            "iati-identifier": "GB-GOV-1-PASS",
            "hierarchy": 1,
            "title.narrative": ["A Valid Title"],
            "description.narrative": ["A Valid Description"],
            "activity-status.code": "2",
        }
        mock_solr.get_h1_activities.return_value = [passing_activity]
        mock_solr.get_h2_activities.return_value = []
        mock_solr.get_all_downstream_partners_for_h1_and_h2.return_value = set()
        mock_validator.calculate_budget_for_fy.return_value = 0.0

        # Patch ActivityValidator.validate_activity to always return pass
        with (
            patch("app.main.cache", mock_cache),
            patch("app.main.solr_client", mock_solr),
            patch("app.main.ActivityValidator.validate_activity", return_value=([], [])),
        ):
            request_data = {"organisation": "GB-GOV-1"}
            response = client.post("/dqa", data=json.dumps(request_data), content_type="application/json")
            data = json.loads(response.data)
            assert response.status_code == 200
            assert data["pass_count"] == 1
            assert data["fail_count"] == 0
            assert data["not_applicable_count"] == 0


class TestCacheClearEndpoint:
    """Tests for cache clear endpoint."""

    def test_clear_cache_default(self, client, mock_cache):
        """Test clearing cache with default pattern."""
        mock_cache.clear_pattern.return_value = 42

        with patch("app.main.cache", mock_cache):
            response = client.post("/dqa/cache/clear")
            data = json.loads(response.data)

            assert response.status_code == 200
            assert data["cleared"] == 42
            assert data["pattern"] == "*"
            mock_cache.clear_pattern.assert_called_once_with("*")

    def test_clear_cache_with_pattern(self, client, mock_cache):
        """Test clearing cache with specific pattern."""
        mock_cache.clear_pattern.return_value = 5

        with patch("app.main.cache", mock_cache):
            response = client.post(
                "/dqa/cache/clear", data=json.dumps({"pattern": "dqa:GB-GOV-1:*"}), content_type="application/json"
            )
            data = json.loads(response.data)

            assert response.status_code == 200
            assert data["cleared"] == 5
            assert data["pattern"] == "dqa:GB-GOV-1:*"
            mock_cache.clear_pattern.assert_called_once_with("dqa:GB-GOV-1:*")


class TestDownstreamLinkInjection:
    """Unit tests for the downstream partner link injection helpers in main.py."""

    def test_process_h2_downstream_links_basic(self):
        """H2 activity gets EDPL/HDPL fields injected correctly."""
        from app.main import _process_h2_downstream_links

        activity = {
            "iati-identifier": "GB-GOV-1-H2",
            "transaction.transaction-type.code": ["3", "1"],  # 1 outgoing transfer
        }
        referenced = {"GB-GOV-1-H2"}
        h2_links = {}
        _process_h2_downstream_links(activity, referenced, h2_links)

        assert activity["_expected_downstream_partner_links"] == 1
        assert activity["_has_downstream_partner_links"] is True
        assert h2_links["GB-GOV-1-H2"] == {"expected_links": 1, "has_link": True}

    def test_process_h1_downstream_links_h1_has_direct_link(self):
        """H1 whose ID is in referenced_partners returns early (no child loop)."""
        from app.main import _process_h1_downstream_links

        activity = {"iati-identifier": "GB-GOV-1-H1", "transaction.transaction-type.code": []}
        referenced = {"GB-GOV-1-H1"}
        _process_h1_downstream_links(activity, referenced, {"GB-GOV-1-H1": []}, {})

        assert activity["_has_downstream_partner_links"] is True
        # EDPL stays at 0 (no transactions), early return before child loop
        assert activity["_expected_downstream_partner_links"] == 0

    def test_process_h1_downstream_links_with_h2_child_linking_back(self):
        """H1 not in referenced_partners but child H2 is — H1 inherits has_link=True."""
        from app.main import _process_h1_downstream_links

        activity = {"iati-identifier": "GB-GOV-1-H1", "transaction.transaction-type.code": []}
        referenced = set()  # H1 not directly referenced
        activity_ids = {"GB-GOV-1-H1": ["GB-GOV-1-H1", "GB-GOV-1-H2"]}
        h2_links = {"GB-GOV-1-H2": {"expected_links": 1, "has_link": True}}

        _process_h1_downstream_links(activity, referenced, activity_ids, h2_links)

        assert activity["_has_downstream_partner_links"] is True
        assert activity["_expected_downstream_partner_links"] == 1

    def test_inject_downstream_partner_links_with_related_activity(self):
        """H1 json.related-activity type-2 entries are added to activity_ids; H2 activities are processed."""
        from unittest.mock import patch as _patch

        from app.main import _inject_downstream_partner_links
        from app.solr_client import SolrClient

        mock_solr_instance = Mock(spec=SolrClient)
        mock_solr_instance.get_all_downstream_partners_for_h1_and_h2.return_value = set()

        h1 = {
            "iati-identifier": "GB-GOV-1-H1",
            "transaction.transaction-type.code": [],
            "json.related-activity": ['{"type": 2, "ref": "GB-GOV-1-H2"}'],
        }
        h2 = {
            "iati-identifier": "GB-GOV-1-H2",
            "transaction.transaction-type.code": [],
        }

        with _patch("app.main.solr_client", mock_solr_instance):
            _inject_downstream_partner_links([h1], [h2])

        call_args = mock_solr_instance.get_all_downstream_partners_for_h1_and_h2.call_args[0][0]
        assert "GB-GOV-1-H2" in call_args.get("GB-GOV-1-H1", [])
        assert h2["_has_downstream_partner_links"] is False
