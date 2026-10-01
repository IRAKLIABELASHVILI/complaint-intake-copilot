# Complaint Intake Copilot

AI-assisted intake for regulated complaints: each complaint email becomes a case with UK regulatory deadlines (FCA DISP 1.5 / 1.6), a suggested category, priority and vulnerability flags with evidence. Personal data is redacted before it reaches the model, and a person makes every final decision.

> 🚧 Work in progress. Milestone 1 (analysis and design) is done.

**Stack (planned):** Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 · Alembic · PostgreSQL · RabbitMQ worker · OpenAI-compatible LLM provider · React + TypeScript · Docker Compose · GitHub Actions

## Documentation

- [Company notes](docs/company-notes.md): context and the regulatory rules used
- [Brief](docs/brief.md): the problem, users, scope
- [User stories](docs/user-stories.md): acceptance criteria
- [Data model](docs/data-model.md)
- [Architecture](docs/architecture.md)

All complaint data in this repository is synthetic and fictional.
