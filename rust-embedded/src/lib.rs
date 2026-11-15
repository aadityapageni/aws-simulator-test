//! Demonstrates running AWS Emulator in embedded mode inside Rust tests.
//! Each test creates its own isolated in-memory emulator without opening network ports.

#[cfg(test)]
mod tests {
    use aws_emulator_embedded::{Authentication, AwsEmulatorEmbedded, EmbeddedOptions, Telemetry};
    use aws_sdk_s3::primitives::ByteStream;

    async fn s3_client_for_emulator(emulator: &AwsEmulatorEmbedded) -> aws_sdk_s3::Client {
        let config = aws_config::defaults(aws_config::BehaviorVersion::latest())
            .http_client(emulator.http_client())
            .region(aws_config::Region::new("us-east-1"))
            .credentials_provider(emulator.aws_credentials_provider())
            .load()
            .await;

        aws_sdk_s3::Client::new(&config)
    }

    #[tokio::test]
    async fn put_then_get_returns_the_body() {
        // Start an isolated in-process emulator for this test only.
        let emulator = AwsEmulatorEmbedded::new(
            EmbeddedOptions::default()
                .authentication(Authentication::On)
                .telemetry(Telemetry::Off),
        );

        let s3 = s3_client_for_emulator(&emulator).await;

        s3.create_bucket()
            .bucket("emulator-demo-bucket")
            .send()
            .await
            .unwrap();

        s3.put_object()
            .bucket("emulator-demo-bucket")
            .key("hello.txt")
            .body(ByteStream::from_static(b"hi from rust embedded mode"))
            .send()
            .await
            .unwrap();

        let got = s3
            .get_object()
            .bucket("emulator-demo-bucket")
            .key("hello.txt")
            .send()
            .await
            .unwrap();

        assert_eq!(
            got.body.collect().await.unwrap().to_vec(),
            b"hi from rust embedded mode"
        );
    }

    #[tokio::test]
    async fn parallel_emulators_do_not_share_state() {
        // Two emulators running in parallel can create the exact same bucket name
        // without colliding because their in-memory states are completely isolated.
        let emulator_a = AwsEmulatorEmbedded::default();
        let emulator_b = AwsEmulatorEmbedded::default();

        let s3_a = s3_client_for_emulator(&emulator_a).await;
        let s3_b = s3_client_for_emulator(&emulator_b).await;

        s3_a.create_bucket().bucket("shared-name").send().await.unwrap();
        s3_b.create_bucket().bucket("shared-name").send().await.unwrap();

        let buckets_a = s3_a.list_buckets().send().await.unwrap();
        let buckets_b = s3_b.list_buckets().send().await.unwrap();

        assert_eq!(buckets_a.buckets().len(), 1);
        assert_eq!(buckets_b.buckets().len(), 1);
    }
}
