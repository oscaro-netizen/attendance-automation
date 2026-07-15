FROM python:3.11-slim-bookworm as builder

WORKDIR /app

ENV PYTHONUNBUFFERED 1

# Install Poetry
RUN pip install poetry

# Copy pyproject.toml and poetry.lock
COPY pyproject.toml poetry.lock ./ 

# Install project dependencies into a virtual environment
RUN poetry install --no-root --no-interaction --no-ansi

# --- Runtime Stage ---
FROM python:3.11-slim-bookworm as runtime

WORKDIR /app

ENV PYTHONUNBUFFERED 1

# Copy the virtual environment from the builder stage
COPY --from=builder /app/.venv /app/.venv

# Add poetry to PATH (if needed for CMD, otherwise remove)
ENV PATH="/app/.venv/bin:$PATH"

# Install Playwright system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    libnss3 \
    libfontconfig1 \
    libharfbuzz0b \
    libfreetype6 \
    libglib2.0-0 \
    libxkbcommon0 \
    libdbus-1-3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libxrender1 \
    libxshmfence1 \
    libxss1 \
    libxtst6 \
    libasound2 \
    libatk1.0-0 \
    libcairo2 \
    libcups2 \
    libgdk-pixbuf2.0-0 \
    libjpeg-turbo8 \
    libpangocairo-1.0-0 \
    libwebp6 \
    libwoff1 \
    libxcursor1 \
    libxinerama1 \
    libxmu6 \
    libxpm4 \
    libxres1 \
    libxslt1.1 \
    libxxf86vm1 \
    fonts-wqy-zenhei \
    fonts-noto-color-emoji \
    fonts-freefont-ttf \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright browsers (Chromium, Firefox, Webkit)
RUN poetry run playwright install chromium

COPY . .

# Expose port for FastAPI
EXPOSE 8000

# Command to run the FastAPI application
CMD ["poetry", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
