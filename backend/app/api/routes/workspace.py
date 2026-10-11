"""Personal views and case collaboration, scoped to the authenticated tenant."""

import uuid

from fastapi import APIRouter, HTTPException

from app.ai.provider import ProviderRejectedError, ProviderUnavailableError
from app.api.deps import CaseServiceDep, CurrentUser, NowDep, SessionDep
from app.db.models import AuditEvent, ResponseDraft, SavedView
from app.db.repositories import AuditRepository, DraftRepository, SavedViewRepository
from app.domain.draft_placeholders import unfilled_placeholders
from app.domain.enums import AuditSource, CaseStatus, DeadlineKind, DeadlineRisk, UserRole
from app.domain.redaction import RedactionError
from app.schemas.cases import AuditEventRead, CaseFilters
from app.schemas.workspace import (
    DeadlineNotice,
    DraftRead,
    DraftUpdate,
    HandoffCreate,
    NoteCreate,
    ViewCreate,
    ViewRead,
)
from app.services.case_service import AssigneeNotFoundError, CaseNotFoundError
from app.services.drafts import generate_draft

router = APIRouter(tags=["workspace"])


@router.get("/saved-views", response_model=list[ViewRead])
def saved_views(session: SessionDep, user: CurrentUser) -> list[ViewRead]:
    return [
        ViewRead.model_validate(view)
        for view in SavedViewRepository(session, user.tenant_id).for_user(user.id)
    ]


@router.post("/saved-views", response_model=ViewRead, status_code=201)
def save_view(data: ViewCreate, session: SessionDep, user: CurrentUser) -> ViewRead:
    view = SavedViewRepository(session, user.tenant_id).add(
        SavedView(
            user_id=user.id,
            name=data.name,
            filters=data.filters.model_dump(mode="json", by_alias=True),
        )
    )
    session.commit()
    return ViewRead.model_validate(view)


@router.delete("/saved-views/{view_id}", status_code=204)
def delete_view(view_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    view = SavedViewRepository(session, user.tenant_id).owned(view_id, user.id)
    if view is None:
        raise HTTPException(404, "Saved view not found")
    session.delete(view)
    session.commit()


@router.post("/cases/{case_id}/comments", response_model=AuditEventRead, status_code=201)
def comment(
    case_id: uuid.UUID,
    data: NoteCreate,
    service: CaseServiceDep,
    session: SessionDep,
    user: CurrentUser,
) -> AuditEventRead:
    case = service.get(case_id)
    event = service.audit.add(
        AuditEvent(
            case=case,
            actor_user_id=user.id,
            action="comment_added",
            source=AuditSource.HANDLER,
            new_value={"note": data.note},
        )
    )
    session.commit()
    return AuditEventRead.model_validate(event)


@router.post("/cases/{case_id}/handoff", status_code=204)
def handoff(
    case_id: uuid.UUID,
    data: HandoffCreate,
    service: CaseServiceDep,
    session: SessionDep,
    user: CurrentUser,
) -> None:
    case = service.cases.get_for_update(case_id)
    if case is None:
        raise CaseNotFoundError(case_id)
    if case.status == CaseStatus.RESOLVED:
        raise HTTPException(409, "A closed case cannot be handed over")
    assignee = service.users.get(data.assigned_to_user_id)
    if assignee is None:
        raise AssigneeNotFoundError(data.assigned_to_user_id)
    old = case.assigned_to_user_id
    case.assigned_to_user_id = assignee.id
    service.audit.add(
        AuditEvent(
            case=case,
            actor_user_id=user.id,
            action="case_handed_over",
            source=AuditSource.HANDLER,
            old_value=str(old) if old else None,
            new_value={
                "note": data.note,
                "assignee": assignee.display_name,
                "user_id": str(assignee.id),
            },
        )
    )
    session.commit()


@router.get("/notifications", response_model=list[DeadlineNotice])
def notifications(service: CaseServiceDep, user: CurrentUser, now: NowDep) -> list[DeadlineNotice]:
    notices = []
    for kind in DeadlineKind:
        for risk in DeadlineRisk:
            filters = CaseFilters(
                deadline=kind,
                deadline_risk=risk,
                assigned_to_user_id=user.id if user.role == UserRole.HANDLER else None,
            )
            cases, total = service.list(filters, now, limit=100, offset=0)
            all_cases = list(cases)
            for offset in range(100, total, 100):
                page, _ = service.list(filters, now, limit=100, offset=offset)
                all_cases.extend(page)
            for case in all_cases:
                deadline_at = (
                    case.src_deadline_at
                    if kind == DeadlineKind.SUMMARY_RESOLUTION
                    else case.final_response_deadline_at
                )
                if deadline_at is not None:
                    notices.append(
                        DeadlineNotice(
                            case_id=case.id,
                            reference=case.reference,
                            subject=case.subject,
                            deadline=kind.value,
                            deadline_at=deadline_at,
                            overdue=risk == DeadlineRisk.OVERDUE,
                        )
                    )
    return sorted(notices, key=lambda notice: notice.deadline_at)


@router.get("/cases/{case_id}/drafts", response_model=list[DraftRead])
def drafts(
    case_id: uuid.UUID, service: CaseServiceDep, session: SessionDep, user: CurrentUser
) -> list[DraftRead]:
    service.get(case_id)
    return [
        DraftRead.model_validate(draft)
        for draft in DraftRepository(session, user.tenant_id).for_case(case_id)
    ]


@router.post("/cases/{case_id}/drafts", response_model=DraftRead, status_code=201)
def create_draft(
    case_id: uuid.UUID, service: CaseServiceDep, session: SessionDep, user: CurrentUser
) -> DraftRead:
    case = service.get(case_id)
    if case.status == CaseStatus.RESOLVED:
        raise HTTPException(409, "A closed case cannot have a new response draft")
    try:
        body, provider = generate_draft(case)
    except (ProviderRejectedError, ProviderUnavailableError, RedactionError):
        raise HTTPException(503, "The draft could not be generated. Try again later.") from None
    draft = DraftRepository(session, user.tenant_id).add(
        ResponseDraft(case_id=case.id, body=body, provider=provider, created_by_user_id=user.id)
    )
    session.flush()
    service.audit.add(
        AuditEvent(
            case=case,
            actor_user_id=user.id,
            action="response_drafted",
            source=AuditSource.HANDLER,
            new_value={"draft_id": str(draft.id), "provider": provider},
        )
    )
    session.commit()
    return DraftRead.model_validate(draft)


@router.put("/cases/{case_id}/drafts/{draft_id}", response_model=DraftRead)
def update_draft(
    case_id: uuid.UUID,
    draft_id: uuid.UUID,
    data: DraftUpdate,
    service: CaseServiceDep,
    session: SessionDep,
    user: CurrentUser,
    now: NowDep,
) -> DraftRead:
    case = service.cases.get_for_update(case_id)
    if case is None:
        raise CaseNotFoundError(case_id)
    draft = DraftRepository(session, user.tenant_id).locked(case_id, draft_id)
    if draft is None:
        raise HTTPException(404, "Draft not found")
    if draft.approved_at or draft.version != data.version or case.status == CaseStatus.RESOLVED:
        raise HTTPException(
            409, "This draft was changed, approved or its case closed. Refresh before continuing."
        )
    placeholders = unfilled_placeholders(data.body)
    if data.approve and placeholders:
        raise HTTPException(
            422, f"Fill in these placeholders before approving: {', '.join(placeholders)}"
        )
    old_body = draft.body
    draft.body = data.body
    draft.version += 1
    if data.approve:
        draft.approved_at, draft.approved_by_user_id = now, user.id
    AuditRepository(session, user.tenant_id).add(
        AuditEvent(
            case=case,
            actor_user_id=user.id,
            action="response_approved" if data.approve else "response_edited",
            source=AuditSource.HANDLER,
            old_value={"body": old_body},
            new_value={"body": draft.body, "draft_id": str(draft.id)},
        )
    )
    session.commit()
    return DraftRead.model_validate(draft)
