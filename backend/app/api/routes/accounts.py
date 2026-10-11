"""Account login, logout, password changes and administrator-managed users."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, SessionDep, SignedInUser, _bearer, hash_token
from app.db.repositories import AccountRepository, UserRepository
from app.domain.enums import UserRole
from app.schemas.users import UserRead
from app.services.accounts import (
    InvalidCredentialsError,
    PasswordReuseError,
    change_password,
    login,
    new_account,
    set_temporary_password,
)

router = APIRouter(tags=["accounts"])


class LoginRequest(BaseModel):
    """Not EmailStr: signing in only looks the address up. A format rule here would turn a
    wrong address into a 422 with validation details instead of the usual 401."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class LoginRead(BaseModel):
    token: str


# Every password a person chooses or is given: long enough to resist guessing.
NewPassword = Annotated[str, Field(min_length=12, max_length=256)]


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    password: NewPassword = Field(description="Temporary: replaced by the user at first sign-in")
    role: UserRole
    is_admin: bool = False


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)
    new_password: NewPassword


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temporary_password: NewPassword


@router.post("/auth/login", response_model=LoginRead)
def sign_in(data: LoginRequest, session: SessionDep) -> LoginRead:
    try:
        return LoginRead(token=login(session, data.email, data.password))
    except InvalidCredentialsError:
        raise HTTPException(
            401, "Email or password not accepted. After repeated attempts, try again in 15 minutes."
        ) from None


@router.post("/auth/logout", status_code=204)
def sign_out(
    session: SessionDep,
    user: SignedInUser,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> None:
    AccountRepository(session).revoke(hash_token(credentials.credentials))
    session.commit()


@router.post(
    "/auth/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={403: {"description": "The current password is not correct"}},
)
def change_own_password(
    data: PasswordChange,
    session: SessionDep,
    user: SignedInUser,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> None:
    """Choose a new password. Required after an administrator set a temporary one; this
    session stays signed in, every other one is signed out."""
    try:
        change_password(
            session,
            user,
            data.current_password,
            data.new_password,
            keep_token_hash=hash_token(credentials.credentials),
        )
    except InvalidCredentialsError:
        raise HTTPException(403, "The current password is not correct.") from None
    except PasswordReuseError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Choose a password different from the current one.",
        ) from None


@router.get("/users", response_model=list[UserRead])
def list_users(session: SessionDep, user: CurrentUser) -> list[UserRead]:
    return [
        UserRead.model_validate(person)
        for person in UserRepository(session, user.tenant_id).list_users()
    ]


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(data: AccountCreate, session: SessionDep, user: CurrentUser) -> UserRead:
    if not user.is_admin:
        raise HTTPException(403, "Only administrators can create accounts")
    created = new_account(
        str(data.email), data.display_name.strip(), data.password, data.role, admin=data.is_admin
    )
    UserRepository(session, user.tenant_id).add(created)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            409, "This account could not be created. Check the email address."
        ) from None
    return UserRead.model_validate(created)


@router.post("/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: uuid.UUID, data: PasswordReset, session: SessionDep, user: CurrentUser
) -> None:
    """An administrator gives a colleague a temporary password (for example, a forgotten one).
    The colleague is signed out everywhere and chooses their own at the next sign-in."""
    if not user.is_admin:
        raise HTTPException(403, "Only administrators can reset passwords")
    if user_id == user.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Use Change password for your own account."
        )
    # Tenant-scoped: another organisation's user "does not exist" here.
    person = UserRepository(session, user.tenant_id).get(user_id)
    if person is None:
        raise HTTPException(404, "User not found")
    set_temporary_password(session, person, data.temporary_password)
