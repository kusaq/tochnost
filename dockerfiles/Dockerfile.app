FROM python:3.12.11-slim-bullseye

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache

WORKDIR /app

COPY alembic.ini .
COPY migrations/ migrations/
COPY static/ static/
COPY src/ .

CMD ["sh", "-c", "uv run alembic upgrade head && uv run python main.py"]
