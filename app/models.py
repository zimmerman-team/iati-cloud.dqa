from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class ActivityStatus(str, Enum):
    """IATI Activity Status codes."""

    PIPELINE = "1"
    IMPLEMENTATION = "2"
    FINALISATION = "3"
    CLOSED = "4"
    CANCELLED = "5"
    SUSPENDED = "6"


class ValidationResult(str, Enum):
    """Validation result status."""

    # Reason for nosec: B105 - "pass" is not a password but a validation status
    PASS = "pass"  # nosec: B105
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class AttributeValidation(BaseModel):
    """Single attribute validation result."""

    attribute: str
    status: ValidationResult
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class DocumentValidation(BaseModel):
    """Document publication validation result."""

    document_type: str
    status: ValidationResult
    message: Optional[str] = None
    published: bool = False
    exemption_reason: Optional[str] = None


class ActivityValidationResult(BaseModel):
    """Validation results for a single activity."""

    iati_identifier: str
    hierarchy: int
    title: Optional[str] = None
    activity_status: Optional[ActivityStatus] = None
    attributes: List[AttributeValidation] = Field(default_factory=list)
    documents: List[DocumentValidation] = Field(default_factory=list)
    overall_status: ValidationResult
    failure_count: int = 0


class OrganisationSummary(BaseModel):
    """Organisation-level summary statistics."""

    organisation: str
    total_programmes: int = 0
    total_projects: int = 0
    total_budget: float = 0.0
    financial_year: str


class SegmentationFilter(BaseModel):
    """Filters for segmentation."""

    countries: Optional[List[str]] = None
    regions: Optional[List[str]] = None
    sectors: Optional[List[str]] = None


class OptionalRules(BaseModel):
    """Optional validation rules that are disabled by default."""

    check_acronyms: bool = Field(
        default=False, description="Validate that activity titles contain no unexpanded acronyms"
    )


class DQARequest(BaseModel):
    """Request parameters for DQA endpoint."""

    organisation: str
    segmentation: Optional[SegmentationFilter] = None
    require_funding_and_accountable: bool = False
    include_exemptions: bool = True
    optional_rules: Optional[OptionalRules] = None
    skip_cache: Optional[bool] = False
    failed_activities: bool = True


class HierarchyPercentages(BaseModel):
    """Attribute pass-rate percentages for a single hierarchy level (H1 or H2)."""

    title_percentage: int
    description_percentage: int
    start_date_percentage: int
    end_date_percentage: int
    sector_percentage: int
    participating_org_percentage: int
    location_percentage: int


class DQAPercentages(BaseModel):
    """Percentages for DQA results across all activities."""

    title_percentage: int
    description_percentage: int
    start_date_percentage: int
    end_date_percentage: int
    sector_percentage: int
    location_data_percentage: int
    participating_organisations_percentage: int
    downstream_partner_links_percentage: int
    document_business_case_percentage: int
    document_logical_framework_percentage: int
    document_annual_review_percentage: int
    document_project_completion_review_percentage: int


class ConfigAction(str, Enum):
    """Actions for editing a config list."""

    ADD = "add"
    REMOVE = "remove"
    UPDATE = "update"


class ConfigEditRequest(BaseModel):
    """Request body for editing a config list value."""

    action: ConfigAction
    value: Optional[str] = None  # required for add / remove
    old_value: Optional[str] = None  # required for update
    new_value: Optional[str] = None  # required for update

    @model_validator(mode="after")
    def check_fields_for_action(self):
        if self.action in (ConfigAction.ADD, ConfigAction.REMOVE) and self.value is None:
            raise ValueError(f"'value' is required for action '{self.action}'")
        if self.action == ConfigAction.UPDATE and (self.old_value is None or self.new_value is None):
            raise ValueError("'old_value' and 'new_value' are required for action 'update'")
        return self


class AvailableSegmentations(BaseModel):
    """Available countries, regions, and sectors in the fetched activity data."""

    countries: List[str] = Field(default_factory=list)
    regions: List[str] = Field(default_factory=list)
    sectors: List[str] = Field(default_factory=list)


class DQAResponse(BaseModel):
    """Response from DQA endpoint."""

    summary: OrganisationSummary
    failed_activities: List[ActivityValidationResult] = Field(default_factory=list)
    pass_count: int = 0
    fail_count: int = 0
    not_applicable_count: int = 0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_percentages: Optional[DQAPercentages] = None
    h1_percentages: Optional[HierarchyPercentages] = None
    h2_percentages: Optional[HierarchyPercentages] = None
    percentages: Optional[DQAPercentages] = None  # DEPRECATED: use total_percentages
    available_segmentations: AvailableSegmentations = Field(default_factory=AvailableSegmentations)
