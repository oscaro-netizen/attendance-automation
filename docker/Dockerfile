# ----------------------------
# Builder Stage
# ----------------------------
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
ENV POETRY_REQUESTS_TIMEOUT=300

# Install Poetry
RUN pip install --no-cache-dir poetry

# Copy dependency files first (better Docker cache)
COPY pyproject.toml poetry.lock ./

# Install dependencies into /app/.venv
RUN poetry install --no-root --no-interaction --no-ansi

# ----------------------------
# Runtime Stage
# ----------------------------
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

# Copy virtual environment
COPY --from=builder /app/.venv /app/.venv

# Copy application source
COPY . .

# Install Chromium only
RUN apt-get update && \
    apt-get install -y --no-install-recommends chromium && \
    rm -rf /var/lib/apt/lists/*

# Install Playwright browser + required Linux dependencies
RUN playwright install --with-deps chromium

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
