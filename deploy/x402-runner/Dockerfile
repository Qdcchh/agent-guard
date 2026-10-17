# syntax=docker/dockerfile:1
# x402 runtime runner for the local test-chain payment stage.
#
# Base: the project's pinned amd64 Python 3.11 + Rust test/demo image (unchanged).
# Adds, all hash-pinned:
#   - reproducible V3 FROST signer at /usr/local/bin/threshold-demo, rebuilt from
#     this repository's pinned Rust source + Cargo.lock (rust:1.99.1-slim-bookworm,
#     same pin as the threshold runner). The unchanged base image ships a stale
#     V2-era signer at the same path; this layer replaces it so the standard
#     desktop launcher (which never sets AGENT_GUARD_THRESHOLD_DEMO_BIN) runs the
#     current V3 payment-digest protocol;
#   - official Foundry v1.8.5 anvil binary at /usr/local/bin/anvil
#     (release tarball sha256 6c66ffcc55fa4249197721baa3098bc208014ea1d8aa04b2ed50ac6bccffb226,
#      extracted binary sha256 00f97668e1ae0fcca118fd7d2d1b6d25c0496447a523ca6bc2dfd10958c99604);
#   - x402[evm]==2.25.0 and its full transitive lock (requirements-x402.lock);
#   - compiled Circle FiatTokenV2_2 artifact (ABI + bytecode) at /opt/x402/.
#
# Build from the repository root with absolute paths (arm64 Docker Desktop, no
# --platform on the build command; the stages pin their own platform):
#   docker build \
#     -f "/absolute/path/to/agent-guard-handoff/deploy/x402-runner/Dockerfile" \
#     --build-arg HTTP_PROXY=http://host.docker.internal:7897 \
#     --build-arg HTTPS_PROXY=http://host.docker.internal:7897 \
#     -t agent-guard-x402-runner:20261017 \
#     "/absolute/path/to/agent-guard-handoff"
#
# Proxy is only a build-time argument and is not persisted in the image.
ARG BASE_IMAGE=agent-guard-threshold-gateway-runner:20261017
ARG RUST_IMAGE=rust:1.99.1-slim-bookworm
ARG HTTP_PROXY
ARG HTTPS_PROXY

# (1) Reproducible V3 signer: source + Cargo.lock only, `--locked`, no ignored
# local binary. Cargo needs the build-time proxy for crates.io; the proxy env is
# confined to this scratch stage.
FROM --platform=linux/amd64 ${RUST_IMAGE} AS signer
ARG HTTP_PROXY
ARG HTTPS_PROXY
WORKDIR /crate
COPY tools/threshold_demo/Cargo.toml tools/threshold_demo/Cargo.lock ./
COPY tools/threshold_demo/src ./src
RUN HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} \
        cargo build --locked --release \
    && cp target/release/agent-guard-threshold-demo /usr/local/bin/threshold-demo \
    && /usr/local/bin/threshold-demo 2>&1 | grep -q "threshold demo rejected"

# (2) The runtime image itself: base image unchanged.
FROM ${BASE_IMAGE}

COPY dependencies/x402-20261017/vendor/anvil /usr/local/bin/anvil
RUN chmod 0755 /usr/local/bin/anvil && /usr/local/bin/anvil --version

COPY requirements-x402.lock /opt/x402/requirements-x402.lock
RUN /opt/venv/bin/pip install --no-cache-dir --require-hashes --only-binary=:all: \
        -r /opt/x402/requirements-x402.lock \
    && /opt/venv/bin/pip check

COPY dependencies/x402-20261017/FiatTokenV2_2.json /opt/x402/FiatTokenV2_2.json
RUN /opt/venv/bin/python -c "import json; \
    d = json.load(open('/opt/x402/FiatTokenV2_2.json')); \
    assert d['contractName'] == 'FiatTokenV2_2', d['contractName']; \
    assert d['bytecode'].startswith('0x') and len(d['bytecode']) > 20000; \
    assert len(d['abi']) > 0; \
    print('FiatTokenV2_2 artifact ok:', len(d['abi']), 'abi entries,', \
          (len(d['bytecode']) - 2) // 2, 'creation bytes')"

# (3) Replace the base image's stale signer with the reproducible V3 build and
# verify the executable starts (invalid invocation must be rejected).
COPY --from=signer /usr/local/bin/threshold-demo /usr/local/bin/threshold-demo
RUN /usr/local/bin/threshold-demo 2>&1 | grep -q "threshold demo rejected"

ENV PATH=/opt/venv/bin:$PATH
ENV X402_FIATTOKEN_ARTIFACT=/opt/x402/FiatTokenV2_2.json
ENV AGENT_GUARD_X402_ANVIL=/usr/local/bin/anvil
WORKDIR /work

# Runtime verification procedure (private in-container Anvil, no host ports).
COPY deploy/x402-runner/verify_runtime.py /opt/x402/verify_runtime.py
