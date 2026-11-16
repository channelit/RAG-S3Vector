# Amazon Bedrock Agents (incl. multi-agent collaboration) and Amazon Bedrock AgentCore as alternatives to Bedrock Flows for multi-KB routing (status as of 2026-11-06)

> Headline: Amazon Bedrock Agents was renamed "Agents Classic" and closed to new customers on **July 30, 2026**. An AWS account that has not used Bedrock Agents in the past 12 months cannot create agents (or call InvokeInlineAgent), and there is no exception process. AWS now points all new agent work to **AgentCore**, and specifically to the config-based **AgentCore harness** (GA June 2026). Each section below separates documented fact (Cited Findings) from my reasoning (Inferences). Sources are primary AWS docs fetched on 2026-11-06 unless noted.

## 1. Bedrock Agents ("Agents Classic"): availability, number of KBs, KB routing by description, per-request filters, per-request KB enable/disable, citations, guardrails, memory, return of control, action groups, code interpreter

### Takeaway
For accounts on the allowlist, Agents Classic is the closest config-only match to the current design:
- KBs are associated with descriptions, and the model uses those descriptions to decide whether to retrieve.
- Each InvokeAgent call can set a metadata `filter`, `numberOfResults` and search type per KB through `sessionState`.
- Citations come back in the same `Citation` type that RetrieveAndGenerate returns.

The catches:
- The service is in maintenance mode: closed to new accounts, no new features, model catalog frozen.
- The default limit is 2 KBs per agent.
- A KB cannot be disabled for a single request.
- Whether a KB gets queried at all is the model's decision.

### Cited Findings
**Availability / maintenance mode**
- "Amazon Bedrock Agents (launched November 2023) is now Amazon Bedrock Agents Classic and will no longer be open to new customers starting on July 30, 2026." Bedrock models, Knowledge Bases and Guardrails "are not affected." — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- Allowlist rule: "If your account has had Bedrock Agents activity in the past 12 months, you are allowlisted and unaffected. This applies per-account... Accounts without prior usage will receive an AccessDeniedException (HTTP 403) when calling CreateAgent or InvokeInlineAgent." Every other API (UpdateAgent, GetAgent, PrepareAgent, InvokeAgent, action group, KB and alias APIs) stays available. "Only CreateAgent and InvokeInlineAgent are restricted for accounts without prior usage." — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- "There is no exception process." The doc names AgentCore as the path for agent capabilities in a new account. — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- "No new features will be added to Bedrock Agents Classic". "The model catalog available in Bedrock Agents Classic is frozen as of the maintenance mode effective date (July 30, 2026). New models released after that date will be available through AgentCore." — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- There is no migration deadline and "no planned end-of-life date". — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- Agents Classic regions include `us-gov-west-1` (16 regions in total). — [AWS: Supported Regions for Bedrock Agents](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-supported.html)

**KB association and how the agent picks a KB**
- `AssociateAgentKnowledgeBase` requires `agentId`, `agentVersion` and `knowledgeBaseId`.
  - The optional `description` is "Instructions that tell the agent when and how to query this knowledge base. The agent includes this text in its prompt to determine whether to retrieve information from the knowledge base for a given user request."
  - The optional `knowledgeBaseState`: "To prevent the agent from querying the knowledge base, specify `DISABLED`."
  - Source: [AWS: Augment response generation with knowledge base](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-kb-add.html)
- Default quotas, all per agent unless noted ([AWS General Reference: Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)):

  | Quota | Default | Adjustable |
  |---|---|---|
  | Associated knowledge bases per Agent | 2 | Yes |
  | Action groups per Agent | 20 | Yes |
  | Agents per account | 1,000 | Yes |
  | Associated aliases per Agent | 10 | No |

- The InvokeInlineAgent API reference says: "The agent instructions will not be honored if your agent has only one knowledge base, uses default prompts, has no action group, and user input is disabled." — [AWS API: InvokeInlineAgent](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_InvokeInlineAgent.html)

**Per-request retrieval settings (InvokeAgent `sessionState`)**
- "To modify the retrieval configuration of knowledge bases that are attached to your agent, include the `knowledgeBaseConfigurations` field". Per KB you can set:
  - search type `overrideSearchType` (`HYBRID | SEMANTIC`)
  - "Maximum number of retrieved results" (`numberOfResults`)
  - a metadata `filter` (`RetrievalFilter`)

  The same page's JSON sample labels the list `knowledgeBases`, which is a doc inconsistency. — [AWS: Control agent session context](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-session-state.html)
- The runtime `KnowledgeBaseConfiguration` type has only `knowledgeBaseId` (required, a KB "attached to the agent") and `retrievalConfiguration` (required). It has no state/enable field. — [AWS API: KnowledgeBaseConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_KnowledgeBaseConfiguration.html)
- `InvokeInlineAgent` takes a per-request `knowledgeBases` array (`knowledgeBaseId`, `description`, `retrievalConfiguration`).
  - `vectorSearchConfiguration` has `filter`, `implicitFilterConfiguration`, `numberOfResults`, `overrideSearchType` and `rerankingConfiguration`.
  - There is also a `managedSearchConfiguration`.
  - Other fields: `foundationModel` (required), `instruction` (required, min 40 chars), `guardrailConfiguration`, `actionGroups`, `collaborators`, `customOrchestration`, `promptOverrideConfiguration`.
  - `idleSessionTTLInSeconds` ranges from 60 to 3600.
  - Source: [AWS API: InvokeInlineAgent](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_InvokeInlineAgent.html)
- "Accounts with InvokeInlineAgent usage in the past 12 months can continue using inline agents." — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)

**Citations**
- `Attribution` "Contains citations for a part of an agent response" as a list of `Citation` objects. — [AWS API: Attribution](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Attribution.html)
- InvokeAgent and RetrieveAndGenerate use the same `Citation` type (in the `citations` field). It holds `generatedResponsePart` and `retrievedReferences`. — [AWS API: Citation](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Citation.html)
- In the response syntax, `chunk.attribution.citations[].retrievedReferences[]` carries:
  - `content`
  - `location` (`s3Location.uri`, `webLocation.url`, `customDocumentLocation.id`, etc.)
  - `metadata`

  Source: [AWS API: InvokeInlineAgent](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_InvokeInlineAgent.html)

**Guardrails, memory, return of control, action groups, code interpreter**
- In CloudFormation, `AWS::Bedrock::Agent` has a `GuardrailConfiguration` property: "Details about the guardrail associated with the agent." — [AWS CloudFormation: AWS::Bedrock::Agent](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-agent.html)
- AWS's comparison table describes Classic as having "Guardrails and agent policy attached declaratively to the agent and enforced during orchestration". — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- Inline agents add `streamingConfigurations.applyGuardrailInterval`. — [AWS API: InvokeInlineAgent](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_InvokeInlineAgent.html)
- Memory: session summaries are stored per user under a `memoryId` and produced asynchronously by a "memory summarization" prompt after a session ends. Retention is "up to 365 days" (configurable 1–365). — [AWS: Agent memory](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-memory.html)
- `IdleSessionTTLInSeconds` ranges from 60 to 5400. — [AWS CloudFormation: AWS::Bedrock::Agent](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-agent.html)
- Return of control: InvokeAgent returns a `ReturnControlPayload` with an `invocationId`. The client then sends `returnControlInvocationResults` (an `ApiResult` or `FunctionResult`) in the next request's `sessionState`. — [AWS: Control agent session context](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-session-state.html)
- Session attributes:
  - `sessionAttributes` persist across a session and are passed to the action-group Lambda.
  - `promptSessionAttributes` last a single turn and can be injected into the orchestration template through the `$prompt_session_attributes$` placeholder.

  Source: [AWS: Control agent session context](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-session-state.html)
- Action groups are "defined through OpenAPI / function schema + optional Lambda executor". There are built-in `AMAZON.UserInput` and `AMAZON.CodeInterpreter` action groups. — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- KB API throughput quotas:
  - Standard KBs: Retrieve, RetrieveAndGenerate and RetrieveAndGenerateStream are each 20 requests/second, not adjustable.
  - Managed KBs: Retrieve is 100 RPS per account (adjustable) and 600 requests/minute per KB.

  Source: [AWS General Reference: Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)

### Inferences
- The project's per-request `date_numeric` filter maps one-to-one onto `sessionState.knowledgeBaseConfigurations[].retrievalConfiguration.vectorSearchConfiguration.filter`. Backend code sets the filter, not the model, so date enforcement stays deterministic. What becomes non-deterministic is whether, and which, KB the agent queries.
- Per-user-group permissions on Agents Classic come in three forms, none of them a per-request toggle on InvokeAgent:
  - (a) A separate agent, or alias, per group, with only that group's KBs associated (aliases are capped at 10 per agent, not adjustable).
  - (b) Per-request `InvokeInlineAgent` that names only the KBs the group may use (needs inline-agent allowlisting).
  - (c) App-enforced ACL metadata filters on shared KBs.
- The default of 2 KBs per agent can be raised. Still, a design with "several KBs" points toward multi-agent collaboration (one collaborator per KB, see section 2) or a quota increase.
- **Decisive practical point:** unless this AWS account has had Bedrock Agents activity in the 12 months before July 30, 2026, this whole path is unavailable. AWS documents no exception process. I found no sign in the repo context that the project ever used Bedrock Agents.

### Gaps
- I could not determine whether the project's AWS account is allowlisted. Only the account owner can check, for example by calling CreateAgent or reviewing past usage.
- The exact Nova model IDs in the frozen Agents Classic catalog are not documented on the pages I read (see section 3).
- The "Characters in Agent instructions" and InvokeAgent requests-per-second quotas were not in the portion of the General Reference page I read.
- The user guide lists only search type, `numberOfResults` and `filter` for `sessionState`. It does not say whether `implicitFilterConfiguration` and reranking can also be overridden there; the inline-agent API does show them.

## 2. Multi-agent collaboration (supervisor / supervisor-with-routing): routing, limits, latency/cost overhead, GA status

### Takeaway
- **Status and modes:** multi-agent collaboration went GA on March 10, 2025, with two modes, `SUPERVISOR` and `SUPERVISOR_ROUTER`. Each collaborator can own its own KBs, guardrails and action groups.
- **Routing:** the supervisor model decides from natural-language role descriptions. Routing mode sends "simple" requests straight to one sub-agent and falls back to full orchestration otherwise.
- **Overhead and limits:** AWS publishes no latency or cost figures.
- **Availability:** it is part of Agents Classic, so it is closed to new accounts. AWS says the AgentCore equivalent is "Limited", and that routing-mode multi-agent "is not straightforward today."

### Cited Findings
- GA blog post dated 10 Mar 2025: "Today, we're announcing the general availability (GA) of multi-agent collaboration on Amazon Bedrock." — [AWS ML Blog: multi-agent collaboration GA](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-announces-general-availability-of-multi-agent-collaboration/)
- How it works:
  - You designate a supervisor and associate collaborators. You "must first save the supervisor agent" before adding collaborators.
  - "The supervisor agent uses the instructions you provide to understand the structure and role of each collaborator agent... you must clearly designate the role and responsibilities... and minimize overlapping responsibilities."
  - Each agent "has all the capabilities of Amazon Bedrock Agents, including access to tools, action groups, knowledge bases, and guardrails."
  - The supervisor "automatically creates and executes a plan across a set of collaborator agents and routes relevant requests and tasks to the appropriate collaborator agent."
  - Source: [AWS: Use multi-agent collaboration](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-multi-agent-collaboration.html)
- Mode values: `AgentCollaboration` is `DISABLED | SUPERVISOR | SUPERVISOR_ROUTER`. — [AWS CloudFormation: AWS::Bedrock::Agent](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-agent.html)
- Routing mode can "route simple requests directly to specialized subagents, bypassing full orchestration". For complex or unclear requests, "it automatically falls back to the full supervisor mode". The page does not explain how "simple" is judged. — [AWS ML Blog: multi-agent collaboration GA](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-announces-general-availability-of-multi-agent-collaboration/)
- History sharing:
  - `sessionState.conversationHistory` "accepts additional context... if `conversationalHistorySharing` is enabled for a collaborator agent". By default the supervisor builds it automatically. — [AWS: Control agent session context](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-session-state.html)
  - Collaborator configs have a `relayConversationHistory` field. — [AWS API: InvokeInlineAgent](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_InvokeInlineAgent.html)
- Limits:
  - The General Reference lists "Agent Collaborators per Agent: 1,000 (adjustable)". — [AWS General Reference: Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html) **Caveat:** an automated page summarizer extracted this value. The GA blog says only that GA "Expands self-service limits for agent collaborators and execution steps", with no numbers. — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-announces-general-availability-of-multi-agent-collaboration/)
- Latency and cost:
  - The only claims are qualitative. Payload referencing "Reduces latency and costs by allowing the supervisor agent to reference external data sources", and parallel execution "Improve[s] execution efficiency"; neither is quantified.
  - GA also added "deploy agent networks as code" (CloudFormation), inline supervisor agents "dynamically at runtime", trace/debug tooling and "Improved citation handling".
  - Source: [AWS ML Blog: multi-agent collaboration GA](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-announces-general-availability-of-multi-agent-collaboration/)
- The docs page now carries the banner: "You can no longer sign up for Amazon Bedrock Agents (now Amazon Bedrock Agents Classic)." — [AWS: Use multi-agent collaboration](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-multi-agent-collaboration.html)
- AWS's own mapping to AgentCore: "Limited. The supervisor pattern is possible by exposing agents as MCP tools (agent-as-tool). Routing mode multi-agent is not straightforward today. Full multi-agent collaboration requires custom framework code." The managed harness "supports an agent-as-tool pattern for simpler multi-agent use cases." — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- AgentCore Gateway can front "other agents and HTTP services through passthrough targets (including Agent-to-Agent (A2A) traffic)". — [AWS: AgentCore Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)

### Inferences
- A layout of one supervisor plus one collaborator per KB/category puts at least two LLM orchestration passes (supervisor, then collaborator, plus the collaborator's KB answer generation) in front of every question. A single `retrieve_and_generate` call has one generation. Latency and token cost would therefore grow per question. AWS gives no numbers, so this needs measuring.
- Routing is decided by the model, so the same question can land on different collaborators. Overlapping scopes make this likely; in this project, for example, CSMS message text and attachments both describe the same messages. This is the same predictability problem the team cited when it rejected a tool-using agent.
- Routing mode lowers the overhead for clear-cut questions only. Ambiguous ones fall back to full supervisor planning, which is the slow path.

### Gaps
- No AWS-published latency or cost overhead figures for supervisor or routing mode.
- No documented maximum hierarchy depth found.
- Not documented in what I read: whether `sessionState.knowledgeBaseConfigurations` sent to the supervisor (for example the date filter) reaches the collaborators' KBs. That matters for this project's date-range enforcement.

## 3. Amazon Nova support: Agents (orchestration, supervisor), Nova 2 / Premier, AgentCore, known issues

### Takeaway
- **Agents Classic:** it "supports all models supported by Amazon Bedrock", and the Nova v1 docs say Agents is preconfigured with prompts for Nova, including multi-agent collaboration. The catalog froze on July 30, 2026, so no Nova model released after that date will ever reach Classic.
- **AgentCore:** the Runtime and the harness accept any Bedrock model, and the AWS harness docs include a Nova Micro example.
- **Nova-only defaults:** several AgentCore defaults are not Nova and must be overridden explicitly. These are the harness default model (Claude) and, in the managed-KB connector, the default service-managed answer model and reranker.
- **Known issues:** I found no AWS primary source listing Nova-specific orchestrator problems.

### Cited Findings
- "Amazon Bedrock Agents supports all models supported by Amazon Bedrock." — [AWS: Supported Regions for Bedrock Agents](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-supported.html)
- Catalog frozen as of July 30, 2026. — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- Nova v1 user guide:
  - "Amazon Nova models are enabled in Bedrock Agents and follow the user instructions of Amazon Bedrock Agents. Amazon Bedrock Agents is preconfigured with key features and prompts in order to work effectively with the Amazon Nova models."
  - It lists KB integration, memory, code interpreter and "Multi-Agent Collaboration".
  - Source: [AWS Nova User Guide: Using Nova as FM in an agent](https://docs.aws.amazon.com/nova/latest/userguide/agents-use-nova.html)
- The same guide says "Amazon Nova models can be used with all Bedrock AgentCore services". Its Strands example uses `us.amazon.nova-premier-v1:0` with `temperature=0.3`, `top_p=0.8`. That page is marked "documentation for Amazon Nova Version 1". — [AWS Nova User Guide: Building AI agents with Nova](https://docs.aws.amazon.com/nova/latest/userguide/agents.html)
- Nova 2 user guide:
  - "Amazon Nova models are optimized for building AI agents with Amazon Nova Act."
  - It recommends a framework such as Strands Agents, enabling "reasoning on medium or high" for complex multi-step workflows, and "tool choice `auto`". It also points to Bedrock Guardrails.
  - Its examples use `us.amazon.nova-2-lite-v1:0` with `reasoningConfig`. The page does not mention Bedrock Agents.
  - Source: [AWS Nova 2 User Guide: Building AI agents](https://docs.aws.amazon.com/nova/latest/nova2-userguide/building-ai-agents.html)
- AgentCore Runtime works with "any foundation model in or outside of Amazon Bedrock including... Amazon Nova". The harness works with "Amazon Bedrock, OpenAI, Google Gemini, and any OpenAI-compatible model provider". — [AWS: What is AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- The harness guardrail example uses `"modelId": "us.amazon.nova-micro-v1:0"` with `apiFormat: converse_stream`.
  - When the model is omitted, the API uses `global.anthropic.claude-sonnet-4-6`, and `agentcore add harness` writes `global.anthropic.claude-sonnet-5-5`.
  - The model can be overridden on each invocation.
  - Source: [AWS: AgentCore harness models and instructions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-models.html)
- Managed-KB Gateway connector (`AgenticRetrieveStream`):
  - `foundationModelType` is `MANAGED` ("uses the service-managed model (default)") or `CUSTOM` ("uses a Bedrock model ARN you supply").
  - `rerankingModelType` is `MANAGED` (default), `CUSTOM` or `NONE`.
  - Source: [AWS: Managed KB connector target](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-managed-kb.html)
- Intelligent prompt routing supports Nova Lite and Nova Pro, including single-region `us-gov-west-1`. — [AWS: Intelligent prompt routing](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html)

### Inferences
- Nova-only compliance on AgentCore means setting model IDs explicitly in several places:
  - harness `bedrockModelConfig.modelId`, because the default is Claude;
  - managed-KB `foundationModelType: CUSTOM` with a Nova model ARN, because the "service-managed model" is not identified;
  - reranker `NONE` or an approved model.
- Nova 2 Lite came out before the July 30, 2026 freeze (re:Invent, Dec 2025), so it is plausibly in the Classic catalog. I did not verify this.

### Gaps
- No AWS-documented known issues for Nova as an Agents Classic orchestrator or supervisor were found. Treat orchestrator quality as something to test.
- Which Nova versions (Premier, Nova 2 Lite/Pro) are in the frozen Agents Classic catalog, and whether each is supported as a multi-agent supervisor, is not stated on the pages read.
- I did not check which model the "service-managed" option in the managed-KB connector uses, nor Nova availability in GovCloud.

## 4. Predictability: can an agent be forced to always query a KB? Determinism trade-offs

### Takeaway
- **Who decides:** in Agents Classic and in the AgentCore harness alike, whether and which KB/tool gets called is the model's choice, driven by KB or tool descriptions.
- **Code-based override:** Agents Classic offers a custom-orchestration Lambda that can run a fixed state machine, but that is code. The harness cannot run custom orchestrators at all (Runtime only).
- **Harness controls:** `allowedTools` scoping, and Lambda lifecycle hooks that can only allow or deny.
- **Deterministic controls (Gateway):** Policy (Cedar) and interceptors. They constrain *what may be called and with which parameters*, not *what must be called*.
- **Counts:** none of these levers stops the model from writing numbers.

### Cited Findings
- KB choice is model-driven: "The agent includes these instructions in its prompt context to decide whether to retrieve information from the knowledge base". — [AWS: Augment response generation with knowledge base](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-kb-add.html)
- Agents Classic supports prompt overrides at stages: "pre-processing, orchestration, KB response generation, post-processing". — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html) It is exposed as `PromptOverrideConfiguration` in CloudFormation. — [AWS CloudFormation: AWS::Bedrock::Agent](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-agent.html)
- Custom orchestration ([AWS: Custom orchestration](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-custom-orchestration.html)):
  - You write a Lambda that "controls how the agent responds to input by providing instructions to the Bedrock's runtime process on when and how to invoke the model, when to invoke actions tools, and then determining the final response".
  - Incoming states: `START | MODEL_INVOKED | TOOL_INVOKED | APPLY_GUARDRAIL_INVOKED | user-defined`. Returned events: `INVOKE_MODEL | INVOKE_TOOL | APPLY_GUARDRAIL | FINISH`.
  - Payloads use Converse format, and the agent's `tools` and `guardrails` are in the context.
  - You enable it with `orchestrationType: CUSTOM_ORCHESTRATION`. It is "available across all AWS Regions where Amazon Bedrock Agents is available".
- On the harness, stage-specific prompt overrides "are not directly replicated", and a custom orchestrator is "Not available through harness" (supported only by deploying code on AgentCore Runtime). — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- Harness `allowedTools` "scopes LLM tool selection during `InvokeHarness` only". Tools can be overridden per invocation through the SDK. — [AWS: AgentCore harness tools](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-tools.html)
- Harness lifecycle hooks ([AWS: Harness lifecycle hooks](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-lifecycle-hooks.html)):
  - A deny at `before_invocation` stops the run. A deny at `before_tool_call` skips the tool and the loop continues. A deny at `after_tool_call` stops the run.
  - "Lambda is the only target type that can change agent-loop behavior"; SNS and EventBridge only notify.
  - Up to 20 hooks per harness. Hooks are "not available as an `InvokeHarness` override". `failureMode` defaults to `deny`.
- Policy gives "deterministic control". "Every agent action through Amazon Bedrock AgentCore Gateway is intercepted and evaluated at the boundary outside of agent's code". — [AWS: Policy in AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html)
- Default deny: "A request is allowed only when a `permit` policy applies to it and no `forbid` policy overrides it, so a policy engine with no policies denies everything." — [AWS: Policy authoring guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-authoring-guide.html)
- Gateway REQUEST interceptors can "Filter or modify requests based on user context". The docs give the example "adding user-specific filters or limiting data scope". — [AWS: Gateway fine-grained access control](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-fine-grained-access-control.html)
- Managed-KB connector parameter control ([AWS: Managed KB connector target](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-managed-kb.html)):
  - By default the only field the agent sees is `retrievalQuery.text`. `numberOfResults`, `filter` and similar settings are set by the administrator unless exposed through `parameterOverrides`.
  - `userContext` must come from "the calling application (not the model)".

### Inferences
- The only way to *guarantee* "always retrieve from KB X with filter F" is for code to make the retrieval call. That is today's design, a custom-orchestration Lambda in Classic, or an inline-function tool in the harness that the client executes with a filter it controls. Even with an inline function, the model still decides *when* to call it.
- Pinning filters through the Gateway (admin-set `parameterValues`, or an interceptor injecting the UI date range) stops the model from widening the date range or reaching unauthorized data. That is a real determinism gain for *access* and *date scope*. Retrieval *selection* stays model-driven.
- These levers do not address the team's earlier objection on counts. Any number in the final answer is still written by the model unless code computes it, as in the planned count path.

### Gaps
- No documented `toolChoice`/"force tool" option for the harness was found.
- I did not confirm that associated KBs show up as entries in the custom-orchestration payload's `tools` list. That seems likely, but it is not stated on the page read.
- I did not find how a per-request value from the app (the UI date range) is handed to a Gateway interceptor, for example through headers or JWT claims.

## 5. IaC: AWS::Bedrock::Agent, AgentAlias, KB association, versions/aliases; AgentCore resources

### Takeaway
- **Agents Classic:** fully declarative in CloudFormation and CDK (`AWS::Bedrock::Agent` with inline `KnowledgeBases`, `AgentCollaboration`, guardrail, memory, orchestration type). Templates keep working only for allowlisted accounts.
- **AgentCore:** has CloudFormation resources, including `AWS::BedrockAgentCore::GatewayTarget` and an `AWS::BedrockAgentCore::Harness` resource with gateway config, and a CDK `aws_bedrockagentcore` module. The AgentCore CLI also keeps harness config in `harness.yaml`.

### Cited Findings
- `AWS::Bedrock::Agent` properties ([AWS CloudFormation: AWS::Bedrock::Agent](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-agent.html)):
  - `ActionGroups`, `AgentCollaboration` (`DISABLED | SUPERVISOR | SUPERVISOR_ROUTER`), `AgentCollaborators`, `AgentName`, `AgentResourceRoleArn`
  - `AutoPrepare` ("whether to automatically update the `DRAFT` version... By default, this value is `false`")
  - `CustomerEncryptionKeyArn`, `CustomOrchestration`, `Description` (max 200), `FoundationModel`
  - `GuardrailConfiguration`, `IdleSessionTTLInSeconds` (60–5400), `Instruction` (min 40)
  - `KnowledgeBases` (array of `AgentKnowledgeBase`; the example shows `KnowledgeBaseId`, `Description`, `KnowledgeBaseState: ENABLED`)
  - `MemoryConfiguration`, `OrchestrationType` (`DEFAULT | CUSTOM_ORCHESTRATION`), `PromptOverrideConfiguration`, `SkipResourceInUseCheckOnDelete`, `Tags`, `TestAliasTags`
  - `Fn::GetAtt` returns `AgentVersion`, `AgentStatus` and other attributes.
- Aliases: "Associated aliases per Agent: 10 (not adjustable)". — [AWS General Reference: Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- "Existing API namespaces (bedrock-agent), SDK clients, CloudFormation resource types, and IAM action prefixes remain unchanged." The FAQ continues: "Existing IaC templates... will continue to work for allowlisted accounts. If you are provisioning new environments in accounts without prior Bedrock Agents usage, use Amazon Bedrock AgentCore resources in your templates instead." — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- At AgentCore GA, all AgentCore services gained support for VPC, PrivateLink, CloudFormation and resource tagging. — [AWS What's New: AgentCore GA (Oct 2025)](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-bedrock-agentcore-available) (from the search-result summary of this page)
- `AWS::BedrockAgentCore::GatewayTarget` requires `Name` and `TargetConfiguration`. Per the search snippet, the page still says AgentCore "is in preview release and is subject to change", which is likely stale text. — [AWS CloudFormation: AWS::BedrockAgentCore::GatewayTarget](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-gatewaytarget.html)
- `AWS::BedrockAgentCore::Harness` has a `HarnessAgentCoreGatewayConfig` property type: `GatewayArn` is required, and `OutboundAuth` defaults to AWS_IAM (SigV4). — [AWS CloudFormation: Harness HarnessAgentCoreGatewayConfig](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-bedrockagentcore-harness-harnessagentcoregatewayconfig.html) (from the search snippet)
- CDK: `aws_cdk.aws_bedrockagentcore` has an L1 `CfnGatewayTarget` and an L2 `IGatewayTarget` (targets: Lambda, OpenAPI, Smithy). — [AWS CDK: CfnGatewayTarget](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_bedrockagentcore/CfnGatewayTarget.html), [AWS CDK: IGatewayTarget](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_bedrockagentcore/IGatewayTarget.html)
- AgentCore CLI projects keep harness defaults in `app/<name>/harness.yaml` (using CreateHarness API field names) and the system prompt in `system-prompt.md`, then run `agentcore deploy`. — [AWS: AgentCore harness models and instructions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-models.html)
- The harness has "immutable versions and named endpoints" with instant rollback. It can be exported "to Strands code", and AWS Step Functions has an "InvokeHarness state". — [AWS: AgentCore harness](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness.html)
- "Customers can also use the AgentCore CLI to import existing Bedrock Agents Classic configurations". — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)

### Inferences
- This project uses CDK in Python, so AgentCore Gateway and targets can be added with `aws_bedrockagentcore` constructs. The harness and Policy engine would most likely be L1 `Cfn*` constructs, or managed through the AgentCore CLI and `harness.yaml` outside CDK. This is not verified.

### Gaps
- I did not fetch the `AWS::Bedrock::AgentAlias` page. How agent versions are created from CloudFormation (alias routing configuration) is not verified here.
- I did not confirm full property lists for `AWS::BedrockAgentCore::Harness` or the Policy-engine resources, nor whether CDK L2 constructs exist for them.

## 6. Bedrock AgentCore: components, GA dates, config vs. code, Identity (inbound/outbound), Gateway (KB/Lambda as MCP), Policy (Cedar), Nova

### Takeaway
AgentCore is now the strategic AWS agent platform. Dates:
- the platform went GA on Oct 13, 2025;
- Policy went GA in March 2026;
- the harness went GA in June 2026.

The **harness** is config-driven: model, system prompt and tools are declared, with per-invocation overrides. Everything else (Runtime, Strands, LangGraph and so on) is code-first.

For this project:
- **KB access goes through Gateway.** The *built-in* KB connector supports **only Bedrock Managed Knowledge Bases**. A standard S3 Vectors KB like this one needs a Lambda, or another API-style target, which means custom code.
- **Per-group permissions can be declarative.** Gateway inbound JWT validation and Cedar Policy can permit or forbid each tool, and therefore each KB if each KB is its own tool, by user identity.

### Cited Findings
**Components and status**
- Services listed ([AWS: What is AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)):
  - **Harness:** "A managed agent loop that lets you define and invoke AI agents with a single API call"
  - Runtime, Memory, Gateway, Identity, Code Interpreter, Browser, Observability (OTEL)
  - Payments, Evaluations, Optimization
  - **Policy:** "deterministic control"; Dogwood or Cedar; "Integrates with AgentCore Gateway, to intercept every tool call"
  - Registry
- Supported frameworks: CrewAI, LangGraph, LlamaIndex, Google ADK, OpenAI Agents SDK, Strands Agents. Supported IdPs: "Amazon Cognito, Okta, Microsoft Azure Entra ID, Auth0". — [AWS: What is AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- AgentCore GA: October 13, 2025, in nine regions at launch. — [AWS What's New: AgentCore GA](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-bedrock-agentcore-available) (date from the search-result summary; the URL path confirms 2025/10)
- Policy and Evaluations went to preview in Dec 2025. — [AWS What's New: Policy & Evaluations preview](https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-bedrock-agentcore-policy-evaluations-preview)
- Policy went GA in March 2026 (the search summary says March 3, 2026). — [AWS What's New: Policy GA](https://aws.amazon.com/about-aws/whats-new/2026/03/policy-amazon-bedrock-agentcore-generally-available)
- Evaluations GA per a blog update dated Mar 31, 2026. — [AWS News Blog](https://aws.amazon.com/blogs/aws/amazon-bedrock-agentcore-adds-quality-evaluations-and-policy-controls-for-deploying-trusted-ai-agents/) (from the search summary, not fetched)
- Harness GA in June 2026 (the search summary says June 17, 2026). — [AWS What's New: harness GA](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-agentcore-harness-generally-available) The docs say "AgentCore harness is available in GA across all regions shown". — [AWS: AgentCore harness](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness.html)
- Bedrock Guardrails as signals in Policy went GA in June 2026 in us-east-1, eu-west-2, eu-north-1, ap-southeast-2 and ap-northeast-1. — [AWS What's New: Policy + Guardrails](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-agentcore-policy-guardrails-generally-available) (from the search summary)
- AWS GovCloud (US-West) offers the harness, Runtime microVMs, Memory, Gateway, Identity, Policy, Evaluations, Observability and the built-in tools. It does not offer Optimization or the Agent Registry. Web Answer is us-east-1 only. — [AWS: AgentCore Supported Regions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html)

**Config vs. code**
- The harness "turns that work into configuration. You declare what your agent does (model, tools, skills, instructions)... Trying a different model or adding a new tool is a config change, not a code rewrite."
  - Each session runs in "an isolated microVM per session" with a filesystem and shell.
  - It is "powered by Strands Agents" and can be exported to Strands code "when configuration isn't enough".
  - Source: [AWS: AgentCore harness](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness.html)
- "Defaults at creation time, overrides at invocation time" applies to model, system prompt, tools and limits. — [AWS: AgentCore harness models and instructions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-models.html)
- AWS's guidance: "Use the harness unless you have a specific reason to own the loop yourself". Code-defined agents on Runtime cover stage-specific prompt overrides, multi-agent/supervisor patterns and custom orchestration. — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- Harness tools ([AWS: AgentCore harness tools](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-tools.html)):
  - "Tools are declarative." There are five types: `remote_mcp`, `agentcore_gateway`, `agentcore_browser`, `agentcore_code_interpreter`, `inline_function`.
  - Built-in `shell` and `file_operations` are always present unless restricted with `allowedTools`. Together they add "approximately 900 input tokens to each model request".
- KB mapping: Classic's KB association becomes "Gateway-fronted knowledge base integration in AgentCore. Knowledge base accessible through code-level retrieval tool." Migration mapping: "KBs — Gateway or retrieval tool". — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- Harness guardrails: put `guardrailConfig` in `bedrockModelConfig.additionalParams`, which requires `apiFormat: converse_stream`. The stream reports `guardrail_intervened` when the guardrail fires. — [AWS: AgentCore harness models and instructions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-models.html)
- "Guardrails configured on the Bedrock model still apply when the model is invoked through AgentCore. Agent-level guardrail enforcement is available through AgentCore gateway policies." — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)

**Gateway: exposing KBs and Lambdas as MCP tools**
- Gateway "converts APIs, Lambda functions, and existing services into Model Context Protocol (MCP)-compatible tools". It "supports OpenAPI, Smithy, and Lambda as tool input types" and offers semantic tool search and inbound/outbound auth. — [AWS: AgentCore Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
- Target categories: MCP (aggregation), HTTP (passthrough) and Inference ("model-based routing"). — [AWS: Gateway supported targets](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-supported-targets.html)
- MCP target types: Lambda, API Gateway REST stages, OpenAPI, Smithy, MCP servers, integration-provider templates and built-in connectors. — [AWS: Gateway MCP targets](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-targets-mcp.html)
- Built-in connectors: "Amazon Bedrock Managed Knowledge Bases", Web Search Tool, Web Answer and AWS Step Functions. — [AWS: Gateway built-in connectors](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connectors.html)
- Managed-KB connector ([AWS: Managed KB connector target](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-managed-kb.html)):
  - **Scope:** "This connector is supported only for Amazon Bedrock Managed Knowledge Bases."
  - **Tools:** it exposes two.
    - `AgenticRetrieveStream` "plans a retrieval strategy, runs multiple retrieval steps across your managed knowledge bases... and streams back both the supporting results and a synthesized, citation-backed answer". The retrievers it queries "are configured by the administrator on the target". It has `maxAgentIteration` and a guardrail through `policyConfiguration.guardrailConfiguration`.
    - `Retrieve` runs a single hybrid search. `numberOfResults` ranges 1–100; it also takes `overrideSearchType`, reranking, and a metadata `filter` (`equals`, `greaterThanOrEquals`, `lessThanOrEquals`, `in`, `andAll`, `orAll`, ...).
  - **Results:** each result includes `location.s3Location.uri`, `score` and `metadata`.
  - **Access control:** `userContext` filtering applies to managed KBs, and "The Gateway does not populate `userContext` from the caller's IAM identity — your application must supply it explicitly."

**Identity**
- AgentCore Identity treats agent identities as workload identities and lets agents "access AWS resources and third-party services on behalf of users". It covers inbound JWT authorizers, outbound credential providers, a consent portal and private IdPs. — [AWS: AgentCore Identity](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity.html)
- Inbound JWT authorizer ([AWS: Configure inbound JWT authorizer](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/inbound-jwt-authorizer.html)):
  - It authorizes "incoming OAuth 2.0 API requests to AgentCore Runtime and AgentCore Gateway" and is "IdP agnostic".
  - Configuration: an OIDC/RFC 8414 **discovery URL**, plus allowed audiences (`aud`), allowed clients (`client_id`), allowed scopes, and **required custom claims**.
  - Claim types: `STRING` with `EQUALS`, or `STRING_ARRAY` with `CONTAINS`/`CONTAINS_ANY`. The documented example is "`Group must equal Developer`".
  - All configured checks must pass.
- Outbound credentials: API keys and OAuth providers are stored in the Identity token vault and resolved at call time; "Your agent code never sees raw credentials". — [AWS: AgentCore harness models and instructions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-models.html), [AWS: AgentCore harness tools](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-tools.html)

**Fine-grained authorization (interceptors, Policy)**
- Gateway access control works at four levels: gateway, tool, operation (`tools/list`, `tools/call`) and parameter. It uses interceptors that check JWT claims, plus Cedar `principal.id` pattern matching for IAM callers. — [AWS: Gateway fine-grained access control](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-fine-grained-access-control.html)
- Policy ([AWS: Policy in AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html)):
  - Policy engines are associated with gateways and evaluate every tool request.
  - Policies are written in Cedar, or in natural language that is converted to Cedar and checked with automated reasoning for overly permissive, overly restrictive or unsatisfiable rules. Dogwood is also supported, adding temporal and guardrail conditions.
  - It "supports fine-grained permissions based on user identity and tool input parameters", and decisions are logged to CloudWatch.
- "Principal-scoped policies decide from who is calling — a JWT identity or an IAM caller". Engines deny by default. — [AWS: Policy authoring guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-authoring-guide.html)
- Nova: "Amazon Nova models can be used with all Bedrock AgentCore services". — [AWS Nova User Guide: Building AI agents](https://docs.aws.amazon.com/nova/latest/userguide/agents.html)

### Inferences
- **Multi-KB routing with minimal code on AgentCore has two very different paths:**
  - **(a) Managed KBs:** the built-in connector's `AgenticRetrieveStream` does planned multi-KB retrieval with cited answers, configured entirely on the Gateway target. That is the most config-only multi-KB option found. But it requires managed KBs. This project moved *off* a managed KB because RetrieveAndGenerate is rejected there. Whether managed KBs honor custom sidecar metadata such as `date_numeric` is unverified.
  - **(b) Standard S3 Vectors KBs (current):** no built-in connector, so each KB needs a Lambda target (or possibly an OpenAPI/Smithy target, unverified) that calls `Retrieve` and applies the filter. That is custom code, though small. The harness model then picks among KB tools by their descriptions.
- **Per-group KB permissions become mostly configuration:**
  - expose each KB as a separate Gateway target or tool;
  - validate the Cognito/OIDC JWT at the Gateway;
  - write Cedar `permit` rules per group per tool.

  Default deny makes "no rule = no access" safe. Policy can also check tool-input parameters, for example bounding a date filter.
- The harness's per-session microVM, shell and filesystem are heavyweight for a stateless Q&A RAG backend. You would at least restrict `allowedTools` to the KB tools, both to cut the ~900-token overhead and for security.

### Gaps
- The inbound JWT authorizer page names Runtime and Gateway. Whether `InvokeHarness` itself sits behind a JWT authorizer, and how end-user identity reaches Gateway Policy from the harness, was not verified.
- I did not fetch the exact Cedar syntax for matching JWT group claims (for example `cognito:groups`) in Policy; the principal-scoped example page was not read.
- Not verified whether an OpenAPI or Smithy Gateway target can call `bedrock-agent-runtime:Retrieve` on a standard KB without a Lambda.
- Not verified whether managed KBs support custom metadata attributes and numeric range filters equivalent to this project's sidecar `date_numeric`.

## 7. Bedrock intelligent prompt routing: what it is, and is it relevant to KB routing?

### Takeaway
Intelligent prompt routing picks between two models *of the same family* (for example Nova Lite and Nova Pro) by predicting response quality per prompt. It does no KB, data-source or intent routing, so it is not a substitute for multi-KB routing. At most it is a cost lever for the generation step.

### Cited Findings
- It "provides a single serverless endpoint to efficiently route requests between different foundational models within the same model family. It can dynamically predict the response quality of each model for each request". — [AWS: Intelligent prompt routing](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html)
- Supported Nova models: Nova Lite and Nova Pro (single-region us-east-1 and us-gov-west-1, plus cross-region profiles). Meta Llama 3.1/3.3 models are also supported. Default routers cover the Nova and Llama families. — [AWS: Intelligent prompt routing](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html)
- "You must choose exactly two models within the same family". Routing uses a fallback model and a `responseQualityDifference`. — [AWS: Intelligent prompt routing](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html)
- Limitations: "only optimized for English prompts"; "can't adjust routing decisions or responses based on application-specific performance data". — [AWS: Intelligent prompt routing](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html)
- AgentCore Gateway "Inference targets" are also *model* routing ("Route LLM traffic to model providers with model-based routing"), not KB routing. — [AWS: Gateway supported targets](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-supported-targets.html)

### Inferences
- This confirms the coordinator's expectation: it is not relevant to routing across KBs. It could cut generation cost by sending easy questions to Nova Lite and harder ones to Nova Pro, if it works as the model in `retrieve_and_generate`.

### Gaps
- Not verified whether a prompt-router ARN is accepted as the `modelArn` in `RetrieveAndGenerate` or as an agent or harness model.

## 8. Pricing model differences (Agents Classic vs. AgentCore)

### Takeaway
- **Agents Classic:** no charge of its own; you pay for model tokens (orchestration prompts included), KBs and Lambdas.
- **AgentCore:** consumption-priced per component, with no separate harness fee. A harness agent still pays for:
  - Runtime microVM time;
  - Gateway calls;
  - Policy authorizations;
  - Memory, if used;
  - model tokens, including the built-in tool definitions unless restricted.

### Cited Findings
- "There is no charge for Bedrock Agents Classic itself. You continue to pay only for the underlying model inference and any associated resources (Knowledge Bases, Lambda invocations, etc.)". — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- "There is no separate harness orchestration charge. AgentCore's harness is more token-efficient than Bedrock Agents Classic's internal prompts, so customers may see comparable or lower model inference costs" (AWS's claim, not independently measured). — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- "There is no separate harness charge. You pay only for the underlying AgentCore capabilities you use." — [AWS: AgentCore harness](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness.html)
- AgentCore list prices as shown on the pricing page ([AWS: AgentCore pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)):

  | Component | Listed price |
  |---|---|
  | Runtime microVM v1 | $0.0895/vCPU-hour, $0.00945/GB-hour |
  | Runtime microVM v2 consumption | $0.1276/vCPU-hour, $0.0169/GB-hour |
  | Runtime billing rules | Per second, 1-second minimum; "CPU scales to zero during I/O wait" |
  | Gateway | $0.005 per 1,000 invocations (ListTools/InvokeTool/Ping); $0.025 per 1,000 Search; $0.02 per 100 tools indexed per month |
  | Identity | $0.010 per 1,000 token/API-key requests for non-AWS resources; no charge via Runtime or Gateway |
  | Memory | Short-term ingestion $0.25 per 1,000 events through Oct 5, 2026, then $1.00/GB; long-term retrieval $0.50 per 1,000 |
  | Policy | $0.000025 per authorization request; $0.13 per 1,000 input tokens for natural-language authoring |
  | Observability | Billed at CloudWatch rates |
  | Free tier | New AWS customers get "up to $200 in Free Tier credits" |

  Figures were read through a page summarizer.
- Token overhead: the harness's default `shell` and `file_operations` definitions add about 900 input tokens to each model request, and "an invocation can make multiple model requests". — [AWS: AgentCore harness tools](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-tools.html)

### Inferences
- **Per-unit fees are small.** At list prices, 1M questions with about 2 tool calls each cost roughly $10 in Gateway fees and $50 in Policy fees (about 2M authorizations).
- **The bigger costs are model tokens and microVM session time.** Agent loops make several model calls per question, against one generation in the current `retrieve_and_generate` design.
- **Unmeasured:** Runtime cost per question depends on session length and can't be estimated from docs alone.

### Gaps
- I did not fetch the Bedrock pricing page to confirm current Nova token prices or KB Retrieve and RetrieveAndGenerate charges.

## 9. How much is configuration vs. code, and what it means for this project

### Takeaway
- **Agents Classic** would be close to pure configuration and keeps today's deterministic, app-set date filter and RetrieveAndGenerate-style citations. It is closed to accounts without prior usage, with a frozen model catalog.
- **AgentCore harness + Gateway + Policy** is the supported path. It is config-driven for model, prompt, tools, JWT validation and Cedar permissions. For a *standard* S3 Vectors KB it still needs a small retrieval Lambda (or inline function) per KB, because the built-in KB connector serves only *managed* KBs.
- **Both** make KB selection a model decision, which is the predictability trade-off the team previously rejected for counts.

### Cited Findings
- Classic is closed to new accounts and frozen; AWS recommends the harness ("config-based starting point where developers can declare the agent's model, tools, and instructions"). — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- For a simple agent, migrating to the harness takes "hours"; "Complex agents with custom orchestrators or multi-agent collaboration will require more significant code work." — [AWS: Agents Classic maintenance mode](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)
- The KB connector serves managed KBs only. — [AWS: Managed KB connector target](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-managed-kb.html)
- Per-request KB retrieval config in Classic. — [AWS: Control agent session context](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-session-state.html)
- Inbound JWT and custom claims. — [AWS: Configure inbound JWT authorizer](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/inbound-jwt-authorizer.html)
- Cedar Policy (deny by default). — [AWS: Policy authoring guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-authoring-guide.html)

### Inferences
Comparison (C = configuration, Code = custom code; every cell rests on the findings above):

| Need | Agents Classic (allowlisted accounts only) | AgentCore harness + Gateway + Policy |
|---|---|---|
| Can this account use it? | Only with Agents activity in the 12 months before 2026-07-30; no exceptions | Yes (GA; also in GovCloud US-West) |
| Route a question across several KBs | C: KB associations with descriptions (2/agent default, adjustable) or supervisor/collaborators; model decides | Managed KBs: C via `AgenticRetrieveStream` with admin-configured retrievers. Standard KBs: Code (a Lambda or other target per KB), then the model picks the tool |
| Per-request UI date filter | C + small code: `sessionState...filter`, set by the app (deterministic) | No InvokeHarness KB-filter field found. Options: interceptor injection (Code), admin-pinned `parameterValues` (C, but static), or an inline function where the client runs retrieval (Code) |
| Per-user-group KB access | One agent/alias per group (≤10 aliases) or `InvokeInlineAgent` per request; ACL metadata filters | C: JWT authorizer (claims) + Cedar permit per KB tool; interceptors (Code) for finer filtering; managed-KB `userContext` ACLs |
| Citations / source links | Native `attribution.citations` (same type as RetrieveAndGenerate) with `location` + `metadata` | Tool results carry `location`/`metadata`; `AgenticRetrieveStream` returns answer + citations; a harness's *final* answer citations depend on what the model passes through (not verified) |
| Guardrail | C: `GuardrailConfiguration` on the agent | C: `guardrailConfig` in the model config (`converse_stream`); Policy guardrail signals (5 regions) |
| Nova-only | Any Bedrock model, catalog frozen 2026-07-30 | Any Bedrock model; defaults are Claude or "service-managed", so set Nova explicitly |
| Determinism | KB use is model-decided; custom-orchestration Lambda (Code) for fixed flows | Tool use is model-decided; `allowedTools`, allow/deny hooks (Lambda), Policy = deterministic *authorization* only |
| IaC | `AWS::Bedrock::Agent` (+ alias) in CFN/CDK | `AWS::BedrockAgentCore::*` (GatewayTarget, Harness, ...) + CDK `aws_bedrockagentcore`; AgentCore CLI `harness.yaml` |
| Extra platform charge | None | Per component (Runtime, Gateway, Policy, Memory); no harness fee |

- **Net for this project.**
  - **Shared agent weakness:** with either platform, adding an agent makes KB selection probabilistic, adds latency and cost per question, and moves answer composition into an agent loop.
  - **AgentCore's real gains:** declarative per-group authorization (JWT + Cedar) and a supported, region-broad platform.
  - **What it breaks:** for standard KBs it does not remove code, and the single-call determinism of today's `retrieve_and_generate` design would be lost.
  - **Lower-risk alternative:** keep app-side routing, for example code choosing which KB(s) to call per category and user group, each with a deterministic filter. That preserves determinism and citations. AgentCore Policy/Gateway would then be optional, mainly if MCP-style tool exposure becomes a goal.

### Gaps
- No AWS benchmark compares answer quality or latency of agent-routed multi-KB retrieval against app-routed calls. That would need a project-specific evaluation, for example with AgentCore Evaluations or the planned ~20-question harness.
- Not checked: whether Bedrock Flows is affected by any maintenance-mode change. The Agents Classic page says only that models, Knowledge Bases and Guardrails are unaffected.
