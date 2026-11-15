"""Cross-service S3 + DynamoDB example that runs unchanged against AWS Emulator or AWS."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import boto3


class DocumentStore:
    """Stores JSON documents in Amazon S3 and indexes metadata in Amazon DynamoDB."""

    def __init__(self, bucket_name: str, table_name: str) -> None:
        self.bucket_name = bucket_name
        self.table_name = table_name
        # Standard Boto3 clients—no hardcoded endpoint URLs or credentials
        self.s3 = boto3.client("s3")
        self.dynamodb = boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(table_name)

    def provision(self) -> None:
        """Create the backing S3 bucket and DynamoDB table, waiting until ACTIVE."""
        self.s3.create_bucket(Bucket=self.bucket_name)
        self.dynamodb.meta.client.create_table(
            TableName=self.table_name,
            AttributeDefinitions=[{"AttributeName": "doc_id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "doc_id", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        # Just like real AWS, CreateTable starts in CREATING status before becoming ACTIVE
        self.table.wait_until_exists(WaiterConfig={"Delay": 1, "MaxAttempts": 10})


    def save_document(self, doc_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Serialize payload to S3 and record its SHA-256 metadata in DynamoDB."""
        raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
        s3_key = f"documents/{doc_id}.json"

        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=raw_bytes,
            ContentType="application/json",
        )

        item: dict[str, Any] = {
            "doc_id": doc_id,
            "s3_key": s3_key,
            "sha256": sha256_hex,
            "size_bytes": len(raw_bytes),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.table.put_item(Item=item)
        return item

    def get_document(self, doc_id: str) -> dict[str, Any]:
        """Fetch document metadata from DynamoDB and read the JSON body from S3."""
        response = self.table.get_item(Key={"doc_id": doc_id})
        meta = response.get("Item")
        if not meta:
            raise KeyError(f"Document '{doc_id}' not found in DynamoDB index")

        obj = self.s3.get_object(Bucket=self.bucket_name, Key=meta["s3_key"])
        body = json.loads(obj["Body"].read().decode("utf-8"))
        return {"metadata": meta, "content": body}
