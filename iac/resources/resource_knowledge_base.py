"""Standard Bedrock Knowledge Base (S3 Vectors storage + S3 data source) used by
the container UI's RetrieveAndGenerate call.

Managed KBs reject RetrieveAndGenerate and ignore .metadata.json sidecars, so
this is a classic VECTOR knowledge base:

  * its own S3 Vectors index in the project's vector bucket — Bedrock needs
    AMAZON_BEDROCK_TEXT / AMAZON_BEDROCK_METADATA registered as non-filterable
    keys, which is immutable after index creation, so the Lambda pipeline's
    index cannot be shared;
  * an S3 data source on the documents bucket under `knowledge_base.source_prefix`
    (the scraper's uploads), whose sidecar attributes (date_numeric, ...) are
    indexed as filterable metadata.
"""

from aws_cdk import aws_bedrock as bedrock, aws_iam as iam, aws_s3 as s3, custom_resources as cr
from constructs import Construct

from config import resource_name


def create_knowledge_base(
    scope: Construct,
    config: dict,
    document_bucket: s3.Bucket,
    vector_bucket_name: str,
    vector_bucket_cr: cr.AwsCustomResource,
) -> dict:
    project_name = config["project_name"]
    kb_config = config["knowledge_base"]
    embedding_model_id = kb_config["embedding_model_id"]
    dimension = kb_config["vector_dimension"]
    source_prefix = kb_config["source_prefix"]
    region, account = scope.region, scope.account

    kb_name = resource_name(config, f"{project_name}-kb")
    kb_index_name = resource_name(config, f"{project_name}-kb-index")
    index_arn = f"arn:aws:s3vectors:{region}:{account}:bucket/{vector_bucket_name}/index/{kb_index_name}"
    embedding_model_arn = f"arn:aws:bedrock:{region}::foundation-model/{embedding_model_id}"

    kb_index_cr = cr.AwsCustomResource(
        scope,
        "KnowledgeBaseIndex",
        install_latest_aws_sdk=True,  # S3Vectors is not in Lambda's built-in SDK
        on_create=cr.AwsSdkCall(
            service="S3Vectors",
            action="CreateIndex",
            parameters={
                "vectorBucketName": vector_bucket_name,
                "indexName": kb_index_name,
                "dataType": "float32",
                "dimension": dimension,
                "distanceMetric": "cosine",
                "metadataConfiguration": {
                    "nonFilterableMetadataKeys": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
                },
            },
            physical_resource_id=cr.PhysicalResourceId.of(f"{vector_bucket_name}/{kb_index_name}"),
        ),
        on_delete=cr.AwsSdkCall(
            service="S3Vectors",
            action="DeleteIndex",
            parameters={"vectorBucketName": vector_bucket_name, "indexName": kb_index_name},
        ),
        policy=cr.AwsCustomResourcePolicy.from_statements([
            iam.PolicyStatement(actions=["s3vectors:CreateIndex", "s3vectors:DeleteIndex"], resources=["*"])
        ]),
    )
    kb_index_cr.node.add_dependency(vector_bucket_cr)

    # Service role Bedrock assumes to embed documents and read/write the index.
    kb_role = iam.Role(
        scope,
        "KnowledgeBaseRole",
        assumed_by=iam.ServicePrincipal(
            "bedrock.amazonaws.com",
            conditions={
                "StringEquals": {"aws:SourceAccount": account},
                "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{region}:{account}:knowledge-base/*"},
            },
        ),
    )
    kb_role.add_to_policy(
        iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=[embedding_model_arn])
    )
    kb_role.add_to_policy(
        iam.PolicyStatement(
            actions=[
                "s3vectors:GetIndex",
                "s3vectors:QueryVectors",
                "s3vectors:PutVectors",
                "s3vectors:GetVectors",
                "s3vectors:DeleteVectors",
                "s3vectors:ListVectors",
            ],
            resources=[index_arn],
        )
    )
    kb_role.add_to_policy(
        iam.PolicyStatement(
            actions=["s3:ListBucket"],
            resources=[document_bucket.bucket_arn],
            conditions={"StringEquals": {"aws:ResourceAccount": account}},
        )
    )
    kb_role.add_to_policy(
        iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[document_bucket.arn_for_objects(f"{source_prefix}*")],
            conditions={"StringEquals": {"aws:ResourceAccount": account}},
        )
    )

    knowledge_base = bedrock.CfnKnowledgeBase(
        scope,
        "KnowledgeBase",
        name=kb_name,
        description="CBP CSMS messages (scraper uploads + metadata sidecars) for the container UI",
        role_arn=kb_role.role_arn,
        knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
            type="VECTOR",
            vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                embedding_model_arn=embedding_model_arn,
                embedding_model_configuration=bedrock.CfnKnowledgeBase.EmbeddingModelConfigurationProperty(
                    bedrock_embedding_model_configuration=bedrock.CfnKnowledgeBase.BedrockEmbeddingModelConfigurationProperty(
                        dimensions=dimension,
                        embedding_data_type="FLOAT32",
                    )
                ),
            ),
        ),
        storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
            type="S3_VECTORS",
            s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                index_arn=index_arn,
            ),
        ),
    )
    knowledge_base.node.add_dependency(kb_index_cr)
    # Bedrock validates the role's permissions at create time — wait for the inline policy.
    for child in kb_role.node.find_all():
        if isinstance(child, iam.CfnPolicy):
            knowledge_base.node.add_dependency(child)

    data_source = bedrock.CfnDataSource(
        scope,
        "KnowledgeBaseDataSource",
        name=resource_name(config, f"{project_name}-kb-source"),
        knowledge_base_id=knowledge_base.attr_knowledge_base_id,
        data_deletion_policy="DELETE",
        data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
            type="S3",
            s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                bucket_arn=document_bucket.bucket_arn,
                inclusion_prefixes=[source_prefix],
            ),
        ),
    )

    return {
        "knowledge_base": knowledge_base,
        "data_source": data_source,
        "kb_role": kb_role,
        "kb_index_cr": kb_index_cr,
        "kb_index_name": kb_index_name,
    }
