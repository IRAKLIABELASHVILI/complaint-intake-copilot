"""Validation of the model's answer (US-2): schema, real evidence only, priority floor."""

import json

import pytest

from app.ai.output import InvalidModelOutputError, validate_model_output
from app.domain.enums import Category, IndicatorType, Priority, VulnerabilityDriver

TEXT = (
    "My husband passed away last month. I am finding all of this very hard to deal with.\n"
    "You charged a late fee anyway."
)


def answer(**overrides: object) -> str:
    base: dict[str, object] = {
        "category": "fees_and_charges",
        "summary": "Late fee charged after a bereavement.",
        "priority": "medium",
        "vulnerability_indicators": [],
    }
    return json.dumps(base | overrides)


def test_a_valid_answer_is_accepted() -> None:
    result = validate_model_output(answer(), TEXT)

    assert result.category is Category.FEES_AND_CHARGES
    assert result.summary == "Late fee charged after a bereavement."
    assert result.priority is Priority.MEDIUM
    assert result.indicators == ()


def test_indicators_with_word_for_word_evidence_are_kept_with_their_driver() -> None:
    indicator = {"type": "bereavement", "evidence_quote": "My husband passed away last month."}

    [kept] = validate_model_output(answer(vulnerability_indicators=[indicator]), TEXT).indicators

    assert kept.type is IndicatorType.BEREAVEMENT
    assert kept.driver is VulnerabilityDriver.LIFE_EVENTS
    assert kept.evidence_quote == "My husband passed away last month."


def test_invented_or_paraphrased_evidence_is_dropped() -> None:
    """US-2.3: the model may not invent evidence."""
    indicators = [
        {"type": "bereavement", "evidence_quote": "My husband died recently."},  # paraphrase
        {"type": "mental_health", "evidence_quote": "I have severe depression."},  # invented
    ]

    result = validate_model_output(answer(vulnerability_indicators=indicators), TEXT)

    assert result.indicators == ()


def test_a_quote_spanning_a_line_break_still_counts() -> None:
    quote = "very hard to deal with. You charged a late fee"
    indicator = {"type": "mental_health", "evidence_quote": quote}

    assert validate_model_output(answer(vulnerability_indicators=[indicator]), TEXT).indicators


def test_duplicate_indicators_are_kept_once() -> None:
    indicator = {"type": "bereavement", "evidence_quote": "My husband passed away last month."}

    result = validate_model_output(answer(vulnerability_indicators=[indicator, indicator]), TEXT)

    assert len(result.indicators) == 1


@pytest.mark.parametrize("model_priority", ["low", "medium"])
def test_vulnerability_lifts_the_priority_to_at_least_high(model_priority: str) -> None:
    """US-2.6: a business rule in code, not left to the model."""
    indicator = {"type": "bereavement", "evidence_quote": "My husband passed away last month."}

    result = validate_model_output(
        answer(priority=model_priority, vulnerability_indicators=[indicator]), TEXT
    )

    assert result.priority is Priority.HIGH


def test_urgent_stays_urgent_with_vulnerability() -> None:
    indicator = {"type": "bereavement", "evidence_quote": "My husband passed away last month."}

    result = validate_model_output(
        answer(priority="urgent", vulnerability_indicators=[indicator]), TEXT
    )

    assert result.priority is Priority.URGENT


def test_dropped_evidence_does_not_lift_the_priority() -> None:
    fake = {"type": "bereavement", "evidence_quote": "Something that is not in the text."}

    result = validate_model_output(answer(priority="low", vulnerability_indicators=[fake]), TEXT)

    assert result.priority is Priority.LOW


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("not json at all", "not valid JSON"),
        (answer(category="parking_tickets"), "category"),
        (answer(priority="whenever"), "priority"),
        (answer(summary="x" * 401), "summary"),
        (answer(summary=""), "summary"),
        (answer(extra_field="hello"), "extra_field"),
        (answer(vulnerability_indicators=[{"type": "sadness", "evidence_quote": "abc"}]), "type"),
        (json.dumps({"category": "other"}), "summary"),
        (json.dumps(["a", "list"]), "answer"),
    ],
    ids=["not-json", "category", "priority", "long", "empty", "extra", "type", "missing", "list"],
)
def test_invalid_answers_are_rejected_with_a_reason(raw: str, reason: str) -> None:
    with pytest.raises(InvalidModelOutputError, match=reason):
        validate_model_output(raw, TEXT)


def test_the_rejection_reason_never_quotes_the_answer() -> None:
    with pytest.raises(InvalidModelOutputError) as caught:
        validate_model_output(answer(category="SECRET-VALUE"), TEXT)

    assert "SECRET-VALUE" not in str(caught.value)
