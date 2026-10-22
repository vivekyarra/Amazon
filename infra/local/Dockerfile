# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS web
WORKDIR /app
COPY package*.json tsconfig.json vite.config.ts ./
COPY apps/judge-godmode-console apps/judge-godmode-console
COPY packages/physical-contract-schema packages/physical-contract-schema
RUN --mount=type=secret,id=proxy_ca,target=/run/secrets/proxy-ca.pem,mode=0444,required=false \
    if [ -f /run/secrets/proxy-ca.pem ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy-ca.pem; fi; \
    npm ci --no-audit --no-fund && npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.0 /uv /usr/local/bin/uv
WORKDIR /app
RUN --mount=type=secret,id=proxy_ca,target=/run/secrets/proxy-ca.pem,mode=0444,required=false \
    if [ -f /run/secrets/proxy-ca.pem ]; then echo 'Acquire::https::CaInfo "/run/secrets/proxy-ca.pem";' > /etc/apt/apt.conf.d/90-build-ca; fi; \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update -o APT::Update::Error-Mode=any && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgles2 libegl1 ffmpeg && \
    rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/90-build-ca
ENV UV_COMPILE_BYTECODE=1 PYTHONPATH=/app/apps/mcp-orchestrator DATA_DIR=/data GUIDED_MODE=true
ARG ENABLE_LIVE_RUNTIME=false
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=proxy_ca,target=/run/secrets/proxy-ca.pem,mode=0444,required=false \
    if [ -f /run/secrets/proxy-ca.pem ]; then export SSL_CERT_FILE=/run/secrets/proxy-ca.pem; fi; \
    if [ "$ENABLE_LIVE_RUNTIME" = "true" ]; then uv sync --frozen --no-dev --extra aws --extra ring-video; else uv sync --frozen --no-dev; fi && useradd --create-home --uid 10001 app && mkdir /data && chown app:app /data
COPY --chown=app:app apps/mcp-orchestrator apps/mcp-orchestrator
COPY --chown=app:app packages/testing-fixtures packages/testing-fixtures
COPY --from=web --chown=app:app /app/dist dist
USER app
EXPOSE 8080
VOLUME ["/data"]
CMD ["/app/.venv/bin/uvicorn", "done_irl.api:app", "--host", "0.0.0.0", "--port", "8080"]
