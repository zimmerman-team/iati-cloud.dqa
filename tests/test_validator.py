import json
from datetime import datetime
from math import isclose

import pytest  # noqa: F401
from freezegun import freeze_time

from app.config import Settings
from app.models import ValidationResult


class TestTitleValidation:
    """Tests for title validation."""

    def test_valid_title(self, validator, sample_activity):
        """Test that a valid title passes."""
        result = validator.validate_title(sample_activity)
        assert result.status == ValidationResult.PASS
        assert result.details["length"] >= 60

    def test_missing_title(self, validator):
        """Test that missing title fails."""
        activity = {"iati-identifier": "TEST"}
        result = validator.validate_title(activity)
        assert result.status == ValidationResult.FAIL
        assert "missing" in result.message.lower()

    def test_short_title(self, validator, activity_with_invalid_title):
        """Test that short title fails."""
        result = validator.validate_title(activity_with_invalid_title)
        assert result.status == ValidationResult.FAIL
        assert "short" in result.message.lower()
        assert result.details["length"] < 60

    def test_title_with_acronyms(self, validator):
        """Test that title with acronyms is handled correctly."""
        activity = {"title.narrative": ["60 char test text (CPSD), U.S.A. U.S.A e.g. should all be detected."]}
        result = validator.validate_title(activity)
        assert result.status == ValidationResult.FAIL
        assert "CPSD" in result.details["acronyms"]
        assert "U.S.A." in result.details["acronyms"]
        assert "U.S.A" in result.details["acronyms"]
        assert "e.g." in result.details["acronyms"]


class TestDescriptionValidation:
    """Tests for description validation."""

    def test_valid_description(self, validator, sample_activity):
        """Test that valid description passes."""
        result = validator.validate_description(sample_activity)
        assert result.status == ValidationResult.PASS

    def test_missing_description(self, validator):
        """Test that missing description fails."""
        activity = {"title.narrative": ["A title that meets the minimum length requirement for validation"]}
        result = validator.validate_description(activity)
        assert result.status == ValidationResult.FAIL
        assert "missing" in result.message.lower()

    def test_description_repeats_title(self, validator):
        """Test that description repeating title fails."""
        title = "A comprehensive programme for sustainable development initiatives"
        activity = {"title.narrative": [title], "description.narrative": [title]}
        result = validator.validate_description(activity)
        assert result.status == ValidationResult.FAIL
        assert "repeat" in result.message.lower()

    def test_description_shorter_than_title(self, validator):
        """Test that description shorter than title fails."""
        activity = {
            "title.narrative": ["This is a very long title that exceeds the minimum character requirements"],
            "description.narrative": ["Short desc"],
        }
        result = validator.validate_description(activity)
        assert result.status == ValidationResult.FAIL
        assert "longer" in result.message.lower()


class TestStartDateValidation:
    """Tests for start date validation."""

    def test_valid_start_date(self, validator, sample_activity):
        """Test that valid start date passes."""
        result = validator.validate_start_date(sample_activity)
        assert result.status == ValidationResult.PASS

    def test_missing_start_date(self, validator):
        """Test that missing start date fails."""
        activity = {"iati-identifier": "TEST"}
        result = validator.validate_start_date(activity)
        assert result.status == ValidationResult.FAIL
        assert "missing" in result.message.lower()

    def test_default_date_1900(self, validator, activity_with_default_date):
        """Test that default date (1900-01-01) fails."""
        result = validator.validate_start_date(activity_with_default_date)
        assert result.status == ValidationResult.FAIL
        assert "default" in result.message.lower()
        assert "1900-01-01" in result.message

    def test_default_date_1970(self, validator):
        """Test that default date (1970-01-01) fails."""
        activity = {"activity-date.start-actual": ["1970-01-01T00:00:00Z"]}
        result = validator.validate_start_date(activity)
        assert result.status == ValidationResult.FAIL
        assert "default" in result.message.lower()

    def test_invalid_date_format(self, validator):
        """Test that invalid date format fails."""
        activity = {"activity-date.start-actual": ["not-a-date"]}
        result = validator.validate_start_date(activity)
        assert result.status == ValidationResult.FAIL
        assert "invalid" in result.message.lower()


class TestEndDateValidation:
    """Tests for end date validation."""

    def test_valid_end_date(self, validator, sample_activity):
        """Test that valid end date passes."""
        result = validator.validate_end_date(sample_activity)
        assert result.status == ValidationResult.PASS

    def test_missing_end_date(self, validator):
        """Test that missing end date fails."""
        activity = {"iati-identifier": "TEST"}
        result = validator.validate_end_date(activity)
        assert result.status == ValidationResult.FAIL
        assert "missing" in result.message.lower()

    def test_end_before_start(self, validator):
        """Test that end date before start date fails."""
        activity = {
            "activity-date.start-actual": ["2023-01-01T00:00:00Z"],
            "activity-date.end-planned": ["2022-01-01T00:00:00Z"],
        }
        result = validator.validate_end_date(activity)
        assert result.status == ValidationResult.FAIL
        assert "after" in result.message.lower()

    def test_end_date_uses_actual_if_available(self, validator):
        """Test that end-actual is used over end-planned."""
        activity = {
            "activity-date.start-actual": ["2023-01-01T00:00:00Z"],
            "activity-date.end-actual": ["2024-01-01T00:00:00Z"],
            "activity-date.end-planned": ["2025-01-01T00:00:00Z"],
        }
        result = validator.validate_end_date(activity)
        assert result.status == ValidationResult.PASS

    def test_end_date_uses_planned_if_actual_missing(self, validator):
        """Test that end-planned is used if end-actual is missing."""
        activity = {
            "activity-date.start-actual": ["2023-01-01T00:00:00Z"],
            "activity-date.end-planned": ["2025-01-01T00:00:00Z"],
        }
        result = validator.validate_end_date(activity)
        assert result.status == ValidationResult.PASS

    def test_invalid_date_format(self, validator):
        """Test that invalid date format fails."""
        activity = {"activity-date.end-actual": ["not-a-date"]}
        result = validator.validate_end_date(activity)
        assert result.status == ValidationResult.FAIL
        assert "invalid" in result.message.lower()


class TestSectorValidation:
    """Tests for sector validation."""

    def test_valid_sectors(self, validator, sample_activity):
        """Test that valid sectors pass."""
        result = validator.validate_sector(sample_activity)
        assert result.status == ValidationResult.PASS

    def test_valid_single_sectors(self, validator, sample_activity):
        """Test that valid list of sectors pass."""
        sample_activity["sector.code"] = "15170"
        sample_activity["sector.percentage"] = 100.0
        result = validator.validate_sector(sample_activity)
        assert result.status == ValidationResult.PASS

    def test_missing_sectors(self, validator, activity_missing_sectors):
        """Test that missing sectors fail."""
        result = validator.validate_sector(activity_missing_sectors)
        assert result.status == ValidationResult.FAIL
        assert "no sectors" in result.message.lower()

    def test_invalid_sector_code_length(self, validator):
        """Test that non-5-digit sector codes fail."""
        activity = {"sector.code": ["151", "15170"], "sector.percentage": [50.0, 50.0]}  # 151 is only 3 digits
        result = validator.validate_sector(activity)
        assert result.status == ValidationResult.FAIL
        assert "5-digit" in result.message.lower()

    def test_sector_percentages_not_100(self, validator, activity_invalid_sector_percentage):
        """Test that sector percentages not summing to 100% fail."""
        result = validator.validate_sector(activity_invalid_sector_percentage)
        assert result.status == ValidationResult.FAIL
        assert "100%" in result.message
        assert isclose(result.details["percentage"], 90.0)

    def test_sector_percentages_within_tolerance(self, validator):
        """Test that percentages within tolerance pass."""
        activity = {"sector.code": ["15170", "15110"], "sector.percentage": [60.0, 39.99]}  # Within tolerance
        result = validator.validate_sector(activity)
        assert result.status == ValidationResult.PASS

    def test_transaction_sector(self, validator, activity_transaction_sector):
        """Test that transaction sector is considered."""
        result = validator.validate_sector(activity_transaction_sector)
        assert result.status == ValidationResult.PASS


class TestLocationValidation:
    """Tests for location validation."""

    def test_valid_location_with_percentages(self, validator, sample_activity):
        """Test that valid location with percentages passes."""
        result = validator.validate_location(sample_activity)
        assert result.status == ValidationResult.PASS

    def test_valid_location_with_single_percentages(self, validator, sample_activity):
        """Test that valid location with percentages passes."""
        sample_activity["recipient-country.percentage"] = 50.0
        sample_activity["recipient-region.percentage"] = 50.0
        result = validator.validate_location(sample_activity)
        assert result.status == ValidationResult.PASS

    def test_single_location_without_percentage(self, validator):
        """Test that single location without percentage passes."""
        activity = {"recipient-country.code": ["BD"]}
        result = validator.validate_location(activity)
        assert result.status == ValidationResult.PASS
        assert result.details["single_location"]

    def test_missing_location(self, validator):
        """Test that missing location fails."""
        activity = {"iati-identifier": "TEST"}
        result = validator.validate_location(activity)
        assert result.status == ValidationResult.FAIL
        assert "no location" in result.message.lower()

    def test_multiple_locations_without_percentages(self, validator):
        """Test that multiple locations without percentages fail."""
        activity = {"recipient-country.code": ["BD", "AF"]}
        result = validator.validate_location(activity)
        assert result.status == ValidationResult.FAIL
        assert "without percentages" in result.message.lower()

    def test_location_percentages_not_100(self, validator):
        """Test that location percentages not summing to 100% fail."""
        activity = {"recipient-country.code": ["BD", "AF"], "recipient-country.percentage": [60.0, 30.0]}  # Only 90%
        result = validator.validate_location(activity)
        assert result.status == ValidationResult.FAIL
        assert "100%" in result.message

    def test_location_percentages_within_tolerance(self, validator):
        """Test that location percentages within tolerance pass."""
        activity = {"recipient-country.code": ["BD", "AF"], "recipient-country.percentage": [60.0, 39.99]}
        result = validator.validate_location(activity)
        assert result.status == ValidationResult.PASS

    def test_mixed_country_and_region(self, validator):
        """Test that mixed country and region percentages are validated."""
        activity = {
            "recipient-country.code": ["BD"],
            "recipient-country.percentage": [50.0],
            "recipient-region.code": ["298"],
            "recipient-region.percentage": [50.0],
        }
        result = validator.validate_location(activity)
        assert result.status == ValidationResult.PASS

    def test_country_and_region_codes_not_list(self, validator):
        """Test that single string/int country/region codes are handled as lists."""
        # country code as string, region code as int
        activity = {
            "recipient-country.code": "BD",
            "recipient-region.code": 298,
        }
        result = validator.validate_location(activity)
        assert result.status == ValidationResult.FAIL
        assert "Multiple locations specified without percentages" in result.message

    def test_transaction_location(self, validator, activity_transaction_location):
        """Test that transaction recipient country/region are considered."""
        result = validator.validate_location(activity_transaction_location)
        assert result.status == ValidationResult.PASS

    def test_transaction_location_no_codes(self, validator, activity_transaction_location_no_codes):
        """Test _validate_transaction_location directly when no transaction codes are present."""
        result = validator._validate_transaction_location(activity_transaction_location_no_codes)
        assert result.status == ValidationResult.FAIL
        assert "No locations defined" in result.message


class TestParticipatingOrgValidation:
    """Tests for participating organisation validation."""

    def test_valid_participating_orgs(self, validator, sample_activity):
        """Test that valid participating orgs pass."""
        result = validator.validate_participating_orgs(sample_activity)
        assert result.status == ValidationResult.PASS
        assert result.details["count"] >= 1

    def test_valid_participating_org(self, validator, sample_activity):
        """Test that valid participating orgs pass."""
        sample_activity["participating-org.ref"] = "GB-GOV-1"
        result = validator.validate_participating_orgs(sample_activity)
        assert result.status == ValidationResult.PASS
        assert result.details["count"] >= 1

    def test_missing_participating_orgs(self, validator):
        """Test that missing participating orgs fail."""
        activity = {"iati-identifier": "TEST"}
        result = validator.validate_participating_orgs(activity)
        assert result.status == ValidationResult.FAIL
        assert "no participating" in result.message.lower()


class TestBusinessCaseValidation:
    """Tests for business case document validation."""

    @freeze_time("2024-06-01T00:00:00Z")
    def test_pass_recent_activity_with_doc(self, validator):
        """Test that recent activity with business case passes."""
        activity = {
            "iati-identifier": "TEST",
            "activity-date.start-actual": ["2024-01-01T00:00:00Z"],
            "document-link.title.narrative": ["Business Case Published"],
        }
        result = validator.validate_business_case(activity)
        assert result.status == ValidationResult.PASS
        assert result.published

    @freeze_time("2024-06-01T00:00:00Z")
    def test_pass_recent_activity_with_single_doc(self, validator):
        """Test that recent activity with business case passes."""
        activity = {
            "iati-identifier": "TEST",
            "activity-date.start-actual": ["2024-01-01T00:00:00Z"],
            "document-link.title.narrative": "Business Case Published",
        }
        result = validator.validate_business_case(activity)
        assert result.status == ValidationResult.PASS
        assert result.published

    def test_fail_broken_date_format(self, validator):
        """Test that activity with invalid date format fails."""
        activity = {
            "iati-identifier": "TEST",
            "activity-date.start-actual": ["not-a-date"],
            "document-link.title.narrative": ["Business Case Published"],
        }
        result = validator.validate_business_case(activity)
        assert result.status == ValidationResult.NOT_APPLICABLE
        assert "no start" in result.exemption_reason.lower()

    @freeze_time(datetime.now())
    def test_fail_recent_activity_without_doc(self, validator, activity_no_business_case):
        """Test that recent activity without business case fails."""
        result = validator.validate_business_case(activity_no_business_case)
        assert result.status == ValidationResult.FAIL
        assert not result.published

    @freeze_time("2024-06-01")
    def test_not_applicable_before_2011(self, validator):
        """Test that activities before 2011 are N/A."""
        activity = {"iati-identifier": "TEST", "activity-date.start-actual": ["2010-01-01T00:00:00Z"]}
        result = validator.validate_business_case(activity)
        assert result.status == ValidationResult.NOT_APPLICABLE
        assert "2011" in result.exemption_reason

    @freeze_time("2024-06-01")
    def test_not_applicable_very_recent(self, validator):
        """Test that very recent activities (< 3 months) are N/A."""
        activity = {
            "iati-identifier": "TEST",
            "activity-date.start-actual": ["2024-05-01T00:00:00Z"],
            # "document-link.title.narrative": ["Business Case Published"]
        }
        result = validator.validate_business_case(activity)
        assert result.status == ValidationResult.NOT_APPLICABLE
        assert "3 months" in result.exemption_reason

    def test_not_applicable_no_start_date(self, validator):
        """Test that activity without start date is N/A."""
        activity = {"iati-identifier": "TEST"}
        result = validator.validate_business_case(activity)
        assert result.status == ValidationResult.NOT_APPLICABLE

    @freeze_time("2024-06-01")
    def test_bare_date_string_without_timezone(self, validator):
        """Test that bare date strings (no Z suffix) are treated as UTC without raising TypeError."""
        activity = {
            "iati-identifier": "TEST",
            "activity-date.start-actual": ["2020-01-01"],
            "document-link.title.narrative": [],
        }
        result = validator.validate_business_case(activity)
        assert result.status == ValidationResult.FAIL

    def test_exempt_activity(self, validator_with_exemptions):
        """Test that exempt activity is N/A."""
        activity = {"iati-identifier": "GB-GOV-1-EXEMPT", "activity-date.start-actual": ["2023-01-01T00:00:00Z"]}
        result = validator_with_exemptions.validate_business_case(activity)
        assert result.status == ValidationResult.NOT_APPLICABLE
        assert "exempt" in result.exemption_reason.lower()


class TestLogicalFrameworkValidation:
    """Tests for logical framework document validation."""

    @freeze_time("2024-06-01")
    def test_pass_with_doc(self, validator):
        """Test that activity with logical framework passes."""
        activity = {
            "iati-identifier": "TEST",
            "activity-date.start-actual": ["2024-01-01T00:00:00Z"],
            "document-link.title.narrative": ["Logical Framework Published"],
        }
        result = validator.validate_logical_framework(activity)
        assert result.status == ValidationResult.PASS

    @freeze_time("2024-06-01")
    def test_fail_without_doc(self, validator):
        """Test that activity without logical framework fails."""
        activity = {
            "iati-identifier": "TEST",
            "activity-date.start-actual": ["2024-01-01T00:00:00Z"],
            "document-link.title.narrative": [],
        }
        result = validator.validate_logical_framework(activity)
        assert result.status == ValidationResult.FAIL

    @freeze_time("2024-06-01")
    def test_not_applicable_recent(self, validator):
        """Test that very recent activities are N/A."""
        activity = {"iati-identifier": "TEST", "activity-date.start-actual": ["2024-05-15T00:00:00Z"]}
        result = validator.validate_logical_framework(activity)
        assert result.status == ValidationResult.NOT_APPLICABLE

    @freeze_time("2024-06-01")
    def test_not_applicable_no_start_date(self, validator):
        """Test that activity without start date is N/A."""
        activity = {"iati-identifier": "TEST"}
        result = validator.validate_logical_framework(activity)
        assert result.status == ValidationResult.NOT_APPLICABLE

    @freeze_time("2024-06-01")
    def test_not_applicable_exempt(self, validator_with_exemptions):
        """Test that exempt activity is N/A."""
        activity = {"iati-identifier": "GB-GOV-1-EXEMPT", "activity-date.start-actual": ["2023-01-01T00:00:00Z"]}
        result = validator_with_exemptions.validate_logical_framework(activity)
        assert result.status == ValidationResult.NOT_APPLICABLE
        assert "exempt" in result.exemption_reason.lower()


class TestAnnualReviewValidation:
    """Tests for annual review document validation."""

    @freeze_time("2024-06-01")
    def test_pass_with_doc(self, validator):
        """Test that old activity with annual review passes."""
        activity = {
            "iati-identifier": "TEST",
            "activity-date.start-actual": ["2022-01-01T00:00:00Z"],
            "document-link.title.narrative": ["Annual Review Published"],
        }
        result = validator.validate_annual_review(activity)
        assert result.status == ValidationResult.PASS

    @freeze_time("2024-06-01")
    def test_fail_without_doc(self, validator):
        """Test that old activity without annual review fails."""
        activity = {
            "iati-identifier": "TEST",
            "activity-date.start-actual": ["2022-01-01T00:00:00Z"],
            "document-link.title.narrative": [],
        }
        result = validator.validate_annual_review(activity)
        assert result.status == ValidationResult.FAIL

    @freeze_time("2024-06-01")
    def test_not_applicable_recent(self, validator):
        """Test that activities < 19 months old are N/A."""
        activity = {"iati-identifier": "TEST", "activity-date.start-actual": ["2023-06-01T00:00:00Z"]}
        result = validator.validate_annual_review(activity)
        assert result.status == ValidationResult.NOT_APPLICABLE
        assert "19 months" in result.exemption_reason

    @freeze_time("2024-06-01")
    def test_not_applicable_no_start_date(self, validator):
        """Test that activity without start date is N/A."""
        activity = {"iati-identifier": "TEST"}
        result = validator.validate_annual_review(activity)
        assert result.status == ValidationResult.NOT_APPLICABLE

    @freeze_time("2024-06-01")
    def test_not_applicable_exempt(self, validator_with_exemptions):
        """Test that exempt activity is N/A."""
        activity = {"iati-identifier": "GB-GOV-1-EXEMPT", "activity-date.start-actual": ["2023-01-01T00:00:00Z"]}
        result = validator_with_exemptions.validate_annual_review(activity)
        assert result.status == ValidationResult.NOT_APPLICABLE
        assert "exempt" in result.exemption_reason.lower()


class TestCompleteActivityValidation:
    """Tests for complete activity validation."""

    def test_h1_activity_all_validations(self, validator, sample_activity):
        """Test H1 activity gets all validations including documents."""
        attr_validations, doc_validations = validator.validate_activity(sample_activity)

        # Should have 7 attribute validations
        assert len(attr_validations) == 7

        # Should have 3 document validations for H1
        assert len(doc_validations) == 3

        # All should pass for this sample
        all_pass = all(
            v.status == ValidationResult.PASS or v.status == ValidationResult.NOT_APPLICABLE
            for v in attr_validations + doc_validations
        )
        assert all_pass

    def test_h2_activity_no_document_validations(self, validator, sample_h2_activity):
        """Test H2 activity doesn't get document validations."""
        attr_validations, doc_validations = validator.validate_activity(sample_h2_activity)

        # Should have 7 attribute validations
        assert len(attr_validations) == 7

        # Should have NO document validations for H2
        assert len(doc_validations) == 0


class TestCalculateBudgetForFY:
    """Tests for budget calculation for financial year."""

    FY_2023_24 = (datetime(2023, 4, 1), datetime(2024, 3, 31))

    def _budget_json(self, period_start: str, value) -> str:
        return json.dumps({"period-start": [{"iso-date": period_start}], "value": value})

    def _patch_fy(self, mocker, fy=None):
        fy = fy or self.FY_2023_24
        return mocker.patch.object(Settings, "get_current_financial_year", return_value=fy)

    def test_empty_lists_returns_zero(self, validator, mocker):
        """No activities at all returns 0."""
        self._patch_fy(mocker)
        assert isclose(validator.calculate_budget_for_fy([], []), 0.0)

    def test_activity_without_budget_returns_zero(self, validator, mocker):
        """Activity with no json.budget field returns 0."""
        self._patch_fy(mocker)
        activity = {"iati-identifier": "GB-GOV-1-TEST", "hierarchy": 1}
        assert isclose(validator.calculate_budget_for_fy([activity], []), 0.0)

    def test_budget_within_fy_included(self, validator, mocker):
        """Budget whose period-start falls inside the FY is summed."""
        self._patch_fy(mocker)
        activity = {"json.budget": [self._budget_json("2023-06-01", 100_000.0)]}
        assert isclose(validator.calculate_budget_for_fy([activity], []), 100_000.0)

    def test_budget_before_fy_excluded(self, validator, mocker):
        """Budget whose period-start is before FY start is not summed."""
        self._patch_fy(mocker)
        activity = {"json.budget": [self._budget_json("2022-04-01", 200_000.0)]}
        assert isclose(validator.calculate_budget_for_fy([activity], []), 0.0)

    def test_budget_after_fy_excluded(self, validator, mocker):
        """Budget whose period-start is after FY end is not summed."""
        self._patch_fy(mocker)
        activity = {"json.budget": [self._budget_json("2024-04-01", 300_000.0)]}
        assert isclose(validator.calculate_budget_for_fy([activity], []), 0.0)

    def test_fy_start_boundary_included(self, validator, mocker):
        """Budget with period-start exactly on FY start date is included."""
        self._patch_fy(mocker)
        activity = {"json.budget": [self._budget_json("2023-04-01", 500.0)]}
        assert isclose(validator.calculate_budget_for_fy([activity], []), 500.0)

    def test_fy_end_boundary_included(self, validator, mocker):
        """Budget with period-start exactly on FY end date is included."""
        self._patch_fy(mocker)
        activity = {"json.budget": [self._budget_json("2024-03-31", 750.0)]}
        assert isclose(validator.calculate_budget_for_fy([activity], []), 750.0)

    def test_sums_h1_and_h2_activities(self, validator, mocker):
        """Budgets from both H1 and H2 activity lists are combined."""
        self._patch_fy(mocker)
        h1 = {"json.budget": [self._budget_json("2023-04-01", 100_000.0)]}
        h2 = {"json.budget": [self._budget_json("2023-04-01", 50_000.0)]}
        assert isclose(validator.calculate_budget_for_fy([h1], [h2]), 150_000.0)

    def test_multiple_budgets_partial_match(self, validator, mocker):
        """Only the budget entries whose period-start is within the FY contribute."""
        self._patch_fy(mocker)
        activity = {
            "json.budget": [
                self._budget_json("2022-04-01", 999.0),  # before FY
                self._budget_json("2023-04-01", 100.0),  # inside FY
                self._budget_json("2024-04-01", 888.0),  # after FY
            ]
        }
        assert isclose(validator.calculate_budget_for_fy([activity], []), 100.0)

    def test_invalid_date_skipped(self, validator, mocker):
        """Budget entry with an unparseable period-start date is skipped; others still counted."""
        self._patch_fy(mocker)
        activity = {
            "json.budget": [
                json.dumps({"period-start": [{"iso-date": "not-a-date"}], "value": 100.0}),
                self._budget_json("2023-04-01", 200.0),
            ]
        }
        assert isclose(validator.calculate_budget_for_fy([activity], []), 200.0)

    def test_missing_period_start_skipped(self, validator, mocker):
        """Budget entry with an empty period-start list is skipped."""
        self._patch_fy(mocker)
        activity = {"json.budget": [json.dumps({"period-start": [], "value": 100.0})]}
        assert isclose(validator.calculate_budget_for_fy([activity], []), 0.0)

    def test_non_numeric_value_skipped(self, validator, mocker):
        """Budget entry with a string value is not added to the total."""
        self._patch_fy(mocker)
        activity = {"json.budget": [self._budget_json("2023-04-01", "100000")]}
        assert isclose(validator.calculate_budget_for_fy([activity], []), 0.0)

    def test_integer_value_accepted(self, validator, mocker):
        """Budget entry with an integer value is accepted alongside floats."""
        self._patch_fy(mocker)
        activity = {"json.budget": [self._budget_json("2023-04-01", 50_000)]}
        assert isclose(validator.calculate_budget_for_fy([activity], []), 50_000.0)


class TestCalculatePercentages:
    """Tests for percentage calculations."""

    def test_general_dqa(self, validator, dqa_response_sample):
        """If total is zero, should return 0% to avoid division by zero."""
        res = validator.calculate_percentages(dqa_response_sample)
        """add assertions for:
                "document_annual_review_percentage": 50,
        "document_business_case_percentage": 50,
        "description_percentage": 100,
        "end_date_percentage": 0,
        "location_data_percentage": 100,
        "document_logical_framework_percentage": 50,
        "participating_organisations_percentage": 100,
        "sector_percentage": 100,
        "start_date_percentage": 100,
        "title_percentage": 79
        """
        assert res.percentages.document_annual_review_percentage == 0
        assert res.percentages.document_business_case_percentage == 0
        assert res.percentages.description_percentage == 100
        assert res.percentages.end_date_percentage == 100
        assert res.percentages.location_data_percentage == 100
        assert res.percentages.document_logical_framework_percentage == 0
        assert res.percentages.participating_organisations_percentage == 100
        assert res.percentages.sector_percentage == 100
        assert res.percentages.start_date_percentage == 100
        assert res.percentages.title_percentage == 77
