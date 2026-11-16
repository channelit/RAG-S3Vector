import aws_cdk as cdk
from aws_cdk import Stack
from config import load_config
from constructs import Construct
from resources.resource_flow import create_flow
from resources.resource_guardrail import create_guardrail
from resources.resource_knowledge_base import (
    PRIMARY,
    construct_id_prefix,
    create_knowledge_bases,
)
from resources.resource_s3 import create_document_bucket
from resources.resource_s3_vectors import create_vector_resources

# from resources.resource_fargate import create_fargate_resources  # UI runs locally via docker-compose

# knowledge_base.additional key the scraper writes its collection summary for.
SUMMARY_KNOWLEDGE_BASE = "summary"


class RagStack(Stack):
    """Documents bucket → Bedrock Knowledge Bases (S3 Vectors) → Bedrock Flow.

    Every document is indexed by a knowledge base: each one reads its own folder
    of the documents bucket and owns one index in the vector bucket. Nothing else
    in the stack reads the documents or writes vectors.
    """

    def __init__(self, scope: Construct, construct_id: str, env_name: str = "dev", **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        config = load_config(env_name)

        # Apply common + env tags to all resources in this stack
        for key, value in config.get("tags", {}).items():
            cdk.Tags.of(self).add(key, value)

        document_bucket = create_document_bucket(self, config)

        vector_resources = create_vector_resources(self, config)
        vector_bucket_name = vector_resources["vector_bucket_name"]

        guardrail_resources = create_guardrail(self, config)
        guardrail = guardrail_resources["guardrail"]
        guardrail_version = guardrail_resources["guardrail_version"]

        # The primary knowledge base (CSMS messages) plus each knowledge_base.additional entry.
        knowledge_bases = create_knowledge_bases(
            self,
            config,
            document_bucket=document_bucket,
            vector_bucket_name=vector_bucket_name,
            vector_bucket_cr=vector_resources["vector_bucket_cr"],
        )
        kb_resources = knowledge_bases[PRIMARY]

        # Classifies each question and answers it from the knowledge base for its category.
        flow_resources = create_flow(
            self,
            config,
            knowledge_bases=knowledge_bases,
            guardrail=guardrail,
            guardrail_version=guardrail_version,
        )
        flow = flow_resources["flow"]
        flow_alias = flow_resources["flow_alias"]

        # Fargate disabled — UI container runs locally via docker-compose with
        # the same KB + guardrail wired in through .env.local (see the
        # ContainerUiEnv output below).
        # fargate_resources = create_fargate_resources(
        #     self,
        #     config,
        #     knowledge_base=kb_resources["knowledge_base"],
        #     guardrail=guardrail,
        #     guardrail_version=guardrail_version,
        #     flow=flow,
        #     flow_alias=flow_alias,
        # )

        cdk.CfnOutput(self, "DocumentBucketName", value=document_bucket.bucket_name)
        cdk.CfnOutput(self, "VectorBucketName", value=vector_bucket_name)
        cdk.CfnOutput(self, "GuardrailId", value=guardrail.attr_guardrail_id)
        cdk.CfnOutput(self, "GuardrailVersion", value=guardrail_version.attr_version)
        # KnowledgeBaseId / ...DataSourceId / ...IndexName for the primary knowledge
        # base, and the same three with a name prefix (SummaryKnowledgeBaseId, ...)
        # for each additional one.
        for key, resources in knowledge_bases.items():
            prefix = construct_id_prefix(key)
            cdk.CfnOutput(self, f"{prefix}KnowledgeBaseId", value=resources["knowledge_base"].attr_knowledge_base_id)
            cdk.CfnOutput(self, f"{prefix}KnowledgeBaseDataSourceId", value=resources["data_source"].attr_data_source_id)
            cdk.CfnOutput(self, f"{prefix}KnowledgeBaseIndexName", value=resources["kb_index_name"])
        cdk.CfnOutput(self, "FlowId", value=flow.attr_id)
        cdk.CfnOutput(self, "FlowAliasId", value=flow_alias.attr_id)
        cdk.CfnOutput(self, "FlowVersion", value=flow_resources["flow_version"].attr_version)
        # Paste-ready app/ui/container/.env.local lines: the standard KB, the
        # generation model, the stack's guardrail (ID + pinned version), and the
        # flow (read by backend/flow_ask.py; the backend itself does not call it).
        cdk.CfnOutput(
            self,
            "ContainerUiEnv",
            value=cdk.Fn.join(
                " ",
                [
                    f"KNOWLEDGE_BASE_ID={kb_resources['knowledge_base'].attr_knowledge_base_id}",
                    f"BEDROCK_MODEL_ARN={config['knowledge_base']['generation_model_id']}",
                    f"GUARDRAIL_ID={guardrail.attr_guardrail_id}",
                    f"GUARDRAIL_VERSION={guardrail_version.attr_version}",
                    f"FLOW_ID={flow.attr_id}",
                    f"FLOW_ALIAS_ID={flow_alias.attr_id}",
                ],
            ),
        )
        # Paste-ready app/scraper/.env.local lines: where messages and the
        # collection summary go, and the knowledge bases that index them.
        scraper_env = [
            f"S3_BUCKET_NAME={document_bucket.bucket_name}",
            f"S3_PREFIX={kb_resources['source_prefix']}",
            f"KNOWLEDGE_BASE_ID={kb_resources['knowledge_base'].attr_knowledge_base_id}",
            f"KB_DATA_SOURCE_ID={kb_resources['data_source'].attr_data_source_id}",
        ]
        summary_kb = knowledge_bases.get(SUMMARY_KNOWLEDGE_BASE)
        if summary_kb:
            scraper_env += [
                f"SUMMARY_PREFIX={summary_kb['source_prefix']}",
                f"SUMMARY_KNOWLEDGE_BASE_ID={summary_kb['knowledge_base'].attr_knowledge_base_id}",
                f"SUMMARY_KB_DATA_SOURCE_ID={summary_kb['data_source'].attr_data_source_id}",
            ]
        cdk.CfnOutput(self, "ScraperEnv", value=cdk.Fn.join(" ", scraper_env))
        # cdk.CfnOutput(self, "FargateUrl", value=f"http://{fargate_resources['alb'].load_balancer_dns_name}")
