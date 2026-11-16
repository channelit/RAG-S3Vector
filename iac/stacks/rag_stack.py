import aws_cdk as cdk
from aws_cdk import Stack
from config import load_config
from constructs import Construct
from resources.resource_flow import create_flow
from resources.resource_guardrail import create_guardrail
from resources.resource_iam import create_lambda_role
from resources.resource_knowledge_base import (
    PRIMARY,
    construct_id_prefix,
    create_knowledge_bases,
    knowledge_base_settings,
)
from resources.resource_lambda import create_lambda_functions
from resources.resource_s3 import create_document_bucket
from resources.resource_s3_vectors import create_vector_resources

# from resources.resource_fargate import create_fargate_resources  # UI runs locally via docker-compose
from resources.resource_ui import create_ui_resources

# knowledge_base.additional key the scraper writes its collection summary for.
SUMMARY_KNOWLEDGE_BASE = "summary"


class RagStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, env_name: str = "dev", **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        config = load_config(env_name)

        # Apply common + env tags to all resources in this stack
        for key, value in config.get("tags", {}).items():
            cdk.Tags.of(self).add(key, value)

        document_bucket = create_document_bucket(self, config)

        vector_resources = create_vector_resources(self, config)
        vector_bucket_name = vector_resources["vector_bucket_name"]
        vector_index_name = vector_resources["vector_index_name"]

        guardrail_resources = create_guardrail(self, config)
        guardrail = guardrail_resources["guardrail"]
        guardrail_version = guardrail_resources["guardrail_version"]

        lambda_role = create_lambda_role(self, config, document_bucket, guardrail)

        # The Knowledge Bases' documents live in the documents bucket too, so the
        # ingestion Lambda (fired by every object) is told to skip their prefixes.
        kb_settings = knowledge_base_settings(config)

        lambda_functions = create_lambda_functions(
            self,
            config,
            lambda_role=lambda_role,
            document_bucket=document_bucket,
            guardrail_id=guardrail.attr_guardrail_id,
            guardrail_version=guardrail_version.attr_version,
            vector_bucket_name=vector_bucket_name,
            vector_index_name=vector_index_name,
            ignore_prefixes=[settings["source_prefix"] for settings in kb_settings.values()],
        )

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

        ui_resources = create_ui_resources(
            self,
            config,
            query_fn=lambda_functions["query_fn"],
        )

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
        cdk.CfnOutput(self, "VectorIndexName", value=vector_index_name)
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
        cdk.CfnOutput(self, "IngestionFunctionName", value=lambda_functions["ingestion_fn"].function_name)
        cdk.CfnOutput(self, "QueryFunctionName", value=lambda_functions["query_fn"].function_name)
        # No UiUrl when ui.cloudfront is off: the page has no distribution in front of it.
        if ui_resources["distribution"]:
            cdk.CfnOutput(
                self,
                "UiUrl",
                value=f"https://{ui_resources['distribution'].distribution_domain_name}",
            )
        cdk.CfnOutput(self, "UiBucketName", value=ui_resources["site_bucket"].bucket_name)
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
