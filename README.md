# Complaint Intake Copilot

AI-assisted intake for regulated complaints: each complaint email becomes a case with UK regulatory deadlines (FCA DISP 1.5 / 1.6), a suggested category, priority and vulnerability flags with evidence. Personal data is redacted before it reaches the model, and a person makes every final decision.

> 🚧 Work in progress. Milestones 1–4 are complete (backend foundation, tenant isolation, deadline engine, queue and worker); milestone 5 (AI analysis with PII redaction) is next.

**Stack:** Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · PostgreSQL · Docker Compose · GitHub Actions (ruff, mypy, pytest)
**Messaging:** RabbitMQ · transactional outbox · idempotent worker with retries and a dead-letter queue
**Planned:** OpenAI-compatible LLM provider with PII redaction · React + TypeScript

## Run it

Requires Docker.

```bash
docker compose up --build
```

This starts PostgreSQL and RabbitMQ, applies the Alembic migrations, loads fictional demo data, serves the API, and runs the outbox relay and the analysis worker.

- **API docs (Swagger UI):** http://localhost:8000/docs
- **RabbitMQ management UI:** http://localhost:15672 (`cic` / `cic`, local only): queues `case.analysis`, `case.analysis.retry`, `case.analysis.dead`
- **Demo tokens:** click **Authorize** in Swagger UI and paste one of these.

| Tenant (fictional) | Role | Token |
|---|---|---|
| Northbridge Bank | handler | `demo-nb-handler` |
| Northbridge Bank | team lead | `demo-nb-lead` |
| Harbour Lane Building Society | handler | `demo-hl-handler` |
| Harbour Lane Building Society | team lead | `demo-hl-lead` |

Each tenant only ever sees its own cases. Try opening a Northbridge case id with a Harbour Lane token: you get a 404.

## Develop and test

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows; on macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest                         # fast, uses in-memory SQLite
ruff check . && mypy app tests
```

CI runs the same checks, applies and verifies the migrations, and runs the full test suite against **PostgreSQL** on every push.

## Background processing

A new case returns at once; its analysis runs in the background (US-1).

1. The case, its audit event and an **outbox** row commit in one transaction. The API never calls RabbitMQ, so a broker outage cannot lose a case or a job.
2. The **outbox relay** publishes pending rows to the `case.analysis` queue (publisher confirms, persistent messages).
3. The **worker** handles each job once: a `processed_messages` row makes redeliveries harmless. It loads the case by case id **and** tenant id. Transient failures retry with backoff (2 s, 4 s, 8 s, 16 s) through a retry queue; invalid messages and permanent failures go to the dead-letter queue.

Milestone 4 moves the case from `new` to `analysing`; milestone 5 adds the analysis itself.

## Regulatory deadlines

Every case gets two deadlines at intake, calculated in UK time by pure functions in [`app/domain/deadlines.py`](backend/app/domain/deadlines.py):

- **Summary resolution (SRC):** 17:00 on the third business day after the day of receipt (DISP 1.5.1R)
- **Final response:** end of the day, 8 weeks after receipt (DISP 1.6.2R)

Business days skip weekends and the tenant's regional UK bank holidays. Each read of a case adds a `deadline_tracking` block: business days remaining, overdue, or resolved in time.

Bank holidays come from a local copy of the gov.uk feed. The app never calls gov.uk at runtime. To refresh the file (validated before it is written):

```bash
cd backend
python -m app.reference_data.refresh_bank_holidays
```

## Documentation

- [Company notes](docs/company-notes.md): context and the regulatory rules used
- [Brief](docs/brief.md): the problem, users, scope
- [User stories](docs/user-stories.md): acceptance criteria
- [Data model](docs/data-model.md)
- [Architecture](docs/architecture.md)

All complaint data in this repository is synthetic and fictional.
