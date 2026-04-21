from aws_cdk import aws_bedrock as bedrock, aws_iam as iam, aws_s3 as s3
from constructs import Construct


def create_lambda_role(
    scope: Construct,
    config: dict,
    document_bucket: s3.Bucket,
    guardrail: bedrock.CfnGuardrail,
) -> iam.Role:
    embedding_model_id = config["bedrock"]["embedding_model_id"]
    llm_model_id = config["bedrock"]["llm_model_id"]
    region = scope.region

    lambda_role = iam.Role(
        scope,
        "LambdaRole",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        managed_policies=[
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        ],
    )

    document_bucket.grant_read(lambda_role)

    lambda_role.add_to_policy(
        iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[
                f"arn:aws:bedrock:{region}::foundation-model/{embedding_model_id}",
                f"arn:aws:bedrock:{region}::foundation-model/{llm_model_id}",
            ],
        )
    )

    lambda_role.add_to_policy(
        iam.PolicyStatement(
            actions=["bedrock:ApplyGuardrail"],
            resources=[guardrail.attr_guardrail_arn],
        )
    )

    lambda_role.add_to_policy(
        iam.PolicyStatement(
            actions=[
                "s3vectors:PutVectors",
                "s3vectors:QueryVectors",
                "s3vectors:GetVectors",
                "s3vectors:DeleteVectors",
                "s3vectors:ListVectors",
            ],
            resources=["*"],
        )
    )

    return lambda_role
