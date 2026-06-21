from aws_cdk import BundlingOptions, Duration, aws_iam as iam, aws_lambda as lambda_, aws_s3 as s3, aws_s3_notifications as s3n
from constructs import Construct

from config import resource_name


def create_lambda_functions(
    scope: Construct,
    config: dict,
    lambda_role: iam.Role,
    document_bucket: s3.Bucket,
    guardrail_id: str,
    guardrail_version: str,
    vector_bucket_name: str,
    vector_index_name: str,
) -> dict:
    project_name = config["project_name"]
    embedding_model_id = config["bedrock"]["embedding_model_id"]
    llm_model_id = config["bedrock"]["llm_model_id"]
    lambda_cfg = config["lambda"]
    ingestion_cfg = lambda_cfg["ingestion"]
    query_cfg = lambda_cfg["query"]
    runtime = getattr(lambda_.Runtime, lambda_cfg["runtime"])
    handler = lambda_cfg["handler"]

    shared_env = {
        "VECTOR_BUCKET_NAME": vector_bucket_name,
        "VECTOR_INDEX_NAME": vector_index_name,
        "EMBEDDING_MODEL_ID": embedding_model_id,
        "LLM_MODEL_ID": llm_model_id,
        "GUARDRAIL_ID": guardrail_id,
        "GUARDRAIL_VERSION": guardrail_version,
    }

    ingestion_fn = lambda_.Function(
        scope,
        "IngestionFunction",
        function_name=resource_name(config, f"{project_name}-ingestion"),
        runtime=runtime,
        handler=handler,
        code=lambda_.Code.from_asset(
            ingestion_cfg["code_path"],
            bundling=BundlingOptions(
                image=runtime.bundling_image,
                command=[
                    "bash", "-c",
                    "pip install -r requirements.txt -t /asset-output --quiet "
                    "&& cp -au . /asset-output",
                ],
            ),
        ),
        role=lambda_role,
        timeout=Duration.minutes(ingestion_cfg["timeout_minutes"]),
        memory_size=ingestion_cfg["memory_size"],
        environment=shared_env,
    )

    document_bucket.add_event_notification(
        s3.EventType.OBJECT_CREATED,
        s3n.LambdaDestination(ingestion_fn),
    )

    query_fn = lambda_.Function(
        scope,
        "QueryFunction",
        function_name=resource_name(config, f"{project_name}-query"),
        runtime=runtime,
        handler=handler,
        code=lambda_.Code.from_asset(query_cfg["code_path"]),
        role=lambda_role,
        timeout=Duration.minutes(query_cfg["timeout_minutes"]),
        memory_size=query_cfg["memory_size"],
        environment=shared_env,
    )

    return {"ingestion_fn": ingestion_fn, "query_fn": query_fn}
