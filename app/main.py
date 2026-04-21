import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS

from app.cache import cache
from app.config import DATA_DIR, settings
from app.docs import init_swagger
from app.models import (
    ActivityValidationResult,
    ConfigAction,
    ConfigEditRequest,
    DQARequest,
    DQAResponse,
    OrganisationSummary,
    ValidationResult,
)
from app.solr_client import solr_client
from app.validator import ActivityValidator

logger = logging.getLogger("app")
app = Flask(__name__)
CORS(app)
init_swagger(app)

FL_TITLE_NARRATIVE = "title.narrative"
_EDPL = "_expected_downstream_partner_links"
_HDPL = "_has_downstream_partner_links"

# Swagger UI paths are exempt from authentication
_SWAGGER_PATHS = {"/dqa/docs/", "/dqa/apispec.json"}


@app.before_request
def require_api_key():
    """Reject requests that do not carry a valid Authorization header."""
    if request.path.startswith("/flasgger_static") or request.path in _SWAGGER_PATHS:
        return
    if request.headers.get("Authorization") != settings.secret_key:
        return jsonify({"error": "Unauthorized"}), 401


@app.route("/dqa/health", methods=["GET"])
def health_check():
    """
    Service health check.
    ---
    tags:
      - Health
    summary: Returns the health status of the API and its dependencies.
    responses:
      200:
        description: Service health status.
        schema:
          $ref: '#/definitions/HealthResponse'
    """
    redis_ok = cache.ping()
    return jsonify(
        {
            "status": "healthy" if redis_ok else "degraded",
            "redis": "connected" if redis_ok else "disconnected",
            "timestamp": datetime.now().isoformat(),
        }
    )


@app.route("/dqa", methods=["POST"])
def run_dqa():
    """
    Run Data Quality Assessment.
    ---
    tags:
      - DQA
    summary: Validate IATI data quality for an organisation.
    description: |
      Fetches IATI activities for the given organisation from Solr and validates:
      - **Attribute completeness** - title, description, dates, sectors, locations,
        participating organisations.
      - **Downstream partner links** (H1 programmes only) - whether any external organisation
        has published an activity linking back to this programme or its projects.
      - **Document publication** (H1 programmes only) - Business Case, Logical Framework,
        Annual Review, Project Completion Review (closed programmes only).

      Only activities with status 2 (implementation) or 4 (closed within the last 18 months)
      are included. Results are cached in Redis for 24 hours.

      The response also includes `available_segmentations`: the unique country, region, and
      sector codes present in the fetched data. These can be used to populate filter dropdowns
      for follow-up segmented requests.
    parameters:
      - in: body
        name: body
        required: true
        schema:
          $ref: '#/definitions/DQARequest'
    responses:
      200:
        description: DQA results including per-activity failures and aggregate percentages.
        schema:
          $ref: '#/definitions/DQAResponse'
      400:
        description: Invalid or missing request body.
        schema:
          $ref: '#/definitions/ErrorResponse'
    """
    try:
        req_data = request.get_json()
        dqa_request = DQARequest(**req_data)
    except Exception as e:
        logger.error(f"Invalid DQA request: {e}")
        return jsonify({"error": f"Invalid request: {str(e)}"}), 400

    logger.info(f"DQA request for organisation: {dqa_request.organisation}")

    # Check cache
    cache_key = cache.make_key(
        "dqa",
        dqa_request.organisation,
        countries=dqa_request.segmentation.countries if dqa_request.segmentation else None,
        regions=dqa_request.segmentation.regions if dqa_request.segmentation else None,
        sectors=dqa_request.segmentation.sectors if dqa_request.segmentation else None,
        require_funding_and_accountable=dqa_request.require_funding_and_accountable,
        optional_rules=dqa_request.optional_rules,
    )

    cached_result = cache.get(cache_key)
    if cached_result and not dqa_request.skip_cache:
        logger.debug(f"Cache hit for DQA: {dqa_request.organisation}")
        if not dqa_request.failed_activities:
            cached_result["failed_activities"] = []
        return jsonify(cached_result)

    with open(os.path.join(DATA_DIR, "document_validation_exemptions.json")) as f:
        exemptions: List[str] = json.load(f)
    logger.info(f"Loaded {len(exemptions)} document validation exemptions: {exemptions}")
    validator = ActivityValidator(exemptions=exemptions, optional_rules=dqa_request.optional_rules)

    # Build filters
    filters = {}
    if dqa_request.segmentation:
        if dqa_request.segmentation.countries:
            filters["countries"] = dqa_request.segmentation.countries
        if dqa_request.segmentation.regions:
            filters["regions"] = dqa_request.segmentation.regions
        if dqa_request.segmentation.sectors:
            filters["sectors"] = dqa_request.segmentation.sectors
    if dqa_request.require_funding_and_accountable:
        filters["filter_results"] = dqa_request.require_funding_and_accountable

    # Get activities
    h1_activities = solr_client.get_h1_activities(dqa_request.organisation, **filters)
    h2_activities = solr_client.get_h2_activities(dqa_request.organisation, **filters)

    # Determine downstream partner links for each H1 programme
    _inject_downstream_partner_links(h1_activities, h2_activities)

    # Get budgets for financial year
    fy_start, fy_end = settings.get_current_financial_year()
    total_budget = validator.calculate_budget_for_fy(h1_activities, h2_activities)

    # Create summary
    summary = OrganisationSummary(
        organisation=dqa_request.organisation,
        total_programmes=len(h1_activities),
        total_projects=len(h2_activities),
        total_budget=total_budget,
        financial_year=f"{fy_start.year}-{fy_end.year}",
    )
    logger.info(
        f"Fetched {len(h1_activities)} programmes, {len(h2_activities)} projects for {dqa_request.organisation}"
    )

    failed_activities, pass_count, fail_count, not_applicable_count = _run_dqa_validate(
        validator, h1_activities, h2_activities
    )
    logger.info(
        f"DQA complete for {dqa_request.organisation}: {pass_count} pass, {fail_count} fail, {not_applicable_count} N/A"
    )

    available_segmentations = solr_client.extract_segmentations(h1_activities + h2_activities)

    # Build response
    response = DQAResponse(
        summary=summary,
        failed_activities=failed_activities,
        pass_count=pass_count,
        fail_count=fail_count,
        not_applicable_count=not_applicable_count,
        generated_at=datetime.now(),
        available_segmentations=available_segmentations,
    )

    # Add calculated percentages
    response = validator.calculate_percentages(response)

    # Cache result
    result_dict = response.model_dump(mode="json")
    cache.set(cache_key, result_dict)

    if not dqa_request.failed_activities:
        result_dict["failed_activities"] = []

    return jsonify(result_dict)


def _run_dqa_validate(
    validator: ActivityValidator, h1_activities: List[Dict[str, Any]], h2_activities: List[Dict[str, Any]]
) -> tuple[List[ActivityValidationResult], int, int, int]:
    """Run DQA validation logic."""
    failed_activities: List[ActivityValidationResult] = []
    pass_count = 0
    fail_count = 0
    not_applicable_count = 0

    # Validate all activities (H1 and H2)
    all_activities = h1_activities + h2_activities

    for activity in all_activities:
        attr_validations, doc_validations = validator.validate_activity(activity)

        # Count results
        all_validations = attr_validations + doc_validations
        has_failure = any(v.status == ValidationResult.FAIL for v in all_validations)

        if has_failure:
            # Build validation result
            failure_count = sum(1 for v in all_validations if v.status == ValidationResult.FAIL)

            result = ActivityValidationResult(
                iati_identifier=activity.get("iati-identifier", ""),
                hierarchy=activity.get("hierarchy", 2),
                title=(
                    activity.get(FL_TITLE_NARRATIVE, [""])[0]
                    if isinstance(activity.get(FL_TITLE_NARRATIVE), list)
                    else activity.get(FL_TITLE_NARRATIVE, "")
                ),
                activity_status=activity.get("activity-status.code"),
                attributes=attr_validations,
                documents=doc_validations,
                overall_status=ValidationResult.FAIL,
                failure_count=failure_count,
            )
            failed_activities.append(result)
            fail_count += 1
        else:
            pass_count += 1

        # Count N/A
        not_applicable_count += sum(1 for v in all_validations if v.status == ValidationResult.NOT_APPLICABLE)
    return failed_activities, pass_count, fail_count, not_applicable_count


def _process_h2_downstream_links(
    activity: Dict[str, Any], referenced_partners: set, h2_links: Dict[str, Dict[str, Any]]
):
    iati_id = activity.get("iati-identifier", "")
    # Expected links is how many times "3" occurs in transaction.transaction-type.code
    expected_links = sum(1 for t in activity.get("transaction.transaction-type.code", []) if t == "3")
    activity[_EDPL] = expected_links
    activity[_HDPL] = iati_id in referenced_partners
    h2_links[iati_id] = {"expected_links": expected_links, "has_link": activity[_HDPL]}


def _process_h1_downstream_links(
    activity: Dict[str, Any],
    referenced_partners: set,
    activity_ids: Dict[str, List[str]],
    h2_links: Dict[str, Dict[str, Any]],
):
    iati_id = activity.get("iati-identifier", "")
    # Expected links is the sum of expected links for all child H2 activities and the H1 itself
    activity[_EDPL] = sum(1 for t in activity.get("transaction.transaction-type.code", []) if t == "3")
    activity[_HDPL] = iati_id in referenced_partners
    if activity[_HDPL]:
        return
    for h2_id in activity_ids.get(iati_id, []):
        if h2_id in h2_links:
            activity[_EDPL] += h2_links.get(h2_id, {}).get("expected_links", 0)
            if h2_links.get(h2_id, {}).get("has_link", False):
                activity[_HDPL] = True


def _inject_downstream_partner_links(
    h1_activities: List[Dict[str, Any]],
    h2_activities: List[Dict[str, Any]],
) -> None:
    """Inject `_has_downstream_partner_links` into each activity dict.

    Builds a map of H1 → H2 identifiers from the H2 activities' parent references,
    then queries Solr for external activities that link to any of these identifiers.
    """
    # Make a list of all iati-identifiers belonging to the h1 activity.
    activity_ids = {}
    for activity in h1_activities:
        parent_id = activity.get("iati-identifier", "")
        activity_ids[parent_id] = [parent_id]
        rel_activities = activity.get("json.related-activity", [])
        for _rel in rel_activities:
            rel = json.loads(_rel)
            if rel.get("type", 0) == 2 and rel.get("ref", None):
                activity_ids[parent_id].append(rel.get("ref", ""))

    # get all downstream partners that link back to any H1 or H2 activity
    referenced_partners = solr_client.get_all_downstream_partners_for_h1_and_h2(activity_ids)

    h2_links = {}

    for activity in h2_activities:
        _process_h2_downstream_links(activity, referenced_partners, h2_links)

    for activity in h1_activities:
        _process_h1_downstream_links(activity, referenced_partners, activity_ids, h2_links)


@app.route("/dqa/cache/clear", methods=["POST"])
def clear_cache():
    """
    Clear cached DQA results.
    ---
    tags:
      - Cache
    summary: Evict one or more entries from the Redis cache.
    description: |
      Removes cache keys matching the given glob-style pattern.
      Defaults to all keys (`*`).
    parameters:
      - in: body
        name: body
        required: false
        schema:
          type: object
          properties:
            pattern:
              type: string
              default: "*"
              description: Redis key pattern to match (glob-style). Defaults to all keys.
    responses:
      200:
        description: Number of keys removed and the pattern used.
        schema:
          $ref: '#/definitions/CacheClearResponse'
    """
    req_data = request.get_json(silent=True) or {}
    pattern = req_data.get("pattern", "*")
    count = cache.clear_pattern(pattern)
    logger.info(f"Cache cleared: {count} keys matching pattern '{pattern}'")
    return jsonify({"cleared": count, "pattern": pattern})


def _config_path(config_name: str) -> Optional[str]:
    """Return absolute path to data/<config_name>.json, or None if it doesn't exist."""
    path = os.path.join(DATA_DIR, f"{config_name}.json")
    return path if os.path.isfile(path) else None


def _config_add(values: List[str], value: str):
    if value in values:
        return None, f"Value '{value}' already exists", 409
    return sorted(values + [value]), None, None


def _config_remove(values: List[str], value: str):
    if value not in values:
        return None, f"Value '{value}' not found", 404
    return [v for v in values if v != value], None, None


def _config_update(values: List[str], old_value: str, new_value: str):
    if old_value not in values:
        return None, f"Value '{old_value}' not found", 404
    if new_value in values:
        return None, f"Value '{new_value}' already exists", 409
    return [new_value if v == old_value else v for v in values], None, None


def _apply_config_edit(values: List[str], edit_req: ConfigEditRequest):
    """Apply an add/remove/update edit to a config list. Returns (updated, error_msg, status_code)."""
    if edit_req.action == ConfigAction.ADD:
        if edit_req.value is None:
            return None, "Missing value for add action", 400
        return _config_add(values, edit_req.value)
    if edit_req.action == ConfigAction.REMOVE:
        if edit_req.value is None:
            return None, "Missing value for remove action", 400
        return _config_remove(values, edit_req.value)
    if edit_req.old_value is None or edit_req.new_value is None:
        return None, "Missing old_value or new_value for update action", 400
    return _config_update(values, edit_req.old_value, edit_req.new_value)


@app.route("/dqa/config", methods=["GET"])
def list_configs():
    """
    List available configuration lists.
    ---
    tags:
      - Config
    summary: Return the names of all editable config lists.
    responses:
      200:
        description: Sorted list of config names (filenames without .json extension).
        schema:
          $ref: '#/definitions/ConfigListResponse'
    """
    names = sorted(f[:-5] for f in os.listdir(DATA_DIR) if f.endswith(".json"))
    return jsonify({"configs": names})


_CONFIG_NAME_RE = re.compile(r"^\w+$")


@app.route("/dqa/config/<config_name>", methods=["GET"])
def get_config(config_name: str):
    """
    Get all values in a config list.
    ---
    tags:
      - Config
    summary: Return every value stored in a named config list.
    parameters:
      - in: path
        name: config_name
        type: string
        required: true
    responses:
      200:
        description: Config name and its values.
        schema:
          $ref: '#/definitions/ConfigValuesResponse'
      400:
        description: Invalid config name.
      404:
        description: Config list not found.
    """
    if not _CONFIG_NAME_RE.match(config_name):
        return jsonify({"error": "Invalid config name"}), 400
    path = _config_path(config_name)
    if path is None:
        return jsonify({"error": f"Config '{config_name}' not found"}), 404
    with open(path) as f:
        values = json.load(f)
    return jsonify({"config_name": config_name, "values": values})


@app.route("/dqa/config/<config_name>", methods=["PATCH"])
def edit_config(config_name: str):
    """
    Add, remove, or update a value in a config list.
    ---
    tags:
      - Config
    summary: Mutate a single entry in a named config list.
    parameters:
      - in: path
        name: config_name
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          $ref: '#/definitions/ConfigEditRequest'
    responses:
      200:
        description: Updated config list.
        schema:
          type: object
          properties:
            config_name:
              type: string
            values:
              type: array
              items:
                type: string
      400:
        description: Invalid request body.
      404:
        description: Config not found, or value to remove/update not found.
      409:
        description: Value already exists (add) or replacement value already exists (update).
    """
    if not _CONFIG_NAME_RE.match(config_name):
        return jsonify({"error": "Invalid config name"}), 400
    path = _config_path(config_name)
    if path is None:
        return jsonify({"error": f"Config '{config_name}' not found"}), 404

    try:
        req_data = request.get_json()
        edit_req = ConfigEditRequest(**req_data)
    except Exception as e:
        return jsonify({"error": f"Invalid request: {str(e)}"}), 400

    with open(path) as f:
        values: List[str] = json.load(f)

    updated, error, code = _apply_config_edit(values, edit_req)
    if error:
        return jsonify({"error": error}), code

    with open(path, "w") as f:
        json.dump(updated, f, indent=4)
    values = updated

    # Keep in-memory settings in sync for default_dates (loaded at startup)
    if config_name == "default_dates":
        settings.default_dates = ",".join(values)

    logger.info(f"Config '{config_name}' updated via {edit_req.action}: {values}")
    return jsonify({"config_name": config_name, "values": values})


if __name__ == "__main__":  # pragma: no cover
    app.run(host="127.0.0.1", port=5000, debug=settings.flask_debug)
