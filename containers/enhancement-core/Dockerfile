# Build with the repository root as context. No model weights or app state.
FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c AS build
WORKDIR /opt/enhancement
RUN pip install --no-cache-dir uv==0.10.4
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
ARG ENHANCEMENT_WITH_MODELS=0
RUN if [ "$ENHANCEMENT_WITH_MODELS" = "1" ]; then \
      uv sync --frozen --no-dev --extra enhancement-acp --extra models --no-editable; \
    elif [ "$ENHANCEMENT_WITH_MODELS" = "0" ]; then \
      uv sync --frozen --no-dev --extra enhancement-acp --no-editable; \
    else exit 1; fi

FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c AS runtime
WORKDIR /opt/enhancement
COPY --from=build /opt/enhancement/.venv /opt/enhancement/.venv
ENV PATH="/opt/enhancement/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
RUN useradd --system --uid 10001 --no-create-home enhancement
USER 10001:10001
ENTRYPOINT ["/opt/enhancement/.venv/bin/python", "-m", "prompt_enhancer.enhancement.cli"]
CMD ["--synthetic-benchmark", "--port", "8787"]
