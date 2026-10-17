# syntax=docker/dockerfile:1
# Combined amd64 test/demo runner for the threshold gateway work.
#
#   docker build --platform linux/amd64 \
#     -f deploy/threshold-runner/Dockerfile \
#     -t agent-guard-threshold-gateway-runner:20261017 .
#
# The Python base is the project's own wheel-mode demo image (built with
# deploy/demo/Dockerfile); it already carries the pinned Python 3.11 runtime
# dependencies. Only the pinned Ed25519 verification dependency is added here.
# The Rust signer is built for linux/amd64 in a separate stage.
ARG PYTHON_BASE=agent-guard-normal-wheel:4ee1803d-b709-453d-9ab5-7da652495d54

FROM --platform=linux/amd64 rust:1.99.1-slim-bookworm AS signer
WORKDIR /crate
COPY tools/threshold_demo/Cargo.toml tools/threshold_demo/Cargo.lock ./
COPY tools/threshold_demo/src ./src
RUN cargo build --locked --release \
    && cp target/release/agent-guard-threshold-demo /usr/local/bin/threshold-demo

FROM --platform=linux/amd64 ${PYTHON_BASE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN /opt/venv/bin/pip install --no-cache-dir cryptography==50.0.2
COPY --from=signer /usr/local/bin/threshold-demo /usr/local/bin/threshold-demo
ENV PATH=/opt/venv/bin:$PATH
ENV AGENT_GUARD_THRESHOLD_DEMO_BIN=/usr/local/bin/threshold-demo
WORKDIR /work
