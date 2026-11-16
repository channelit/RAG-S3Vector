from aws_cdk import aws_iam as iam
from aws_cdk import custom_resources as cr
from config import resource_name
from constructs import Construct


def create_vector_resources(scope: Construct, config: dict) -> dict:
    """The S3 Vectors bucket. It holds one index per knowledge base, and each
    knowledge base creates its own (resource_knowledge_base.py)."""
    project_name = config["project_name"]
    unique_id = config["naming"]["unique_id"]
    vector_bucket_name = resource_name(config, f"{project_name}-vectors-{unique_id}")

    vector_bucket_cr = cr.AwsCustomResource(
        scope,
        "VectorBucket",
        install_latest_aws_sdk=True,  # S3Vectors is not in Lambda's built-in SDK
        on_create=cr.AwsSdkCall(
            service="S3Vectors",
            action="CreateVectorBucket",
            parameters={"vectorBucketName": vector_bucket_name},
            physical_resource_id=cr.PhysicalResourceId.of(vector_bucket_name),
        ),
        on_delete=cr.AwsSdkCall(
            service="S3Vectors",
            action="DeleteVectorBucket",
            parameters={"vectorBucketName": vector_bucket_name},
        ),
        policy=cr.AwsCustomResourcePolicy.from_statements([
            iam.PolicyStatement(
                actions=["s3vectors:CreateVectorBucket", "s3vectors:DeleteVectorBucket"],
                resources=["*"],
            )
        ]),
    )

    return {
        "vector_bucket_cr": vector_bucket_cr,
        "vector_bucket_name": vector_bucket_name,
    }
