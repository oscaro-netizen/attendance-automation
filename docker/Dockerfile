FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# No build toolchain is needed: every dependency ships a wheel.
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
        "fastapi~=0.139.0" \
        "uvicorn~=0.51.0" \
        "httpx~=0.27.0" \
        "pydantic-settings~=2.3.3" \
        "python-dotenv~=1.0.1"

COPY app ./app
COPY scripts ./scripts

# The token database lives on a mounted volume so it survives redeploys.
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
