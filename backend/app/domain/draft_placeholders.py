"""Gaps a person must fill in a response draft before it can be approved.

A draft is written from the redacted complaint, so it can contain privacy placeholders such as
[NAME_1] (see redaction.py), and the offline template asks for the handler's findings with
[Handler: ...]. Approving a draft that still has either would approve an unfinished letter.
"""

import re

_PLACEHOLDER = re.compile(r"\[(?:[A-Z]+(?:_[A-Z]+)*_\d+|Handler:[^\]]*)\]")


def unfilled_placeholders(body: str) -> list[str]:
    """Each placeholder left in the text, once, in the order it first appears."""
    return list(dict.fromkeys(_PLACEHOLDER.findall(body)))
