# Complaint Intake Copilot

AI-assisted intake for regulated complaints: each complaint email becomes a case with UK regulatory deadlines (FCA DISP 1.5 / 1.6), a suggested category, priority and vulnerability flags with evidence. Personal data is redacted before it reaches the model, and a person makes every final decision.

> 🚧 Work in progress. Milestone 2 (backend foundation, tenant isolation) is complete; milestone 3 (deadline engine) is next.

**Stack:** Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · PostgreSQL · Docker Compose · GitHub Actions (ruff, mypy, pytest)
**Planned:** RabbitMQ worker · OpenAI-compatible LLM provider with PII redaction · React + TypeScript

## Run it

Requires Docker.

```bash
docker compose up --build
```

This starts PostgreSQL, applies the Alembic migrations, loads fictional demo data and serves the API.

- **API docs (Swagger UI):** http://localhost:8000/docs
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

## Documentation

- [Company notes](docs/company-notes.md): context and the regulatory rules used
- [Brief](docs/brief.md): the problem, users, scope
- [User stories](docs/user-stories.md): acceptance criteria
- [Data model](docs/data-model.md)
- [Architecture](docs/architecture.md)

All complaint data in this repository is synthetic and fictional.
