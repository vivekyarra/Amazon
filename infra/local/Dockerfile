FROM node:24-bookworm-slim AS web
WORKDIR /app
COPY package*.json tsconfig.json vite.config.ts ./
COPY apps/judge-godmode-console apps/judge-godmode-console
COPY packages/physical-contract-schema packages/physical-contract-schema
RUN npm ci --no-audit --no-fund && npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.0 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 PYTHONPATH=/app/apps/mcp-orchestrator DATA_DIR=/data DEMO_MODE=true
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev && useradd --create-home --uid 10001 app && mkdir /data && chown app:app /data
COPY apps/mcp-orchestrator apps/mcp-orchestrator
COPY --from=web /app/dist dist
USER app
EXPOSE 8080
VOLUME ["/data"]
CMD ["/app/.venv/bin/uvicorn", "done_irl.api:app", "--host", "0.0.0.0", "--port", "8080"]
