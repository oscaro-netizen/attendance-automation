FROM python:3.11-slim-bookworm as builder

WORKDIR /app

ENV PYTHONUNBUFFERED 1

# Install Poetry
RUN pip install poetry

# Copy pyproject.toml and poetry.lock
COPY pyproject.toml poetry.lock ./ 

# Install project dependencies into a virtual environment
RUN poetry config virtualenvs.in-project true \
    && poetry install --no-root --no-interaction --no-ansi

# --- Runtime Stage ---
FROM python:3.11-slim-bookworm as runtime

WORKDIR /app

ENV PYTHONUNBUFFERED 1

# Copy the virtual environment from the builder stage
COPY --from=builder /app/.venv /app/.venv

# Add poetry to PATH (if needed for CMD, otherwise remove)
ENV PATH="/app/.venv/bin:$PATH"

# Install Playwright system dependencies and browsers
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-wqy-zenhei \
    fonts-noto-color-emoji \
    fonts-freefont-ttf \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Expose port for FastAPI
EXPOSE 8000

# Command to run the FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
