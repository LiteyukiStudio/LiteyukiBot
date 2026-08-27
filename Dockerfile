FROM python:3.14-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build

RUN pip install --no-cache-dir uv==0.11.16

COPY pyproject.toml uv.lock README.md LICENSE LICENSE.en LICENSE.zh-CN ./
COPY src ./src
COPY packages ./packages
COPY examples ./examples

RUN uv sync --locked --no-dev --no-editable \
    --package liteyukibot-v7 \
    && /opt/venv/bin/liteyuki version

FROM python:3.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    LITEYUKI__CORE__DATA_DIR=/app/data \
    LITEYUKI__CORE__CACHE_DIR=/app/cache

WORKDIR /app

RUN groupadd --system --gid 10001 liteyuki \
    && useradd --system --uid 10001 --gid liteyuki --home-dir /app --no-create-home liteyuki \
    && mkdir -p /app/data /app/cache \
    && chown -R liteyuki:liteyuki /app

COPY --from=builder /opt/venv /opt/venv

VOLUME ["/app/data", "/app/cache"]

USER liteyuki

ENTRYPOINT ["liteyuki"]
CMD ["run"]
