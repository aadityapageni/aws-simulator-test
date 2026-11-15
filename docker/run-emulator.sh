#!/usr/bin/env bash
# Build and run AWS Emulator in a Docker container with a 2 GiB memory limit.
# Publishes the port exclusively on 127.0.0.1 and mounts ~/.aws/emulator.

set -euo pipefail

PORT="${1:-9297}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect architecture for RPM selection
UNAME_ARCH="$(uname -m)"
if [[ "${UNAME_ARCH}" == "arm64" || "${UNAME_ARCH}" == "aarch64" ]]; then
  RPM_ARCH="aarch64"
else
  RPM_ARCH="x86_64"
fi

echo "Building aws-emulator Docker image for ${RPM_ARCH}..."
docker build --build-arg ARCH="${RPM_ARCH}" -t aws-emulator "${SCRIPT_DIR}"

# Pre-create shared directory so Docker does not create it owned by root on Linux
mkdir -p "${HOME}/.aws/emulator"

USER_FLAGS=()
if [[ "$(uname -s)" == "Linux" ]]; then
  USER_FLAGS=(--user "$(id -u):$(id -g)")
fi

echo "Starting AWS Emulator container on https://127.0.0.1:${PORT} ..."
exec docker run --rm \
  --memory=2g --memory-swap=2g \
  "${USER_FLAGS[@]}" \
  -p "127.0.0.1:${PORT}:${PORT}" \
  -e HOME="${HOME}" \
  -v "${HOME}/.aws/emulator:${HOME}/.aws/emulator" \
  aws-emulator -p "${PORT}"
