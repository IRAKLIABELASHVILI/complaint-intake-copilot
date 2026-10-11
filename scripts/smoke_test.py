"""Smoke test of a running stack: the promise of `docker compose up` (docs/brief.md).

    docker compose up --build --detach --wait
    python scripts/smoke_test.py

It uses the system the way a browser does: through nginx, and through nginx's /api proxy to the
API. RabbitMQ, the outbox relay and the worker are proven by their effect: complaints get
analysed. Standard library only, so it runs anywhere Python 3.12 does.

Without Docker, point it at the local stack (app.devtools.local_stack) on a fresh database:
    python scripts/smoke_test.py --web "" --api http://127.0.0.1:8000
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

SEED_FILE = Path(__file__).resolve().parent.parent / "backend" / "seed" / "complaints.json"
TOKENS = {
    "northbridge": ("demo-nb-handler", "demo-nb-lead"),
    "harbourlane": ("demo-hl-handler", "demo-hl-lead"),
}
NOT_ANALYSED = {"new", "analysing"}
ANALYSIS_TIMEOUT_SECONDS = 180


class SmokeTestFailure(Exception):
    pass


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeTestFailure(message)


class Api:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def call(
        self, method: str, path: str, token: str, body: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        request = urllib.request.Request(
            self.base_url + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, None

    def get(self, path: str, token: str) -> Any:
        status, body = self.call("GET", path, token)
        expect(status == 200, f"GET {path} answered {status}")
        return body

    def cases(self, token: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = self.get("/cases?limit=100", token)["items"]
        return items


def wait_for(description: str, done: Callable[[], bool]) -> None:
    deadline = time.monotonic() + ANALYSIS_TIMEOUT_SECONDS
    while not done():
        expect(time.monotonic() < deadline, f"timed out waiting for {description}")
        time.sleep(2)


def check_web_app(web_url: str) -> None:
    with urllib.request.urlopen(web_url, timeout=10) as response:
        page = response.read().decode()
        expect('<div id="root">' in page, "the web app's page has no root element")
        expect(
            response.headers.get("Content-Security-Policy") is not None,
            "the web app is served without a Content-Security-Policy",
        )


def check_seeded_cases_are_analysed(api: Api) -> None:
    seeded = Counter(complaint["tenant"] for complaint in json.loads(SEED_FILE.read_text("utf-8")))
    handlers = {tenant: tokens[0] for tenant, tokens in TOKENS.items()}

    def all_analysed() -> bool:
        return all(
            case["status"] not in NOT_ANALYSED
            for token in handlers.values()
            for case in api.cases(token)
        )

    wait_for("the worker to analyse the seeded complaints", all_analysed)
    for tenant, token in handlers.items():
        cases = api.cases(token)
        expect(
            len(cases) >= seeded[tenant],
            f"{tenant} has {len(cases)} of {seeded[tenant]} cases",
        )
        failed = [case["reference"] for case in cases if case["status"] == "needs_human_review"]
        expect(failed == [], f"{tenant}: analysis failed for {failed}")
        detail = api.get(f"/cases/{cases[0]['id']}", token)
        expect(
            detail["suggestion"] is not None,
            f"{tenant}: an analysed case has no suggestion",
        )
        expect(detail["suggestion"]["provider"] == "fake", "the demo needs no API key")


def check_tenant_isolation(api: Api) -> None:
    northbridge_case = api.cases(TOKENS["northbridge"][0])[0]
    status, _ = api.call("GET", f"/cases/{northbridge_case['id']}", TOKENS["harbourlane"][0])
    expect(status == 404, f"another tenant's case answered {status}, not 404")


def check_dashboard(api: Api) -> None:
    handler, lead = TOKENS["northbridge"]
    dashboard = api.get("/dashboard", lead)
    expect(dashboard["open_cases"] > 0, "the dashboard counts no open cases")
    status, _ = api.call("GET", "/dashboard", handler)
    expect(status == 403, f"a handler opening the dashboard got {status}, not 403")


def check_a_new_complaint_end_to_end(api: Api) -> None:
    """Intake, outbox, relay, queue, worker, suggestion, decision, audit: the whole path."""
    handler = TOKENS["harbourlane"][0]
    status, case = api.call(
        "POST",
        "/cases",
        handler,
        {
            "subject": "Smoke test: charged twice",
            "body": "I was charged twice for the same payment and want one of them refunded.",
            "sender_email": "smoke.test@example.com",
            "external_message_id": f"<smoke-{uuid.uuid4()}@example.com>",
        },
    )
    expect(status == 201, f"creating a case answered {status}")
    expect(case["status"] in NOT_ANALYSED, "intake waited for the analysis")

    def analysed() -> bool:
        return bool(api.get(f"/cases/{case['id']}", handler)["status"] not in NOT_ANALYSED)

    wait_for("the new complaint to be analysed", analysed)
    detail = api.get(f"/cases/{case['id']}", handler)
    expect(detail["status"] == "awaiting_review", f"the new case is {detail['status']}")

    suggested = detail["suggestion"]["suggested_category"]
    status, _ = api.call("PUT", f"/cases/{case['id']}/category", handler, {"category": suggested})
    expect(status == 200, f"accepting the suggestion answered {status}")
    sources = {event["source"] for event in api.get(f"/cases/{case['id']}/audit", handler)}
    expect("accepted_suggestion" in sources, "the decision is not in the audit trail")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--web", default="http://127.0.0.1:8080/", help='"" to skip')
    parser.add_argument("--api", default="http://127.0.0.1:8080/api")
    args = parser.parse_args()
    api = Api(args.api)

    checks: list[tuple[str, Callable[[], None]]] = [
        (
            "seeded complaints are analysed by the fake model",
            lambda: check_seeded_cases_are_analysed(api),
        ),
        (
            "a tenant cannot open another tenant's case",
            lambda: check_tenant_isolation(api),
        ),
        (
            "team leads see the dashboard, handlers get 403",
            lambda: check_dashboard(api),
        ),
        (
            "a new complaint goes all the way to an audited decision",
            lambda: check_a_new_complaint_end_to_end(api),
        ),
    ]
    if args.web:
        checks.insert(0, ("the web app is served with its CSP", lambda: check_web_app(args.web)))

    for description, check in checks:
        try:
            check()
        except (SmokeTestFailure, OSError, KeyError, TypeError) as error:
            print(f"FAIL  {description}: {error!r}")
            return 1
        print(f"ok    {description}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
