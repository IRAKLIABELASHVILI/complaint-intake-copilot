"""Tenant-scoped data access. THE one place where tenant isolation is enforced (US-7).

Every repository is created with the tenant id of the authenticated user (see app/api/deps.py),
so endpoints never write their own `WHERE tenant_id = ...`.

C# comparison: this plays the role of an EF Core global query filter
(`modelBuilder.Entity<Case>().HasQueryFilter(c => c.TenantId == _tenantId)`), made explicit.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.base import TenantScopedMixin
from app.db.models import (
    AuditEvent,
    Case,
    CaseAnalysis,
    OutboxMessage,
    User,
    VulnerabilityIndicator,
)
from app.domain.enums import AnalysisStatus, CaseStatus, IndicatorDecision


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


class CaseRepository(TenantScopedRepository[Case]):
    model = Case

    def get(self, case_id: uuid.UUID) -> Case | None:
        return self.session.scalars(self._scoped(select(Case).where(Case.id == case_id))).first()

    def get_by_external_message_id(self, external_message_id: str) -> Case | None:
        statement = select(Case).where(Case.external_message_id == external_message_id)
        return self.session.scalars(self._scoped(statement)).first()

    def list(
        self, *, status: CaseStatus | None, limit: int, offset: int
    ) -> tuple[Sequence[Case], int]:
        statement = self._scoped(select(Case))
        if status is not None:
            statement = statement.where(Case.status == status)

        total = self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        page = statement.order_by(Case.received_at.desc()).limit(limit).offset(offset)
        return self.session.scalars(page).all(), total

    def add(self, case: Case) -> Case:
        return self._add(case)


class UserRepository(TenantScopedRepository[User]):
    model = User

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
