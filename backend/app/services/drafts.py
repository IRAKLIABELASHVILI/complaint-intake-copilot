"""Generate a draft from redacted data; human approval is a separate operation."""

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai.factory import build_provider
from app.ai.openai_provider import OpenAiCompatibleProvider
from app.ai.provider import ProviderRejectedError
from app.config import get_settings
from app.db.models import Case
from app.domain.redaction import redact


class DraftBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=8000)


def generate_draft(case: Case) -> tuple[str, str]:
    complaint = redact(f"Subject: {case.subject}\n{case.body}", sender_name=case.sender_name)
    provider = build_provider(get_settings())
    if isinstance(provider, OpenAiCompatibleProvider):
        raw = provider.draft_response(complaint)
    else:
        raw = json.dumps(
            {
                "body": "Dear customer,\n\nThank you for contacting us about your complaint. "
                "We acknowledge your concerns regarding: "
                + complaint.value.splitlines()[0].removeprefix("Subject: ")
                + "\n\n[Handler: add verified findings and next steps.]"
                "\n\nKind regards,\nComplaints team"
            }
        )
    try:
        return DraftBody.model_validate_json(raw).body, provider.name
    except ValidationError:
        raise ProviderRejectedError(
            "The model returned an invalid draft. Please try again."
        ) from None
