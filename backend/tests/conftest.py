"""Shared test fixtures.

C# comparison: pytest fixtures replace xUnit's constructor setup / IClassFixture. A test asks for a
fixture by naming it as a parameter, and pytest builds it (and its dependencies) for that test.

Database: by default the tests use an in-memory SQLite database, so they run with no infrastructure.
CI sets TEST_DATABASE_URL to a real PostgreSQL, so everything is also proven on the real engine.
"""

import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_session, hash_token
from app.db.base import Base
from app.db.models import Tenant, User
from app.db.session import build_engine
from app.domain.enums import UserRole
from app.main import app


def _build_test_engine() -> Engine:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return build_engine(url)
    # One shared in-memory connection, so every session sees the same database.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


@pytest.fixture(scope="session")
def engine() -> Engine:
    return _build_test_engine()


@pytest.fixture
def session_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    """A clean schema for every test."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.drop_all(engine)


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    yield session
    session.close()


@dataclass(frozen=True)
class SeededUser:
    id: uuid.UUID
    tenant_id: uuid.UUID
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@dataclass(frozen=True)
class TwoTenants:
    """Tenant A ('acme') and tenant B ('globex'), with users in each."""

    handler_a: SeededUser
    second_handler_a: SeededUser
    lead_a: SeededUser
    handler_b: SeededUser


def _add_user(session: Session, tenant: Tenant, key: str, role: UserRole) -> SeededUser:
    token = f"test-token-{key}"
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=f"{key}@example.com",
        display_name=key,
        role=role,
        api_token_hash=hash_token(token),
    )
    session.add(user)
    return SeededUser(id=user.id, tenant_id=tenant.id, token=token)


@pytest.fixture
def tenants(db: Session) -> TwoTenants:
    acme = Tenant(id=uuid.uuid4(), name="Acme Finance (fictional)", slug="acme")
    globex = Tenant(id=uuid.uuid4(), name="Globex Lending (fictional)", slug="globex")
    db.add_all([acme, globex])
    result = TwoTenants(
        handler_a=_add_user(db, acme, "handler-a", UserRole.HANDLER),
        second_handler_a=_add_user(db, acme, "handler-a2", UserRole.HANDLER),
        lead_a=_add_user(db, acme, "lead-a", UserRole.TEAM_LEAD),
        handler_b=_add_user(db, globex, "handler-b", UserRole.HANDLER),
    )
    db.commit()
    return result


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    """HTTP client against the real app, with the database swapped for the test one.

    C# comparison: WebApplicationFactory<Program> with a replaced DbContext registration.
    """

    def _override_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def complaint_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "subject": "Unexpected overdraft fee",
        "body": "I was charged a £35 fee without warning. Please refund it.",
        "sender_email": "jane.doe@example.com",
        "sender_name": "Jane Doe",
        "received_at": "2026-09-14T09:30:00+01:00",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def create_case(client: TestClient) -> Callable[..., dict[str, object]]:
    """Helper: create a case as `user` and return the JSON body."""

    def _create(user: SeededUser, **overrides: object) -> dict[str, object]:
        response = client.post("/cases", json=complaint_payload(**overrides), headers=user.headers)
        assert response.status_code == 201, response.text
        body: dict[str, object] = response.json()
        return body

    return _create
