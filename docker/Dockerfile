FROM python:3.13-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED 1

COPY pyproject.toml ./ 

RUN pip install --no-cache-dir -r <(grep "^\s*\S" pyproject.toml | sed -n "/^dependencies/,/^requires-python/p" | sed "1d;\$d" | sed "s/\s*\([a-zA-Z0-9_-]*\)~=\([0-9.]*\)/\1==\2/g")

COPY . .

RUN playwright install-deps && playwright install

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
