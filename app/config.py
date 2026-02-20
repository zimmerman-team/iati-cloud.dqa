import calendar
import json
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

logger = logging.getLogger("app.config")


def setup_logging() -> None:
    os.makedirs(_LOG_DIR, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(os.path.join(_LOG_DIR, "dqa.log"), maxBytes=10 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Root at WARNING — library noise (werkzeug, pysolr) stays out unless it's an error
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # All app.* loggers inherit INFO from this parent
    logging.getLogger("app").setLevel(logging.INFO)


def _get_dates() -> str:
    with open(os.path.join(DATA_DIR, "default_dates.json")) as f:
        default_dates: str = ",".join(json.load(f))
    return default_dates


class Settings(BaseSettings):
    """Application settings."""

    # Solr Configuration
    solr_url: str = "http://localhost:8983/solr/activity"

    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl: int = 86400  # 24 hours in seconds

    default_dates: str = Field(default_factory=_get_dates)

    # Time periods (in months)
    business_case_exemption_months: int = 3
    logical_framework_exemption_months: int = 3
    annual_review_exemption_months: int = 19

    # Tolerance for percentage validation
    sector_tolerance: float = 0.02
    location_tolerance: float = 0.02

    # Financial year (April to March)
    financial_year_start_month: int = 4

    # Activity closed within months
    closed_within_months: int = 18

    # API authentication
    secret_key: str = "ZIMMERMAN"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    def get_default_dates(self) -> List[datetime]:
        """Parse default dates from comma-separated string."""
        dates = []
        for date_str in self.default_dates.split(","):
            try:
                dates.append(datetime.fromisoformat(date_str.strip()))
            except ValueError:
                logger.warning(f"Skipping invalid default date: {date_str!r}")
                continue
        return dates

    def get_current_financial_year(self) -> tuple[datetime, datetime]:
        """Get current financial year boundaries (April 1 - March 31)."""
        today = datetime.now()
        end_month = self.financial_year_start_month - 1 or 12
        if today.month >= self.financial_year_start_month:
            # We're in the current financial year
            start = datetime(today.year, self.financial_year_start_month, 1)
            _, last_day = calendar.monthrange(today.year + 1, end_month)
            end = datetime(today.year + 1, end_month, last_day)
        else:
            # We're in the previous financial year
            start = datetime(today.year - 1, self.financial_year_start_month, 1)
            _, last_day = calendar.monthrange(today.year, end_month)
            end = datetime(today.year, end_month, last_day)
        return start, end


settings = Settings()
setup_logging()
