# Root context is restricted by the adjacent Dockerfile.dockerignore.
FROM docker:29.1.3-cli@sha256:4fa0ee1f3a7e4354c4ea34558b6d4ee32859baf4973d4c8ccc8e7fe3dd730c04 AS docker-cli
FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c AS build
WORKDIR /build
ENV UV_PROJECT_ENVIRONMENT=/opt/bench/.venv
RUN pip install --no-cache-dir uv==0.10.4
COPY bench/pyproject.toml bench/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY bench/src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c AS runtime
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates socat \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10002 --no-create-home bench \
    && mkdir -p /data && chown 10002:10002 /data \
    && mkdir -p /run/bench-gateway /run/bench-consumer-api \
    && chown 10002:10003 /run/bench-gateway /run/bench-consumer-api \
    && chmod 2770 /run/bench-gateway /run/bench-consumer-api
COPY --from=build /opt/bench/.venv /opt/bench/.venv
COPY contracts/enhancement /opt/bench/contracts/enhancement
ENV PATH="/opt/bench/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 \
    BENCH_CONTRACTS=/opt/bench/contracts/enhancement BENCH_DATABASE=/data/bench.sqlite3
ARG BENCH_REVISION=unknown
LABEL org.opencontainers.image.revision=$BENCH_REVISION
RUN printf '%s' "$BENCH_REVISION" > /opt/bench/.venv/lib/python3.12/site-packages/enhancement_bench/revision.txt
USER 10002:10002
ENTRYPOINT ["/opt/bench/.venv/bin/python", "-m", "enhancement_bench.cli"]
CMD ["serve"]
