"""Account login, logout and administrator-managed users."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, SessionDep, _bearer, hash_token
from app.db.repositories import AccountRepository, UserRepository
from app.domain.enums import UserRole
from app.schemas.users import UserRead
from app.services.accounts import InvalidCredentialsError, login, new_account

router = APIRouter(tags=["accounts"])


class LoginRequest(BaseModel):
    """Not EmailStr: signing in only looks the address up. A format rule here would turn a
    wrong address into a 422 with validation details instead of the usual 401."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class LoginRead(BaseModel):
    token: str


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=256)
    role: UserRole
    is_admin: bool = False


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
    user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> None:
    AccountRepository(session).revoke(hash_token(credentials.credentials))
    session.commit()


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
