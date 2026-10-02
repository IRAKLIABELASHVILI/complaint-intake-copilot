"""A deterministic, offline stand-in for an LLM (keyword rules).

It lets anyone run the demo and the tests with no API key and no cost. It returns JSON exactly like
a real model would, so the same validation path is exercised. Its evidence quotes are real
sentences from the text, as a well-behaved model's would be.
"""

import json
import re

from app.domain.enums import Category, IndicatorType, Priority
from app.domain.redaction import RedactedText

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")

# First match wins, so the more specific categories come first.
_CATEGORY_KEYWORDS: list[tuple[Category, tuple[str, ...]]] = [
    (Category.FRAUD_AND_SCAMS, ("fraud", "scam", "never made", "unauthorised", "didn't make")),
    (Category.COLLECTIONS_AND_ARREARS, ("debt collect", "arrears", "bailiff")),
    (Category.FEES_AND_CHARGES, ("fee", "charge", "interest")),
    (Category.LENDING_AND_AFFORDABILITY, ("loan", "credit limit", "afford", "mortgage")),
    (Category.PAYMENTS_AND_TRANSFERS, ("transfer", "payment", "direct debit", "standing order")),
    (Category.ADVICE_AND_MIS_SELLING, ("mis-sold", "missold", "advised", "not explained")),
    (Category.ACCOUNT_ADMINISTRATION, ("statement", "account closed", "address", "card arrived")),
    (Category.SERVICE_QUALITY, ("rude", "waiting", "delay", "hung up", "no reply", "ignored")),
]

_INDICATOR_KEYWORDS: dict[IndicatorType, tuple[str, ...]] = {
    IndicatorType.BEREAVEMENT: ("passed away", "died", "death", "funeral", "bereave"),
    IndicatorType.JOB_LOSS: ("lost my job", "redundan", "unemployed", "laid off"),
    IndicatorType.MENTAL_HEALTH: ("anxiety", "depress", "mental health", "hard to deal with"),
    IndicatorType.PHYSICAL_ILLNESS: ("hospital", "cancer", "illness", "surgery", "chemo"),
    IndicatorType.DISABILITY: ("disab", "wheelchair", "blind", "deaf"),
    IndicatorType.RELATIONSHIP_BREAKDOWN: ("divorce", "separated", "split up"),
    IndicatorType.FINANCIAL_HARDSHIP: ("can't afford", "cannot afford", "food bank", "into debt"),
    IndicatorType.LOW_CAPABILITY: ("don't understand", "english is not", "not good with"),
}


class FakeLlmProvider:
    name = "fake"
    model = "fake-keywords-v1"

    def complete(self, complaint: RedactedText, *, previous_error: str | None = None) -> str:
        text = complaint.value
        lowered = text.lower()
        category = next(
            (cat for cat, words in _CATEGORY_KEYWORDS if any(w in lowered for w in words)),
            Category.OTHER,
        )
        indicators = [
            {"type": indicator_type.value, "evidence_quote": sentence}
            for indicator_type, words in _INDICATOR_KEYWORDS.items()
            if (sentence := _first_sentence_containing(text, words))
        ]
        priority = Priority.HIGH if category is Category.FRAUD_AND_SCAMS else Priority.MEDIUM
        return json.dumps(
            {
                "category": category.value,
                "summary": _summary(text, category),
                "priority": priority.value,
                "vulnerability_indicators": indicators,
            }
        )


def _first_sentence_containing(text: str, words: tuple[str, ...]) -> str | None:
    for match in _SENTENCE.finditer(text):
        sentence = match.group(0).strip()
        if any(word in sentence.lower() for word in words):
            return sentence
    return None


def _summary(text: str, category: Category) -> str:
    subject = text.split("\n", 1)[0].removeprefix("Subject:").strip()
    label = category.value.replace("_", " ")
    return f"Complaint about {label}: {subject}"[:400]
