#!/usr/bin/env bash
# Point the AWS CLI and AWS SDKs at a local AWS Emulator instance.
# Usage:
#   source examples/env-setup.sh [PORT]
# Default port is 9297.

EMULATOR_PORT="${1:-9297}"
EMULATOR_DIR="${HOME}/.aws/emulator/${EMULATOR_PORT}"

export AWS_ENDPOINT_URL="https://127.0.0.1:${EMULATOR_PORT}"
export AWS_SHARED_CREDENTIALS_FILE="${EMULATOR_DIR}/emulator_credentials"
export AWS_CONFIG_FILE="${EMULATOR_DIR}/config"
export AWS_CA_BUNDLE="${EMULATOR_DIR}/ca.pem"
export AWS_EC2_METADATA_DISABLED="true"
export AWS_DISABLE_HOST_PREFIX_INJECTION="true"
export AWS_REGION="us-east-1"
export AWS_DEFAULT_REGION="us-east-1"

# Node.js appends this certificate to its default trust store without breaking other HTTPS calls
export NODE_EXTRA_CA_CERTS="${EMULATOR_DIR}/ca.pem"

# Note: Only set SSL_CERT_FILE="${EMULATOR_DIR}/ca.pem" when running Rust (non-embedded) or .NET SDKs,
# as SSL_CERT_FILE replaces the system trust store for curl, git, and terraform init.

# Unset any variables that could supply real AWS credentials
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE


echo "Configured shell for AWS Emulator at ${AWS_ENDPOINT_URL}"
echo "Verifying caller identity (expect Account: 000000000000)..."
if command -v aws >/dev/null 2>&1 && [ -f "${AWS_CA_BUNDLE}" ]; then
  aws sts get-caller-identity
else
  echo "Note: Ensure aws-emulator is running on port ${EMULATOR_PORT} and AWS CLI is installed."
fi
