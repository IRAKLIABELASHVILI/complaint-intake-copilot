"""Personal data redaction (US-6). Runs before any text leaves our system for the LLM.

Each personal value becomes a typed, numbered placeholder such as [EMAIL_1]. The same value always
gets the same placeholder within one complaint, so the model can still follow the story.

Rules run in a fixed order, most specific first: a card number must be recognised before its
digits could look like a phone or account number, and "DOB 12-03-80" must be read as a date of
birth before it could look like a sort code.

Other dates are kept: "I called on 12-03-2026" is the complaint's timeline, and a date alone does
not identify anyone. Only a date introduced as a date of birth is redacted.

Honest limitation: names are only caught when they are the sender's name or follow a greeting or
sign-off. Other names in free text (e.g. a relative mentioned in passing) are not. A production
system would add an NER model such as Microsoft Presidio.
"""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

_APOSTROPHES = "'" + chr(0x2019)  # straight and curly, as typed on a phone
# A capital, then letters / apostrophes / hyphens, ending in a lower-case letter:
# Margaret, O'Brien, McDonald, Smith-Jones. Not "NHS", not "I".
_NAME_WORD = rf"[A-Z][A-Za-z{_APOSTROPHES}\-]*[a-z]"
_NAME = rf"{_NAME_WORD}(?:[ \t]+{_NAME_WORD}){{0,2}}"  # one to three capitalised words
_TITLE = r"(?:Mr|Mrs|Ms|Miss|Dr|Mx)\.?[ \t]+"

# Words that follow "Dear ..." or "Regards, ..." but are not people's names.
_NOT_NAMES: Final = frozenset(
    {"sir", "madam", "team", "customer", "customers", "support", "complaints", "all", "there"}
)

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# National Insurance number: 2 letters, 6 digits, A-D. HMRC never issues D, F, I, Q, U or V, nor O
# as the second letter, nor the prefixes in the lookahead.
_NI_NUMBER = re.compile(
    r"\b(?!BG|GB|KN|NK|NT|TN|ZZ)[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]"
    r"[ \t]?\d{2}[ \t]?\d{2}[ \t]?\d{2}[ \t]?[A-D]\b",
    re.IGNORECASE,
)
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
_ORDINAL = r"(?:st|nd|rd|th)?"
_DATE = (
    rf"(?:\d{{1,2}}[/.\-]\d{{1,2}}[/.\-]\d{{2,4}}"  # 12/03/1980, 12-03-80, 12.03.1980
    rf"|\d{{1,2}}{_ORDINAL}[ \t]+{_MONTH}[ \t]+\d{{4}}"  # 12th March 1980
    rf"|{_MONTH}[ \t]+\d{{1,2}}{_ORDINAL},?[ \t]+\d{{4}})"  # March 12, 1980
)
_DATE_OF_BIRTH = re.compile(
    rf"\b(?:date[ \t]+of[ \t]+birth|d\.?o\.?b\.?|born(?:[ \t]+on)?)"
    rf"(?:[ \t]+(?:is|was))?[ \t]*[:\-]?[ \t]*(?P<value>{_DATE})",
    re.IGNORECASE,
)
_CARD = re.compile(r"(?<![\d\-])(?:\d[ \-]?){12,18}\d(?![\d\-])")
_SORT_CODE = re.compile(r"(?<![\d\-])\d{2}-\d{2}-\d{2}(?![\d\-])")  # not the "12-03-20" of a date
_PHONE = re.compile(r"(?<![\w+])(?:\+44[ \-]?(?:\(0\)[ \-]?)?|\(?0)(?:\d\)?[ \-]?){8,9}\d(?!\d)")
_ACCOUNT = re.compile(r"(?<![\d,.£$€\-])\d{8}(?!\d)(?![,.]\d)")  # exactly 8, not part of an amount
_POSTCODE = re.compile(r"\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b", re.IGNORECASE)
_GREETING = re.compile(rf"\b(?:Dear|Hi|Hello|Hey)[ \t]+(?:{_TITLE})?(?P<name>{_NAME})")
_SIGN_OFF = re.compile(
    r"\b(?:Kind regards|Best regards|Warm regards|Regards|Many thanks|Thanks|Thank you"
    r"|Yours sincerely|Yours faithfully|Sincerely|Best wishes|Cheers)"
    rf"(?:[ \t]*[,!]?[ \t]*\r?\n[ \t]*|,[ \t]*)(?:{_TITLE})?(?P<name>{_NAME})"
)


class RedactionError(Exception):
    """Redaction could not be completed. The text must not be sent anywhere (fail closed)."""


@dataclass(frozen=True)
class RedactedText:
    """Text that has been through `redact`. LLM providers accept only this type.

    `counts` says how many distinct values of each kind were replaced: safe to log, no values.
    """

    value: str
    counts: MappingProxyType[str, int]

    def truncated(self, max_chars: int) -> "RedactedText":
        return RedactedText(self.value[:max_chars], self.counts)


@dataclass
class _Placeholders:
    """Hands out [KIND_n] placeholders: same kind + same value -> same placeholder."""

    by_value: dict[tuple[str, str], str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def for_value(self, kind: str, value: str) -> str:
        key = (kind, value)
        if key not in self.by_value:
            self.counts[kind] = self.counts.get(kind, 0) + 1
            self.by_value[key] = f"[{kind}_{self.counts[kind]}]"
        return self.by_value[key]


def redact(text: str, *, sender_name: str | None = None) -> RedactedText:
    try:
        placeholders = _Placeholders()
        text = _replace(text, _EMAIL, "EMAIL", placeholders, normalise=str.lower)
        text = _replace(text, _NI_NUMBER, "NI_NUMBER", placeholders, normalise=_compact_upper)
        text = _replace(
            text,
            _DATE_OF_BIRTH,
            "DATE_OF_BIRTH",
            placeholders,
            normalise=_squashed_lower,
            group="value",  # keep "Date of birth:" so the model knows what was there
        )
        text = _replace(text, _CARD, "CARD", placeholders, normalise=_digits, accept=_is_card)
        text = _replace(text, _SORT_CODE, "SORT_CODE", placeholders, normalise=_digits)
        text = _replace(
            text, _PHONE, "PHONE", placeholders, normalise=_uk_phone, accept=_is_uk_phone
        )
        text = _replace(text, _ACCOUNT, "ACCOUNT", placeholders, normalise=_digits)
        text = _replace(text, _POSTCODE, "POSTCODE", placeholders, normalise=_postcode)
        text = _replace_names(text, sender_name, placeholders)
    except Exception as error:
        raise RedactionError(type(error).__name__) from error
    return RedactedText(text, MappingProxyType(dict(placeholders.counts)))


def _replace(
    text: str,
    pattern: re.Pattern[str],
    kind: str,
    placeholders: _Placeholders,
    *,
    normalise: Callable[[str], str],
    accept: Callable[[str], bool] = lambda _: True,
    group: str | int = 0,
) -> str:
    """Replace each match (or just its `group`) with the placeholder for its normalised value."""

    def substitute(match: re.Match[str]) -> str:
        found = match.group(group)
        if not accept(found):
            return match.group(0)
        whole, offset = match.group(0), match.start()
        before, after = whole[: match.start(group) - offset], whole[match.end(group) - offset :]
        return before + placeholders.for_value(kind, normalise(found)) + after

    return pattern.sub(substitute, text)


def _replace_names(text: str, sender_name: str | None, placeholders: _Placeholders) -> str:
    """Collect names (the sender's, and after greetings / sign-offs), then replace every
    occurrence. Parts of the sender's name ("Margaret" of "Margaret Ellison") count as them."""
    aliases: dict[str, str] = {}  # lower-case name or name part -> placeholder

    def register(name: str, parts: Iterable[str] = ()) -> None:
        placeholder = aliases.get(name.lower()) or placeholders.for_value("NAME", name.lower())
        for alias in (name, *parts):
            if len(alias) >= 2 and alias.lower() not in _NOT_NAMES:
                aliases.setdefault(alias.lower(), placeholder)

    if sender_name and sender_name.strip():
        full = " ".join(sender_name.split())
        register(full, full.split())
    for pattern in (_GREETING, _SIGN_OFF):
        for match in pattern.finditer(text):
            name = " ".join(match.group("name").split())
            if name.split()[0].lower() not in _NOT_NAMES:
                register(name)

    for alias in sorted(aliases, key=len, reverse=True):  # "Margaret Ellison" before "Margaret"
        text = _name_pattern(alias).sub(aliases[alias], text)
    return text


def _name_pattern(alias: str) -> re.Pattern[str]:
    """A full name matches in any case. A single word matches only capitalised, so a sender
    called "Will" does not turn every "will" in the text into a placeholder."""
    if " " in alias:
        return re.compile(rf"(?<![\w\[]){re.escape(alias)}(?!\w)", re.IGNORECASE)
    capitalised = alias[:1].upper() + alias[1:]
    return re.compile(rf"(?<![\w\[]){re.escape(capitalised)}(?!\w)")


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _is_card(value: str) -> bool:
    digits = _digits(value)
    return 13 <= len(digits) <= 19 and _passes_luhn(digits)


def _passes_luhn(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        digit = int(char)
        if position % 2 == 1:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        total += digit
    return total % 10 == 0


def _uk_phone(value: str) -> str:
    """The national form (leading 0), so +44 7700 900123 and 07700 900123 are the same number."""
    digits = _digits(value)
    if digits.startswith("44"):
        digits = "0" + digits[2:].removeprefix("0")
    return digits


def _is_uk_phone(value: str) -> bool:
    national = _uk_phone(value)
    # 01/02 landlines, 03 non-geographic, 07 mobiles; 10 or 11 digits including the 0.
    return len(national) in (10, 11) and national[:2] in ("01", "02", "03", "07")


def _postcode(value: str) -> str:
    return value.replace(" ", "").upper()


def _compact_upper(value: str) -> str:
    return "".join(value.split()).upper()


def _squashed_lower(value: str) -> str:
    return " ".join(value.split()).lower()
