from unittest.mock import Mock, patch

import pysolr
import pytest  # noqa: F401

from app.models import ActivityStatus, AvailableSegmentations
from app.solr_client import SolrClient


class TestSolrClient:
    """Tests for SolrClient class."""

    @patch("app.solr_client.pysolr.Solr")
    def test_build_activity_scope_query_implementation(self, mock_solr_class):
        """Test query building for implementation activities."""
        client = SolrClient()
        query = client._build_activity_scope_query("GB-GOV-1")

        assert 'reporting-org.ref:"GB-GOV-1"' in query
        assert ActivityStatus.IMPLEMENTATION.value in query
        assert ActivityStatus.CLOSED.value in query

    @patch("app.solr_client.pysolr.Solr")
    def test_get_activities_basic(self, mock_solr_class):
        """Test getting activities with basic filters."""
        mock_solr = Mock()
        mock_solr.search.return_value = [{"id": "1"}, {"id": "2"}]
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        results = client.get_activities("GB-GOV-1")

        assert len(results) == 2
        mock_solr.search.assert_called_once()

    @patch("app.solr_client.pysolr.Solr")
    def test_get_activities_with_hierarchy(self, mock_solr_class):
        """Test getting activities with hierarchy filter."""
        mock_solr = Mock()
        mock_solr.search.return_value = [{"id": "1", "hierarchy": 1}]
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        results = client.get_activities("GB-GOV-1", hierarchy=1)

        assert len(results) == 1
        # Check that hierarchy filter was in query
        call_args = mock_solr.search.call_args
        query = call_args[0][0]
        assert "hierarchy:1" in query

    @patch("app.solr_client.pysolr.Solr")
    def test_get_activities_with_countries(self, mock_solr_class):
        """Test getting activities with country filter."""
        mock_solr = Mock()
        mock_solr.search.return_value = []
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        client.get_activities("GB-GOV-1", countries=["AF", "BD"])

        call_args = mock_solr.search.call_args
        query = call_args[0][0]
        assert 'recipient-country.code:"AF"' in query or 'recipient-country.code:"BD"' in query

    @patch("app.solr_client.pysolr.Solr")
    def test_get_activities_with_sectors_3_digit(self, mock_solr_class):
        """Test getting activities with 3-digit sector codes."""
        mock_solr = Mock()
        mock_solr.search.return_value = []
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        client.get_activities("GB-GOV-1", sectors=["151"])

        call_args = mock_solr.search.call_args
        query = call_args[0][0]
        # Should use wildcard for 3-digit codes
        assert "sector.code:151*" in query

    @patch("app.solr_client.pysolr.Solr")
    def test_get_activities_with_sectors_5_digit(self, mock_solr_class):
        """Test getting activities with 5-digit sector codes."""
        mock_solr = Mock()
        mock_solr.search.return_value = [{"id": "1", "sector": "15170"}]
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        client.get_activities("GB-GOV-1", sectors=["15170"])

        call_args = mock_solr.search.call_args
        query = call_args[0][0]
        # Should use exact match for 5-digit codes
        assert 'sector.code:"15170"' in query

    @patch("app.solr_client.pysolr.Solr")
    def test_get_h1_activities(self, mock_solr_class):
        """Test getting H1 activities shortcut."""
        mock_solr = Mock()
        mock_solr.search.return_value = [{"hierarchy": 1}]
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        client.get_h1_activities("GB-GOV-1")

        call_args = mock_solr.search.call_args
        query = call_args[0][0]
        assert "hierarchy:1" in query

    @patch("app.solr_client.pysolr.Solr")
    def test_get_h2_activities(self, mock_solr_class):
        """Test getting H2 activities shortcut."""
        mock_solr = Mock()
        mock_solr.search.return_value = [{"hierarchy": 2}]
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        client.get_h2_activities("GB-GOV-1")

        call_args = mock_solr.search.call_args
        query = call_args[0][0]
        assert "hierarchy:2" in query

    @patch("app.solr_client.pysolr.Solr")
    def test_solr_error_handling(self, mock_solr_class):
        """Test error handling for Solr errors."""
        import pysolr

        mock_solr = Mock()
        mock_solr.search.side_effect = pysolr.SolrError("Solr connection error")
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        results = client.get_activities("GB-GOV-1")

        # Should return empty list on error
        assert results == []

    @patch("app.solr_client.pysolr.Solr")
    def test_get_activities_with_regions(self, mock_solr_class):
        """Test getting activities with region filter."""
        mock_solr = Mock()
        mock_solr.search.return_value = []
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        client.get_activities("GB-GOV-1", regions=["298", "299"])

        call_args = mock_solr.search.call_args
        query = call_args[0][0]
        assert 'recipient-region.code:"298"' in query or 'recipient-region.code:"299"' in query

    @patch("app.solr_client.pysolr.Solr")
    def test_get_activities_with_hierarchy_filter(self, mock_solr_class):
        """Test that hierarchy filter is included in query when provided."""
        mock_solr = Mock()
        mock_solr.search.return_value = []
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        client.get_activities("GB-GOV-1", hierarchy=2)

        call_args = mock_solr.search.call_args
        query = call_args[0][0]
        assert "hierarchy:2" in query

    @patch("app.solr_client.pysolr.Solr")
    def test_init_raises_connection_error_on_ping_failure(self, mock_solr_class):
        mock_solr = Mock()
        mock_solr.ping.side_effect = pysolr.SolrError("ping failed")
        mock_solr_class.return_value = mock_solr

        with pytest.raises(ConnectionError, match="Could not connect to Solr"):
            SolrClient()

    @patch("app.solr_client.pysolr.Solr")
    def test_get_activities_with_filter_results_false(self, mock_solr_class):
        """Test get_activities with filter_results=False returns unfiltered results."""
        mock_solr = Mock()
        mock_solr.search.return_value = [
            {"id": "1", "json.participating-org": ['{"role": 1, "ref": "NOT-GB-GOV-1"}']},
            {"id": "2", "json.participating-org": ['{"role": 1, "ref": "GB-GOV-1"}', '{"role": 2, "ref": "GB-GOV-1"}']},
        ]
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        results = client.get_activities("GB-GOV-1", filter_results=True)
        assert results[0]["id"] == "2"
        assert len(results) == 1

    @patch("app.solr_client.pysolr.Solr")
    def test_get_all_downstream_partners_basic(self, mock_solr_class):
        """Returns the set of activity IDs that link back to the queried identifiers."""
        mock_solr = Mock()
        mock_solr.search.return_value = [
            {
                "iati-identifier": "EXTERNAL-1",
                "transaction_provider_org_provider_activity_id": ["GB-GOV-1-H1"],
            }
        ]
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        activities = {"GB-GOV-1-H1": ["GB-GOV-1-H1"]}
        result = client.get_all_downstream_partners_for_h1_and_h2(activities)

        assert "GB-GOV-1-H1" in result

    @patch("app.solr_client.pysolr.Solr")
    def test_get_all_downstream_partners_solr_error(self, mock_solr_class):
        """A SolrError during downstream query is swallowed and returns empty set."""
        mock_solr = Mock()
        mock_solr.search.side_effect = pysolr.SolrError("timeout")
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        result = client.get_all_downstream_partners_for_h1_and_h2({"GB-GOV-1": ["GB-GOV-1"]})

        assert result == set()

    @patch("app.solr_client.pysolr.Solr")
    def test_extract_referenced_partners_non_list_ref(self, mock_solr_class):
        """Scalar (non-list) ref values are coerced to a one-element list."""
        mock_solr = Mock()
        mock_solr_class.return_value = mock_solr

        client = SolrClient()
        iati_set = {"GB-GOV-1-H1"}
        referenced: set = set()

        fake_results = [{"transaction_provider_org_provider_activity_id": "GB-GOV-1-H1"}]
        client._extract_referenced_partners(fake_results, iati_set, referenced)

        assert "GB-GOV-1-H1" in referenced

    @patch("app.solr_client.pysolr.Solr")
    def test_extract_segmentations_list_fields(self, mock_solr_class):
        """Extracts unique codes from list-valued Solr fields."""
        mock_solr_class.return_value = Mock()
        client = SolrClient()
        activities = [
            {
                "recipient-country.code": ["BD", "KE"],
                "recipient-region.code": ["298"],
                "sector.code": ["15170", "15110"],
            },
            {
                "recipient-country.code": "BD",  # scalar
                "transaction.recipient-country.code": ["ET"],
                "transaction.recipient-region.code": "89",
                "transaction.sector.code": ["72010"],
            },
        ]
        result = client.extract_segmentations(activities)
        assert isinstance(result, AvailableSegmentations)
        assert result.countries == sorted(["BD", "ET", "KE"])
        assert result.regions == sorted(["298", "89"])
        assert result.sectors == sorted(["15110", "15170", "72010"])

    @patch("app.solr_client.pysolr.Solr")
    def test_extract_segmentations_empty(self, mock_solr_class):
        """Returns empty lists when activities have no location/sector data."""
        mock_solr_class.return_value = Mock()
        client = SolrClient()
        result = client.extract_segmentations([{}, {}])
        assert result.countries == []
        assert result.regions == []
        assert result.sectors == []

    @patch("app.solr_client.pysolr.Solr")
    def test_extract_segmentations_deduplicates(self, mock_solr_class):
        """Duplicate codes across activities appear only once."""
        mock_solr_class.return_value = Mock()
        client = SolrClient()
        activities = [
            {"recipient-country.code": ["BD"]},
            {"recipient-country.code": ["BD"]},
        ]
        result = client.extract_segmentations(activities)
        assert result.countries == ["BD"]
