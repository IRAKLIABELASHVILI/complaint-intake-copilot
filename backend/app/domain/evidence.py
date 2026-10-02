"""Evidence quotes: one rule for the model and for handlers. A quote counts only if its words
appear in the text in the same order. Whitespace differences (line breaks) are ignored."""


def squash_whitespace(text: str) -> str:
    return " ".join(text.split())


def quote_appears_in(quote: str, text: str) -> bool:
    return squash_whitespace(quote) in squash_whitespace(text)
