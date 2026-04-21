from aws_cdk import RemovalPolicy, aws_s3 as s3
from constructs import Construct


def create_document_bucket(scope: Construct, config: dict) -> s3.Bucket:
    project_name = config["project_name"]
    account = scope.account

    return s3.Bucket(
        scope,
        "DocumentBucket",
        bucket_name=f"{project_name}-documents-{account}",
        encryption=s3.BucketEncryption.S3_MANAGED,
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        versioned=True,
        removal_policy=RemovalPolicy.RETAIN,
    )
