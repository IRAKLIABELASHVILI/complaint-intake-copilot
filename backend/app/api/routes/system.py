from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import CurrentUser, SessionDep
from app.schemas.users import UserRead

router = APIRouter(tags=["system"])


@router.get("/health/live")
def live() -> dict[str, str]:
    """The process is up. Used by Docker / Azure Container Apps liveness probes."""
    return {"status": "ok"}


@router.get("/health/ready")
def ready(session: SessionDep) -> dict[str, str]:
    """The process can reach the database."""
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
