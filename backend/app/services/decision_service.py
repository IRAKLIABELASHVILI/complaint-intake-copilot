"""Handler decisions on a case (US-3): accept or override suggestions, confirm or reject
vulnerability indicators, add one the AI missed.

The AI never decides. A suggestion only becomes "final" when a person accepts or overrides it,
and every decision is audited in the same transaction as the change (US-3.6).
"""

import uuid
from typing import Literal

from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import AuditEvent, Case, CaseAnalysis, User, VulnerabilityIndicator
from app.db.repositories import (
    AnalysisRepository,
    AuditRepository,
    CaseRepository,
    IndicatorRepository,
)
from app.domain.enums import (
    AnalysisStatus,
    AuditSource,
    CaseStatus,
    Category,
    IndicatorDecision,
    IndicatorSource,
    IndicatorType,
    Priority,
)
from app.domain.evidence import quote_appears_in, squash_whitespace
from app.domain.vulnerability import driver_for
from app.logging_config import correlation_id_var
from app.services.case_service import CaseNotFoundError
from app.services.status_changes import change_status

# Decisions are possible once the analysis is over, and until the case is resolved.
DECIDABLE_STATUSES = frozenset(
    {CaseStatus.AWAITING_REVIEW, CaseStatus.NEEDS_HUMAN_REVIEW, CaseStatus.IN_PROGRESS}
)
_REVIEW_STATUSES = (CaseStatus.AWAITING_REVIEW, CaseStatus.NEEDS_HUMAN_REVIEW)


class CaseNotDecidableError(Exception):
    """The case is not in a state that accepts decisions (still analysing, or resolved)."""

    def __init__(self, status: CaseStatus) -> None:
        super().__init__(f"Decisions are not possible while the case is '{status}'")


class IndicatorNotFoundError(Exception):
    pass


class EvidenceNotInComplaintError(Exception):
    """A handler's evidence quote must be in the complaint, just like the model's (US-2.3)."""


class DecisionService:
    def __init__(self, session: Session, actor: User) -> None:
        self.session = session
        self.actor = actor
        self.cases = CaseRepository(session, actor.tenant_id)
        self.analyses = AnalysisRepository(session, actor.tenant_id)
        self.indicators = IndicatorRepository(session, actor.tenant_id)
        self.audit = AuditRepository(session, actor.tenant_id)

    def set_category(self, case_id: uuid.UUID, category: Category) -> Case:
        case = self._decidable_case(case_id)
        suggestion = self._latest_suggestion(case)
        suggested = suggestion.suggested_category if suggestion else None
        changed = case.final_category != category
        if changed:
            old, case.final_category = case.final_category, category
            self._record(case, "category_decided", "category", old, category, suggested)
        return self._commit(case, changed)

    def set_priority(self, case_id: uuid.UUID, priority: Priority) -> Case:
        case = self._decidable_case(case_id)
        suggestion = self._latest_suggestion(case)
        suggested = suggestion.suggested_priority if suggestion else None
        changed = case.final_priority != priority
        if changed:
            old, case.final_priority = case.final_priority, priority
            self._record(case, "priority_decided", "priority", old, priority, suggested)
        return self._commit(case, changed)

    def decide_indicator(
        self,
        case_id: uuid.UUID,
        indicator_id: uuid.UUID,
        decision: Literal[IndicatorDecision.CONFIRMED, IndicatorDecision.REJECTED],
    ) -> Case:
        case = self._decidable_case(case_id)
        indicator = self.indicators.get(case.id, indicator_id)
        if indicator is None:
            raise IndicatorNotFoundError(indicator_id)
        changed = indicator.decision != decision
        if changed:
            old = indicator.decision
            indicator.decision = decision
            indicator.decided_by_user_id = self.actor.id
            indicator.decided_at = utc_now()
            self._audit_event(
                case,
                action="indicator_decided",
                field="vulnerability_indicator",
                old_value={"id": str(indicator.id), "decision": old.value},
                new_value={"id": str(indicator.id), "decision": decision.value},
                source=AuditSource.HANDLER,
            )
        return self._commit(case, changed)

    def add_indicator(
        self, case_id: uuid.UUID, indicator_type: IndicatorType, evidence_quote: str
    ) -> Case:
        case = self._decidable_case(case_id)
        if not quote_appears_in(evidence_quote, f"{case.subject}\n{case.body}"):
            raise EvidenceNotInComplaintError()
        indicator = self.indicators.add(
            VulnerabilityIndicator(
                id=uuid.uuid4(),
                case=case,
                indicator_type=indicator_type,
                driver=driver_for(indicator_type),
                evidence_quote=squash_whitespace(evidence_quote),
                source=IndicatorSource.HANDLER,
                decision=IndicatorDecision.CONFIRMED,  # a person added it: it is their decision
                decided_by_user_id=self.actor.id,
                decided_at=utc_now(),
            )
        )
        self._audit_event(
            case,
            action="indicator_added",
            field="vulnerability_indicator",
            old_value=None,
            new_value={"id": str(indicator.id), "type": indicator_type.value},
            source=AuditSource.HANDLER,
        )
        return self._commit(case, changed=True)

    # --- helpers --------------------------------------------------------------------------------

    def _decidable_case(self, case_id: uuid.UUID) -> Case:
        case = self.cases.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        if case.status not in DECIDABLE_STATUSES:
            raise CaseNotDecidableError(case.status)
        return case

    def _latest_suggestion(self, case: Case) -> CaseAnalysis | None:
        return self.analyses.latest_for_case(case.id, status=AnalysisStatus.COMPLETED)

    def _record(
        self,
        case: Case,
        action: str,
        field: str,
        old: Category | Priority | None,
        new: Category | Priority,
        suggested: Category | Priority | None,
    ) -> None:
        """US-3.1/3.2: equal to the suggestion = accepted; different = override; no suggestion
        (e.g. the analysis failed) = the handler's own decision."""
        if suggested is None:
            source = AuditSource.HANDLER
        elif new == suggested:
            source = AuditSource.ACCEPTED_SUGGESTION
        else:
            source = AuditSource.OVERRIDE
        self._audit_event(
            case,
            action=action,
            field=field,
            old_value=old.value if old else None,
            new_value=new.value,
            source=source,
        )

    def _audit_event(
        self,
        case: Case,
        *,
        action: str,
        field: str,
        old_value: object,
        new_value: object,
        source: AuditSource,
    ) -> None:
        self.audit.add(
            AuditEvent(
                case=case,
                actor_user_id=self.actor.id,
                action=action,
                field=field,
                old_value=old_value,
                new_value=new_value,
                source=source,
                correlation_id=correlation_id_var.get(),
            )
        )

    def _commit(self, case: Case, changed: bool) -> Case:
        """Repeating a decision that is already recorded changes nothing and audits nothing.
        The first real decision on a case under review starts the work on it: -> in_progress."""
        if changed:
            if case.status in _REVIEW_STATUSES:
                change_status(
                    case,
                    CaseStatus.IN_PROGRESS,
                    audit=self.audit,
                    action="review_started",
                    source=AuditSource.HANDLER,
                    actor_user_id=self.actor.id,
                    correlation_id=correlation_id_var.get(),
                )
            self.session.commit()  # the change and its audit events: one transaction
        return case
