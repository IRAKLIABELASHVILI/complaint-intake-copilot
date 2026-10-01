import pytest

from app.domain.case_status import (
    ALLOWED_TRANSITIONS,
    InvalidStatusTransitionError,
    can_transition,
    ensure_transition,
)
from app.domain.enums import CaseStatus


def test_every_status_has_a_transition_entry() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(CaseStatus)


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        (CaseStatus.NEW, CaseStatus.ANALYSING),
        (CaseStatus.ANALYSING, CaseStatus.AWAITING_REVIEW),
        (CaseStatus.ANALYSING, CaseStatus.NEEDS_HUMAN_REVIEW),
        (CaseStatus.AWAITING_REVIEW, CaseStatus.IN_PROGRESS),
        (CaseStatus.NEEDS_HUMAN_REVIEW, CaseStatus.IN_PROGRESS),
        (CaseStatus.IN_PROGRESS, CaseStatus.RESOLVED),
    ],
)
def test_allowed_transitions(current: CaseStatus, requested: CaseStatus) -> None:
    assert can_transition(current, requested)
    ensure_transition(current, requested)  # does not raise


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        (CaseStatus.NEW, CaseStatus.RESOLVED),  # cannot skip analysis and review
        (CaseStatus.ANALYSING, CaseStatus.IN_PROGRESS),  # a person must review first
        (CaseStatus.RESOLVED, CaseStatus.IN_PROGRESS),  # resolved is final
        (CaseStatus.NEW, CaseStatus.NEW),
    ],
)
def test_forbidden_transitions(current: CaseStatus, requested: CaseStatus) -> None:
    assert not can_transition(current, requested)
    with pytest.raises(InvalidStatusTransitionError):
        ensure_transition(current, requested)
