"""Application entry point: `uvicorn app.main:app`.

C# comparison: this is Program.cs: build the app, register middleware, map the routers.
"""

import logging
import re
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.api.routes import cases, system
from app.config import get_settings
from app.logging_config import configure_logging, correlation_id_var

logger = logging.getLogger(__name__)

CORRELATION_HEADER = "X-Correlation-ID"
_VALID_CORRELATION_ID = re.compile(r"^[A-Za-z0-9\-_.]{1,64}$")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Complaint Intake Copilot",
        version="0.1.0",
        description="AI-assisted intake for regulated complaints. All data is fictional.",
    )

    @app.middleware("http")
    async def correlation_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Accept the caller's id only if it looks safe; otherwise make a new one.
        incoming = request.headers.get(CORRELATION_HEADER, "")
        correlation_id = incoming if _VALID_CORRELATION_ID.match(incoming) else uuid.uuid4().hex
        token = correlation_id_var.set(correlation_id)
        try:
            response = await call_next(request)
            logger.info(
                "Request handled",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                },
            )
            response.headers[CORRELATION_HEADER] = correlation_id
            return response
        finally:
            correlation_id_var.reset(token)

    app.include_router(system.router)
    app.include_router(cases.router)
    return app


app = create_app()
