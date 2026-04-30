# StockInsight backend — uv-based image for Railway / Render / Fly.
#
# Two-stage: stage 1 installs deps via uv (cache-friendly), stage 2 runs.
# Railway sets $PORT dynamically; we honor it via start.sh.

FROM python:3.13-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

# uv — fast Python package manager.
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
# --frozen so lockfile is canonical; --no-dev skips test/dev deps.
RUN uv sync --frozen --no-dev

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Copy only the resolved venv from builder (smaller image).
COPY --from=builder /app/.venv /app/.venv

COPY app/ ./app/
COPY scripts/ ./scripts/
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY start.sh ./
RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"]
