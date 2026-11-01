FROM ghcr.io/astral-sh/uv:0.13.1 AS uv
FROM python:3.12.13-slim-bookworm AS builder
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src/ ./src/

FROM python:3.12.13-slim-bookworm
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY healthcheck.py /app/healthcheck.py
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 \
    MCP_TRANSPORT=streamable-http MCP_HOST=0.0.0.0 MCP_PORT=8765
USER 1000:1000
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD ["python", "/app/healthcheck.py"]
EXPOSE 8765
CMD ["python", "src/server.py"]
