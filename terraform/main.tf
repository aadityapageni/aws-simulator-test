terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Look: Zero hardcoded endpoints or credentials needed!
# Because the Terraform AWS provider uses the AWS SDK for Go v2, it reads:
#   AWS_ENDPOINT_URL, AWS_SHARED_CREDENTIALS_FILE, AWS_CONFIG_FILE, and AWS_CA_BUNDLE
# directly from `source examples/env-setup.sh`.
provider "aws" {
  region = "us-east-1"

  # Because AWS_ENDPOINT_URL uses the IP address 127.0.0.1, S3 path-style
  # addressing works automatically, or you can set it explicitly here:
  s3_use_path_style = true
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "app_bucket" {
  bucket = "tf-emulator-demo-bucket"

  tags = {
    Environment = "local-emulator"
    ManagedBy   = "Terraform"
  }
}

resource "aws_dynamodb_table" "app_table" {
  name         = "tf-emulator-orders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "order_id"

  attribute {
    name = "order_id"
    type = "S"
  }

  tags = {
    Environment = "local-emulator"
  }
}

resource "aws_sqs_queue" "app_queue" {
  name                      = "tf-emulator-events-queue"
  visibility_timeout_seconds = 45
}

output "emulator_account_id" {
  description = "Confirms Terraform is talking to AWS Emulator (000000000000)"
  value       = data.aws_caller_identity.current.account_id
}

output "s3_bucket_arn" {
  value = aws_s3_bucket.app_bucket.arn
}

output "dynamodb_table_arn" {
  value = aws_dynamodb_table.app_table.arn
}

output "sqs_queue_url" {
  value = aws_sqs_queue.app_queue.url
}
