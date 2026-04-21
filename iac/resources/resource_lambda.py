from aws_cdk import Duration, aws_iam as iam, aws_lambda as lambda_, aws_s3 as s3, aws_s3_notifications as s3n
from constructs import Construct


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
    ingestion_cfg = config["lambda"]["ingestion"]
    query_cfg = config["lambda"]["query"]

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
        function_name=f"{project_name}-ingestion",
        runtime=lambda_.Runtime.PYTHON_3_12,
        handler="handler.lambda_handler",
        code=lambda_.Code.from_asset("../app/ingestion"),
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
        function_name=f"{project_name}-query",
        runtime=lambda_.Runtime.PYTHON_3_12,
        handler="handler.lambda_handler",
        code=lambda_.Code.from_asset("../app/query"),
        role=lambda_role,
        timeout=Duration.minutes(query_cfg["timeout_minutes"]),
        memory_size=query_cfg["memory_size"],
        environment=shared_env,
    )

    return {"ingestion_fn": ingestion_fn, "query_fn": query_fn}
