import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pysolr

from app.config import settings
from app.models import ActivityStatus, AvailableSegmentations

DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
AND = " AND "
OR = " OR "
TXT_BUDGET_VALUE = "budget.value"


QUERY_FL = ",".join(
    [
        "iati-identifier",
        "hierarchy",
        "title.narrative",
        "description.narrative",
        "activity-status.code",
        "reporting-org.ref",
        "participating-org.ref",
        "json.participating-org",
        "activity-date.start-actual",
        "activity-date.end-actual",
        "activity-date.end-planned",
        "recipient-country.code",
        "recipient-country.percentage",
        "recipient-region.code",
        "recipient-region.percentage",
        "transaction.recipient-country.code",
        "transaction.recipient-region.code",
        "sector.code",
        "transaction.sector.code",
        "transaction.transaction-type.code",
        "sector.percentage",
        "budget.period-start.iso-date",
        TXT_BUDGET_VALUE,
        "document-link.title.narrative",
        "json.budget",
        "json.related-activity",
    ]
)

logger = logging.getLogger("app.solr_client")


class SolrClient:
    """Client for querying Solr IATI data."""

    def __init__(self):
        """Initialize Solr connection."""
        logger.info("Initializing SolrClient")
        self.solr = pysolr.Solr(settings.solr_url, always_commit=True, timeout=10)

        # test solr connection on startup
        try:
            self.solr.ping()
            logger.info("Successfully connected to Solr")
        except pysolr.SolrError as e:
            logger.error(f"Error connecting to Solr: {e}")
            raise ConnectionError(f"Could not connect to Solr at {settings.solr_url}") from e

    def _build_activity_scope_query(self, organisation: str) -> str:
        """Build query for activity scope (implementation or closed within 18 months)."""
        logger.debug(f"Building activity scope query for organisation: {organisation}")
        queries = []

        # Organisation filter
        queries.append(f'reporting-org.ref:"{organisation}"')

        # For closed activities, check if closed within last 18 months
        cutoff_date = datetime.now() - timedelta(days=30 * settings.closed_within_months)
        cutoff_str = cutoff_date.strftime(DATE_FORMAT)

        # Build the complex query: Implementation OR (Closed AND end date within 18 months)
        scope_query = (
            f"(activity-status.code:{ActivityStatus.IMPLEMENTATION.value} OR "
            f"(activity-status.code:{ActivityStatus.CLOSED.value} AND "
            f"activity-date.end-actual:[{cutoff_str} TO NOW]))"
        )

        queries.append(scope_query)

        return AND.join(queries)

    def _segmented_query_parts(
        self,
        query_parts: List[str],
        countries: Optional[List[str]] = None,
        regions: Optional[List[str]] = None,
        sectors: Optional[List[str]] = None,
    ) -> List[str]:
        # Country filter
        if countries:
            country_q = OR.join([f'recipient-country.code:"{c}"' for c in countries])
            transaction_country_q = OR.join([f'transaction.recipient-country.code:"{c}"' for c in countries])
            query_parts.append(f"({country_q} OR {transaction_country_q})")

        # Region filter
        if regions:
            region_q = OR.join([f'recipient-region.code:"{r}"' for r in regions])
            transaction_region_q = OR.join([f'transaction.recipient-region.code:"{r}"' for r in regions])
            query_parts.append(f"({region_q} OR {transaction_region_q})")

        # Sector filter (handle both 3 and 5 digit codes)
        if sectors:
            sector_queries = []
            transaction_sector_queries = []
            for sector in sectors:
                if len(sector) == 3:
                    # Match any 5-digit code starting with this 3-digit code
                    sector_queries.append(f"sector.code:{sector}*")
                    transaction_sector_queries.append(f"transaction.sector.code:{sector}*")
                else:
                    sector_queries.append(f'sector.code:"{sector}"')
                    transaction_sector_queries.append(f'transaction.sector.code:"{sector}"')
            sector_q = OR.join(sector_queries)
            transaction_sector_q = OR.join(transaction_sector_queries)
            query_parts.append(f"({sector_q} OR {transaction_sector_q})")

        return query_parts

    def get_activities(
        self,
        organisation: str,
        hierarchy: Optional[int] = None,
        countries: Optional[List[str]] = None,
        regions: Optional[List[str]] = None,
        sectors: Optional[List[str]] = None,
        rows: int = 999999,  # fetch all available activities; never exceeds ~1 million in practice
        filter_results: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get activities matching criteria.

        Args:
            organisation: Organisation reference
            hierarchy: Activity hierarchy (1 for programmes, 2 for projects)
            countries: List of country codes
            regions: List of region codes
            sectors: List of sector codes (3 or 5 digit)
            rows: Maximum number of rows to return

        Returns:
            List of activity documents
        """
        logger.info(f"Fetching activities for organisation: {organisation}")
        query_parts = [self._build_activity_scope_query(organisation)]

        # Hierarchy filter
        if hierarchy is not None:
            query_parts.append(f"hierarchy:{hierarchy}")

        query_parts = self._segmented_query_parts(query_parts, countries, regions, sectors)

        query = AND.join(query_parts)

        try:
            logger.info(f"Solr query: {query}")
            results = self.solr.search(query, rows=rows, fl=QUERY_FL)
            logger.info(f"Solr returned {len(results)} results")
            # filter where json.participating-org does not contain an object with {"role": 2, "ref": organisation}
            if filter_results:
                return self._filter_results(results, organisation)
            return list(results)
        except pysolr.SolrError as e:
            logger.error(f"Solr query error: {e}")
            return []

    def _filter_results(self, results: pysolr.Results, organisation: str) -> List[Dict[str, Any]]:
        filtered_results = []
        for result in results:
            participating_orgs = result.get("json.participating-org", [])
            is_funding = False
            is_accountable = False
            for org in participating_orgs:
                parsed_org = json.loads(org)
                if parsed_org.get("ref") != organisation:
                    continue
                if parsed_org.get("role") == 1:
                    is_funding = True
                if parsed_org.get("role") == 2:
                    is_accountable = True
            if is_funding and is_accountable:
                filtered_results.append(result)
        return filtered_results

    DOWNSTREAM_CHUNK_SIZE = 100  # stay under Lucene's 1024 boolean-clause limit

    def get_all_downstream_partners_for_h1_and_h2(self, activities: Dict[str, List[str]]) -> set:
        """Get all downstream partners that link back to any H1 or H2 activity."""
        iati_identifiers = [i for sublist in activities.values() for i in sublist]

        iati_set = set(iati_identifiers)
        referenced: set = set()
        chunks = [
            iati_identifiers[i : i + self.DOWNSTREAM_CHUNK_SIZE]  # noqa: E203
            for i in range(0, len(iati_identifiers), self.DOWNSTREAM_CHUNK_SIZE)
        ]

        logger.info(
            f"Querying downstream partner links for {len(iati_identifiers)} identifiers in {len(chunks)} chunk(s)"
        )

        for chunk in chunks:
            id_query = OR.join([f'"{iati_id}"' for iati_id in chunk])
            query = f"transaction_provider_org_provider_activity_id:({id_query})"
            try:
                results = self.solr.search(
                    query, rows=999999, fl="transaction_provider_org_provider_activity_id,iati-identifier"
                )
                self._extract_referenced_partners(results, iati_set, referenced)
            except pysolr.SolrError as e:
                logger.error(f"Solr error querying downstream partner links (chunk): {e}")
        return referenced

    def _extract_referenced_partners(self, results: pysolr.Results, iati_set: set, referenced: set) -> None:
        """Helper function to extract referenced partners from Solr results."""
        for result in results:
            refs = result.get("transaction_provider_org_provider_activity_id", [])
            if not isinstance(refs, list):
                refs = [refs] if refs else []
            for ref in refs:
                if ref in iati_set:
                    referenced.add(ref)

    def extract_segmentations(self, activities: List[Dict[str, Any]]) -> AvailableSegmentations:
        """Extract unique country, region, and sector codes from a list of activity dicts."""
        country_fields: tuple = ("recipient-country.code", "transaction.recipient-country.code")
        region_fields: tuple = ("recipient-region.code", "transaction.recipient-region.code")
        sector_fields: tuple = ("sector.code", "transaction.sector.code")

        return AvailableSegmentations(
            countries=self._extract_segmentation(activities, country_fields),
            regions=self._extract_segmentation(activities, region_fields),
            sectors=self._extract_segmentation(activities, sector_fields),
        )

    def _extract_segmentation(self, activities: List[Dict[str, Any]], fields: tuple) -> List[str]:
        segment: set = set()
        for activity in activities:
            for field in fields:
                val = activity.get(field, [])
                codes = val if isinstance(val, list) else [val]
                segment.update(c for c in codes if c)
        return sorted(segment)

    def get_h1_activities(self, organisation: str, **filters) -> List[Dict[str, Any]]:
        """Get H1 (programme) activities."""
        return self.get_activities(organisation, hierarchy=1, **filters)

    def get_h2_activities(self, organisation: str, **filters) -> List[Dict[str, Any]]:
        """Get H2 (project) activities."""
        return self.get_activities(organisation, hierarchy=2, **filters)


# Global Solr client instance
solr_client = SolrClient()
