# Data model

PostgreSQL. All ids are UUIDs. All timestamps are `timestamptz`, stored in UTC.
Every table except `tenants`, `outbox_messages` and `processed_messages` has a non-null, indexed `tenant_id`. The two messaging tables are infrastructure: the tenant id travels inside the message, and the worker loads the case through the tenant-scoped repository.

```mermaid
erDiagram
    TENANTS ||--o{ USERS : has
    TENANTS ||--o{ CASES : owns
    CASES ||--o{ CASE_ANALYSES : "analysed by"
    CASE_ANALYSES ||--o{ VULNERABILITY_INDICATORS : suggests
    CASES ||--o{ VULNERABILITY_INDICATORS : "flagged with"
    CASES ||--o{ AUDIT_EVENTS : "changes recorded in"
    USERS ||--o{ AUDIT_EVENTS : performs
    USERS ||--o{ CASES : "assigned to"

    TENANTS {
        uuid id PK
        string name
        string slug UK
        string bank_holiday_region "england-and-wales | scotland | northern-ireland"
        timestamptz created_at
    }
    USERS {
        uuid id PK
        uuid tenant_id FK
        string email UK
        string display_name
        string role "handler | team_lead"
        string api_token_hash "SHA-256 of a demo API token"
    }
    CASES {
        uuid id PK
        uuid tenant_id FK
        string reference UK "CMP-2026-3F9A1C2B"
        string external_message_id "idempotent intake, unique per tenant"
        string subject
        text body "original, never sent to the LLM"
        string sender_email
        string sender_name
        timestamptz received_at "immutable"
        string status
        uuid assigned_to_user_id FK
        timestamptz src_deadline_at
        timestamptz final_response_deadline_at
        string final_category "null until a person decides"
        string final_priority "null until a person decides"
        timestamptz resolved_at
        string resolution_type "src | final_response"
        timestamptz created_at
        timestamptz updated_at
    }
    CASE_ANALYSES {
        uuid id PK
        uuid tenant_id FK
        uuid case_id FK
        int attempt
        string status "completed | invalid_output | failed"
        string provider "fake | openai | azure_openai"
        string model
        text redacted_input "exactly what left our system"
        string suggested_category
        string summary
        string suggested_priority
        text raw_output "the answer as received: an invalid one may not even be JSON"
        string error
        string correlation_id
        timestamptz created_at
    }
    VULNERABILITY_INDICATORS {
        uuid id PK
        uuid tenant_id FK
        uuid case_id FK
        uuid analysis_id FK "null when added by a handler"
        string indicator_type
        string driver "health | life_events | resilience | capability"
        text evidence_quote
        string source "ai | handler"
        string decision "pending | confirmed | rejected"
        uuid decided_by_user_id FK
        timestamptz decided_at
    }
    AUDIT_EVENTS {
        uuid id PK
        uuid tenant_id FK
        uuid case_id FK
        uuid actor_user_id FK "null for system or worker"
        string action
        string field
        jsonb old_value
        jsonb new_value
        string source "system | accepted_suggestion | override | handler"
        string correlation_id
        timestamptz created_at
    }
    OUTBOX_MESSAGES {
        uuid id PK "the message_id consumers see"
        string queue
        json payload "ids only: message, case, tenant, correlation"
        timestamptz published_at "null until the relay publishes it"
        int attempts
        string last_error "exception type only"
        timestamptz created_at
    }
    PROCESSED_MESSAGES {
        uuid message_id PK
        uuid case_id
        timestamptz processed_at
    }
```

## Case status (state machine)

```mermaid
stateDiagram-v2
    [*] --> new: complaint submitted
    new --> analysing: worker picks up job
    analysing --> awaiting_review: valid suggestions saved
    analysing --> needs_human_review: invalid output twice / redaction failed / dead-lettered
    awaiting_review --> in_progress: handler accepts or overrides
    needs_human_review --> in_progress: handler triages manually
    in_progress --> resolved: SRC or final response sent
    resolved --> [*]
```

Allowed transitions live in **one** place in code. Any other transition is rejected with `409 Conflict`.

## Enumerations

**Category** (`suggested_category`, `final_category`). This is a simplified set that I chose; it is not an official FCA taxonomy:

| Value | Meaning |
|---|---|
| `fees_and_charges` | Unexpected or disputed fees, interest, charges |
| `service_quality` | Delays, rudeness, poor communication |
| `account_administration` | Errors in account setup, statements, closures |
| `payments_and_transfers` | Failed, delayed or wrong payments |
| `lending_and_affordability` | Loans, credit cards, affordability checks |
| `fraud_and_scams` | Unauthorised transactions, APP scams |
| `advice_and_mis_selling` | Product not suitable or not explained |
| `collections_and_arrears` | Debt collection conduct, arrears handling |
| `other` | Anything else |

**Priority:** `low`, `medium`, `high`, `urgent`. If a case has any vulnerability indicator, its priority is at least `high` (rule in code, US-2.6).

**Vulnerability indicator type → FG21/1 driver**

| `indicator_type` | `driver` |
|---|---|
| `physical_illness` | health |
| `mental_health` | health |
| `disability` | health |
| `bereavement` | life_events |
| `relationship_breakdown` | life_events |
| `job_loss` | life_events |
| `financial_hardship` | resilience |
| `low_capability` (literacy, language, digital skills) | capability |

## Design notes

- **Suggestions and decisions are kept separate.** `case_analyses.suggested_*` is what the AI said. `cases.final_*` is what a person decided. Overriding a suggestion never destroys it, so we can measure AI accuracy later.
- **The original text is kept separate from the redacted text.** `cases.body` is the original. `case_analyses.redacted_input` is what was sent to the model.
- **`outbox_messages` is a transactional outbox.** The analysis job is inserted in the same transaction as the case, so a case can never exist without its job. A separate relay publishes pending rows to RabbitMQ.
- **`processed_messages` gives the worker idempotency.** The worker records each `message_id` in the same transaction as its work. A message seen before is acknowledged and skipped; a concurrent duplicate hits the primary key and is skipped too.
- **Deadlines are stored on the case** (`src_deadline_at`, `final_response_deadline_at`), calculated once at intake, so they can be indexed for the dashboard. "Business days remaining" is calculated when the case is read, because it depends on today's date.
- **Bank holidays are not a table** in v1. They come from a JSON file in the repo, taken from the gov.uk feed.
