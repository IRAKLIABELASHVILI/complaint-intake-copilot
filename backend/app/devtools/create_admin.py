"""Bootstrap an administrator locally: python -m app.devtools.create_admin."""

import argparse
import getpass
import secrets

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from app.db.models import Tenant
from app.db.repositories import AccountRepository, UserRepository
from app.db.session import new_session
from app.domain.enums import UserRole
from app.services.accounts import new_account


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--name", default="Administrator")
    parser.add_argument("--tenant", default="northbridge")
    parser.add_argument("--generate-password", action="store_true")
    args = parser.parse_args()
    try:
        # The same rule as the Accounts screen, so every account can sign in the same way.
        TypeAdapter(EmailStr).validate_python(args.email)
    except ValidationError:
        raise SystemExit(f"Not a valid email address: {args.email}") from None
    with new_session() as session:
        if AccountRepository(session).by_email(args.email):
            raise SystemExit("Account already exists; it has not been modified.")
        tenant = session.scalar(select(Tenant).where(Tenant.slug == args.tenant))
        if tenant is None:
            raise SystemExit("Tenant not found. Run migrations and seed first.")
        password = (
            secrets.token_urlsafe(18)
            if args.generate_password
            else getpass.getpass("Password (12+ characters): ")
        )
        if len(password) < 12:
            raise SystemExit("Password must contain at least 12 characters.")
        account = new_account(args.email, args.name, password, UserRole.TEAM_LEAD, admin=True)
        UserRepository(session, tenant.id).add(account)
        session.commit()
        print(f"Created {args.email}")
        if args.generate_password:
            print(f"Initial password: {password}")


if __name__ == "__main__":
    main()
