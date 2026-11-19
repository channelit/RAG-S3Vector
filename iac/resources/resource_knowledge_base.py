"""Standard Bedrock Knowledge Bases (S3 Vectors storage + S3 data source).

The primary one (the `knowledge_base` config section) holds the CSMS messages
and is what the container UI's RetrieveAndGenerate call and the flow's
`messages` route query. Each entry under `knowledge_base.additional` creates
another knowledge base the flow can route to (see resource_flow.py), such as
the scraper's collection-summary documents.

Managed KBs reject RetrieveAndGenerate and ignore .metadata.json sidecars, so
these are classic VECTOR knowledge bases, each with:

  * its own S3 Vectors index in the project's vector bucket — Bedrock needs
    AMAZON_BEDROCK_TEXT / AMAZON_BEDROCK_METADATA registered as non-filterable
    keys, which is immutable after index creation, so the Lambda pipeline's
    index cannot be shared;
  * an S3 data source on the documents bucket under its `source_prefix`
    (the scraper's uploads), whose sidecar attributes (date_numeric, ...) are
    indexed as filterable metadata;
  * its own service role, scoped to that prefix and that index.
"""

import re

from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import custom_resources as cr
from config import resource_name
from constructs import Construct

# Name routes use for the primary knowledge base (the `knowledge_base` section itself).
PRIMARY = "primary"

_KEY_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def knowledge_base_settings(config: dict) -> dict[str, dict]:
    """Settings of every knowledge base, keyed by the name routes refer to:
    "primary" plus each key under `knowledge_base.additional`. Additional
    entries inherit embedding_model_id / vector_dimension from the primary."""
    base = config["knowledge_base"]
    settings = {PRIMARY: {k: v for k, v in base.items() if k != "additional"}}
    for key, overrides in (base.get("additional") or {}).items():
        if key == PRIMARY or not _KEY_RE.match(key):
            raise ValueError(
                f"knowledge_base.additional.{key}: use lowercase letters, digits and single hyphens "
                f'(and not "{PRIMARY}", which names the knowledge_base section itself)'
            )
        if "source_prefix" not in (overrides or {}):
            raise ValueError(f"knowledge_base.additional.{key} needs a source_prefix")
        settings[key] = {
            "embedding_model_id": base["embedding_model_id"],
            "vector_dimension": base["vector_dimension"],
            **overrides,
        }

    # A prefix inside another one would put the same documents into two knowledge bases.
    prefixes = {key: cfg["source_prefix"] for key, cfg in settings.items()}
    for key, prefix in prefixes.items():
        for other, other_prefix in prefixes.items():
            if key != other and prefix.startswith(other_prefix):
                raise ValueError(
                    f"Knowledge base source prefixes overlap: {key} ({prefix!r}) is inside {other} ({other_prefix!r})"
                )
    return settings


def construct_id_prefix(key: str) -> str:
    """Prefix for a knowledge base's construct IDs and stack outputs. Empty for
    the primary one, so its CloudFormation logical IDs never change."""
    return "" if key == PRIMARY else "".join(part.capitalize() for part in key.split("-"))


def create_knowledge_bases(
    scope: Construct,
    config: dict,
    document_bucket: s3.Bucket,
    vector_bucket_name: str,
    vector_bucket_cr: cr.AwsCustomResource,
) -> dict[str, dict]:
    """Create every configured knowledge base. Returns {name: resources}."""
    return {
        key: create_knowledge_base(
            scope,
            config,
            document_bucket=document_bucket,
            vector_bucket_name=vector_bucket_name,
            vector_bucket_cr=vector_bucket_cr,
            key=key,
            kb_config=kb_config,
        )
        for key, kb_config in knowledge_base_settings(config).items()
    }


def _vector_ingestion(key: str, chunking) -> bedrock.CfnDataSource.VectorIngestionConfigurationProperty | None:
    """Chunking is fixed when a data source is created. Unset keeps Bedrock's
    default (about 300 tokens per chunk); "none" indexes each file as one chunk,
    for documents that are already written to be retrieved whole."""
    if chunking is None:
        return None
    if str(chunking).lower() != "none":
        raise ValueError(f'knowledge base {key}: chunking must be "none" or left out, not {chunking!r}')
    return bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
        chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(chunking_strategy="NONE")
    )


def create_knowledge_base(
    scope: Construct,
    config: dict,
    document_bucket: s3.Bucket,
    vector_bucket_name: str,
    vector_bucket_cr: cr.AwsCustomResource,
    key: str = PRIMARY,
    kb_config: dict | None = None,
) -> dict:
    project_name = config["project_name"]
    kb_config = kb_config or knowledge_base_settings(config)[key]
    embedding_model_id = kb_config["embedding_model_id"]
    dimension = kb_config["vector_dimension"]
    source_prefix = kb_config["source_prefix"]
    region, account = scope.region, scope.account

    # The primary knowledge base keeps its original construct IDs and names.
    id_prefix = construct_id_prefix(key)
    name_base = f"{project_name}-kb" if key == PRIMARY else f"{project_name}-{key}-kb"
    description = kb_config.get("description") or (
        "CBP CSMS messages (scraper uploads + metadata sidecars) for the container UI"
        if key == PRIMARY
        else f"{key} documents under {source_prefix}"
    )

    kb_name = resource_name(config, name_base)
    kb_index_name = resource_name(config, f"{name_base}-index")
    index_arn = f"arn:aws:s3vectors:{region}:{account}:bucket/{vector_bucket_name}/index/{kb_index_name}"
    embedding_model_arn = f"arn:aws:bedrock:{region}::foundation-model/{embedding_model_id}"

    kb_index_cr = cr.AwsCustomResource(
        scope,
        f"{id_prefix}KnowledgeBaseIndex",
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
        f"{id_prefix}KnowledgeBaseRole",
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
        f"{id_prefix}KnowledgeBase",
        name=kb_name,
        description=description,
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
        f"{id_prefix}KnowledgeBaseDataSource",
        name=resource_name(config, f"{name_base}-source"),
        knowledge_base_id=knowledge_base.attr_knowledge_base_id,
        data_deletion_policy="DELETE",
        data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
            type="S3",
            s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                bucket_arn=document_bucket.bucket_arn,
                inclusion_prefixes=[source_prefix],
            ),
        ),
        vector_ingestion_configuration=_vector_ingestion(key, kb_config.get("chunking")),
    )

    return {
        "knowledge_base": knowledge_base,
        "data_source": data_source,
        "kb_role": kb_role,
        "kb_index_cr": kb_index_cr,
        "kb_index_name": kb_index_name,
        "source_prefix": source_prefix,
    }
