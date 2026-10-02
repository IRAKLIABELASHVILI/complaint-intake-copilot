"""Engine and session factory.

We use synchronous SQLAlchemy. FastAPI runs plain `def` endpoints in a thread pool, so they don't
block the event loop. It is simpler than async and matches Contact Web's current
Flask + SQLAlchemy code.
"""

from sqlalchemy import Engine, create_engine, event, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

CONNECT_TIMEOUT_SECONDS = 10


def build_engine(database_url: str) -> Engine:
    # hide_parameters: SQL errors in logs never include the values (complaint text, emails).
    # connect_timeout: an unreachable database fails in seconds instead of hanging for minutes.
    is_postgres = make_url(database_url).get_backend_name() == "postgresql"
    connect_args = {"connect_timeout": CONNECT_TIMEOUT_SECONDS} if is_postgres else {}
    engine = create_engine(
        database_url, pool_pre_ping=True, hide_parameters=True, connect_args=connect_args
    )
    if engine.dialect.name == "sqlite":
        # SQLite ignores foreign keys unless you switch them on per connection.
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = build_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def new_session() -> Session:
    return SessionLocal()
