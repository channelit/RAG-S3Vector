from aws_cdk import RemovalPolicy, aws_s3 as s3
from constructs import Construct

from config import resource_name


def create_document_bucket(scope: Construct, config: dict) -> s3.Bucket:
    unique_id = config["naming"]["unique_id"]
    bucket_name = resource_name(config, f"{config['project_name']}-documents-{unique_id}")

    return s3.Bucket(
        scope,
        "DocumentBucket",
        bucket_name=bucket_name,
        encryption=s3.BucketEncryption.S3_MANAGED,
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        versioned=True,
        removal_policy=RemovalPolicy.DESTROY,
    )
