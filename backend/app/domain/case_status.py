"""The case status state machine. The only place that decides which transitions are allowed.

See docs/data-model.md for the diagram.
"""

from app.domain.enums import CaseStatus

ALLOWED_TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.NEW: frozenset({CaseStatus.ANALYSING}),
    CaseStatus.ANALYSING: frozenset({CaseStatus.AWAITING_REVIEW, CaseStatus.NEEDS_HUMAN_REVIEW}),
    CaseStatus.AWAITING_REVIEW: frozenset({CaseStatus.IN_PROGRESS}),
    CaseStatus.NEEDS_HUMAN_REVIEW: frozenset({CaseStatus.IN_PROGRESS}),
    CaseStatus.IN_PROGRESS: frozenset({CaseStatus.RESOLVED}),
    CaseStatus.RESOLVED: frozenset(),
}


class InvalidStatusTransitionError(Exception):
    def __init__(self, current: CaseStatus, requested: CaseStatus) -> None:
        super().__init__(f"Cannot move a case from '{current}' to '{requested}'")
        self.current = current
        self.requested = requested


def can_transition(current: CaseStatus, requested: CaseStatus) -> bool:
    return requested in ALLOWED_TRANSITIONS[current]


def ensure_transition(current: CaseStatus, requested: CaseStatus) -> None:
    if not can_transition(current, requested):
        raise InvalidStatusTransitionError(current, requested)
