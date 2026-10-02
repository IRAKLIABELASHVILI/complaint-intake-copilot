# Architecture

## Overview

```mermaid
flowchart LR
    subgraph Client
        UI["React + TypeScript (Vite)<br/>typed client generated from OpenAPI"]
    end

    subgraph API["API service (FastAPI)"]
        R["Routers<br/>cases · decisions · dashboard"]
        T["Tenant dependency<br/>current_user → tenant_id"]
        D["Deadline engine<br/>pure functions + UK bank holidays"]
        P["Publisher"]
    end

    subgraph Worker["Worker service (Python)"]
        C["Consumer<br/>manual ack / nack, retries"]
        X["PII redactor"]
        L["LLMProvider interface"]
        F["FakeProvider<br/>(tests, no API key)"]
        O["OpenAI-compatible provider<br/>(OpenAI / Azure OpenAI)"]
        V["Output validator<br/>Pydantic + evidence check"]
    end

    DB[("PostgreSQL<br/>Alembic migrations")]
    Q[["RabbitMQ<br/>case.analysis queue"]]
    DLQ[["Dead-letter queue"]]
    LLM(("LLM API"))

    UI -- "HTTPS + JSON" --> R
    R --> T --> DB
    R --> D
    R --> P -- "case_id, tenant_id,<br/>correlation_id" --> Q
    Q --> C
    C --> X --> L
    L -.-> F
    L -.-> O -- "redacted text only" --> LLM
    L --> V --> DB
    C -- "after max retries" --> DLQ
```

## Request flow: a new complaint

```mermaid
sequenceDiagram
    autonumber
    actor H as Handler
    participant API as FastAPI
    participant DB as PostgreSQL
    participant Q as RabbitMQ
    participant W as Worker
    participant LLM as LLM provider

    H->>API: POST /cases (subject, body, sender, received_at)
    API->>API: validate (Pydantic), take tenant from user
    API->>API: calculate SRC and 8-week deadlines
    API->>DB: insert case (status=new) + audit event
    API->>Q: publish {message_id, case_id, tenant_id, correlation_id}
    API-->>H: 201 Created (case, deadlines)

    Q->>W: deliver message
    W->>DB: insert processed_messages(message_id), duplicate → ack and skip
    W->>DB: load case by (case_id, tenant_id), status=analysing
    W->>W: redact PII
    W->>LLM: redacted text + JSON schema
    LLM-->>W: JSON
    W->>W: validate schema + check evidence quotes exist in text
    alt valid
        W->>DB: save analysis + indicators, status=awaiting_review
        W->>Q: ack
    else invalid (first time)
        W->>LLM: retry once
    else invalid twice
        W->>DB: status=needs_human_review, reason
        W->>Q: ack
    else transient error (DB down, LLM timeout)
        W->>Q: nack → retry with backoff, after N attempts → DLQ
    end
```

## Main decisions

| Decision | Why | C# / .NET equivalent |
|---|---|---|
| **FastAPI + Pydantic v2** | Contact Web's target stack. Typed request and response models generate the OpenAPI contract automatically. | ASP.NET Core minimal APIs + DTOs + Swashbuckle |
| **SQLAlchemy 2.0 (typed `Mapped[...]`) + Alembic** | Contact Web already uses both. Alembic gives versioned migrations. | EF Core + EF migrations |
| **Separate worker process** | AI calls are slow and can fail. They must not block the HTTP request, and they must scale on their own. | `BackgroundService` / Worker Service consuming RabbitMQ |
| **RabbitMQ behind a `MessageBus` interface** | I already know RabbitMQ from .NET. The interface means Azure Service Bus is a new class, not a rewrite. | `IMessageBus` with a RabbitMQ implementation |
| **`LLMProvider` interface + fake provider** | Tests are deterministic, and anyone can run the demo without a key. OpenAI and Azure OpenAI share one implementation. | `ILlmClient` + a test double |
| **Redaction before the provider call** | The provider interface only ever receives redacted text. A privacy bug cannot be "fixed" by accident somewhere else. | A decorator around the client |
| **Tenant id from the auth dependency only** | One place to get right, one place to test. | Global query filter in EF Core (`HasQueryFilter`) + claims |
| **Deadlines as pure functions** | Rules like these are where bugs hide, and pure functions are easy to test at the boundaries. | Static domain service with injected `TimeProvider` |
| **Bank holidays from a JSON file** | No runtime dependency on gov.uk; reproducible tests. | Embedded resource |

## Known trade-offs (to discuss in interviews)

- **Publishing after the database commit is not atomic.** If the publish fails after the commit, the case exists but no job was sent. Fix options: a transactional outbox table, or a sweeper that re-queues cases stuck in `new`. This is decided in milestone 4.
- **Regex redaction misses some names.** A production system would add NER (e.g. Microsoft Presidio) and use Azure OpenAI in a UK region.
- **Shared-schema multi-tenancy** (a `tenant_id` column) is the simplest model to start with. PostgreSQL row-level security would add defence in depth and is a stretch goal.
- **Simple token auth** with seeded users. Production would use Entra ID / OIDC.

## Repository layout (planned)

```
complaint-intake-copilot/
├── backend/
│   ├── app/
│   │   ├── api/            # routers, dependencies (auth, tenant)
│   │   ├── domain/         # deadlines, redaction, status rules, pure logic
│   │   ├── reference_data/ # bank holiday file (from gov.uk) and its loader
│   │   ├── db/             # SQLAlchemy models, session, repositories
│   │   ├── messaging/      # MessageBus interface, RabbitMQ implementation
│   │   ├── ai/             # LLMProvider, fake + OpenAI providers, schemas
│   │   ├── worker/         # consumer entry point
│   │   └── schemas/        # Pydantic request and response models
│   ├── migrations/         # Alembic
│   ├── tests/
│   └── pyproject.toml
├── frontend/               # milestone 6
├── docs/
├── docker-compose.yml
└── .github/workflows/ci.yml
```
