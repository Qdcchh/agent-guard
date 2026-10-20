#!/bin/sh
# Build exact tags consumed by the existing fixed demo launchers.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
docker info >/dev/null
docker compose version
docker build --platform linux/amd64 -f deploy/demo/Dockerfile \
  --build-arg INSTALL_MODE=wheel -t agent-guard-normal-wheel:local .
docker build --platform linux/amd64 -f deploy/threshold-runner/Dockerfile \
  --build-arg PYTHON_BASE=agent-guard-normal-wheel:local \
  -t agent-guard-threshold-gateway-runner:20261017 .
docker build --platform linux/amd64 -f deploy/x402-runner/Dockerfile \
  --build-arg BASE_IMAGE=agent-guard-threshold-gateway-runner:20261017 \
  -t agent-guard-x402-runner:20261017 .
printf '%s\n' '镜像构建完成；尚未运行实验。启动：python3 tools/full_demo_server.py'
