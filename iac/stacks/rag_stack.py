import aws_cdk as cdk
from aws_cdk import Stack
from constructs import Construct

from config import load_config
from resources.resource_guardrail import create_guardrail
from resources.resource_iam import create_lambda_role
from resources.resource_knowledge_base import create_knowledge_base
from resources.resource_lambda import create_lambda_functions
from resources.resource_s3 import create_document_bucket
from resources.resource_s3_vectors import create_vector_resources
# from resources.resource_fargate import create_fargate_resources  # UI runs locally via docker-compose
from resources.resource_ui import create_ui_resources


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

        lambda_functions = create_lambda_functions(
            self,
            config,
            lambda_role=lambda_role,
            document_bucket=document_bucket,
            guardrail_id=guardrail.attr_guardrail_id,
            guardrail_version=guardrail_version.attr_version,
            vector_bucket_name=vector_bucket_name,
            vector_index_name=vector_index_name,
        )

        kb_resources = create_knowledge_base(
            self,
            config,
            document_bucket=document_bucket,
            vector_bucket_name=vector_bucket_name,
            vector_bucket_cr=vector_resources["vector_bucket_cr"],
        )

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
        # )

        cdk.CfnOutput(self, "DocumentBucketName", value=document_bucket.bucket_name)
        cdk.CfnOutput(self, "VectorBucketName", value=vector_bucket_name)
        cdk.CfnOutput(self, "VectorIndexName", value=vector_index_name)
        cdk.CfnOutput(self, "GuardrailId", value=guardrail.attr_guardrail_id)
        cdk.CfnOutput(self, "GuardrailVersion", value=guardrail_version.attr_version)
        cdk.CfnOutput(self, "KnowledgeBaseId", value=kb_resources["knowledge_base"].attr_knowledge_base_id)
        cdk.CfnOutput(self, "KnowledgeBaseDataSourceId", value=kb_resources["data_source"].attr_data_source_id)
        cdk.CfnOutput(self, "KnowledgeBaseIndexName", value=kb_resources["kb_index_name"])
        cdk.CfnOutput(self, "IngestionFunctionName", value=lambda_functions["ingestion_fn"].function_name)
        cdk.CfnOutput(self, "QueryFunctionName", value=lambda_functions["query_fn"].function_name)
        cdk.CfnOutput(
            self,
            "UiUrl",
            value=f"https://{ui_resources['distribution'].distribution_domain_name}",
        )
        cdk.CfnOutput(self, "UiBucketName", value=ui_resources["site_bucket"].bucket_name)
        # Paste-ready app/ui/container/.env.local lines: the standard KB, the
        # generation model, and the stack's guardrail (ID + pinned version).
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
                ],
            ),
        )
        # cdk.CfnOutput(self, "FargateUrl", value=f"http://{fargate_resources['alb'].load_balancer_dns_name}")
