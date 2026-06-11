from flasgger import Swagger
from flask import Flask

_SWAGGER_TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": "IATI Data Quality API",
        "description": (
            "Validates IATI (International Aid Transparency Initiative) activity data quality "
            "for organisations. Checks attribute completeness and document publication compliance "
            "across programme (H1) and project (H2) hierarchies."
        ),
        "version": "1.0.0",
    },
    "basePath": "/",
    "schemes": ["http", "https"],
    "consumes": ["application/json"],
    "produces": ["application/json"],
    "securityDefinitions": {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "API key for authentication. Set SECRET_KEY in .env (default: ZIMMERMAN).",
        }
    },
    "security": [{"ApiKeyAuth": []}],
    "tags": [
        {"name": "Health", "description": "Service health monitoring"},
        {"name": "DQA", "description": "Data Quality Assessment"},
        {"name": "Cache", "description": "Cache management"},
        {"name": "Config", "description": "Runtime config list management"},
    ],
    "definitions": {
        "SegmentationFilter": {
            "type": "object",
            "description": "Optional filters to narrow the assessment scope.",
            "properties": {
                "countries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "ISO 3166-1 alpha-2 country codes.",
                    "example": ["AF", "BD"],
                },
                "regions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "DAC region codes.",
                    "example": ["998"],
                },
                "sectors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "DAC sector codes (3- or 5-digit). A 3-digit code matches any 5-digit code with the same prefix.",  # noqa: E501
                    "example": ["43081"],
                },
            },
        },
        "DQARequest": {
            "type": "object",
            "required": ["organisation"],
            "properties": {
                "organisation": {
                    "oneOf": [
                        {"type": "string", "description": "IATI organisation identifier.", "example": "GB-GOV-1"},
                        {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of IATI organisation identifiers.",
                            "example": ["GB-GOV-9", "GB-GOV-10"],
                        },
                    ],
                },
                "segmentation": {"$ref": "#/definitions/SegmentationFilter"},
                "include_exemptions": {
                    "type": "boolean",
                    "description": "Whether to apply exemption rules.",
                    "default": True,
                },
                "require_funding_and_accountable": {
                    "type": "boolean",
                    "description": "Whether to only include activities where the organisation is both funding and accountable.",  # noqa: E501
                    "default": False,
                },
                "skip_cache": {
                    "type": "boolean",
                    "description": "When true, bypass the Redis cache and always fetch fresh data from Solr. The response is still written to cache afterwards.",  # noqa: E501
                    "default": False,
                },
                "failed_activities": {
                    "type": "boolean",
                    "description": "When false, the `failed_activities` list is omitted from the response. Useful when only summary metadata and percentages are needed.",  # noqa: E501
                    "default": True,
                },
                "optional_rules": {
                    "type": "object",
                    "description": "Optional validation rules that are disabled by default.",
                    "properties": {
                        "check_acronyms": {
                            "type": "boolean",
                            "description": "Validate that activity titles contain no unexpanded acronyms.",
                            "default": False,
                        }
                    },
                },
                "use_budget_date_filter": {
                    "type": "boolean",
                    "description": (
                        "When true, activities are scoped by budget date rather than activity status. "
                        "An H2 is in scope if any budget element has period-start or period-end within "
                        "the current financial year (April-March). An H1 is in scope if it has its own "
                        "budget in the current FY and either has no H2 children or at least one H2 child "
                        "is in scope. The existing status-code filter (implementation / closed within "
                        "18 months) is not applied when this flag is true."
                    ),
                    "default": False,
                },
            },
        },
        "OrganisationSummary": {
            "type": "object",
            "properties": {
                "organisation": {"type": "string"},
                "total_programmes": {"type": "integer"},
                "total_projects": {"type": "integer"},
                "total_budget": {"type": "number", "format": "float"},
                "financial_year": {"type": "string", "example": "2025-2026"},
            },
        },
        "AttributeValidation": {
            "type": "object",
            "properties": {
                "attribute": {"type": "string", "description": "Name of the validated attribute."},
                "status": {"type": "string", "enum": ["pass", "fail", "not_applicable"]},
                "message": {"type": "string"},
                "details": {"type": "object"},
            },
        },
        "DocumentValidation": {
            "type": "object",
            "properties": {
                "document_type": {"type": "string", "example": "Business Case"},
                "status": {"type": "string", "enum": ["pass", "fail", "not_applicable"]},
                "message": {"type": "string"},
                "published": {"type": "boolean"},
                "exemption_reason": {"type": "string"},
            },
        },
        "ActivityValidationResult": {
            "type": "object",
            "properties": {
                "iati_identifier": {"type": "string"},
                "hierarchy": {"type": "integer", "description": "1 = programme (H1), 2 = project (H2)."},
                "title": {"type": "string"},
                "activity_status": {"type": "string"},
                "attributes": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/AttributeValidation"},
                },
                "documents": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/DocumentValidation"},
                },
                "overall_status": {"type": "string", "enum": ["pass", "fail", "not_applicable"]},
                "failure_count": {"type": "integer"},
            },
        },
        "HierarchyPercentages": {
            "type": "object",
            "description": "Attribute pass-rate percentages for a single hierarchy level (H1 or H2). All values are floored integers.",
            "properties": {
                "title_percentage": {"type": "integer"},
                "description_percentage": {"type": "integer"},
                "start_date_percentage": {"type": "integer"},
                "end_date_percentage": {"type": "integer"},
                "sector_percentage": {"type": "integer"},
                "participating_org_percentage": {"type": "integer"},
                "location_percentage": {"type": "integer"},
            },
        },
        "DQAPercentages": {
            "type": "object",
            "description": "Pass-rate percentages across all activities. All values are floored integers.",
            "properties": {
                "title_percentage": {"type": "integer"},
                "description_percentage": {"type": "integer"},
                "start_date_percentage": {"type": "integer"},
                "end_date_percentage": {"type": "integer"},
                "sector_percentage": {"type": "integer"},
                "location_data_percentage": {"type": "integer"},
                "participating_organisations_percentage": {"type": "integer"},
                "downstream_partner_links_percentage": {"type": "integer"},
                "document_business_case_percentage": {"type": "integer"},
                "document_logical_framework_percentage": {"type": "integer"},
                "document_annual_review_percentage": {"type": "integer"},
                "document_project_completion_review_percentage": {"type": "integer"},
            },
        },
        "AvailableSegmentations": {
            "type": "object",
            "description": "Unique country, region, and sector codes present in the fetched activity data. Use these values to populate segmentation filter dropdowns for follow-up requests.",
            "properties": {
                "countries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "ISO 3166-1 alpha-2 country codes found in the data.",
                    "example": ["BD", "ET", "KE"],
                },
                "regions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "DAC region codes found in the data.",
                    "example": ["298", "89"],
                },
                "sectors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "DAC sector codes found in the data.",
                    "example": ["15110", "15170", "72010"],
                },
            },
        },
        "DQAResponse": {
            "type": "object",
            "properties": {
                "summary": {"$ref": "#/definitions/OrganisationSummary"},
                "failed_activities": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/ActivityValidationResult"},
                },
                "pass_count": {"type": "integer"},
                "fail_count": {"type": "integer"},
                "not_applicable_count": {"type": "integer"},
                "generated_at": {"type": "string", "format": "date-time"},
                "total_percentages": {"$ref": "#/definitions/DQAPercentages", "x-nullable": True},
                "h1_percentages": {"$ref": "#/definitions/HierarchyPercentages", "x-nullable": True},
                "h2_percentages": {"$ref": "#/definitions/HierarchyPercentages", "x-nullable": True},
                "percentages": {
                    "$ref": "#/definitions/DQAPercentages",
                    "x-nullable": True,
                    "description": "DEPRECATED: use total_percentages. Mirrors total_percentages for backwards compatibility.",
                },
                "available_segmentations": {"$ref": "#/definitions/AvailableSegmentations"},
            },
        },
        "ErrorResponse": {
            "type": "object",
            "properties": {"error": {"type": "string"}},
        },
        "HealthResponse": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["healthy", "degraded"],
                    "description": "Degraded when Redis is unavailable.",
                },
                "redis": {"type": "string", "enum": ["connected", "disconnected"]},
                "timestamp": {"type": "string", "format": "date-time"},
            },
        },
        "CacheClearResponse": {
            "type": "object",
            "properties": {
                "cleared": {"type": "integer", "description": "Number of cache keys removed."},
                "pattern": {"type": "string", "description": "Pattern that was matched."},
            },
        },
        "ConfigListResponse": {
            "type": "object",
            "properties": {
                "configs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Sorted list of config names (filenames without .json extension).",
                    "example": ["default_dates", "document_validation_exemptions", "non_acronyms"],
                },
            },
        },
        "ConfigValuesResponse": {
            "type": "object",
            "properties": {
                "config_name": {"type": "string", "example": "default_dates"},
                "values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "example": ["1900-01-01", "1970-01-01"],
                },
            },
        },
        "ConfigEditRequest": {
            "type": "object",
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "remove", "update"],
                    "description": "Mutation to apply. `add` and `remove` require `value`; `update` requires `old_value` and `new_value`.",  # noqa: E501
                },
                "value": {
                    "type": "string",
                    "description": "Value to add or remove.",
                    "example": "2000-01-01",
                },
                "old_value": {
                    "type": "string",
                    "description": "Existing value to replace (update only).",
                    "example": "1900-01-01",
                },
                "new_value": {
                    "type": "string",
                    "description": "Replacement value (update only).",
                    "example": "1901-06-01",
                },
            },
        },
    },
}


def init_swagger(app: Flask) -> Swagger:
    return Swagger(
        app,
        template=_SWAGGER_TEMPLATE,
        config={
            "headers": [],
            "specs": [
                {
                    "endpoint": "apispec",
                    "route": "/dqa/apispec.json",
                    "rule_filter": lambda _r: True,
                    "model_filter": lambda _t: True,
                }
            ],
            "static_url_path": "/flasgger_static",
            "swagger_ui": True,
            "specs_route": "/dqa/docs/",
        },
    )
