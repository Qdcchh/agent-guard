# Threshold gateway runner image

An amd64 Python 3.11 + Rust image for the threshold integration tests and the
fixed local demo. It combines:

- the project's wheel-mode Python base (`deploy/demo/Dockerfile`), which
  already pins the Python 3.11 runtime dependencies;
- `cryptography==50.0.2` (Ed25519 verification; Apache-2.0 OR BSD-3-Clause,
  maintained by the Python Cryptographic Authority, pinned in
  `requirements.lock` / `pyproject.toml`);
- the pinned Rust signer crate `tools/threshold_demo` built with the locked
  dependency graph in `Cargo.lock`.

## Build

```sh
# 1) The Python base, once (same command the demo deployment uses):
docker build --platform linux/amd64 -f deploy/demo/Dockerfile \
  --build-arg INSTALL_MODE=wheel -t agent-guard-normal-wheel:local .

# 2) The combined runner:
docker build --platform linux/amd64 -f deploy/threshold-runner/Dockerfile \
  --build-arg PYTHON_BASE=agent-guard-normal-wheel:local \
  -t agent-guard-threshold-runner:local .
```

If a compatible project image already exists (for example
`agent-guard-normal-wheel:4ee1803d-b709-453d-9ab5-7da652495d54` from an
earlier verified run), pass it as `PYTHON_BASE` and skip step 1.

## Run the threshold tests and demo

The container expects a reachable PostgreSQL 16 (for example the project's
`compose.test.yaml`). From the repository root:

```sh
export AGENT_GUARD_TEST_DATABASE_URL="postgresql://<test-only-user>:<test-only-pw>@host.docker.internal:55432/<test-db>"
docker run --rm -v "$PWD":/work -w /work \
  -e PYTHONPATH=/work/src \
  -e AGENT_GUARD_TEST_DATABASE_URL \
  -e AGENT_GUARD_A31_TEST_AUDIT_DATABASE_URL="$AGENT_GUARD_TEST_DATABASE_URL" \
  agent-guard-threshold-runner:local \
  /opt/venv/bin/python -m pytest tests/integration/test_threshold_gateway.py -q

docker run --rm -v "$PWD":/work -w /work \
  -e PYTHONPATH=/work/src -e AGENT_GUARD_THRESHOLD_DEMO_DSN="$AGENT_GUARD_TEST_DATABASE_URL" \
  agent-guard-threshold-runner:local \
  /opt/venv/bin/python tools/threshold_gateway_demo.py
```

The Rust signer binary is on `PATH` and also exported as
`AGENT_GUARD_THRESHOLD_DEMO_BIN=/usr/local/bin/threshold-demo`, which the test
fixtures use. The demo writes sanitized `result.json` evidence under
`artifacts/threshold-gateway-demo-live/<run id>/` and removes the signer
material, the isolated schema and the downstream database it created.

Limitations: this is a same-host teaching/test runner. It has no claim of
production hardening, separate organizational identities or an SM2 threshold
signature (the quorum signature is FROST-Ed25519).
