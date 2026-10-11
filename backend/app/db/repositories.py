"""Tenant-scoped data access. THE one place where tenant isolation is enforced (US-7).

Every repository is created with the tenant id of the authenticated user (see app/api/deps.py),
so endpoints never write their own `WHERE tenant_id = ...`.

C# comparison: this plays the role of an EF Core global query filter
(`modelBuilder.Entity<Case>().HasQueryFilter(c => c.TenantId == _tenantId)`), made explicit.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Row,
    Select,
    Subquery,
    and_,
    case,
    delete,
    func,
    not_,
    or_,
    select,
)
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.db.base import TenantScopedMixin
from app.db.models import (
    AuditEvent,
    Case,
    CaseAnalysis,
    LoginSession,
    OutboxMessage,
    ResponseDraft,
    SavedView,
    User,
    VulnerabilityIndicator,
)
from app.domain.case_status import ANALYSING_STATUSES
from app.domain.deadline_risk import DeadlineWindow
from app.domain.enums import (
    AnalysisStatus,
    CaseStatus,
    Category,
    DeadlineKind,
    IndicatorDecision,
    IndicatorType,
)


class CrossTenantWriteError(Exception):
    """Raised when code tries to save an entity that belongs to a different tenant."""


class TenantScopedRepository[ModelT: TenantScopedMixin]:
    model: type[ModelT]

    def __init__(self, session: Session, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def _scoped[StatementT: Select[*tuple[Any, ...]]](self, statement: StatementT) -> StatementT:
        """Restrict a SELECT to rows of the current tenant. Works for any SELECT on this model:
        whole rows, or aggregates such as counts.

        `where` returns a new statement (statements are immutable, like LINQ queries).
        """
        return statement.where(self.model.tenant_id == self.tenant_id)

    def _add(self, entity: ModelT) -> ModelT:
        """Attach a new entity to the session, making sure it belongs to the current tenant.

        A missing tenant_id is filled in. A different tenant_id is refused, never silently
        "fixed": a wrong tenant id means a bug somewhere else.
        """
        if entity.tenant_id is None:
            entity.tenant_id = self.tenant_id
        elif entity.tenant_id != self.tenant_id:
            raise CrossTenantWriteError(
                f"Entity belongs to tenant {entity.tenant_id}, not {self.tenant_id}"
            )
        self.session.add(entity)
        return entity


@dataclass(frozen=True)
class DeadlineCriterion:
    kind: DeadlineKind
    window: DeadlineWindow


@dataclass(frozen=True)
class CaseCriteria:
    """Which cases a list shows. Every field narrows the result; the defaults match everything."""

    q: str | None = None
    received_from: date | None = None
    received_to: date | None = None
    status: CaseStatus | None = None
    assigned_to_user_id: uuid.UUID | None = None
    unassigned: bool = False
    open_only: bool = False
    deadline: DeadlineCriterion | None = None
    final_category: Category | None = None
    suggested_category: Category | None = None  # the AI's, on cases no person has categorised
    uncategorised: bool = False  # neither decided nor suggested yet
    confirmed_vulnerability: IndicatorType | None = None


_DEADLINE_COLUMNS: dict[DeadlineKind, InstrumentedAttribute[Any]] = {
    DeadlineKind.SUMMARY_RESOLUTION: Case.src_deadline_at,
    DeadlineKind.FINAL_RESPONSE: Case.final_response_deadline_at,
}


def _is_open() -> ColumnElement[bool]:
    return Case.status != CaseStatus.RESOLVED


def _in_window(criterion: DeadlineCriterion) -> ColumnElement[bool]:
    column = _DEADLINE_COLUMNS[criterion.kind]
    window = criterion.window
    if window.starts_at is None:
        return column < window.ends_at  # NULL (unknown deadline) never matches
    return and_(column >= window.starts_at, column < window.ends_at)


def _as_counts(rows: Sequence[Row[Any, int]]) -> dict[Any, int]:
    """Rows of (group key, count) as a dictionary. Callers declare the key type they return."""
    return {key: count for key, count in rows}


class CaseRepository(TenantScopedRepository[Case]):
    """Cases, and the counts the team lead dashboard is made of (US-5).

    The list filters and the dashboard counts are built from the same conditions below, so a
    number on the dashboard and the list it links to cannot disagree.
    """

    model = Case

    def get(self, case_id: uuid.UUID) -> Case | None:
        return self.session.scalars(self._scoped(select(Case).where(Case.id == case_id))).first()

    def get_for_update(self, case_id: uuid.UUID) -> Case | None:
        statement = self._scoped(select(Case).where(Case.id == case_id)).with_for_update()
        return self.session.scalars(statement.execution_options(populate_existing=True)).first()

    def get_by_external_message_id(self, external_message_id: str) -> Case | None:
        statement = select(Case).where(Case.external_message_id == external_message_id)
        return self.session.scalars(self._scoped(statement)).first()

    def list(
        self, criteria: CaseCriteria, *, limit: int, offset: int
    ) -> tuple[Sequence[Case], int]:
        statement = self._scoped(select(Case)).where(*self._conditions(criteria))

        total = self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        page = statement.order_by(Case.received_at.desc(), Case.id).limit(limit).offset(offset)
        return self.session.scalars(page).all(), total

    def add(self, case: Case) -> Case:
        return self._add(case)

    # --- Dashboard counts: open cases only ------------------------------------------------------

    def count_by_assignee(self) -> dict[uuid.UUID | None, int]:
        statement = (
            self._scoped(select(Case.assigned_to_user_id, func.count()))
            .where(_is_open())
            .group_by(Case.assigned_to_user_id)
        )
        return _as_counts(self.session.execute(statement).all())

    def count_open(self) -> int:
        statement = self._scoped(select(func.count()).select_from(Case)).where(_is_open())
        return self.session.scalar(statement) or 0

    def count_deadlines(
        self, criteria: Sequence[DeadlineCriterion]
    ) -> dict[DeadlineCriterion, int]:
        """Open cases matching each deadline criterion, all in one query."""
        columns = [func.count(case((_in_window(criterion), 1))) for criterion in criteria]
        statement = self._scoped(select(*columns).select_from(Case)).where(_is_open())
        counts = self.session.execute(statement).one()
        return dict(zip(criteria, counts, strict=True))

    def count_by_final_category(self) -> dict[Category, int]:
        statement = (
            self._scoped(select(Case.final_category, func.count()))
            .where(_is_open(), Case.final_category.is_not(None))
            .group_by(Case.final_category)
        )
        return _as_counts(self.session.execute(statement).all())

    def count_by_suggested_category(self) -> dict[Category, int]:
        suggestions = self._latest_suggestions()
        statement = (
            self._scoped(select(suggestions.c.suggested_category, func.count()))
            .select_from(Case)
            .join(suggestions, suggestions.c.case_id == Case.id)
            .where(_is_open(), *self._suggestion_applies())
            .group_by(suggestions.c.suggested_category)
        )
        return _as_counts(self.session.execute(statement).all())

    def count_uncategorised(self) -> int:
        statement = self._scoped(select(func.count()).select_from(Case)).where(
            _is_open(), self._uncategorised()
        )
        return self.session.scalar(statement) or 0

    def count_by_confirmed_vulnerability(self) -> dict[IndicatorType, int]:
        """Open cases per confirmed indicator type. A case with two confirmed indicators of the
        same type counts once."""
        statement = (
            self._scoped(
                select(VulnerabilityIndicator.indicator_type, func.count(Case.id.distinct()))
            )
            .select_from(Case)
            .join(VulnerabilityIndicator, VulnerabilityIndicator.case_id == Case.id)
            .where(
                _is_open(),
                VulnerabilityIndicator.tenant_id == self.tenant_id,
                VulnerabilityIndicator.decision == IndicatorDecision.CONFIRMED,
            )
            .group_by(VulnerabilityIndicator.indicator_type)
        )
        return _as_counts(self.session.execute(statement).all())

    # --- The conditions shared by the list filters and the counts -------------------------------

    def _conditions(self, criteria: CaseCriteria) -> Sequence[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []
        if criteria.q and criteria.q.strip():
            term = criteria.q.strip()
            conditions.append(
                or_(
                    *(
                        column.icontains(term, autoescape=True)
                        for column in (Case.reference, Case.subject, Case.body)
                    )
                )
            )
        if criteria.received_from:
            conditions.append(
                Case.received_at >= datetime.combine(criteria.received_from, time.min, UTC)
            )
        if criteria.received_to:
            conditions.append(
                Case.received_at <= datetime.combine(criteria.received_to, time.max, UTC)
            )
        if criteria.status is not None:
            conditions.append(Case.status == criteria.status)
        if criteria.assigned_to_user_id is not None:
            conditions.append(Case.assigned_to_user_id == criteria.assigned_to_user_id)
        if criteria.unassigned:
            conditions.append(Case.assigned_to_user_id.is_(None))
        if criteria.open_only:
            conditions.append(_is_open())
        if criteria.deadline is not None:
            conditions.append(_in_window(criteria.deadline))
        if criteria.final_category is not None:
            conditions.append(Case.final_category == criteria.final_category)
        if criteria.suggested_category is not None:
            conditions.append(self._suggested(criteria.suggested_category))
        if criteria.uncategorised:
            conditions.append(self._uncategorised())
        if criteria.confirmed_vulnerability is not None:
            conditions.append(self._confirmed(criteria.confirmed_vulnerability))
        return conditions

    def _latest_suggestions(self) -> Subquery:
        """The newest completed analysis of each case: (case_id, suggested_category).

        Older analyses of a re-analysed case are history, not the current suggestion.
        C# comparison: GroupBy(a => a.CaseId).Select(g => g.OrderByDescending(...).First()).
        """
        ranked = (
            select(
                CaseAnalysis.case_id,
                CaseAnalysis.suggested_category,
                func.row_number()
                .over(
                    partition_by=CaseAnalysis.case_id,
                    order_by=(CaseAnalysis.created_at.desc(), CaseAnalysis.attempt.desc()),
                )
                .label("position"),
            )
            .where(
                CaseAnalysis.tenant_id == self.tenant_id,
                CaseAnalysis.status == AnalysisStatus.COMPLETED,
            )
            .subquery()
        )
        return (
            select(ranked.c.case_id, ranked.c.suggested_category)
            .where(ranked.c.position == 1, ranked.c.suggested_category.is_not(None))
            .subquery()
        )

    @staticmethod
    def _suggestion_applies() -> tuple[ColumnElement[bool], ...]:
        """A suggestion stands only where no person has decided yet, and the case shows it."""
        return (
            Case.final_category.is_(None),
            Case.status.not_in(ANALYSING_STATUSES),
        )

    def _suggested(self, category: Category) -> ColumnElement[bool]:
        suggestions = self._latest_suggestions()
        suggested_ids = select(suggestions.c.case_id).where(
            suggestions.c.suggested_category == category
        )
        return and_(*self._suggestion_applies(), Case.id.in_(suggested_ids))

    def _uncategorised(self) -> ColumnElement[bool]:
        suggestions = self._latest_suggestions()
        has_suggestion = and_(
            *self._suggestion_applies(), Case.id.in_(select(suggestions.c.case_id))
        )
        return and_(Case.final_category.is_(None), not_(has_suggestion))

    def _confirmed(self, indicator_type: IndicatorType) -> ColumnElement[bool]:
        confirmed_case_ids = select(VulnerabilityIndicator.case_id).where(
            VulnerabilityIndicator.tenant_id == self.tenant_id,
            VulnerabilityIndicator.indicator_type == indicator_type,
            VulnerabilityIndicator.decision == IndicatorDecision.CONFIRMED,
        )
        return Case.id.in_(confirmed_case_ids)


class UserRepository(TenantScopedRepository[User]):
    model = User

    def list_users(self) -> Sequence[User]:
        return self.session.scalars(self._scoped(select(User)).order_by(User.display_name)).all()

    def add(self, user: User) -> User:
        return self._add(user)

    def display_names(self, user_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not user_ids:
            return {}
        rows = self.session.execute(
            self._scoped(select(User.id, User.display_name).where(User.id.in_(user_ids)))
        )
        return {user_id: name for user_id, name in rows}

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.session.scalars(self._scoped(select(User).where(User.id == user_id))).first()


class AuditRepository(TenantScopedRepository[AuditEvent]):
    """Append and read only. No update, no delete (US-3.7)."""

    model = AuditEvent

    def add(self, event: AuditEvent) -> AuditEvent:
        return self._add(event)

    def list_for_case(self, case_id: uuid.UUID) -> Sequence[AuditEvent]:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.case_id == case_id)
            .order_by(AuditEvent.created_at.desc())
        )
        return self.session.scalars(self._scoped(statement)).all()

    def latest_for_case_with_action(self, case_id: uuid.UUID, action: str) -> AuditEvent | None:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.case_id == case_id, AuditEvent.action == action)
            .order_by(AuditEvent.created_at.desc())
        )
        return self.session.scalars(self._scoped(statement)).first()


class AnalysisRepository(TenantScopedRepository[CaseAnalysis]):
    """Append only: every attempt is kept as evidence of what was sent and what came back."""

    model = CaseAnalysis

    def add(self, analysis: CaseAnalysis) -> CaseAnalysis:
        return self._add(analysis)

    def latest_for_case(
        self, case_id: uuid.UUID, *, status: AnalysisStatus | None = None
    ) -> CaseAnalysis | None:
        statement = select(CaseAnalysis).where(CaseAnalysis.case_id == case_id)
        if status is not None:
            statement = statement.where(CaseAnalysis.status == status)
        statement = statement.order_by(CaseAnalysis.created_at.desc(), CaseAnalysis.attempt.desc())
        return self.session.scalars(self._scoped(statement)).first()


class IndicatorRepository(TenantScopedRepository[VulnerabilityIndicator]):
    """No delete: a rejected indicator stays visible as rejected (US-3.4)."""

    model = VulnerabilityIndicator

    def add(self, indicator: VulnerabilityIndicator) -> VulnerabilityIndicator:
        return self._add(indicator)

    def get(self, case_id: uuid.UUID, indicator_id: uuid.UUID) -> VulnerabilityIndicator | None:
        statement = select(VulnerabilityIndicator).where(
            VulnerabilityIndicator.id == indicator_id, VulnerabilityIndicator.case_id == case_id
        )
        return self.session.scalars(self._scoped(statement)).first()

    def open_counts(self, case_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Indicators not rejected (pending or confirmed), per case. One query for a whole page
        of cases instead of one per case."""
        if not case_ids:
            return {}
        statement = (
            select(VulnerabilityIndicator.case_id, func.count())
            .where(
                VulnerabilityIndicator.case_id.in_(case_ids),
                VulnerabilityIndicator.decision != IndicatorDecision.REJECTED,
            )
            .group_by(VulnerabilityIndicator.case_id)
        )
        rows = self.session.execute(self._scoped(statement)).all()
        return dict(rows)

    def list_for_case(self, case_id: uuid.UUID) -> Sequence[VulnerabilityIndicator]:
        statement = (
            select(VulnerabilityIndicator)
            .where(VulnerabilityIndicator.case_id == case_id)
            .order_by(VulnerabilityIndicator.created_at, VulnerabilityIndicator.id)
        )
        return self.session.scalars(self._scoped(statement)).all()


class OutboxRepository:
    """System-level, deliberately NOT tenant-scoped: the relay publishes every tenant's messages.

    Only infrastructure code (the case service's intake and the relay) uses it, never endpoints.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, message: OutboxMessage) -> OutboxMessage:
        self.session.add(message)
        return message

    def lock_pending(self, limit: int) -> Sequence[OutboxMessage]:
        """Oldest unpublished messages, locked for this transaction.

        SKIP LOCKED lets several relays run side by side without publishing the same row twice.
        (SQLite, used in tests, ignores it; PostgreSQL honours it.)
        """
        statement = (
            select(OutboxMessage)
            .where(OutboxMessage.published_at.is_(None))
            .order_by(OutboxMessage.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return self.session.scalars(statement).all()


class AccountRepository:
    """Authentication resolves identity before a tenant is known."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def by_email(self, email: str) -> User | None:
        return self.session.scalar(
            select(User).where(func.lower(User.email) == email.lower()).with_for_update()
        )

    def by_session(self, token_hash: str, now: datetime) -> User | None:
        return self.session.scalar(
            select(User)
            .join(LoginSession, LoginSession.user_id == User.id)
            .where(
                LoginSession.token_hash == token_hash,
                LoginSession.expires_at > now,
                LoginSession.tenant_id == User.tenant_id,
            )
        )

    def revoke(self, token_hash: str) -> None:
        login = self.session.scalar(
            select(LoginSession).where(LoginSession.token_hash == token_hash)
        )
        if login:
            self.session.delete(login)

    def revoke_all(self, user_id: uuid.UUID, *, except_token_hash: str | None = None) -> None:
        """Sign the user out everywhere (or everywhere but this one session)."""
        statement = delete(LoginSession).where(LoginSession.user_id == user_id)
        if except_token_hash is not None:
            statement = statement.where(LoginSession.token_hash != except_token_hash)
        self.session.execute(statement)


class SavedViewRepository(TenantScopedRepository[SavedView]):
    model = SavedView

    def for_user(self, user_id: uuid.UUID) -> Sequence[SavedView]:
        return self.session.scalars(
            self._scoped(select(SavedView))
            .where(SavedView.user_id == user_id)
            .order_by(SavedView.created_at)
        ).all()

    def owned(self, view_id: uuid.UUID, user_id: uuid.UUID) -> SavedView | None:
        return self.session.scalar(
            self._scoped(select(SavedView)).where(
                SavedView.id == view_id, SavedView.user_id == user_id
            )
        )

    def add(self, view: SavedView) -> SavedView:
        return self._add(view)


class DraftRepository(TenantScopedRepository[ResponseDraft]):
    model = ResponseDraft

    def for_case(self, case_id: uuid.UUID) -> Sequence[ResponseDraft]:
        return self.session.scalars(
            self._scoped(select(ResponseDraft))
            .where(ResponseDraft.case_id == case_id)
            .order_by(ResponseDraft.created_at.desc())
        ).all()

    def locked(self, case_id: uuid.UUID, draft_id: uuid.UUID) -> ResponseDraft | None:
        return self.session.scalar(
            self._scoped(select(ResponseDraft))
            .where(ResponseDraft.case_id == case_id, ResponseDraft.id == draft_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def add(self, draft: ResponseDraft) -> ResponseDraft:
        return self._add(draft)
