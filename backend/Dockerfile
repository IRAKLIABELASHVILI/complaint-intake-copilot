FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install only the dependencies first, so this layer stays cached when only the code changes.
# (pip needs a package to install, so we install an empty one and then remove it.)
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py \
    && pip install ".[dev]" \
    && pip uninstall -y complaint-intake-copilot \
    && rm -rf app build *.egg-info

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY seed ./seed
COPY tests ./tests

# Run as a non-root user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
