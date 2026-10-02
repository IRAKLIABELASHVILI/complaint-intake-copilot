"""How a complaint is laid out for the model: one place, so building and reading it agree."""

SUBJECT_LABEL = "Subject:"


def compose(subject: str, body: str) -> str:
    return f"{SUBJECT_LABEL} {subject}\n\n{body}"


def split(text: str) -> tuple[str, str]:
    """The (subject, body) of a composed text. Works on redacted text too."""
    first_line, _, body = text.partition("\n\n")
    return first_line.removeprefix(SUBJECT_LABEL).strip(), body


def without_label(quote: str) -> str:
    """A quote of the subject line should not include our label: those are not the customer's
    words, and the handler should see only what the customer wrote."""
    return quote.strip().removeprefix(SUBJECT_LABEL).strip()
