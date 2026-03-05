# chess-master backend
FROM python:3.12-slim

WORKDIR /app

# Install Stockfish, curl (for healthcheck), and system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    stockfish \
    && rm -rf /var/lib/apt/lists/*

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY chess-openings ./chess-openings
COPY alembic ./alembic
COPY alembic.ini ./

# Install project and dependencies
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev

# Non-root user for Celery (avoids SecurityWarning)
RUN useradd -m -u 1000 chess && chown -R chess:chess /app
USER chess

ENV PYTHONUNBUFFERED=1
ENV STOCKFISH_PATH=/usr/games/stockfish

EXPOSE 8000

CMD ["sh", "-c", "uv run alembic upgrade head && exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
