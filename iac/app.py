import aws_cdk as cdk
from stacks.rag_stack import RagStack

app = cdk.App()

env_name = app.node.try_get_context("env") or "dev"

RagStack(
    app,
    "RagS3VectorStack",
    env_name=env_name,
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "us-east-1",
    ),
)

app.synth()
