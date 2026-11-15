"""Integration tests for DocumentStore running against AWS Emulator."""

import uuid

import boto3
import pytest
from botocore.exceptions import ClientError

from document_store import DocumentStore


def test_running_against_emulator() -> None:
    """Safety check: ensure tests are connected to AWS Emulator (Account 000000000000)."""
    sts = boto3.client("sts")
    identity = sts.get_caller_identity()
    assert identity["Account"] == "000000000000", (
        "Refusing to run integration tests against a non-emulator AWS account! "
        "Run `source examples/env-setup.sh` first."
    )


def test_save_and_retrieve_document() -> None:
    """Verify cross-service writes and reads across S3 and DynamoDB."""
    suffix = uuid.uuid4().hex[:8]
    store = DocumentStore(
        bucket_name=f"docs-bucket-{suffix}",
        table_name=f"docs-index-{suffix}",
    )
    store.provision()

    payload = {"customer": "Ada Lovelace", "items": ["Analytical Engine"], "total": 1843}
    saved_meta = store.save_document("invoice-001", payload)

    fetched = store.get_document("invoice-001")
    assert fetched["content"] == payload
    assert fetched["metadata"]["sha256"] == saved_meta["sha256"]
    assert fetched["metadata"]["size_bytes"] == saved_meta["size_bytes"]


def test_dynamodb_rejects_short_table_name() -> None:
    """Verify AWS Emulator enforces real DynamoDB table name length constraints."""
    suffix = uuid.uuid4().hex[:8]
    store = DocumentStore(
        bucket_name=f"valid-bucket-{suffix}",
        table_name="ab",  # Invalid: DynamoDB requires >= 3 characters
    )

    with pytest.raises(ClientError) as exc_info:
        store.provision()

    error = exc_info.value.response["Error"]
    assert error["Code"] == "ValidationException"
    assert "length greater than or equal to 3" in error["Message"]
