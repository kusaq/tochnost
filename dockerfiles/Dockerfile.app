FROM python:3.12.11-slim-bullseye

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# PyPI downloads can be slow/unreliable inside Docker; allow override via build arg.
ARG UV_DEFAULT_INDEX
ENV UV_LINK_MODE=copy \
    UV_HTTP_CONNECT_TIMEOUT=120 \
    UV_HTTP_TIMEOUT=300 \
    UV_HTTP_RETRIES=10 \
    UV_DEFAULT_INDEX=${UV_DEFAULT_INDEX}

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

COPY alembic.ini .
COPY migrations/ migrations/
COPY static/ static/
COPY src/ .

CMD ["sh", "-c", "uv run alembic upgrade head && uv run python main.py"]
