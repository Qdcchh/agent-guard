FROM python:3.11.17-slim-bookworm
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends openssl ca-certificates gcc libssl-dev libffi-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.lock requirements-dev.lock requirements-ci.lock ./
RUN python -m venv /opt/venv && pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements-ci.lock
COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
COPY deploy/demo ./deploy/demo
ARG INSTALL_MODE=wheel
RUN if [ "$INSTALL_MODE" = wheel ]; then pip wheel --no-build-isolation --no-deps . -w /wheels && pip install --no-deps /wheels/agent_guard-*.whl; else pip install --no-build-isolation --no-deps .; fi && pip check && rm -rf /build
WORKDIR /tmp
ENTRYPOINT []
