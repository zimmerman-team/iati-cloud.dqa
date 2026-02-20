# Validator Rules

Validation logic for every attribute and document that is validated.
Applies to both H1 (programmes) and H2 (projects) unless noted.

---

## Attributes

### Title

Source field: `title.narrative` (first element if list)

| Condition | Status | Message | Percentage |
|---|---|---|---|
| Field is missing or empty | FAIL | "Title is missing" | 0% |
| Length < 60 characters | FAIL | "Title is too short (N characters, minimum 60 required)" | `len / 60 × 100` |
| Contains unexpanded acronyms¹ | FAIL | "Title contains potential acronyms that should be expanded: ..." | `(1 − Σ len(acronym) / len(title)) × 100` |
| All checks pass | PASS | — | 100% |

¹ Acronym detection uses `(?<!\w)(?:[A-Z]{2,}|[A-Za-z](?:\.[A-Za-z])+\.?)(?!\w)`. Words in `data/non_acronyms.json` are excluded from detection.

---

### Description

Source fields: `description.narrative` (first element if list), compared against `title.narrative`

| Condition | Status | Message | Percentage |
|---|---|---|---|
| Field is missing or empty | FAIL | "Description is missing" | 0% |
| Description equals title (case-insensitive) | FAIL | "Description is a repeat of the title" | 0% |
| `len(description) ≤ len(title)` | FAIL | "Description must be longer than title" | `len(description) / len(title) × 100` |
| All checks pass | PASS | — | 100% |

---

### Start Date

Source field: `activity-date.start-actual` (first element if list)

| Condition | Status | Message | Percentage |
|---|---|---|---|
| Field is missing or empty | FAIL | "Start date is missing" | 0% |
| Date matches a known default/system date¹ | FAIL | "Start date is a default system date: YYYY-MM-DD" | 0% |
| Date cannot be parsed | FAIL | "Invalid start date format: ..." | 0% |
| All checks pass | PASS | — | 100% |

¹ Default dates (e.g. 1900-01-01, 1970-01-01) are stored in `data/default_dates.json` and editable at runtime via the config API.

---

### End Date

Source fields: `activity-date.end-planned` (preferred) or `activity-date.end-actual` (first element if list each)

| Condition | Status | Message | Percentage |
|---|---|---|---|
| Both end date fields are missing | FAIL | "End date is missing" | 0% |
| Date cannot be parsed | FAIL | "Invalid end date format: ..." | 0% |
| End date ≤ start date (when start date is present) | FAIL | "End date must be after start date" | 0% |
| All checks pass | PASS | — | 100% |

---

### Sector

Source fields: `sector.code` and `sector.percentage` (activity-level); `transaction.sector.code` (transaction-level fallback)

| Condition | Status | Message | Percentage |
|---|---|---|---|
| No activity-level sectors AND no transaction-level sectors | FAIL | "No sectors defined" | 0% |
| No activity-level sectors, but transaction-level sectors present | NOT_APPLICABLE | "No activity-level sectors defined, only transaction-level sectors" | 100% |
| Any sector code is not exactly 5 digits | FAIL | "All sectors must use 5-digit DAC CRS codes" | `(count of invalid / total) × 100` |
| Sector percentages present and do not sum to 100% (±0.02)¹ | FAIL | "Sector percentages must sum to 100% (got N%)" | actual sum |
| All checks pass | PASS | — | 100% |

¹ Tolerance is configurable (`sector_tolerance`, default 0.02). Sector percentages are optional — if absent, only code validity is checked.

---

### Location

Source fields: `recipient-country.code`, `recipient-country.percentage`, `recipient-region.code`, `recipient-region.percentage`, `transaction.recipient-country.code`, `transaction.recipient-region.code`

Evaluation follows three mutually exclusive paths, checked in order:

**Path A — Transaction-level codes present**
(Takes priority. Entered when `transaction.recipient-country.code` or `transaction.recipient-region.code` is non-empty.)

| Condition | Status | Message | Percentage |
|---|---|---|---|
| Transaction codes present | NOT_APPLICABLE | "No activity-level locations defined, only transaction-level locations" | 100% |

**Path B — No activity-level percentages and no transaction-level codes**
(Entered when country/region percentages are absent and no transaction codes exist.)

| Condition | Status | Message | Percentage |
|---|---|---|---|
| No country or region codes at all | FAIL | "No location (country or region) specified" | 0% |
| Exactly one country or region code (percentage implied 100%) | PASS | — | 100% |
| More than one code, no percentages | FAIL | "Multiple locations specified without percentages" | 0% |

**Path C — Activity-level percentages present, no transaction-level codes**

| Condition | Status | Message | Percentage |
|---|---|---|---|
| Percentages do not sum to 100% (±0.02)¹ | FAIL | "Location percentages must sum to 100% (got N%)" | actual sum |
| Percentages sum to 100% (±0.02) | PASS | — | actual sum |

¹ Tolerance is configurable (`location_tolerance`, default 0.02).

---

### Participating Organisations

Source field: `participating-org.ref`

| Condition | Status | Message | Percentage |
|---|---|---|---|
| Field is missing or all values are empty | FAIL | "No participating organisations defined" | 0% |
| At least one organisation present | PASS | — | 100% |

---

## Documents (H1 only)

Document validations only apply to H1 (programme-level, hierarchy 1) activities. Each check scans `document-link.title.narrative` for a matching pattern (case-insensitive regex). An activity is fully exempt from all document checks if its IATI identifier appears in `data/document_validation_exemptions.json`.

---

### Business Case

Title pattern: `Business Case.*Published`

| Condition | Status | Reason / Message |
|---|---|---|
| Activity is on the exemption list | NOT_APPLICABLE | "Activity is exempt from document requirements" |
| No start date | NOT_APPLICABLE | "No start date available" |
| Start date before 2011-01-01 | NOT_APPLICABLE | "Activity started before 2011-01-01" |
| Started within the last N months¹ | NOT_APPLICABLE | "Activity started less than N months ago" |
| Document published | PASS | — |
| Document not published | FAIL | "Business Case document not published" |

¹ Exemption period configurable (`business_case_exemption_months`, default 3). The 2011-01-01 cutoff is unique to the Business Case.

---

### Logical Framework

Title pattern: `Logical Framework.*Published`

| Condition | Status | Reason / Message |
|---|---|---|
| Activity is on the exemption list | NOT_APPLICABLE | "Activity is exempt from document requirements" |
| No start date | NOT_APPLICABLE | "No start date available" |
| Started within the last N months¹ | NOT_APPLICABLE | "Activity started less than N months ago" |
| Document published | PASS | — |
| Document not published | FAIL | "Logical Framework document not published" |

¹ Exemption period configurable (`logical_framework_exemption_months`, default 3). No 2011-01-01 cutoff (unlike Business Case).

---

### Annual Review

Title pattern: `Annual Review.*Published`

| Condition | Status | Reason / Message |
|---|---|---|
| Activity is on the exemption list | NOT_APPLICABLE | "Activity is exempt from document requirements" |
| No start date | NOT_APPLICABLE | "No start date available" |
| Started within the last N months¹ | NOT_APPLICABLE | "Activity started less than N months ago" |
| Document published | PASS | — |
| Document not published | FAIL | "Annual Review document not published" |

¹ Exemption period configurable (`annual_review_exemption_months`, default 19).
