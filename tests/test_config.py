from math import isclose

import pytest  # noqa: F401
from freezegun import freeze_time

from app.config import Settings


class TestSettings:
    """Tests for Settings class."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = Settings()

        assert settings.cache_ttl == 86400
        assert settings.business_case_exemption_months == 3
        assert settings.logical_framework_exemption_months == 3
        assert settings.annual_review_exemption_months == 19
        assert isclose(settings.sector_tolerance, 0.02, rel_tol=1e-9)
        assert isclose(settings.location_tolerance, 0.02, rel_tol=1e-9)

    def test_custom_settings(self):
        """Test custom settings values."""
        settings = Settings(cache_ttl=3600, business_case_exemption_months=6, sector_tolerance=0.001)

        assert settings.cache_ttl == 3600
        assert settings.business_case_exemption_months == 6
        assert isclose(settings.sector_tolerance, 0.001, rel_tol=1e-9)

    def test_get_default_dates(self):
        """Test parsing default dates."""
        settings = Settings(default_dates="1900-01-01,1970-01-01")
        dates = settings.get_default_dates()

        assert len(dates) == 2
        assert dates[0].year == 1900
        assert dates[1].year == 1970

    def test_get_default_dates_invalid(self):
        """Test parsing with invalid dates."""
        settings = Settings(default_dates="1900-01-01,invalid-date")
        dates = settings.get_default_dates()

        # Should skip invalid dates
        assert len(dates) == 1
        assert dates[0].year == 1900

    @freeze_time("2024-06-15")
    def test_get_current_financial_year_after_april(self):
        """Test financial year when current month is after April."""
        settings = Settings(financial_year_start_month=4)
        start, end = settings.get_current_financial_year()

        # June 2024 -> FY 2024-2025
        assert start.year == 2024
        assert start.month == 4
        assert start.day == 1
        assert end.year == 2025
        assert end.month == 3
        assert end.day == 31

    @freeze_time("2024-02-15")
    def test_get_current_financial_year_before_april(self):
        """Test financial year when current month is before April."""
        settings = Settings(financial_year_start_month=4)
        start, end = settings.get_current_financial_year()

        # February 2024 -> FY 2023-2024
        assert start.year == 2023
        assert start.month == 4
        assert start.day == 1
        assert end.year == 2024
        assert end.month == 3
        assert end.day == 31

    @freeze_time("2024-04-01")
    def test_get_current_financial_year_on_april_1(self):
        """Test financial year on April 1."""
        settings = Settings(financial_year_start_month=4)
        start, end = settings.get_current_financial_year()

        # April 1, 2024 -> FY 2024-2025
        assert start.year == 2024
        assert start.month == 4
        assert start.day == 1
        assert end.year == 2025
        assert end.month == 3
        assert end.day == 31
