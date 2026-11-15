"""Real-world scenarios tested against live AWS Emulator:
1. SNS Topic -> SQS Queue fan-out with message delivery
2. AWS Lambda in-process execution (uploading a Python .zip function and invoking it)
3. AWS CloudFormation stack deployment that provisions actual S3 & SQS resources
4. S3 Presigned URLs (generating a presigned PUT/GET URL and using standard HTTP)
"""

import io
import json
import time
import urllib.request
import ssl
import uuid
import zipfile
import os

import boto3


def test_sns_to_sqs_fanout() -> None:
    """Publish a message to an SNS topic and verify it arrives in a subscribed SQS queue."""
    sns = boto3.client("sns")
    sqs = boto3.client("sqs")
    suffix = uuid.uuid4().hex[:8]

    topic_arn = sns.create_topic(Name=f"orders-topic-{suffix}")["TopicArn"]
    queue_url = sqs.create_queue(QueueName=f"orders-queue-{suffix}")["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]

    sns.subscribe(TopicArn=topic_arn, Protocol="sqs", Endpoint=queue_arn)

    # Just like real AWS, SQS requires a resource policy allowing sns.amazonaws.com to SendMessage!
    queue_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "sns.amazonaws.com"},
                "Action": "sqs:SendMessage",
                "Resource": queue_arn,
                "Condition": {"ArnEquals": {"aws:SourceArn": topic_arn}},
            }
        ],
    }
    sqs.set_queue_attributes(
        QueueUrl=queue_url, Attributes={"Policy": json.dumps(queue_policy)}
    )

    sns.publish(
        TopicArn=topic_arn,
        Message=json.dumps({"order_id": "ord-999", "event": "ORDER_PAID"}),
    )


    messages = sqs.receive_message(
        QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=2
    ).get("Messages", [])
    assert len(messages) == 1
    envelope = json.loads(messages[0]["Body"])
    payload = json.loads(envelope["Message"])
    assert payload == {"order_id": "ord-999", "event": "ORDER_PAID"}


def test_lambda_zip_execution_and_sdk_calls() -> None:
    """Deploy a Python Lambda .zip function, invoke it, and verify it writes to S3."""
    iam = boto3.client("iam")
    lambda_client = boto3.client("lambda")
    s3 = boto3.client("s3")
    suffix = uuid.uuid4().hex[:8]

    bucket_name = f"lambda-out-{suffix}"
    s3.create_bucket(Bucket=bucket_name)

    # Create an IAM execution role for the Lambda function (with S3 write permission!)
    role_name = f"lambda-role-{suffix}"
    role_arn = iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "lambda.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                    }
                ],
            }
        ),
    )["Role"]["Arn"]
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="allow-s3-write",
        PolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["s3:PutObject", "s3:GetObject"],
                        "Resource": f"arn:aws:s3:::{bucket_name}/*",
                    }
                ],
            }
        ),
    )


    # Build an in-memory .zip deployment package with a Python handler
    zip_buffer = io.BytesIO()
    handler_code = """
import json
import boto3

def handler(event, context):
    s3 = boto3.client("s3")
    bucket = event["bucket"]
    key = event["key"]
    msg = f"Processed {event['name']} inside Lambda {context.function_name}"
    s3.put_object(Bucket=bucket, Key=key, Body=msg.encode("utf-8"))
    return {"statusCode": 200, "message": msg}
"""
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.py", handler_code)

    fn_name = f"processor-{suffix}"
    lambda_client.create_function(
        FunctionName=fn_name,
        Runtime="python3.12",
        Role=role_arn,
        Handler="index.handler",
        Code={"ZipFile": zip_buffer.getvalue()},
    )

    # Wait until function is Active
    waiter = lambda_client.get_waiter("function_active_v2")
    waiter.wait(FunctionName=fn_name)

    # Invoke the function synchronously
    invoke_res = lambda_client.invoke(
        FunctionName=fn_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(
            {"bucket": bucket_name, "key": "result.txt", "name": "Ada"}
        ).encode("utf-8"),
    )
    response_payload = json.loads(invoke_res["Payload"].read().decode("utf-8"))
    assert response_payload["statusCode"] == 200
    assert f"Processed Ada inside Lambda {fn_name}" in response_payload["message"]

    # Verify the Lambda function actually wrote the object to S3
    s3_obj = s3.get_object(Bucket=bucket_name, Key="result.txt")
    assert (
        s3_obj["Body"].read().decode("utf-8")
        == f"Processed Ada inside Lambda {fn_name}"
    )


def test_cloudformation_stack_provisions_real_resources() -> None:
    """Deploy a CloudFormation stack and verify the S3 bucket & SQS queue exist in those services."""
    cfn = boto3.client("cloudformation")
    s3 = boto3.client("s3")
    sqs = boto3.client("sqs")
    suffix = uuid.uuid4().hex[:8]

    bucket_name = f"cfn-bucket-{suffix}"
    queue_name = f"cfn-queue-{suffix}"
    stack_name = f"demo-stack-{suffix}"

    template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Resources": {
            "AppBucket": {
                "Type": "AWS::S3::Bucket",
                "Properties": {"BucketName": bucket_name},
            },
            "AppQueue": {
                "Type": "AWS::SQS::Queue",
                "Properties": {"QueueName": queue_name},
            },
        },
        "Outputs": {
            "BucketNameOut": {"Value": {"Ref": "AppBucket"}},
            "QueueUrlOut": {"Value": {"Ref": "AppQueue"}},
        },
    }

    cfn.create_stack(StackName=stack_name, TemplateBody=json.dumps(template))
    cfn.get_waiter("stack_create_complete").wait(
        StackName=stack_name, WaiterConfig={"Delay": 1, "MaxAttempts": 15}
    )
    stack_desc = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]
    assert stack_desc["StackStatus"] == "CREATE_COMPLETE"


    # Verify the bucket and queue actually exist in the S3 and SQS services!
    all_buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    assert bucket_name in all_buckets

    queue_url = sqs.get_queue_url(QueueName=queue_name)["QueueUrl"]
    assert queue_name in queue_url


def test_s3_presigned_url_upload_and_download() -> None:
    """Generate S3 presigned PUT and GET URLs and execute them with standard HTTP (urllib)."""
    s3 = boto3.client("s3")
    suffix = uuid.uuid4().hex[:8]
    bucket_name = f"presigned-bucket-{suffix}"
    s3.create_bucket(Bucket=bucket_name)

    put_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket_name, "Key": "upload.txt"},
        ExpiresIn=300,
    )
    get_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": "upload.txt"},
        ExpiresIn=300,
    )

    ca_bundle = os.environ["AWS_CA_BUNDLE"]
    ssl_ctx = ssl.create_default_context(cafile=ca_bundle)

    # Upload via standard HTTP PUT using only the presigned URL (no AWS SDK!)
    put_req = urllib.request.Request(
        put_url, data=b"uploaded via presigned url!", method="PUT"
    )
    with urllib.request.urlopen(put_req, context=ssl_ctx) as resp:
        assert resp.status == 200

    # Download via standard HTTP GET using only the presigned URL
    with urllib.request.urlopen(get_url, context=ssl_ctx) as resp:
        assert resp.read() == b"uploaded via presigned url!"
