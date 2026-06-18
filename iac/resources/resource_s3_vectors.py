from aws_cdk import aws_iam as iam, custom_resources as cr
from constructs import Construct

from config import resource_name


def create_vector_resources(scope: Construct, config: dict) -> dict:
    project_name = config["project_name"]
    unique_id = config["naming"]["unique_id"]
    vector_bucket_name = resource_name(config, f"{project_name}-vectors-{unique_id}")
    vector_index_name = resource_name(config, f"{project_name}-index")
    vector_dimension = config["bedrock"]["vector_dimension"]

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

    vector_index_cr = cr.AwsCustomResource(
        scope,
        "VectorIndex",
        install_latest_aws_sdk=True,  # S3Vectors is not in Lambda's built-in SDK
        on_create=cr.AwsSdkCall(
            service="S3Vectors",
            action="CreateIndex",
            parameters={
                "vectorBucketName": vector_bucket_name,
                "indexName": vector_index_name,
                "dataType": "float32",
                "dimension": vector_dimension,
                "distanceMetric": "cosine",
                "metadataConfiguration": {
                    "nonFilterableMetadataKeys": ["text", "source", "chunk_id"]
                },
            },
            physical_resource_id=cr.PhysicalResourceId.of(
                f"{vector_bucket_name}/{vector_index_name}"
            ),
        ),
        on_delete=cr.AwsSdkCall(
            service="S3Vectors",
            action="DeleteIndex",
            parameters={
                "vectorBucketName": vector_bucket_name,
                "indexName": vector_index_name,
            },
        ),
        policy=cr.AwsCustomResourcePolicy.from_statements([
            iam.PolicyStatement(
                actions=["s3vectors:CreateIndex", "s3vectors:DeleteIndex"],
                resources=["*"],
            )
        ]),
    )
    vector_index_cr.node.add_dependency(vector_bucket_cr)

    return {
        "vector_bucket_cr": vector_bucket_cr,
        "vector_index_cr": vector_index_cr,
        "vector_bucket_name": vector_bucket_name,
        "vector_index_name": vector_index_name,
    }
