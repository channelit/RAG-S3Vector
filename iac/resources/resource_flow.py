"""Bedrock Flow that classifies each question and answers it from the knowledge
base mapped to that category.

    FlowInputNode ─► Classify ─► Route ─┬─ statistics ─► Answer_statistics ─► Output_statistics
     (question)      (prompt)  (condition)└─ default ────► Answer_messages   ─► Output_messages

  * Classify is a prompt node. Its prompt lists every route with its
    description (config: flow.routes) and the model replies with one route name.
  * Route is a condition node: `category == "<route>"` per route, and `default`
    for the default route, so an unexpected reply still gets an answer.
  * Each Answer_<route> is a knowledge base node in generate mode: one
    RetrieveAndGenerate against that route's knowledge base with the stack
    guardrail. The question reaches it straight from the input node.
  * The output node's name tells the caller which route answered.

Adding a category is configuration only: a knowledge base under
knowledge_base.additional (when it needs its own documents) and a route under
flow.routes. With more than four non-default routes the condition nodes are
chained (Route ─ default ─► Route_2 ...), because a condition node holds five
conditions.

What a knowledge base node cannot do (Bedrock, November 2026): take a metadata
filter, or return citations. So answers that come through the flow have no
date-range filter and no source links.

Callers invoke the alias, which points at a published, immutable version. The
version is republished whenever the definition, the guardrail version or a
knowledge base it reads changes.
"""

import hashlib
import json
import os
import re

from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from config import resource_name
from constructs import Construct

INPUT_NODE = "FlowInputNode"
CLASSIFY_NODE = "Classify"
DEFAULT_CONDITION = "default"

# Bedrock Flows quotas, none of them adjustable.
MAX_NODES = 40
MAX_KNOWLEDGE_BASE_NODES = 20
MAX_CONDITION_NODES = 5
NAMED_CONDITIONS_PER_NODE = 4      # five conditions per node, one of them "default"
MAX_EXPRESSION_CHARS = 64
MAX_RESULTS = 100

# A route name is the classifier's reply, a condition name and part of two node
# names, so it has to fit all three patterns.
_ROUTE_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
_MAX_ROUTE_NAME_CHARS = 40
_CLASSIFIER_MAX_TOKENS = 16        # a route name and nothing else
_INFERENCE_PROFILE_PREFIXES = ("us.", "eu.", "apac.", "global.")
_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")

F = bedrock.CfnFlow


def _read_prompt(relative_path: str) -> str:
    with open(os.path.join(_CONFIG_DIR, relative_path), encoding="utf-8") as f:
        return f.read().strip()


def _validate(flow_cfg: dict, knowledge_bases: dict[str, dict]) -> None:
    for key in ("classifier_model_id", "classifier_prompt_file", "generation_model_id"):
        if not flow_cfg.get(key):
            raise ValueError(f"flow.{key} is required")
    routes = flow_cfg.get("routes") or {}
    if len(routes) < 2:
        raise ValueError("flow.routes needs at least two routes: with one there is nothing to classify")
    default_route = flow_cfg.get("default_route")
    if default_route not in routes:
        raise ValueError(f"flow.default_route ({default_route!r}) is not one of flow.routes: {sorted(routes)}")

    for name, route in routes.items():
        where = f"flow.routes.{name}"
        if name == DEFAULT_CONDITION or len(name) > _MAX_ROUTE_NAME_CHARS or not _ROUTE_NAME_RE.match(name):
            raise ValueError(
                f"{where}: route names are lowercase letters, digits and single underscores, start with a "
                f'letter, are at most {_MAX_ROUTE_NAME_CHARS} characters long and cannot be "{DEFAULT_CONDITION}"'
            )
        if route.get("knowledge_base") not in knowledge_bases:
            raise ValueError(
                f"{where}.knowledge_base ({route.get('knowledge_base')!r}) is not a knowledge base: "
                f"{sorted(knowledge_bases)}"
            )
        if not (route.get("description") or "").strip():
            raise ValueError(f"{where} needs a description: it is what the classifier chooses by")
        results = route.get("num_results")
        if results is not None and not 1 <= results <= MAX_RESULTS:
            raise ValueError(f"{where}.num_results must be between 1 and {MAX_RESULTS}")

    condition_nodes = -(-(len(routes) - 1) // NAMED_CONDITIONS_PER_NODE)
    nodes = 2 + condition_nodes + 2 * len(routes)   # input + classifier, conditions, answer + output per route
    if len(routes) > MAX_KNOWLEDGE_BASE_NODES or condition_nodes > MAX_CONDITION_NODES or nodes > MAX_NODES:
        raise ValueError(
            f"flow.routes has {len(routes)} routes, which needs {nodes} nodes and {condition_nodes} condition "
            f"nodes. A flow allows {MAX_NODES} nodes, {MAX_CONDITION_NODES} condition nodes and "
            f"{MAX_KNOWLEDGE_BASE_NODES} knowledge base nodes."
        )


def classifier_prompt(flow_cfg: dict) -> str:
    """The classifier's prompt: the template file with the route list filled in.
    `{{question}}` stays, as the prompt node's input variable."""
    template = _read_prompt(flow_cfg["classifier_prompt_file"])
    for marker in ("<<ROUTES>>", "{{question}}"):
        if marker not in template:
            raise ValueError(f"{flow_cfg['classifier_prompt_file']} must contain {marker}")
    route_lines = "\n".join(
        f"- {name}: {' '.join(route['description'].split())}" for name, route in flow_cfg["routes"].items()
    )
    return template.replace("<<ROUTES>>", route_lines).replace("<<DEFAULT_ROUTE>>", flow_cfg["default_route"])


def _answer_prompt(name: str, route: dict) -> F.KnowledgeBasePromptTemplateProperty | None:
    if not route.get("prompt_file"):
        return None     # Bedrock's default generation prompt
    text = _read_prompt(route["prompt_file"])
    if "$search_results$" not in text:
        raise ValueError(f"flow.routes.{name}.prompt_file ({route['prompt_file']}) must contain $search_results$")
    return F.KnowledgeBasePromptTemplateProperty(text_prompt_template=text)


def _is_inference_profile(model_id: str) -> bool:
    return model_id.startswith(_INFERENCE_PROFILE_PREFIXES)


def _node_model_id(scope: Construct, model_id: str) -> str:
    """What a node stores: the ARN for a cross-region inference profile (the
    form RetrieveAndGenerate is known to accept), the plain ID otherwise."""
    if _is_inference_profile(model_id):
        return f"arn:aws:bedrock:{scope.region}:{scope.account}:inference-profile/{model_id}"
    return model_id


def _model_arns(scope: Construct, model_id: str) -> list[str]:
    """IAM resources for invoking a model: an inference profile needs the
    profile itself plus the foundation model in every region it may route to."""
    if _is_inference_profile(model_id):
        return [
            f"arn:aws:bedrock:{scope.region}:{scope.account}:inference-profile/{model_id}",
            f"arn:aws:bedrock:*::foundation-model/{model_id.split('.', 1)[1]}",
        ]
    return [f"arn:aws:bedrock:{scope.region}::foundation-model/{model_id}"]


def _input(name: str) -> F.FlowNodeInputProperty:
    return F.FlowNodeInputProperty(name=name, type="String", expression="$.data")


def _output(name: str) -> F.FlowNodeOutputProperty:
    return F.FlowNodeOutputProperty(name=name, type="String")


def _data(source: str, source_output: str, target: str, target_input: str) -> F.FlowConnectionProperty:
    return F.FlowConnectionProperty(
        name=f"{source}_to_{target}",
        source=source,
        target=target,
        type="Data",
        configuration=F.FlowConnectionConfigurationProperty(
            data=F.FlowDataConnectionConfigurationProperty(source_output=source_output, target_input=target_input)
        ),
    )


def _conditional(source: str, condition: str, target: str) -> F.FlowConnectionProperty:
    return F.FlowConnectionProperty(
        name=f"{source}_if_{condition}",
        source=source,
        target=target,
        type="Conditional",
        configuration=F.FlowConnectionConfigurationProperty(
            conditional=F.FlowConditionalConnectionConfigurationProperty(condition=condition)
        ),
    )


def _definition(
    scope: Construct,
    config: dict,
    knowledge_bases: dict[str, dict],
    guardrail_configuration: F.GuardrailConfigurationProperty,
) -> F.FlowDefinitionProperty:
    flow_cfg = config["flow"]
    routes: dict[str, dict] = flow_cfg["routes"]
    default_route = flow_cfg["default_route"]
    default_model = flow_cfg["generation_model_id"]

    nodes = [
        F.FlowNodeProperty(
            name=INPUT_NODE,
            type="Input",
            configuration=F.FlowNodeConfigurationProperty(input={}),
            outputs=[_output("document")],
        ),
        F.FlowNodeProperty(
            name=CLASSIFY_NODE,
            type="Prompt",
            configuration=F.FlowNodeConfigurationProperty(
                prompt=F.PromptFlowNodeConfigurationProperty(
                    source_configuration=F.PromptFlowNodeSourceConfigurationProperty(
                        inline=F.PromptFlowNodeInlineConfigurationProperty(
                            model_id=_node_model_id(scope, flow_cfg["classifier_model_id"]),
                            template_type="TEXT",
                            template_configuration=F.PromptTemplateConfigurationProperty(
                                text=F.TextPromptTemplateConfigurationProperty(
                                    text=classifier_prompt(flow_cfg),
                                    input_variables=[F.PromptInputVariableProperty(name="question")],
                                )
                            ),
                            inference_configuration=F.PromptInferenceConfigurationProperty(
                                text=F.PromptModelInferenceConfigurationProperty(
                                    temperature=0, max_tokens=_CLASSIFIER_MAX_TOKENS
                                )
                            ),
                        )
                    )
                )
            ),
            inputs=[_input("question")],
            outputs=[_output("modelCompletion")],
        ),
    ]
    connections = [_data(INPUT_NODE, "document", CLASSIFY_NODE, "question")]

    # Condition nodes: four named routes each, chained through `default`. The
    # last `default` goes to the default route.
    named = [name for name in routes if name != default_route]
    groups = [named[i:i + NAMED_CONDITIONS_PER_NODE] for i in range(0, len(named), NAMED_CONDITIONS_PER_NODE)]
    route_nodes = ["Route" if i == 0 else f"Route_{i + 1}" for i in range(len(groups))]
    for i, (route_node, group) in enumerate(zip(route_nodes, groups, strict=True)):
        conditions = []
        for name in group:
            expression = f'category == "{name}"'
            if len(expression) > MAX_EXPRESSION_CHARS:
                raise ValueError(f"flow.routes.{name}: condition {expression!r} is over {MAX_EXPRESSION_CHARS} characters")
            conditions.append(F.FlowConditionProperty(name=name, expression=expression))
        conditions.append(F.FlowConditionProperty(name=DEFAULT_CONDITION))
        nodes.append(
            F.FlowNodeProperty(
                name=route_node,
                type="Condition",
                configuration=F.FlowNodeConfigurationProperty(
                    condition=F.ConditionFlowNodeConfigurationProperty(conditions=conditions)
                ),
                inputs=[_input("category")],
            )
        )
        connections.append(_data(CLASSIFY_NODE, "modelCompletion", route_node, "category"))
        connections += [_conditional(route_node, name, f"Answer_{name}") for name in group]
        fallback = route_nodes[i + 1] if i + 1 < len(route_nodes) else f"Answer_{default_route}"
        connections.append(_conditional(route_node, DEFAULT_CONDITION, fallback))

    for name, route in routes.items():
        answer_node, output_node = f"Answer_{name}", f"Output_{name}"
        knowledge_base = knowledge_bases[route["knowledge_base"]]["knowledge_base"]
        nodes += [
            F.FlowNodeProperty(
                name=answer_node,
                type="KnowledgeBase",
                configuration=F.FlowNodeConfigurationProperty(
                    knowledge_base=F.KnowledgeBaseFlowNodeConfigurationProperty(
                        knowledge_base_id=knowledge_base.attr_knowledge_base_id,
                        # A model makes the node generate an answer (RetrieveAndGenerate)
                        # rather than return raw chunks; a guardrail needs that mode.
                        model_id=_node_model_id(scope, route.get("generation_model_id", default_model)),
                        guardrail_configuration=guardrail_configuration,
                        number_of_results=route.get("num_results"),
                        prompt_template=_answer_prompt(name, route),
                    )
                ),
                inputs=[_input("retrievalQuery")],
                outputs=[_output("outputText")],
            ),
            F.FlowNodeProperty(
                name=output_node,
                type="Output",
                configuration=F.FlowNodeConfigurationProperty(output={}),
                inputs=[_input("document")],
            ),
        ]
        connections += [
            _data(INPUT_NODE, "document", answer_node, "retrievalQuery"),
            _data(answer_node, "outputText", output_node, "document"),
        ]

    return F.FlowDefinitionProperty(nodes=nodes, connections=connections)


def create_flow(
    scope: Construct,
    config: dict,
    knowledge_bases: dict[str, dict],
    guardrail: bedrock.CfnGuardrail,
    guardrail_version: bedrock.CfnGuardrailVersion,
) -> dict:
    """`knowledge_bases` is create_knowledge_bases()' result: {name: resources}."""
    project_name = config["project_name"]
    flow_cfg = config["flow"]
    _validate(flow_cfg, knowledge_bases)
    region, account = scope.region, scope.account
    routes: dict[str, dict] = flow_cfg["routes"]
    default_model = flow_cfg["generation_model_id"]

    # Service role the flow runs every node with.
    flow_role = iam.Role(
        scope,
        "QueryFlowRole",
        assumed_by=iam.ServicePrincipal(
            "bedrock.amazonaws.com",
            conditions={
                "StringEquals": {"aws:SourceAccount": account},
                "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{region}:{account}:flow/*"},
            },
        ),
    )
    model_ids = {flow_cfg["classifier_model_id"]} | {r.get("generation_model_id", default_model) for r in routes.values()}
    flow_role.add_to_policy(
        iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:GetInferenceProfile"],
            resources=sorted({arn for model_id in model_ids for arn in _model_arns(scope, model_id)}),
        )
    )
    used = sorted({route["knowledge_base"] for route in routes.values()})
    flow_role.add_to_policy(
        iam.PolicyStatement(
            actions=["bedrock:Retrieve"],
            resources=[knowledge_bases[key]["knowledge_base"].attr_knowledge_base_arn for key in used],
        )
    )
    # RetrieveAndGenerate has no resource type in IAM, so it cannot be scoped to
    # a knowledge base ARN; a statement that names one never matches.
    flow_role.add_to_policy(iam.PolicyStatement(actions=["bedrock:RetrieveAndGenerate"], resources=["*"]))
    flow_role.add_to_policy(
        iam.PolicyStatement(actions=["bedrock:ApplyGuardrail"], resources=[guardrail.attr_guardrail_arn])
    )

    flow = F(
        scope,
        "QueryFlow",
        name=resource_name(config, f"{project_name}-flow"),
        description="Classifies each CSMS question and answers it from the knowledge base for that category",
        execution_role_arn=flow_role.role_arn,
        definition=_definition(
            scope,
            config,
            knowledge_bases,
            F.GuardrailConfigurationProperty(
                guardrail_identifier=guardrail.attr_guardrail_id,
                guardrail_version=guardrail_version.attr_version,
            ),
        ),
    )
    # Preparing the flow checks what the role can reach — wait for the inline policy.
    for child in flow_role.node.find_all():
        if isinstance(child, iam.CfnPolicy):
            flow.node.add_dependency(child)

    # A FlowVersion is an immutable snapshot and is only republished when one of
    # its own properties changes, so the fingerprint in its description forces a
    # new one. Besides the definition it covers what the snapshot pins by value:
    # the guardrail version number and the knowledge base IDs, which change when
    # those resources are replaced even though the definition text does not.
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                scope.resolve(flow._cfn_properties),  # type: ignore[attr-defined]
                guardrail_version.description,
                [scope.resolve(knowledge_bases[key]["knowledge_base"]._cfn_properties) for key in used],  # type: ignore[attr-defined]
            ],
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()[:12]
    flow_version = bedrock.CfnFlowVersion(
        scope,
        "QueryFlowVersion",
        flow_arn=flow.attr_arn,
        description=f"definition {fingerprint}",
    )
    flow_alias = bedrock.CfnFlowAlias(
        scope,
        "QueryFlowAlias",
        flow_arn=flow.attr_arn,
        name=flow_cfg.get("alias_name", "live"),
        description="What callers invoke; points at the latest published version",
        routing_configuration=[
            bedrock.CfnFlowAlias.FlowAliasRoutingConfigurationListItemProperty(flow_version=flow_version.attr_version)
        ],
    )

    return {
        "flow": flow,
        "flow_version": flow_version,
        "flow_alias": flow_alias,
        "flow_role": flow_role,
    }
