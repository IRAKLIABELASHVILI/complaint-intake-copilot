"""FastAPI dependencies.

C# comparison: FastAPI's `Depends(...)` is constructor injection per request. A dependency that
`yield`s is like a scoped service with Dispose(): code after `yield` runs when the request ends.
"""

import hashlib
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import new_session
from app.services.case_service import CaseService

_bearer = HTTPBearer(auto_error=False)


def get_session() -> Iterator[Session]:
    session = new_session()
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_session)]


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Resolve the user from `Authorization: Bearer <token>`.

    This is the ONLY source of tenant_id in the whole API (US-7.2). Nothing in the request body,
    query string or headers can choose the tenant.
    """
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    user = session.scalars(
        select(User).where(User.api_token_hash == hash_token(credentials.credentials))
    ).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_case_service(session: SessionDep, user: CurrentUser) -> CaseService:
    return CaseService(session, user)


CaseServiceDep = Annotated[CaseService, Depends(get_case_service)]
