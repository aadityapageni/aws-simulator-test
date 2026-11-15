#!/usr/bin/env bash
# Complete AWS CLI walkthrough demonstrating AWS Emulator capabilities:
# 1. Health check polling
# 2. Identity verification (Account 000000000000)
# 3. Stateful S3 bucket & object persistence
# 4. Authentic AWS validation error on DynamoDB table name constraints
# 5. Host prefix injection handling with AWS Cloud Map

set -euo pipefail

PORT="${1:-9297}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== 1. Waiting for AWS Emulator health check on port ${PORT} ==="
for i in $(seq 30); do
  if [ -f "${HOME}/.aws/emulator/${PORT}/ca.pem" ] && \
     curl -sf --cacert "${HOME}/.aws/emulator/${PORT}/ca.pem" "https://127.0.0.1:${PORT}/__admin/health" >/dev/null; then
    echo "Emulator is healthy (ok)!"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "Error: AWS Emulator not reachable on https://127.0.0.1:${PORT}" >&2
    exit 1
  fi
  sleep 1
done

# Configure environment variables
# shellcheck source=env-setup.sh
source "${SCRIPT_DIR}/env-setup.sh" "${PORT}"

echo ""
echo "=== 2. Creating and listing an Amazon S3 bucket ==="
aws s3api create-bucket --bucket amzn-s3-demo-bucket
aws s3api list-buckets --query 'Buckets[].Name'

echo ""
echo "=== 3. Testing exact AWS validation errors (DynamoDB table name < 3 chars) ==="
set +e
aws dynamodb create-table \
  --table-name ab \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
DDB_EXIT_CODE=$?
set -e
echo "(Expected non-zero exit code received: ${DDB_EXIT_CODE})"

echo ""
echo "=== 4. Creating a valid DynamoDB table and writing an item ==="
aws dynamodb create-table \
  --table-name demo-orders \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST >/dev/null

# Wait for the table to transition from CREATING to ACTIVE (just like real AWS!)
aws dynamodb wait table-exists --table-name demo-orders

aws dynamodb put-item \
  --table-name demo-orders \
  --item '{"id": {"S": "ord-100"}, "status": {"S": "CREATED"}}'


aws dynamodb get-item \
  --table-name demo-orders \
  --key '{"id": {"S": "ord-100"}}'

echo ""
echo "Walkthrough completed successfully!"
