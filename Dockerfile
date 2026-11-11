# syntax=docker/dockerfile:1.7

# -----------------------------------------------------------------------------
# Stage 1: Deterministic dependency builder using uv + Python 3.12-slim
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY pyproject.toml README.md ./
COPY app ./app

RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python --no-cache .

# -----------------------------------------------------------------------------
# Stage 2: Hardened non-root runtime image
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8080 \
    MCP_LOG_FORMAT=json

RUN groupadd --gid 10001 mcpuser \
    && useradd --uid 10001 --gid 10001 --shell /usr/sbin/nologin --create-home mcpuser

WORKDIR /app

COPY --from=builder --chown=10001:10001 /opt/venv /opt/venv
COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 pyproject.toml README.md ./

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=3).read()" || exit 1

ENTRYPOINT ["python", "-m", "app.main"]
CMD ["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8080"]
