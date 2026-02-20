import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.config import DATA_DIR, settings
from app.models import (ActivityValidationResult, AttributeValidation,
                        DocumentValidation, DQAPercentages, DQAResponse,
                        ValidationResult)

EXEMPTION_REASON_NO_START_DATE = "No start date available"
EXEMPTION_REASON_EXEMPT = "Activity is exempt from document requirements"
AD_START_ACTUAL = "activity-date.start-actual"

logger = logging.getLogger("app.validator")


class ActivityValidator:
    """Validates IATI activities against DQA requirements."""

    def __init__(self, exemptions: Optional[List[str]] = None):
        """
        Initialize validator.

        Args:
            exemptions: List of IATI identifiers that are exempt from document checks
        """
        self.exemptions = exemptions or []
        self.default_dates = settings.get_default_dates()
        with open(os.path.join(DATA_DIR, "non_acronyms.json")) as f:
            self._non_acronyms = json.load(f)

    def validate_activity(self, activity: Dict[str, Any]) -> tuple[List[AttributeValidation], List[DocumentValidation]]:
        """
        Validate a single activity.

        Returns:
            Tuple of (attribute_validations, document_validations)
        """
        logger.debug(f"Validating activity: {activity.get('iati-identifier', 'unknown')}")
        attr_validations = []
        doc_validations = []

        # Get hierarchy to determine which validations apply
        hierarchy = activity.get("hierarchy", 2)

        # Validate attributes (apply to both H1 and H2)
        attr_validations.append(self.validate_title(activity))
        attr_validations.append(self.validate_description(activity))
        attr_validations.append(self.validate_start_date(activity))
        attr_validations.append(self.validate_end_date(activity))
        attr_validations.append(self.validate_sector(activity))
        attr_validations.append(self.validate_location(activity))
        attr_validations.append(self.validate_participating_orgs(activity))

        # Document validations only apply to H1 activities
        if hierarchy == 1:
            doc_validations.append(self.validate_business_case(activity))
            doc_validations.append(self.validate_logical_framework(activity))
            doc_validations.append(self.validate_annual_review(activity))

        return attr_validations, doc_validations

    def _find_acronyms(self, text: str) -> List[str]:
        """Return a list of acronyms found in *text*.
        Regex logic:
        - Look for sequences of uppercase letters that are 2-5 characters long (common acronym lengths)
        - Also include patterns like "U.N." or "E.U." where letters are separated by periods, optional trailing period
        """
        raw = re.findall(r"(?<!\w)(?:[A-Z]{2,}|[A-Za-z](?:\.[A-Za-z])+\.?)(?!\w)", text)
        if not raw:
            return []
        return [a for a in raw if a not in self._non_acronyms]

    def validate_title(self, activity: Dict[str, Any]) -> AttributeValidation:
        """Validate title exists, has expanded acronyms, and minimum 60 characters."""
        logger.debug(f"Validating title for activity: {activity.get('iati-identifier', 'unknown')}")
        title = activity.get("title.narrative")

        if not title:
            return AttributeValidation(
                attribute="title", status=ValidationResult.FAIL, message="Title is missing", details={"percentage": 0.0}
            )

        # Get first narrative if it's a list
        if isinstance(title, list):
            title = title[0] if title else ""

        if len(title) < 60:
            return AttributeValidation(
                attribute="title",
                status=ValidationResult.FAIL,
                message=f"Title is too short ({len(title)} characters, minimum 60 required)",
                details={"length": len(title), "title": title, "percentage": len(title) / 60.0 * 100},
            )

        # This is a simple heuristic for detecting acronyms - all uppercase words of 2-5 letters
        found_acronyms = self._find_acronyms(title)
        if found_acronyms:
            len_acronyms = sum(len(a) for a in found_acronyms)
            return AttributeValidation(
                attribute="title",
                status=ValidationResult.FAIL,
                message=f"Title contains potential acronyms that should be expanded: {', '.join(found_acronyms)}",
                details={"acronyms": found_acronyms, "percentage": (1 - len_acronyms / len(title)) * 100},
            )

        return AttributeValidation(
            attribute="title", status=ValidationResult.PASS, details={"length": len(title), "percentage": 100.0}
        )

    def validate_description(self, activity: Dict[str, Any]) -> AttributeValidation:
        """Validate description is longer than title and not a repeat."""
        logger.debug(f"Validating description for activity: {activity.get('iati-identifier', 'unknown')}")
        title = activity.get("title.narrative", "")
        description = activity.get("description.narrative", "")

        # Handle lists
        if isinstance(title, list):
            title = title[0] if title else ""
        if isinstance(description, list):
            description = description[0] if description else ""

        if not description:
            return AttributeValidation(
                attribute="description",
                status=ValidationResult.FAIL,
                message="Description is missing",
                details={"percentage": 0.0},
            )

        # Check if description is just a repeat of title
        # Before length check, as a short description that repeats the title is still not valid but with a clear hint
        if description.strip().lower() == title.strip().lower():
            return AttributeValidation(
                attribute="description",
                status=ValidationResult.FAIL,
                message="Description is a repeat of the title",
                details={"percentage": 0.0},
            )

        if len(description) <= len(title):
            return AttributeValidation(
                attribute="description",
                status=ValidationResult.FAIL,
                message="Description must be longer than title",
                details={
                    "desc_length": len(description),
                    "title_length": len(title),
                    "percentage": len(description) / len(title) * 100 if len(title) > 0 else 0.0,
                },
            )

        return AttributeValidation(
            attribute="description",
            status=ValidationResult.PASS,
            details={"length": len(description), "percentage": 100.0},
        )

    def validate_start_date(self, activity: Dict[str, Any]) -> AttributeValidation:
        """Validate start date exists and is not a default system date."""
        logger.debug(f"Validating start date for activity: {activity.get('iati-identifier', 'unknown')}")
        start_date_str = activity.get(AD_START_ACTUAL)

        if not start_date_str:
            return AttributeValidation(
                attribute="start_date",
                status=ValidationResult.FAIL,
                message="Start date is missing",
                details={"percentage": 0.0},
            )

        # Handle list of dates
        if isinstance(start_date_str, list):
            start_date_str = start_date_str[0] if start_date_str else None

        try:
            start_date = datetime.fromisoformat(self._update_date_str(start_date_str))

            # Check against default dates
            for default_date in self.default_dates:
                if start_date.date() == default_date.date():
                    return AttributeValidation(
                        attribute="start_date",
                        status=ValidationResult.FAIL,
                        message=f"Start date is a default system date: {start_date.date()}",
                        details={"date": str(start_date.date()), "percentage": 0.0},
                    )

            return AttributeValidation(
                attribute="start_date",
                status=ValidationResult.PASS,
                details={"date": str(start_date.date()), "percentage": 100.0},
            )

        except (ValueError, AttributeError):
            return AttributeValidation(
                attribute="start_date",
                status=ValidationResult.FAIL,
                message=f"Invalid start date format: {start_date_str}",
                details={"percentage": 0.0},
            )

    def validate_end_date(self, activity: Dict[str, Any]) -> AttributeValidation:
        """Validate end date exists and is after start date."""
        logger.debug(f"Validating end date for activity: {activity.get('iati-identifier', 'unknown')}")
        start_date_str = activity.get(AD_START_ACTUAL)
        end_date_str = activity.get("activity-date.end-actual") or activity.get("activity-date.end-planned")

        # Handle lists
        if isinstance(start_date_str, list):
            start_date_str = start_date_str[0] if start_date_str else None
        if isinstance(end_date_str, list):
            end_date_str = end_date_str[0] if end_date_str else None

        if not end_date_str:
            return AttributeValidation(
                attribute="end_date",
                status=ValidationResult.FAIL,
                message="End date is missing",
                details={"percentage": 0.0},
            )

        try:
            end_date = datetime.fromisoformat(self._update_date_str(end_date_str))

            if start_date_str:
                start_date = datetime.fromisoformat(self._update_date_str(start_date_str))
                if end_date <= start_date:
                    return AttributeValidation(
                        attribute="end_date",
                        status=ValidationResult.FAIL,
                        message="End date must be after start date",
                        details={
                            "start_date": str(start_date.date()),
                            "end_date": str(end_date.date()),
                            "percentage": 0.0,
                        },
                    )

            return AttributeValidation(
                attribute="end_date",
                status=ValidationResult.PASS,
                details={"date": str(end_date.date()), "percentage": 100.0},
            )

        except (ValueError, AttributeError):
            return AttributeValidation(
                attribute="end_date",
                status=ValidationResult.FAIL,
                message=f"Invalid end date format: {end_date_str}",
                details={"percentage": 0.0},
            )

    def _validate_transaction_sector_codes(self, activity: Dict[str, Any]) -> AttributeValidation:
        """Validate sector based on transaction-level sectors if no activity-level sectors are defined."""
        transaction_sector_codes = activity.get("transaction.sector.code", [])
        if not isinstance(transaction_sector_codes, list):
            transaction_sector_codes = [transaction_sector_codes] if transaction_sector_codes else []
        if not transaction_sector_codes:
            return AttributeValidation(
                attribute="sector",
                status=ValidationResult.FAIL,
                message="No sectors defined",
                details={"percentage": 0.0},
            )
        else:
            return AttributeValidation(
                attribute="sector",
                status=ValidationResult.PASS,
                message="No activity-level sectors defined, only transaction-level sectors",
                details={"percentage": 100.0},
            )

    def validate_sector(self, activity: Dict[str, Any]) -> AttributeValidation:
        """Validate sectors use 5-digit DAC codes and sum to 100%."""
        logger.debug(f"Validating sector for activity: {activity.get('iati-identifier', 'unknown')}")
        sector_codes = activity.get("sector.code", [])
        sector_percentages = activity.get("sector.percentage", [])

        if not isinstance(sector_codes, list):
            sector_codes = [sector_codes] if sector_codes else []
        if not isinstance(sector_percentages, list):
            sector_percentages = [sector_percentages] if sector_percentages else []

        if not sector_codes:
            return self._validate_transaction_sector_codes(activity)

        # Check for 5-digit codes
        invalid_codes = [code for code in sector_codes if len(str(code)) != 5]
        percentage_invalid_codes = len(invalid_codes) / len(sector_codes) * 100 if sector_codes else 0.0
        if invalid_codes:
            return AttributeValidation(
                attribute="sector",
                status=ValidationResult.FAIL,
                message="All sectors must use 5-digit DAC CRS codes",
                details={"invalid_codes": invalid_codes, "percentage": percentage_invalid_codes},
            )

        # Check percentage sum
        if sector_percentages:
            total_percentage = sum(float(p) for p in sector_percentages if p is not None)
            tolerance = settings.sector_tolerance

            if abs(total_percentage - 100.0) > tolerance:
                return AttributeValidation(
                    attribute="sector",
                    status=ValidationResult.FAIL,
                    message=f"Sector percentages must sum to 100% (got {total_percentage}%)",
                    details={"total": total_percentage, "tolerance": tolerance, "percentage": total_percentage},
                )

        return AttributeValidation(
            attribute="sector", status=ValidationResult.PASS, details={"count": len(sector_codes), "percentage": 100.0}
        )

    def _validate_transaction_location(self, activity: Dict[str, Any]) -> AttributeValidation:
        """Validate location based on transaction-level locations if no activity-level locations are defined."""
        transaction_country_codes = activity.get("transaction.recipient-country.code", [])
        transaction_region_codes = activity.get("transaction.recipient-region.code", [])

        if not isinstance(transaction_country_codes, list):
            transaction_country_codes = [transaction_country_codes] if transaction_country_codes else []
        if not isinstance(transaction_region_codes, list):
            transaction_region_codes = [transaction_region_codes] if transaction_region_codes else []

        if not (transaction_country_codes or transaction_region_codes):
            return AttributeValidation(
                attribute="location",
                status=ValidationResult.FAIL,
                message="No locations defined",
                details={"percentage": 0.0},
            )
        return AttributeValidation(
            attribute="location",
            status=ValidationResult.PASS,
            message="No activity-level locations defined, only transaction-level locations",
            details={"percentage": 100.0},
        )

    def validate_location(self, activity: Dict[str, Any]) -> AttributeValidation:
        """Validate country/region percentages sum to 100%."""
        logger.debug(f"Validating location for activity: {activity.get('iati-identifier', 'unknown')}")
        country_percentages = activity.get("recipient-country.percentage", [])
        region_percentages = activity.get("recipient-region.percentage", [])
        transaction_country_codes = activity.get("transaction.recipient-country.code", [])
        transaction_region_codes = activity.get("transaction.recipient-region.code", [])

        if not isinstance(country_percentages, list):
            country_percentages = [country_percentages] if country_percentages else []
        if not isinstance(region_percentages, list):
            region_percentages = [region_percentages] if region_percentages else []

        # Combine all location percentages
        all_percentages = country_percentages + region_percentages

        if not all_percentages and not (transaction_country_codes or transaction_region_codes):
            return self._handle_location_no_percentages(activity)

        if transaction_country_codes or transaction_region_codes:
            return self._validate_transaction_location(activity)

        # Check percentage sum
        total_percentage = sum(float(p) for p in all_percentages if p is not None)
        tolerance = settings.location_tolerance

        if abs(total_percentage - 100.0) > tolerance:
            return AttributeValidation(
                attribute="location",
                status=ValidationResult.FAIL,
                message=f"Location percentages must sum to 100% (got {total_percentage}%)",
                details={"total": total_percentage, "tolerance": tolerance, "percentage": total_percentage},
            )

        return AttributeValidation(
            attribute="location",
            status=ValidationResult.PASS,
            details={"total": total_percentage, "percentage": total_percentage},
        )

    def validate_participating_orgs(self, activity: Dict[str, Any]) -> AttributeValidation:
        """Validate at least one participating organisation exists."""
        logger.debug(f"Validating participating orgs for activity: {activity.get('iati-identifier', 'unknown')}")
        participating_orgs = activity.get("participating-org.ref", [])

        if not isinstance(participating_orgs, list):
            participating_orgs = [participating_orgs] if participating_orgs else []

        if not participating_orgs or not any(participating_orgs):
            return AttributeValidation(
                attribute="participating_org",
                status=ValidationResult.FAIL,
                message="No participating organisations defined",
                details={"percentage": 0.0},
            )

        return AttributeValidation(
            attribute="participating_org",
            status=ValidationResult.PASS,
            details={"count": len(participating_orgs), "percentage": 100.0},
        )

    def _get_start_date(self, activity: Dict[str, Any]) -> Optional[datetime]:
        """Extract and parse activity start date."""
        start_date_str = activity.get(AD_START_ACTUAL)

        if isinstance(start_date_str, list):
            start_date_str = start_date_str[0] if start_date_str else None

        if not start_date_str:
            return None

        try:
            dt = datetime.fromisoformat(self._update_date_str(start_date_str))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, AttributeError):
            return None

    def _check_document_published(self, activity: Dict[str, Any], pattern: str) -> bool:
        """Check if a document matching the pattern is published."""
        doc_titles = activity.get("document-link.title.narrative", [])

        if not isinstance(doc_titles, list):
            doc_titles = [doc_titles] if doc_titles else []

        regex = re.compile(pattern, re.IGNORECASE)

        for title in doc_titles:
            if title and regex.search(title):
                return True

        return False

    def _is_exempt(self, activity: Dict[str, Any]) -> bool:
        """Check if activity is exempt from document publication requirements."""
        iati_id = activity.get("iati-identifier", "")
        return iati_id in self.exemptions

    def validate_business_case(self, activity: Dict[str, Any]) -> DocumentValidation:
        """
        Validate Business Case publication.

        PASS: (start.actual after 2011-01-01 AND Business Case published) OR Business Case published
        FAIL: start.actual exists AND start.actual <= 3 months ago AND Business Case NOT published
        N/A: No start.actual OR start.actual before 2011-01-01 OR start.actual > 3 months ago OR exempt
        """
        start_date = self._get_start_date(activity)
        published = self._check_document_published(activity, r"Business Case.*Published")
        exempt = self._is_exempt(activity)

        cutoff_date = datetime(2011, 1, 1, tzinfo=timezone.utc)
        three_months_ago = datetime.now(timezone.utc) - timedelta(days=30 * settings.business_case_exemption_months)

        # N/A cases
        if exempt:
            return DocumentValidation(
                document_type="business_case",
                status=ValidationResult.NOT_APPLICABLE,
                exemption_reason=EXEMPTION_REASON_EXEMPT,
                published=published,
            )

        if not start_date:
            return DocumentValidation(
                document_type="business_case",
                status=ValidationResult.NOT_APPLICABLE,
                exemption_reason=EXEMPTION_REASON_NO_START_DATE,
                published=published,
            )

        if start_date < cutoff_date:
            return DocumentValidation(
                document_type="business_case",
                status=ValidationResult.NOT_APPLICABLE,
                exemption_reason="Activity started before 2011-01-01",
                published=published,
            )

        if start_date >= three_months_ago:
            return DocumentValidation(
                document_type="business_case",
                status=ValidationResult.NOT_APPLICABLE,
                exemption_reason=f"Activity started less than {settings.business_case_exemption_months} months ago",
                published=published,
            )

        # PASS or FAIL
        if published:
            return DocumentValidation(document_type="business_case", status=ValidationResult.PASS, published=True)
        return DocumentValidation(
            document_type="business_case",
            status=ValidationResult.FAIL,
            message="Business Case document not published",
            published=False,
        )

    def validate_logical_framework(self, activity: Dict[str, Any]) -> DocumentValidation:
        """
        Validate Logical Framework publication.

        PASS: start.actual <= 3 months ago AND Logical Framework published
        FAIL: start.actual <= 3 months ago AND Logical Framework NOT published
        N/A: No start.actual OR start.actual > 3 months ago OR exempt
        """
        start_date = self._get_start_date(activity)
        published = self._check_document_published(activity, r"Logical Framework.*Published")
        exempt = self._is_exempt(activity)

        three_months_ago = datetime.now(timezone.utc) - timedelta(days=30 * settings.logical_framework_exemption_months)

        # N/A cases
        if exempt:
            return DocumentValidation(
                document_type="logical_framework",
                status=ValidationResult.NOT_APPLICABLE,
                exemption_reason=EXEMPTION_REASON_EXEMPT,
                published=published,
            )

        if not start_date:
            return DocumentValidation(
                document_type="logical_framework",
                status=ValidationResult.NOT_APPLICABLE,
                exemption_reason=EXEMPTION_REASON_NO_START_DATE,
                published=published,
            )

        if start_date >= three_months_ago:
            return DocumentValidation(
                document_type="logical_framework",
                status=ValidationResult.NOT_APPLICABLE,
                exemption_reason=f"Activity started less than {settings.logical_framework_exemption_months} months ago",
                published=published,
            )

        # PASS or FAIL
        if published:
            return DocumentValidation(document_type="logical_framework", status=ValidationResult.PASS, published=True)
        return DocumentValidation(
            document_type="logical_framework",
            status=ValidationResult.FAIL,
            message="Logical Framework document not published",
            published=False,
        )

    def validate_annual_review(self, activity: Dict[str, Any]) -> DocumentValidation:
        """
        Validate Annual Review publication.

        PASS: start.actual >= 19 months ago AND Annual Review published
        FAIL: start.actual >= 19 months ago AND Annual Review NOT published
        N/A: No start.actual OR start.actual < 19 months ago OR exempt
        """
        start_date = self._get_start_date(activity)
        published = self._check_document_published(activity, r"Annual Review.*Published")
        exempt = self._is_exempt(activity)

        nineteen_months_ago = datetime.now(timezone.utc) - timedelta(days=30 * settings.annual_review_exemption_months)

        # N/A cases
        if exempt:
            return DocumentValidation(
                document_type="annual_review",
                status=ValidationResult.NOT_APPLICABLE,
                exemption_reason=EXEMPTION_REASON_EXEMPT,
                published=published,
            )

        if not start_date:
            return DocumentValidation(
                document_type="annual_review",
                status=ValidationResult.NOT_APPLICABLE,
                exemption_reason=EXEMPTION_REASON_NO_START_DATE,
                published=published,
            )

        if start_date > nineteen_months_ago:
            return DocumentValidation(
                document_type="annual_review",
                status=ValidationResult.NOT_APPLICABLE,
                exemption_reason=f"Activity started less than {settings.annual_review_exemption_months} months ago",
                published=published,
            )

        # PASS or FAIL
        if published:
            return DocumentValidation(document_type="annual_review", status=ValidationResult.PASS, published=True)
        return DocumentValidation(
            document_type="annual_review",
            status=ValidationResult.FAIL,
            message="Annual Review document not published",
            published=False,
        )

    def calculate_budget_for_fy(
        self, h1_activities: List[Dict[str, Any]], h2_activities: List[Dict[str, Any]]
    ) -> float:
        """Calculate the total budget for a specific financial year.
        Uses the json.budget dump to be able to accurately select appropriate budgets.

        Args:
            h1_activities (List[Dict[str, Any]]): List of H1 activities.
            h2_activities (List[Dict[str, Any]]): List of H2 activities.

        Returns:
            float: Total budget for the CURRENT financial year.
        """
        fy_start, fy_end = settings.get_current_financial_year()
        all_activities = h1_activities + h2_activities
        total_budget = 0.0
        for activity in all_activities:
            budget_json = activity.get("json.budget", "")
            if not isinstance(budget_json, list):
                budget_json = [budget_json] if budget_json else []
            if not budget_json:
                continue
            for budget in budget_json:
                total_budget = self._process_individual_budget(budget, total_budget, fy_start, fy_end)
        return total_budget

    def _process_individual_budget(self, budget, total_budget, fy_start, fy_end) -> float:
        """Process an individual budget entry and determine if it should be included in the total."""
        budget = json.loads(budget)
        value = budget.get("value", 0.0)
        budget_period_start = budget.get("period-start", [])
        if not budget_period_start:
            return total_budget
        # IATI Rule: Always only one period start date
        start_iso_date = budget_period_start[0].get("iso-date", None)
        # if start_iso_date is within the bounds of fy_start and fy_end, include in total
        if start_iso_date:
            try:
                start_date = datetime.fromisoformat(start_iso_date)
                if fy_start <= start_date <= fy_end:
                    if isinstance(value, (int, float)):
                        total_budget += value
            except ValueError:
                logger.warning(f"Invalid date format in budget: {start_iso_date}")
                return total_budget
        return total_budget

    def calculate_percentages(self, dqa_response: DQAResponse) -> DQAResponse:
        """Calculate percentages for attributes and documents in the DQA response based on the validation results.

        Args:
            dqa_response (DQAResponse): The DQA response object containing percentages of the validation results.
        Returns:
            DQAResponse: The updated DQA response object with calculated percentages.
        """
        n_reports = dqa_response.pass_count + dqa_response.fail_count
        failed_activities = dqa_response.failed_activities
        n_h1 = dqa_response.summary.total_programmes

        dqa_response.percentages = DQAPercentages(
            title_percentage=self._calculate_attribute_percentage(n_reports, failed_activities, "title"),
            description_percentage=self._calculate_attribute_percentage(n_reports, failed_activities, "description"),
            start_date_percentage=self._calculate_attribute_percentage(n_reports, failed_activities, "start_date"),
            end_date_percentage=self._calculate_attribute_percentage(n_reports, failed_activities, "end_date"),
            sector_percentage=self._calculate_attribute_percentage(n_reports, failed_activities, "sector"),
            location_data_percentage=self._calculate_attribute_percentage(n_reports, failed_activities, "location"),
            participating_organisations_percentage=self._calculate_attribute_percentage(
                n_reports, failed_activities, "participating_org"
            ),
            document_business_case_percentage=self._calculate_document_percentage(
                n_h1, failed_activities, "business_case"
            ),
            document_logical_framework_percentage=self._calculate_document_percentage(
                n_h1, failed_activities, "logical_framework"
            ),
            document_annual_review_percentage=self._calculate_document_percentage(
                n_h1, failed_activities, "annual_review"
            ),
        )

        return dqa_response

    def _calculate_attribute_percentage(
        self, n_reports: int, failed_activities: List[ActivityValidationResult], attribute_name: str
    ) -> int:
        """Calculate the percentage of failed activities for a specific attribute."""
        if not failed_activities:
            return 100
        n_success = n_reports - len(failed_activities)
        percentages = [100.0 for _ in range(n_success)]
        for activity in failed_activities:
            for attr in activity.attributes:
                if attr.status == ValidationResult.NOT_APPLICABLE:
                    continue
                if attr.attribute == attribute_name:
                    percentages.append(attr.details.get("percentage", 0.0))

        return round(sum(percentages) / len(percentages) if percentages else 0.0)

    def _calculate_document_percentage(
        self, n_h1: int, failed_activities: List[ActivityValidationResult], document_type: str
    ) -> int:
        """Calculate the percentage of failed h1 activities for a specific document type."""
        n_failed_h1 = 0
        for activity in failed_activities:
            if activity.hierarchy == 1:
                for doc in activity.documents:
                    if doc.document_type == document_type and doc.status == ValidationResult.FAIL:
                        n_failed_h1 += 1
                        break
        n_success = n_h1 - n_failed_h1
        return round((n_success / n_h1) * 100 if n_h1 > 0 else 100.0)

    @staticmethod
    def _update_date_str(date_str: str):
        return date_str.replace("Z", "+00:00")

    @staticmethod
    def _handle_location_no_percentages(activity: Dict[str, Any]) -> AttributeValidation:
        """Handle case where no location percentages are provided."""
        # No percentages specified - this might be okay if there's only one location
        country_codes = activity.get("recipient-country.code", [])
        region_codes = activity.get("recipient-region.code", [])

        if not isinstance(country_codes, list):
            country_codes = [country_codes] if country_codes else []
        if not isinstance(region_codes, list):
            region_codes = [region_codes] if region_codes else []

        total_locations = len(country_codes) + len(region_codes)

        if total_locations == 0:
            return AttributeValidation(
                attribute="location",
                status=ValidationResult.FAIL,
                message="No location (country or region) specified",
                details={"percentage": 0.0},
            )
        elif total_locations == 1:
            # Single location without percentage is acceptable (implies 100%) as per IATI standard.
            return AttributeValidation(
                attribute="location",
                status=ValidationResult.PASS,
                details={"single_location": True, "percentage": 100.0},
            )
        else:
            return AttributeValidation(
                attribute="location",
                status=ValidationResult.FAIL,
                message="Multiple locations specified without percentages",
                details={"percentage": 0.0},
            )
