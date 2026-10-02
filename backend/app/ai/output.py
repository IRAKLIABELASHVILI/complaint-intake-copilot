"""The model's answer: its expected shape, and the checks it must pass before anyone sees it.

The model is treated like any untrusted client. Its JSON is validated against a strict schema,
every evidence quote must appear word for word in the text we sent (US-2.3), and the priority
floor for vulnerable customers is applied in code (US-2.6).
"""

import json
import logging
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai.complaint_text import without_label
from app.domain.enums import Category, IndicatorType, Priority, VulnerabilityDriver
from app.domain.evidence import quote_appears_in, squash_whitespace
from app.domain.vulnerability import driver_for, suggested_priority

logger = logging.getLogger(__name__)

MAX_SUMMARY_CHARS = 400
MAX_INDICATORS = 10


class ModelIndicator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: IndicatorType
    evidence_quote: str = Field(min_length=3, max_length=500)


class ModelAnalysis(BaseModel):
    """The JSON the model must return. Also shown to the model as its output schema."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)
    priority: Priority
    vulnerability_indicators: list[ModelIndicator] = Field(max_length=MAX_INDICATORS)


class InvalidModelOutputError(Exception):
    """The answer is unusable. The message is safe to store and log: it never quotes the answer."""


@dataclass(frozen=True)
class SuggestedIndicator:
    type: IndicatorType
    driver: VulnerabilityDriver
    evidence_quote: str


@dataclass(frozen=True)
class ValidatedAnalysis:
    category: Category
    summary: str
    priority: Priority  # after the vulnerability floor
    indicators: tuple[SuggestedIndicator, ...]


def validate_model_output(raw: str, sent_text: str) -> ValidatedAnalysis:
    try:
        parsed = ModelAnalysis.model_validate(json.loads(raw))
    except json.JSONDecodeError:
        raise InvalidModelOutputError("The answer is not valid JSON") from None
    except ValidationError as error:
        raise InvalidModelOutputError(_describe(error)) from None

    indicators = _indicators_with_real_evidence(parsed.vulnerability_indicators, sent_text)
    return ValidatedAnalysis(
        category=parsed.category,
        summary=parsed.summary.strip(),
        priority=suggested_priority(parsed.priority, has_vulnerability=bool(indicators)),
        indicators=indicators,
    )


def _indicators_with_real_evidence(
    candidates: list[ModelIndicator], sent_text: str
) -> tuple[SuggestedIndicator, ...]:
    """Keep an indicator only if its quote is really in the text. The model may not invent
    evidence (US-2.3). Whitespace differences (line breaks) are ignored; words are not."""
    kept: dict[tuple[IndicatorType, str], SuggestedIndicator] = {}
    for candidate in candidates:
        quote = squash_whitespace(without_label(candidate.evidence_quote))
        if not quote_appears_in(quote, sent_text):
            logger.warning(
                "Indicator dropped: evidence not found in the text",
                extra={"error_type": candidate.type.value},
            )
            continue
        kept.setdefault(
            (candidate.type, quote),
            SuggestedIndicator(candidate.type, driver_for(candidate.type), quote),
        )
    return tuple(kept.values())


def _describe(error: ValidationError) -> str:
    """Field paths and error kinds only: no values from the answer."""
    problems = sorted(
        {f"{'.'.join(str(p) for p in e['loc']) or 'answer'}: {e['type']}" for e in error.errors()}
    )
    return "Schema errors: " + "; ".join(problems[:10])
