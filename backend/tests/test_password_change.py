"""A temporary password must be replaced before anything else; a user can change their own;
an administrator can give a colleague a new temporary one."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import LoginSession, User
from app.services.accounts import hash_password
from tests.conftest import TwoTenants

ADMIN_PASSWORD = "admin password 123"
TEMPORARY = "temporary password 1"
CHOSEN = "my own password 456"


@pytest.fixture(autouse=True)
def passwords_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sign in the way the web app does: no demo tokens."""
    monkeypatch.setattr(get_settings(), "allow_demo_tokens", False)


def sign_in(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


@pytest.fixture
def admin(client: TestClient, tenants: TwoTenants, db: Session) -> dict[str, str]:
    user = db.get(User, tenants.lead_a.id)
    assert user is not None
    user.is_admin = True
    user.password_hash = hash_password(ADMIN_PASSWORD)
    db.commit()
    return sign_in(client, user.email, ADMIN_PASSWORD)


def create_account(client: TestClient, admin: dict[str, str], email: str) -> str:
    body = {
        "email": email,
        "display_name": "New colleague",
        "password": TEMPORARY,
        "role": "handler",
    }
    response = client.post("/users", json=body, headers=admin)
    assert response.status_code == 201
    assert response.json()["must_change_password"] is True
    return str(response.json()["id"])


def test_a_temporary_password_opens_nothing_but_the_password_change(
    client: TestClient, admin: dict[str, str]
) -> None:
    create_account(client, admin, "new@example.com")
    temporary = sign_in(client, "new@example.com", TEMPORARY)

    # Who am I: allowed, and it says a new password is needed.
    me = client.get("/me", headers=temporary)
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    # Everything else is refused by the API itself, whatever the client does.
    for method, path in [("GET", "/cases"), ("GET", "/notifications"), ("GET", "/users")]:
        response = client.request(method, path, headers=temporary)
        assert response.status_code == 403, path
        assert response.json()["detail"] == "Choose a new password before continuing."

    change = {"current_password": TEMPORARY, "new_password": CHOSEN}
    assert client.post("/auth/password", json=change, headers=temporary).status_code == 204

    # The same session now works, with the flag gone.
    assert client.get("/me", headers=temporary).json()["must_change_password"] is False
    assert client.get("/cases", headers=temporary).status_code == 200
    # The temporary password no longer signs in; the chosen one does.
    old = client.post("/auth/login", json={"email": "new@example.com", "password": TEMPORARY})
    assert old.status_code == 401
    sign_in(client, "new@example.com", CHOSEN)


def test_signing_out_works_with_a_temporary_password(
    client: TestClient, admin: dict[str, str]
) -> None:
    create_account(client, admin, "new@example.com")
    temporary = sign_in(client, "new@example.com", TEMPORARY)
    assert client.post("/auth/logout", headers=temporary).status_code == 204
    assert client.get("/me", headers=temporary).status_code == 401


def test_changing_a_password_needs_the_current_one_and_a_different_new_one(
    client: TestClient, admin: dict[str, str], tenants: TwoTenants, db: Session
) -> None:
    wrong = {"current_password": "not my password", "new_password": CHOSEN}
    refused = client.post("/auth/password", json=wrong, headers=admin)
    assert refused.status_code == 403
    user = db.get(User, tenants.lead_a.id)
    assert user is not None
    db.refresh(user)
    assert user.failed_logins == 1  # counts towards the lockout, like a wrong sign-in

    same = {"current_password": ADMIN_PASSWORD, "new_password": ADMIN_PASSWORD}
    assert client.post("/auth/password", json=same, headers=admin).status_code == 422
    short = {"current_password": ADMIN_PASSWORD, "new_password": "too short"}
    assert client.post("/auth/password", json=short, headers=admin).status_code == 422


def test_a_password_change_signs_out_every_other_session(
    client: TestClient, admin: dict[str, str], tenants: TwoTenants, db: Session
) -> None:
    user = db.get(User, tenants.lead_a.id)
    assert user is not None
    other_browser = sign_in(client, user.email, ADMIN_PASSWORD)

    change = {"current_password": ADMIN_PASSWORD, "new_password": CHOSEN}
    assert client.post("/auth/password", json=change, headers=admin).status_code == 204

    assert client.get("/me", headers=admin).status_code == 200  # this one stays signed in
    assert client.get("/me", headers=other_browser).status_code == 401
    sessions = db.scalar(
        select(func.count()).select_from(LoginSession).where(LoginSession.user_id == user.id)
    )
    assert sessions == 1


def test_an_administrator_resets_a_colleagues_password(
    client: TestClient, admin: dict[str, str], tenants: TwoTenants, db: Session
) -> None:
    colleague_id = create_account(client, admin, "new@example.com")
    first = sign_in(client, "new@example.com", TEMPORARY)
    change = {"current_password": TEMPORARY, "new_password": CHOSEN}
    assert client.post("/auth/password", json=change, headers=first).status_code == 204
    colleague = db.scalar(select(User).where(User.email == "new@example.com"))
    assert colleague is not None
    colleague.failed_logins = 4  # one more wrong password away from a lockout
    db.commit()

    reset = {"temporary_password": "another temporary 9"}
    path = f"/users/{colleague_id}/password"
    assert client.post(path, json=reset, headers=admin).status_code == 204

    assert client.get("/me", headers=first).status_code == 401  # signed out everywhere
    db.refresh(colleague)
    assert colleague.must_change_password is True and colleague.failed_logins == 0
    again = sign_in(client, "new@example.com", "another temporary 9")
    assert client.get("/cases", headers=again).status_code == 403  # must choose a new one


def test_only_an_administrator_resets_and_only_in_their_organisation(
    client: TestClient, admin: dict[str, str], tenants: TwoTenants, db: Session
) -> None:
    reset = {"temporary_password": "another temporary 9"}
    own = client.post(f"/users/{tenants.lead_a.id}/password", json=reset, headers=admin)
    assert own.status_code == 422  # their own password goes through Change password
    other_tenant = client.post(f"/users/{tenants.handler_b.id}/password", json=reset, headers=admin)
    assert other_tenant.status_code == 404

    colleague_id = create_account(client, admin, "new@example.com")
    handler = db.get(User, tenants.handler_a.id)
    assert handler is not None
    handler.password_hash = hash_password(ADMIN_PASSWORD)
    db.commit()
    not_admin = sign_in(client, handler.email, ADMIN_PASSWORD)
    refused = client.post(f"/users/{colleague_id}/password", json=reset, headers=not_admin)
    assert refused.status_code == 403
