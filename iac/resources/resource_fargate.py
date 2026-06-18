from aws_cdk import (
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
    query_fn_name: str,
    query_fn_arn: str,
) -> dict:
    project_name = config["project_name"]
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

    # Task role: only permission needed is invoking the query Lambda
    task_role = iam.Role(
        scope,
        "FargateTaskRole",
        assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
    )
    task_role.add_to_policy(
        iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=[query_fn_arn],
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
            environment={"QUERY_LAMBDA_NAME": query_fn_name},
        ),
    )

    service.target_group.configure_health_check(path="/health")

    return {
        "service": service,
        "alb": service.load_balancer,
    }
