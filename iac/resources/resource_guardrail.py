from aws_cdk import aws_bedrock as bedrock
from constructs import Construct

from config import resource_name


def create_guardrail(scope: Construct, config: dict) -> dict:
    project_name = config["project_name"]

    guardrail = bedrock.CfnGuardrail(
        scope,
        "RagGuardrail",
        name=resource_name(config, f"{project_name}-guardrail"),
        description="Blocks harmful content and anonymizes PII in RAG responses",
        blocked_input_messaging="Your request contains content that cannot be processed.",
        blocked_outputs_messaging=(
            "The response was blocked because it may contain harmful or sensitive information."
        ),
        content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
            filters_config=[
                bedrock.CfnGuardrail.ContentFilterConfigProperty(
                    type="HATE", input_strength="HIGH", output_strength="HIGH"
                ),
                bedrock.CfnGuardrail.ContentFilterConfigProperty(
                    type="INSULTS", input_strength="HIGH", output_strength="HIGH"
                ),
                bedrock.CfnGuardrail.ContentFilterConfigProperty(
                    type="SEXUAL", input_strength="HIGH", output_strength="HIGH"
                ),
                bedrock.CfnGuardrail.ContentFilterConfigProperty(
                    type="VIOLENCE", input_strength="HIGH", output_strength="HIGH"
                ),
                bedrock.CfnGuardrail.ContentFilterConfigProperty(
                    type="MISCONDUCT", input_strength="HIGH", output_strength="HIGH"
                ),
                # PROMPT_ATTACK: block jailbreak attempts on input only
                bedrock.CfnGuardrail.ContentFilterConfigProperty(
                    type="PROMPT_ATTACK",
                    input_strength="HIGH",
                    output_strength="NONE",
                ),
            ]
        ),
        sensitive_information_policy_config=bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty(
            pii_entities_config=[
                bedrock.CfnGuardrail.PiiEntityConfigProperty(type="EMAIL", action="ANONYMIZE"),
                bedrock.CfnGuardrail.PiiEntityConfigProperty(type="PHONE", action="ANONYMIZE"),
                bedrock.CfnGuardrail.PiiEntityConfigProperty(type="NAME", action="ANONYMIZE"),
                bedrock.CfnGuardrail.PiiEntityConfigProperty(type="US_SOCIAL_SECURITY_NUMBER", action="BLOCK"),
                bedrock.CfnGuardrail.PiiEntityConfigProperty(
                    type="CREDIT_DEBIT_CARD_NUMBER", action="BLOCK"
                ),
            ]
        ),
    )

    # Pin a published version so Lambda can reference a stable identifier.
    guardrail_version = bedrock.CfnGuardrailVersion(
        scope,
        "RagGuardrailVersion",
        guardrail_identifier=guardrail.attr_guardrail_id,
    )

    return {"guardrail": guardrail, "guardrail_version": guardrail_version}
