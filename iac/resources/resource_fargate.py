from aws_cdk import (
    aws_bedrock as bedrock,
    aws_ec2 as ec2,
    aws_ecr_assets as ecr_assets,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_iam as iam,
)
from constructs import Construct

from config import resource_name


def create_fargate_resources(
    scope: Construct,
    config: dict,
    knowledge_base: bedrock.CfnKnowledgeBase,
    guardrail: bedrock.CfnGuardrail,
    guardrail_version: bedrock.CfnGuardrailVersion,
) -> dict:
    """ECS Fargate + ALB for the container UI (currently disabled in rag_stack.py).

    The backend (app/ui/container/backend/main.py) makes one Bedrock
    RetrieveAndGenerate call per question against the standard Knowledge Base,
    generating with `knowledge_base.generation_model_id` and applying the
    stack's guardrail. The container env mirrors app/ui/container/.env.local.example
    (KNOWLEDGE_BASE_ID, BEDROCK_MODEL_ARN, GUARDRAIL_ID, GUARDRAIL_VERSION) and
    the task role is scoped to exactly those three resources. The ALTCHA
    captcha is served by the backend itself and is on by default, but with more
    than one task ALTCHA_HMAC_KEY must be shared — a secret, so inject it via
    Secrets Manager / `secrets=` rather than `environment=`; not wired here.
    """
    project_name = config["project_name"]
    region, account = scope.region, scope.account
    generation_model_id = config["knowledge_base"]["generation_model_id"]

    container_env = {
        "KNOWLEDGE_BASE_ID": knowledge_base.attr_knowledge_base_id,
        "BEDROCK_MODEL_ARN": generation_model_id,
        "GUARDRAIL_ID": guardrail.attr_guardrail_id,
        "GUARDRAIL_VERSION": guardrail_version.attr_version,
    }
    fargate_cfg = config.get("fargate", {})
    cpu = fargate_cfg.get("cpu", 256)
    memory = fargate_cfg.get("memory", 512)
    desired_count = fargate_cfg.get("desired_count", 1)
    container_port = fargate_cfg.get("container_port", 8000)

    # Public-only VPC (no NAT gateway); tasks get public IPs to reach ECR
    vpc = ec2.Vpc(
        scope,
        "FargateVpc",
        max_azs=2,
        nat_gateways=0,
        subnet_configuration=[
            ec2.SubnetConfiguration(
                name="public",
                subnet_type=ec2.SubnetType.PUBLIC,
                cidr_mask=24,
            )
        ],
    )

    cluster = ecs.Cluster(
        scope,
        "FargateCluster",
        cluster_name=resource_name(config, f"{project_name}-cluster"),
        vpc=vpc,
    )

    # Build + push Docker image to ECR during cdk deploy
    image_asset = ecr_assets.DockerImageAsset(
        scope,
        "UiContainerImage",
        directory="../app/ui/container",
    )

    task_role = iam.Role(
        scope,
        "FargateTaskRole",
        assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
    )
    # RetrieveAndGenerate against the KB (the KB's own service role handles the
    # vector index and embedding model behind it).
    task_role.add_to_policy(
        iam.PolicyStatement(
            actions=["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
            resources=[knowledge_base.attr_knowledge_base_arn],
        )
    )
    # Generation model: the inference profile plus the foundation model in
    # every region the profile may route to (same shape as resource_iam.py).
    if generation_model_id.startswith(("us.", "eu.", "apac.", "global.")):
        foundation_model_id = generation_model_id.split(".", 1)[1]
        model_arns = [
            f"arn:aws:bedrock:{region}:{account}:inference-profile/{generation_model_id}",
            f"arn:aws:bedrock:*::foundation-model/{foundation_model_id}",
        ]
    else:
        model_arns = [f"arn:aws:bedrock:{region}::foundation-model/{generation_model_id}"]
    task_role.add_to_policy(
        iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=model_arns)
    )
    # Guardrail applied in generationConfiguration.
    task_role.add_to_policy(
        iam.PolicyStatement(
            actions=["bedrock:ApplyGuardrail"],
            resources=[guardrail.attr_guardrail_arn],
        )
    )

    service = ecs_patterns.ApplicationLoadBalancedFargateService(
        scope,
        "FargateService",
        service_name=resource_name(config, f"{project_name}-ui"),
        cluster=cluster,
        cpu=cpu,
        memory_limit_mib=memory,
        desired_count=desired_count,
        assign_public_ip=True,
        public_load_balancer=True,
        min_healthy_percent=0,
        task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
            image=ecs.ContainerImage.from_docker_image_asset(image_asset),
            container_port=container_port,
            task_role=task_role,
            environment=container_env,
        ),
    )

    service.target_group.configure_health_check(path="/health")

    return {
        "service": service,
        "alb": service.load_balancer,
    }
