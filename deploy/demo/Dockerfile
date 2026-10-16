FROM python:3.11.17-slim-bookworm
ARG INSTALL_MODE=wheel
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends openssl ca-certificates gcc libssl-dev libffi-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.lock requirements-dev.lock pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
COPY deploy/demo ./deploy/demo
RUN python -m venv /opt/venv && pip install --no-cache-dir setuptools==80.9.0 wheel==0.45.1 && pip install --no-cache-dir -r requirements-dev.lock && if [ "$INSTALL_MODE" = wheel ]; then pip wheel --no-build-isolation --no-deps . -w /wheels && pip install --no-deps /wheels/agent_guard-*.whl; else pip install --no-build-isolation --no-deps .; fi && pip check && rm -rf /build
WORKDIR /tmp
ENTRYPOINT []
