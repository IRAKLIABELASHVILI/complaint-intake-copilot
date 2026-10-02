"""Load demo data: two fictional tenants, their users, and ~15 fictional complaints.

Run with `python -m app.seed`. Safe to run again: a tenant that already exists is skipped.
Demo tokens are printed below and listed in the README. They are for local demos only.
"""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import hash_token
from app.config import get_settings
from app.db.models import Tenant, User
from app.db.session import new_session
from app.domain.enums import BankHolidayRegion, UserRole
from app.logging_config import configure_logging
from app.reference_data.bank_holidays import calendar_for_region
from app.schemas.cases import CaseCreate
from app.services.case_service import CaseService

logger = logging.getLogger(__name__)

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "complaints.json"

TENANTS = {
    "northbridge": "Northbridge Bank (fictional)",
    "harbourlane": "Harbour Lane Building Society (fictional)",
}

# (tenant slug, key, display name, role). Token = "demo-<key>".
USERS = [
    ("northbridge", "nb-handler", "Nina Handler", UserRole.HANDLER),
    ("northbridge", "nb-lead", "Leo Lead", UserRole.TEAM_LEAD),
    ("harbourlane", "hl-handler", "Hana Handler", UserRole.HANDLER),
    ("harbourlane", "hl-lead", "Luca Lead", UserRole.TEAM_LEAD),
]


def seed(session: Session) -> None:
    complaints = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    now = datetime.now(UTC)

    for slug, name in TENANTS.items():
        if session.scalars(select(Tenant).where(Tenant.slug == slug)).first() is not None:
            logger.info("Tenant already seeded, skipping", extra={"tenant_id": slug})
            continue

        tenant = Tenant(
            id=uuid.uuid4(),
            name=name,
            slug=slug,
            bank_holiday_region=BankHolidayRegion.ENGLAND_AND_WALES,
        )
        session.add(tenant)
        users = {
            key: User(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                email=f"{key}@{slug}.example.com",
                display_name=display_name,
                role=role,
                api_token_hash=hash_token(f"demo-{key}"),
            )
            for tenant_slug, key, display_name, role in USERS
            if tenant_slug == slug
        }
        session.add_all(users.values())
        session.commit()

        handler = next(user for user in users.values() if user.role == UserRole.HANDLER)
        service = CaseService(session, handler, calendar_for_region(tenant.bank_holiday_region))
        for index, complaint in enumerate(c for c in complaints if c["tenant"] == slug):
            service.create(
                CaseCreate(
                    subject=complaint["subject"],
                    body=complaint["body"],
                    sender_email=complaint["sender_email"],
                    sender_name=complaint["sender_name"],
                    received_at=now - timedelta(days=complaint["days_ago"], minutes=index),
                    external_message_id=f"<seed-{slug}-{index}@example.com>",
                )
            )
        logger.info("Seeded tenant", extra={"tenant_id": tenant.id})

    print("Demo API tokens (local demo only):")
    for slug, key, display_name, role in USERS:
        print(f"  {slug:<12} {role.value:<10} {display_name:<14} Bearer demo-{key}")


def main() -> None:
    configure_logging(get_settings().log_level)
    with new_session() as session:
        seed(session)


if __name__ == "__main__":
    main()
