# Step-by-Step Walkthrough of the AWS Emulator Examples

Every example in this directory has been tested and verified against the live **AWS Emulator** (`v1.0.341`). This guide walks you through running each one on your own machine from start to finish.

## Directory Overview

```text
.
├── env-setup.sh                      # Exports AWS Emulator env vars & unsets real AWS keys
├── cli-walkthrough.sh                # AWS CLI demo: S3 persistence & DynamoDB validation
├── docker/
│   ├── Dockerfile                    # Amazon Linux 2023 Minimal container image definition
│   └── run-emulator.sh               # Builds and starts the container on 127.0.0.1:9297
├── python-boto3/
│   ├── requirements.txt              # boto3 and pytest dependencies
│   ├── document_store.py             # Production S3 + DynamoDB class (zero emulator hacks)
│   ├── test_document_store.py        # Integration tests for DocumentStore
│   └── test_real_life_scenarios.py   # SNS->SQS, Lambda .zip, CloudFormation & Presigned URLs
├── terraform/
│   └── main.tf                       # S3, DynamoDB & SQS stack tested with terraform apply
├── rust-embedded/
│   ├── Cargo.toml                    # Rust project using aws-emulator-embedded crate
│   └── src/lib.rs                    # Parallel in-memory tests (no background process needed)
└── ci/
    └── github-actions.yml            # GitHub Actions pipeline with health polling & idle timeout
```

## Step 0: Start AWS Emulator

For all examples **except** Rust Embedded Mode (Step 6), you need a running `aws-emulator` instance listening on `https://127.0.0.1:9297`. Choose **Option A** (Linux Native) or **Option B** (Docker).

### Option A: Run Natively on Linux

Open **Terminal 1** and install/run the package:

```bash
# Debian / Ubuntu (amd64)
curl -fsSLo aws-emulator.deb https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS/latest/aws-emulator_amd64.deb
sudo apt-get install -y ./aws-emulator.deb

# Or RPM-based Linux (x86_64)
sudo dnf install -y https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS/latest/aws-emulator-x86_64.rpm

# Start the emulator in the foreground
aws-emulator --telemetry off
```

> **Tip for Arch Linux / Non-DEB/RPM Distros:** You can extract and run the binary directly using `bsdtar` (from `libarchive`, pre-installed on Arch) or `ar` (from `binutils`):
>
> ```bash
> mkdir -p /tmp/aws-emulator-pkg && cd /tmp/aws-emulator-pkg
> curl -fsSLo aws-emulator.deb https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS/latest/aws-emulator_amd64.deb
> bsdtar -xf aws-emulator.deb && bsdtar -xf data.tar.*
> /tmp/aws-emulator-pkg/opt/aws-emulator/bin/aws-emulator --telemetry off
> ```

### Option B: Run in Docker (macOS, Windows, or Linux)

Open **Terminal 1** in this directory (`examples/` or the root of `aws-simulator-test`) and run:

```bash
bash docker/run-emulator.sh 9297
```

**What this script does:**

1. Detects your CPU architecture (`x86_64` or `aarch64`) and builds `docker/Dockerfile`.
2. Pre-creates `~/.aws/emulator` on your host so Docker doesn't create it owned by `root`.
3. Runs the container with a 2 GiB memory limit (`--memory=2g --memory-swap=2g`), publishes `127.0.0.1:9297:9297` on loopback only, and mounts `~/.aws/emulator` so your host SDKs can read the generated `ca.pem` certificate and `emulator_credentials`.

Leave **Terminal 1** running and open **Terminal 2** in this directory (`examples/` or the root of `aws-simulator-test`) for the steps below.

## Step 1: Point Your Shell at the Emulator (`env-setup.sh`)

In **Terminal 2**, source `env-setup.sh`:

```bash
source ./env-setup.sh 9297
```

**What happens behind the scenes:**

- Sets `AWS_ENDPOINT_URL=https://127.0.0.1:9297`
- Sets `AWS_SHARED_CREDENTIALS_FILE=~/.aws/emulator/9297/emulator_credentials`
- Sets `AWS_CONFIG_FILE=~/.aws/emulator/9297/config`
- Sets `AWS_CA_BUNDLE=~/.aws/emulator/9297/ca.pem` (and `NODE_EXTRA_CA_CERTS` for Node.js)
- Sets `AWS_EC2_METADATA_DISABLED=true` and `AWS_DISABLE_HOST_PREFIX_INJECTION=true`
- Runs `unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE` so real AWS credentials in your shell cannot override the emulator
- Calls `aws sts get-caller-identity` (if the AWS CLI is installed) to confirm you see `"Account": "000000000000"`

You can also test the emulator's HTTPS health route directly with `curl`:

```bash
curl --cacert ~/.aws/emulator/9297/ca.pem https://127.0.0.1:9297/__admin/health
# Expected output: ok
```

## Step 2: Walkthrough 1: AWS CLI (`cli-walkthrough.sh`)

Requires: `aws` CLI v2 and `curl`.

Run the walkthrough script in **Terminal 2**:

```bash
bash ./cli-walkthrough.sh 9297
```

**What to observe:**

1. **Health Check Polling**: The script waits for `https://127.0.0.1:9297/__admin/health` to return `ok` using the emulator's generated `~/.aws/emulator/9297/ca.pem`.
2. **Stateful S3 Persistence**: Creates `amzn-s3-demo-bucket` and lists all buckets to show that state persists in memory across CLI invocations.
3. **Exact AWS Validation Error**: Attempts to create a DynamoDB table named `ab` (only 2 characters). The emulator rejects the call with the exact `ValidationException` message that real AWS returns (`Member must have length greater than or equal to 3`).
4. **DynamoDB Table Creation & Waiter**: Creates a valid table (`demo-orders`), runs `aws dynamodb wait table-exists` to wait for the table to transition from `CREATING` to `ACTIVE`, writes an item with `put-item`, and reads it back with `get-item`.

## Step 3: Walkthrough 2: Python & Boto3 Cross-Service App (`python-boto3/`)

Requires: Python 3.10+ and `venv`.

### 1. Set up a virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r python-boto3/requirements.txt
```

### 2. Inspect the application code (`python-boto3/document_store.py`)

Open `python-boto3/document_store.py`. Notice two important details:

- `boto3.client("s3")` and `boto3.resource("dynamodb")` have **no custom `endpoint_url` or credentials passed in code**. They work against the emulator purely via the environment variables from `env-setup.sh`.
- In `provision()`, after calling `create_table()`, we call `self.table.wait_until_exists(WaiterConfig={"Delay": 1, "MaxAttempts": 10})` because AWS Emulator accurately starts new DynamoDB tables in `CREATING` status before transitioning them to `ACTIVE`.

### 3. Run the `DocumentStore` integration tests

```bash
source ./env-setup.sh 9297
PYTHONPATH=python-boto3 pytest -v python-boto3/test_document_store.py
```

**Expected output:**

```text
python-boto3/test_document_store.py::test_running_against_emulator PASSED [ 33%]
python-boto3/test_document_store.py::test_save_and_retrieve_document PASSED [ 66%]
python-boto3/test_document_store.py::test_dynamodb_rejects_short_table_name PASSED [100%]

============================== 3 passed in 3.24s ===============================
```

## Step 4: Walkthrough 3: Real-Life Production Scenarios (`test_real_life_scenarios.py`)

Next, run `python-boto3/test_real_life_scenarios.py` to see four realistic cloud engineering patterns execute against the local emulator:

```bash
source ./env-setup.sh 9297
PYTHONPATH=python-boto3 pytest -v python-boto3/test_real_life_scenarios.py
```

**Expected output:**

```text
python-boto3/test_real_life_scenarios.py::test_sns_to_sqs_fanout PASSED [ 25%]
python-boto3/test_real_life_scenarios.py::test_lambda_zip_execution_and_sdk_calls PASSED [ 50%]
python-boto3/test_real_life_scenarios.py::test_cloudformation_stack_provisions_real_resources PASSED [ 75%]
python-boto3/test_real_life_scenarios.py::test_s3_presigned_url_upload_and_download PASSED [100%]

============================== 4 passed in 2.57s ===============================
```

**What each test in `test_real_life_scenarios.py` proves:**

1. **`test_sns_to_sqs_fanout`**:
   - Creates an SNS topic and an SQS queue, subscribes the queue to the topic, attaches an SQS Queue Policy allowing `sns.amazonaws.com` to call `sqs:SendMessage`, publishes an event to SNS, and receives the fanned-out message from SQS.
   - *Try this experiment*: Comment out `sqs.set_queue_attributes(...)` in the test and re-run `pytest`. The test will fail and **Terminal 1** will log a warning that the SQS queue policy denied SNS delivery, just like real AWS!
2. **`test_lambda_zip_execution_and_sdk_calls`**:
   - Creates an S3 bucket and an IAM execution role with `s3:PutObject` permission.
   - Packages a Python `handler(event, context)` function into an in-memory `.zip` archive, uploads it via `lambda.create_function(Runtime="python3.12")`, waits for `function_active_v2`, and invokes it synchronously.
   - AWS Emulator runs the Python handler **in-process** (no Docker needed!) under the function's IAM role, writes `result.txt` into the S3 bucket, and returns the payload.
3. **`test_cloudformation_stack_provisions_real_resources`**:
   - Calls `cloudformation.create_stack()` with a template declaring an `AWS::S3::Bucket` and an `AWS::SQS::Queue`.
   - Waits for `stack_create_complete` (`CREATE_IN_PROGRESS` -> `CREATE_COMPLETE`) and verifies with `s3.list_buckets()` and `sqs.get_queue_url()` that CloudFormation actually created those resources in the emulated S3 and SQS services.
4. **`test_s3_presigned_url_upload_and_download`**:
   - Generates presigned `put_object` and `get_object` URLs with `s3.generate_presigned_url()`.
   - Uses Python's standard library `urllib.request` (with no AWS SDK credentials) to HTTP `PUT` and `GET` file content via the presigned URLs.

## Step 5: Walkthrough 4: Terraform (`terraform/main.tf`)

Requires: `terraform` >= 1.5.0.

Because the `hashicorp/aws` provider uses the AWS SDK for Go v2, it reads `AWS_ENDPOINT_URL`, `AWS_SHARED_CREDENTIALS_FILE`, `AWS_CONFIG_FILE`, and `AWS_CA_BUNDLE` automatically.

### 1. Initialize the Terraform provider

> **Important:** Make sure `SSL_CERT_FILE` is **not** set when running `terraform init` so Terraform can verify `registry.terraform.io` using your system's root certificates. (`env-setup.sh` leaves `SSL_CERT_FILE` unset for this exact reason.)

```bash
cd terraform
terraform init
```

### 2. Source the emulator environment and run `terraform apply`

```bash
source ../env-setup.sh 9297
terraform apply -auto-approve
```

**Expected output:**

```text
aws_sqs_queue.app_queue: Creating...
aws_dynamodb_table.app_table: Creating...
aws_s3_bucket.app_bucket: Creating...
aws_s3_bucket.app_bucket: Creation complete after 0s [id=tf-emulator-demo-bucket]
aws_dynamodb_table.app_table: Creation complete after 3s [id=tf-emulator-orders]
aws_sqs_queue.app_queue: Creation complete after 25s [id=https://sqs.us-east-1.amazonaws.com/000000000000/tf-emulator-events-queue]

Apply complete! Resources: 3 added, 0 changed, 0 destroyed.

Outputs:

dynamodb_table_arn = "arn:aws:dynamodb:us-east-1:000000000000:table/tf-emulator-orders"
emulator_account_id = "000000000000"
s3_bucket_arn = "arn:aws:s3:::tf-emulator-demo-bucket"
sqs_queue_url = "https://sqs.us-east-1.amazonaws.com/000000000000/tf-emulator-events-queue"
```

### 3. Tear down the resources with `terraform destroy`

```bash
terraform destroy -auto-approve
cd ..
```

## Step 6: Walkthrough 5: Rust Embedded Mode (`rust-embedded/`)

Requires: Rust toolchain (`cargo`, `rustc`) and a C compiler (`gcc` or `clang`).
**Does NOT require a running `aws-emulator` process!**

In Embedded Mode, the emulator is compiled directly into your Rust test binary via the `aws-emulator-embedded` crate. Each test creates its own isolated in-memory `AwsEmulatorEmbedded` instance and passes `emulator.http_client()` to the AWS SDK for Rust.

### Run the parallel Rust tests

```bash
cd rust-embedded
cargo test -- --nocapture
```

> **Note on First Compile Time & Disk Usage:**
> Because `aws-emulator-embedded` compiles and links all 400+ emulated AWS service crates from the `aws/aws-emulator` Git repository, the **very first compile** takes ~15 to 30 minutes depending on your CPU.
> We included two important fixes in `rust-embedded/Cargo.toml` and `rust-embedded/Cargo.lock`:
>
> 1. `[profile.dev] debug = false` and `strip = "debuginfo"` in `Cargo.toml` prevents a `>4 GiB` 32-bit DWARF relocation overflow in the linker (`ld.lld`) and saves ~80 GB of disk space in `target/`.
> 2. `Cargo.lock` pins `malachite-bigint` to `0.12.0` to match `rustpython-stdlib v0.6.0`.

**Expected output once compiled:**

```text
running 2 tests
test tests::parallel_emulators_do_not_share_state ... ok
test tests::put_then_get_returns_the_body ... ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.11s
```

When you are done experimenting with Rust Embedded Mode, you can free the build artifacts at any time with:

```bash
cargo clean
cd ..
```

## Step 7: Walkthrough 6: GitHub Actions CI/CD (`.github/workflows/ci.yml` & `ci/github-actions.yml`)

Inspect `.github/workflows/ci.yml` (or `ci/github-actions.yml`) to see how to wire everything above into a CI pipeline with zero AWS credentials:

1. **Install**: Downloads `aws-emulator_amd64.deb` and installs it on `ubuntu-latest`.
2. **Start in Background with Safety Flags**:
   ```bash
   aws-emulator --idle-timeout 120 --telemetry off &
   ```
   `--idle-timeout 120` ensures the process exits automatically if no API requests arrive for 2 minutes.
3. **Wait for Readiness**: Polls `https://127.0.0.1:9297/__admin/health` using `--cacert ~/.aws/emulator/9297/ca.pem` before starting tests.
4. **Run Tests**: Sources `./env-setup.sh 9297` and runs `PYTHONPATH=python-boto3 pytest -v python-boto3/`.
