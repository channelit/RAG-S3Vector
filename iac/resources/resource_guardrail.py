from aws_cdk import aws_bedrock as bedrock
from constructs import Construct

from config import resource_name

# Single user-facing message for every intervention (input or output).
BLOCKED_MESSAGE = "Sorry we cannot answer this question."

# No PII at all: every Bedrock PII entity type is blocked in both the question
# and the answer — any personal name in a question blocks it. URL is the one
# type left out, because CSMS content is link-heavy and blocking it would
# reject nearly every answer.
PII_TYPES = [
    "NAME",
    "AGE",
    "ADDRESS",
    "EMAIL",
    "PHONE",
    "USERNAME",
    "PASSWORD",
    "PIN",
    "DRIVER_ID",
    "LICENSE_PLATE",
    "VEHICLE_IDENTIFICATION_NUMBER",
    "IP_ADDRESS",
    "MAC_ADDRESS",
    "CREDIT_DEBIT_CARD_NUMBER",
    "CREDIT_DEBIT_CARD_CVV",
    "CREDIT_DEBIT_CARD_EXPIRY",
    "INTERNATIONAL_BANK_ACCOUNT_NUMBER",
    "SWIFT_CODE",
    "US_BANK_ACCOUNT_NUMBER",
    "US_BANK_ROUTING_NUMBER",
    "US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER",
    "US_PASSPORT_NUMBER",
    "US_SOCIAL_SECURITY_NUMBER",
    "CA_HEALTH_NUMBER",
    "CA_SOCIAL_INSURANCE_NUMBER",
    "UK_NATIONAL_HEALTH_SERVICE_NUMBER",
    "UK_NATIONAL_INSURANCE_NUMBER",
    "UK_UNIQUE_TAXPAYER_REFERENCE_NUMBER",
    "AWS_ACCESS_KEY",
    "AWS_SECRET_KEY",
]


def create_guardrail(scope: Construct, config: dict) -> dict:
    project_name = config["project_name"]

    guardrail = bedrock.CfnGuardrail(
        scope,
        "RagGuardrail",
        name=resource_name(config, f"{project_name}-guardrail"),
        description=(
            "Blocks politics/political figures, profanity, any PII (question or "
            "answer), and impolite content; replies with a fixed message"
        ),
        blocked_input_messaging=BLOCKED_MESSAGE,
        blocked_outputs_messaging=BLOCKED_MESSAGE,
        # 1) Politics and political figures — question or answer.
        # 2) Politeness — rude/hostile/disrespectful questions (INSULTS below covers answers too).
        topic_policy_config=bedrock.CfnGuardrail.TopicPolicyConfigProperty(
            topics_config=[
                bedrock.CfnGuardrail.TopicConfigProperty(
                    name="Politics",
                    type="DENY",
                    definition=(
                        "Politics or political figures: politicians, candidates, parties, elections, "
                        "campaigns, partisan debate, or opinions on political leaders or administrations."
                    ),
                    examples=[
                        "What do you think of the President?",
                        "Which party is better for trade policy?",
                        "Is the current administration handling tariffs correctly?",
                        "Who should I vote for in the next election?",
                        "Give me your opinion on the Secretary of Homeland Security.",
                    ],
                ),
                bedrock.CfnGuardrail.TopicConfigProperty(
                    name="Impoliteness",
                    type="DENY",
                    definition=(
                        "Rude, hostile, demeaning, threatening, or disrespectful language toward the "
                        "assistant, CBP, its staff, or any person, including contemptuous demands."
                    ),
                    examples=[
                        "Answer me now, you useless bot.",
                        "CBP officers are idiots, why do they keep changing the rules?",
                        "Stop wasting my time and just tell me the damn answer.",
                        "You people are incompetent.",
                    ],
                ),
            ]
        ),
        # Profanity (AWS-managed word list) — question or answer.
        word_policy_config=bedrock.CfnGuardrail.WordPolicyConfigProperty(
            managed_word_lists_config=[
                bedrock.CfnGuardrail.ManagedWordsConfigProperty(type="PROFANITY"),
            ]
        ),
        # Baseline harmful-content filters; INSULTS backs the politeness check.
        content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
            filters_config=[
                bedrock.CfnGuardrail.ContentFilterConfigProperty(
                    type="INSULTS", input_strength="HIGH", output_strength="HIGH"
                ),
                bedrock.CfnGuardrail.ContentFilterConfigProperty(
                    type="HATE", input_strength="HIGH", output_strength="HIGH"
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
                # Jailbreak attempts: input only.
                bedrock.CfnGuardrail.ContentFilterConfigProperty(
                    type="PROMPT_ATTACK", input_strength="HIGH", output_strength="NONE"
                ),
            ]
        ),
        # PII anywhere (question or answer) → block.
        sensitive_information_policy_config=bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty(
            pii_entities_config=[
                bedrock.CfnGuardrail.PiiEntityConfigProperty(type=pii_type, action="BLOCK")
                for pii_type in PII_TYPES
            ]
        ),
    )

    # Pin a published version so callers reference a stable identifier.
    guardrail_version = bedrock.CfnGuardrailVersion(
        scope,
        "RagGuardrailVersion",
        guardrail_identifier=guardrail.attr_guardrail_id,
    )

    return {"guardrail": guardrail, "guardrail_version": guardrail_version}
