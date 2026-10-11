"""Password hashing and short-lived, revocable sessions."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import LoginSession, User
from app.db.repositories import AccountRepository
from app.domain.enums import UserRole


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    algorithm, salt, expected = encoded.split("$")
    if algorithm != "scrypt":
        return False
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return hmac.compare_digest(actual.hex(), expected)


_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


class InvalidCredentialsError(Exception):
    pass


def login(session: Session, email: str, password: str) -> str:
    user = AccountRepository(session).by_email(email)
    now = utc_now()
    valid = verify_password(
        password, user.password_hash if user and user.password_hash else _DUMMY_HASH
    )
    if not user or not user.password_hash:
        raise InvalidCredentialsError()
    if user.locked_until and user.locked_until > now:
        raise InvalidCredentialsError()
    if not valid:
        _record_failed_attempt(user, now)
        session.commit()
        raise InvalidCredentialsError()
    user.failed_logins = 0
    user.locked_until = None
    token = secrets.token_urlsafe(32)
    session.add(
        LoginSession(
            user_id=user.id,
            tenant_id=user.tenant_id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=now + timedelta(hours=8),
        )
    )
    session.commit()
    return token


def _record_failed_attempt(user: User, now: datetime) -> None:
    """Five wrong passwords in a row lock the account for fifteen minutes."""
    user.failed_logins += 1
    if user.failed_logins >= 5:
        user.locked_until = now + timedelta(minutes=15)
        user.failed_logins = 0


class PasswordReuseError(Exception):
    """The new password is the one being replaced."""


def change_password(
    session: Session, user: User, current: str, new: str, *, keep_token_hash: str
) -> None:
    """The user replaces their password, temporary or not. Knowing the current one is required,
    so an unattended signed-in browser cannot be used to take the account over. Every other
    session is signed out; this one stays."""
    if not user.password_hash or not verify_password(current, user.password_hash):
        _record_failed_attempt(user, utc_now())
        session.commit()
        raise InvalidCredentialsError()
    if new == current:
        raise PasswordReuseError()
    user.password_hash = hash_password(new)
    user.must_change_password = False
    user.failed_logins = 0
    AccountRepository(session).revoke_all(user.id, except_token_hash=keep_token_hash)
    session.commit()


def set_temporary_password(session: Session, user: User, password: str) -> None:
    """An administrator's reset for someone who forgot their password. It also unlocks the
    account, signs it out everywhere, and the user must choose their own at the next sign-in."""
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.failed_logins = 0
    user.locked_until = None
    AccountRepository(session).revoke_all(user.id)
    session.commit()


def new_account(
    email: str,
    name: str,
    password: str,
    role: UserRole,
    *,
    admin: bool = False,
    temporary: bool = True,
) -> User:
    """`temporary`: the password was chosen for the user, who replaces it at first sign-in."""
    return User(
        email=email.lower(),
        display_name=name,
        password_hash=hash_password(password),
        api_token_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        role=role,
        is_admin=admin,
        must_change_password=temporary,
    )
