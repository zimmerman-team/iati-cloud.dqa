# IATI DQA — Architecture Diagrams

## 1. System Architecture

```mermaid
graph TB
    subgraph Client
        C[HTTP Client]
    end

    subgraph Flask App
        R[Routes<br/>main.py]
        V[ActivityValidator<br/>validator.py]
        SC[SolrClient<br/>solr_client.py]
        CA[Cache<br/>cache.py]
        CFG[Settings<br/>config.py]
        M[Models<br/>models.py]
    end

    subgraph External
        REDIS[(Redis)]
        SOLR[(Solr<br/>IATI index)]
    end

    subgraph Data Files
            DD[data/default_dates.json]
            EX[data/document_validation_exemptions.json]
            NA[data/non_acronyms.json]
    end

    C -->|POST /dqa| R
    C -->|GET /dqa/health| R
    C -->|POST /dqa/cache/clear| R
    C -->|GET /PATCH /dqa/config| R

    R --> CA
    R --> SC
    R --> V
    CFG --> V
    CFG --> SC
    CFG --> CA
    M -.->|types| R
    M -.->|types| V

    CA <--> REDIS
    SC <--> SOLR

    DD --> CFG
    EX --> R
    NA --> CFG
```

---

## 2. Request Pipeline — POST /dqa

```mermaid
flowchart TD
    A([POST /dqa]) --> B[Parse & validate DQARequest]
    B -->|validation error| ERR1([400 Bad Request])
    B --> C[Build cache key from request payload]
    C --> D{Cache hit?}
    D -->|yes| RESP([Return cached DQAResponse])
    D -->|no| E[Load document exemptions]
    E --> F[Query Solr: H1 activities with status 2 or 4]
    G --> H{require_funding_and_accountable?}
    H -->|yes| I[Post-filter: keep only activities where org is role 1 AND role 2]
    H -->|no| J
    I --> J[Validate each H1 activity, 7 attributes + 3 documents]
    J --> K[Validate each H2 activity, 7 attributes only]
    K --> L[Aggregate pass/fail/not_applicable counts]
    L --> M[Calculate percentages per attribute & document]
    M --> N[Store result in Redis — 24h TTL]
    N --> O([Return DQAResponse])
```

---

## 3. Solr Query Construction

```mermaid
flowchart TD
    A[get_activities called] --> B[Base scope query: reporting-org.ref = ORG activity-status = 2 OR activity-status = 4 AND end-date within 18mo]
    B --> C{Segmentation filters?}
    C -->|countries| D[recipient-country.code IN list]
    C -->|regions| E[recipient-region.code IN list]
    C -->|sectors| F[sector.code matches 5-digit or 3-digit wildcard prefix]
    C -->|none| G
    D --> G[Combine with AND]
    E --> G
    F --> G
    G --> H{hierarchy filter?}
    H -->|H1| I[AND hierarchy:1]
    H -->|H2| J[AND hierarchy:2]
    H -->|none| K
    I --> K[Execute pysolr query return up to N rows]
    J --> K
```

---

## 4. Validation Rules

```mermaid
flowchart TD
    ACT([Activity]) --> ATTR[Attribute Validators applied to H1 and H2]
    ACT --> HIER{Hierarchy?}
    HIER -->|H1 only| DOC[Document Validators]

    ATTR --> T[title ≥60 chars, no unmatched acronyms]
    ATTR --> D[description exists, longer than title, not a repeat of title]
    ATTR --> SD[start date exists, not a placeholder date]
    ATTR --> ED[end date exists, after start date]
    ATTR --> SEC[sector 5-digit DAC codes, sum to 100% ±0.02%]
    ATTR --> LOC[location country+region percentages sum to 100% ±0.02%]
    ATTR --> ORG[participating orgs at least one present]

    DOC --> BC[Business Case required if started >3 months ago and after 2011-01-01]
    DOC --> LF[Logical Framework required if started >3 months ago]
    DOC --> AR[Annual Review required if started >19 months ago]

    BC --> EX{Exempt?}
    LF --> EX
    AR --> EX
    EX -->|yes| NA([not_applicable])
    EX -->|no| PF{Published?}
    PF -->|yes| PASS([pass])
    PF -->|no| FAIL([fail])
```

---

## 5. Data Models

```mermaid
classDiagram
    class DQARequest {
        +str organisation
        +SegmentationFilter segmentation
        +bool require_funding_and_accountable
    }

    class SegmentationFilter {
        +list~str~ countries
        +list~str~ regions
        +list~str~ sectors
    }

    class DQAResponse {
        +str organisation
        +DQAPercentages percentages
        +list~ActivityValidationResult~ failed_activities
        +int total_h1
        +int total_h2
        +int failed_h1
        +int failed_h2
    }

    class DQAPercentages {
        +AttributePercentages attributes
        +DocumentPercentages documents
    }

    class ActivityValidationResult {
        +str iati_identifier
        +int hierarchy
        +dict~str,AttributeValidation~ attributes
        +dict~str,DocumentValidation~ documents
        +bool passed
    }

    class AttributeValidation {
        +ValidationResult status
        +str message
        +str details
    }

    class DocumentValidation {
        +ValidationResult status
        +bool published
        +str exemption_reason
    }

    class ValidationResult {
        <<enumeration>>
        Pass
        Fail
        Not_Applicable
    }

    class ActivityStatus {
        <<enumeration>>
        Pipeline = 1
        Implementation = 2
        Finalisation = 3
        Closed = 4
        Cancelled = 5
        Suspended = 6
    }

    DQARequest --> SegmentationFilter
    DQAResponse --> DQAPercentages
    DQAResponse --> ActivityValidationResult
    ActivityValidationResult --> AttributeValidation
    ActivityValidationResult --> DocumentValidation
    AttributeValidation --> ValidationResult
    DocumentValidation --> ValidationResult
```

---

## 6. Cache Key & TTL Strategy

```mermaid
flowchart LR
    REQ[DQARequest payload] -->|JSON serialise + sort keys| RAW[raw key string]
    RAW -->|len ≤ 200 chars| KEY[use as-is]
    RAW -->|len > 200 chars| HASH[SHA256 hex digest]
    KEY --> REDIS[(Redis)]
    HASH --> REDIS
    REDIS -->|TTL = 24h| EXP[auto-expire]
    REDIS -->|POST /dqa/cache/clear| CLR[pattern delete]
```
