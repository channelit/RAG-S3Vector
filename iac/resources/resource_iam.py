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

    # Strip cross-region inference-profile prefix (e.g. "us.") to get the
    # underlying foundation-model ID the profile routes to.
    llm_foundation_model_id = llm_model_id.split(".", 1)[1] if llm_model_id.startswith(("us.", "eu.", "apac.")) else llm_model_id
    account = scope.account

    lambda_role.add_to_policy(
        iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[
                f"arn:aws:bedrock:{region}::foundation-model/{embedding_model_id}",
                # Inference profile (what the lambda actually invokes)
                f"arn:aws:bedrock:{region}:{account}:inference-profile/{llm_model_id}",
                # Foundation model in every region the profile may fan out to
                f"arn:aws:bedrock:*::foundation-model/{llm_foundation_model_id}",
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
