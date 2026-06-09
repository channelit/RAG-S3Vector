from aws_cdk import (
    RemovalPolicy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_lambda as lambda_,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
)
from constructs import Construct

from config import resource_name


def create_ui_resources(
    scope: Construct,
    config: dict,
    query_fn: lambda_.Function,
) -> dict:
    """Static SPA in S3 + CloudFront, with /api/* routed to the query lambda's Function URL."""
    project_name = config["project_name"]
    unique_id = config["naming"]["unique_id"]
    site_bucket_name = resource_name(config, f"{project_name}-ui-{unique_id}")

    # 1) Private bucket for the static site (CloudFront reaches it via OAC)
    site_bucket = s3.Bucket(
        scope,
        "UiSiteBucket",
        bucket_name=site_bucket_name,
        encryption=s3.BucketEncryption.S3_MANAGED,
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        removal_policy=RemovalPolicy.DESTROY,
        auto_delete_objects=True,
    )

    # 2) Public Function URL on the existing query lambda (CloudFront in front)
    fn_url = query_fn.add_function_url(
        auth_type=lambda_.FunctionUrlAuthType.NONE,
        cors=lambda_.FunctionUrlCorsOptions(
            allowed_origins=["*"],
            allowed_methods=[lambda_.HttpMethod.ALL],
            allowed_headers=["content-type"],
        ),
    )

    # 3) CloudFront: S3 for "/" and Function URL for "/api/*"
    distribution = cloudfront.Distribution(
        scope,
        "UiDistribution",
        default_root_object="index.html",
        default_behavior=cloudfront.BehaviorOptions(
            origin=origins.S3BucketOrigin.with_origin_access_control(site_bucket),
            viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
        ),
        additional_behaviors={
            "/api/*": cloudfront.BehaviorOptions(
                origin=origins.FunctionUrlOrigin(fn_url),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
            ),
        },
    )

    # 4) Sync ../app/s3-static/ → bucket and invalidate CloudFront on every deploy
    s3deploy.BucketDeployment(
        scope,
        "UiDeployment",
        sources=[s3deploy.Source.asset("../app/s3-static")],
        destination_bucket=site_bucket,
        distribution=distribution,
        distribution_paths=["/*"],
    )

    return {
        "site_bucket": site_bucket,
        "distribution": distribution,
        "function_url": fn_url,
    }
