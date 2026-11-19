# Amazon Bedrock Flows as an orchestrator for a multi-knowledge-base RAG assistant (state as of November 2026)

Labels used below: **[PREVIEW]** = AWS docs still mark the feature as preview. **[REGION-LIMITED]** = the feature is documented only in some Regions. **[UNCONFIRMED]** = I could not verify it in primary docs. **[THIRD-PARTY]** = the only source is not AWS. **[CONFLICT]** = sources disagree. Research date: 2026-11-06. The Bedrock User Guide document history (checked up to its Oct 30, 2026 entries) has **no Flows entries after Sept 26, 2025**, and a 2026 What's New search found no Flows-specific announcements. So the feature set below appears to be the same as late 2025.

## 1. What node types exist today, what they do, their inputs/outputs and key limits

### Takeaway
The API's `FlowNodeConfiguration` union has 16 members: input, output, condition, iterator, collector, loop, loopInput, loopController, prompt, agent, knowledgeBase, storage (S3), retrieval (S3), lambdaFunction, inlineCode and lex. The User Guide describes these as 14 node types, with "DoWhile" standing for the three loop members. Every node references its resources (KB ID, model ID, agent alias, Lambda ARN, bucket, bot) as **static configuration**, never as runtime inputs. The newest node type is DoWhile (Sept 2025). Inline code is still preview.

### Cited Findings
- The API union members, verbatim names: `agent`, `collector`, `condition`, `inlineCode`, `input`, `iterator`, `knowledgeBase`, `lambdaFunction`, `lex`, `loop` ("configurations for a DoWhile loop"), `loopController`, `loopInput`, `output`, `prompt`, `retrieval` ("Retrieves data from an Amazon S3 location"), `storage` ("Stores an input in an Amazon S3 location") — [FlowNodeConfiguration API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_FlowNodeConfiguration.html)
- Every node has a name, a type, inputs (name, JsonPath-subset expression, type), outputs (name, type) and a type-specific `configuration`. "When this node is reached at runtime, Amazon Bedrock applies the expression to the whole input and validates that the result matches the data type." Data types: String, Number, Boolean, Object, Array — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **Flow input**: "Every flow contains only one flow input node and must begin with it." It takes the `content` from the `InvokeFlow` request and emits output `document` (any type) — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **Flow output**: input `document` (any type), returned in `flowOutputEvent.content`. "A flow can have multiple flow output nodes if there are multiple branches in the flow." — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **Condition**: takes multiple inputs and an ordered list of named conditions. It has no `outputs`. Branches are `Conditional` connections that name a condition, or `default` — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **Iterator**: input `array` (Array), outputs `arrayItem` (Any) and `arraySize` (Number). "The inputs to the iterator node are processed one by one and not in parallel with each other." — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **Collector**: inputs `arrayItem` and `arraySize`, output `collectedArray` (Array) — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **DoWhile loop**: input `loopInput`, outputs `loopOutput` and `iterationCount`. Configured with `condition` and `maxIterations` (default 10) — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html). Added Sept 26, 2025 — [Doc history](https://docs.aws.amazon.com/bedrock/latest/userguide/doc-history.html)
- **Prompt**: inputs are the template variables; output `modelCompletion` (String). The prompt comes either from Prompt management (`resource.promptArn`) or is defined `inline`. Optional `guardrailConfiguration` — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **Agent**: configured with `agentAliasArn`. Inputs `agentInputText` (String), `promptAttributes` (Object), `sessionAttributes` (Object); output `agentResponse` (String). It can pause for multi-turn input — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **Knowledge base**: input `retrievalQuery` (String); output `retrievalResults` (Array) or `outputText` (String). Details in section 2 — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **S3 storage** (type `Storage`): inputs `content` and `objectKey`, output `s3Uri`, configured with `bucketName`. **S3 retrieval** (type `Retrieval`): input `objectKey`, output `s3Content`. "Currently, the data in the S3 location must be a UTF-8 encoded string." — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **Lambda function**: configured with `lambdaArn`. Any number of named inputs; output `functionResponse` (Any). Details in section 5 — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **Inline code** [PREVIEW]: `language: "Python_3"`, output `response`. Details in section 4 — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **Lex**: configured with `botAliasArn` and `localeId`. Inputs `inputText`, `requestAttributes`, `sessionAttributes`; output `predictedIntent` (String). "Currently, the Lex node doesn't support multi-turn conversations. One Lex node can only process one utterance." The docs also warn that Lex "might store and use customer content" for service improvement unless you opt out — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- Only the Condition, Prompt, Lambda function and Inline code nodes accept multiple inputs — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- Timeline from the doc history:
  - Inference profiles in prompts and flows: Sept 23, 2024.
  - Model-specific inference parameters in prompt nodes: Oct 31, 2024.
  - Trace, and guardrails for KB/prompt nodes: Nov 7, 2024.
  - GA as "Amazon Bedrock Flows": Nov 22, 2024.
  - Multi-turn with agent nodes: Jan 22, 2025.
  - Flow templates: Mar 27, 2025.
  - Inline code (preview) and flow executions (preview): June 19, 2025.
  - Region expansion: July 1, 2025.
  - Mortgage-flow CloudFormation tutorial: Sept 2, 2025.
  - Trace enhancements and DoWhile: Sept 26, 2025.

  — [Doc history](https://docs.aws.amazon.com/bedrock/latest/userguide/doc-history.html)

### Inferences
- No node takes a resource identifier (KB ID, model ID, guardrail ID, agent alias, Lambda ARN) as a runtime input. Every one is a configuration field in the node JSON. So "which resource to call" is decided at design or deploy time, never per request.
- **[CONFLICT]** The User Guide shows DoWhile as one node (`type: "DoWhile"`, `configuration.doWhile`). The API union has three members (`loop`, `loopInput`, `loopController`). IaC should follow the API/CloudFormation shapes.

### Gaps
- I found no node type newer than DoWhile. The doc history and the What's New search show no Flows changes in 2026, but I did not scan the full 2026 What's New feed item by item.

## 2. The Knowledge Base node in detail (filters, numberOfResults, reranking, orchestration, prompt templates, inference config, guardrails, citations, output shape)

### Takeaway
The KB node is configured with a fixed `knowledgeBaseId`. Optional fields: `modelId` (turns on generate mode), `guardrailConfiguration` (generate mode only), `inferenceConfiguration`, `numberOfResults` (1–100), `orchestrationConfiguration`, `promptTemplate` and `rerankingConfiguration`. **It has no metadata filter or `retrievalConfiguration` / `vectorSearchConfiguration` field**, so a filter can be set neither per request nor at design time. Its only input is the query string. In generate mode it returns a plain string; no citations or source-reference output is documented. In retrieve mode it returns an array whose element shape is not documented.

### Cited Findings
- Complete field list of `KnowledgeBaseFlowNodeConfiguration` — [KnowledgeBaseFlowNodeConfiguration API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_KnowledgeBaseFlowNodeConfiguration.html):
  - `knowledgeBaseId`: required String, max length 10, pattern `$|^[0-9a-zA-Z]+`.
  - `modelId`: "model or inference profile … Omit this field if you want to return the retrieved results as an array."
  - `guardrailConfiguration`.
  - `inferenceConfiguration`: a `PromptInferenceConfiguration` union.
  - `numberOfResults`: Integer, "Minimum value of 1. Maximum value of 100".
  - `orchestrationConfiguration`.
  - `promptTemplate`: a `KnowledgeBasePromptTemplate`, "A custom prompt template to use with the knowledge base for generating responses".
  - `rerankingConfiguration`: a `VectorSearchRerankingConfiguration`.

  **There is no filter or retrievalConfiguration member.**
- `KnowledgeBaseOrchestrationConfiguration` has exactly `additionalModelRequestFields`, `inferenceConfig`, `performanceConfig` and `promptTemplate`. **There is no query-transformation / query-decomposition member** — [KnowledgeBaseOrchestrationConfiguration API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_KnowledgeBaseOrchestrationConfiguration.html)
- "The input into the node is the query to the knowledge base. The output is either the model response, as a string, or an array of the retrieved results." Node JSON: input `retrievalQuery` (String); output `"retrievalResults" | "outputText"`, type `"Array | String"` — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **[CONFLICT, minor]** The same page's summary table lists the KB output only as `retrievalResults` (Array) — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html). The SageMaker Unified Studio flow-nodes page lists it as `outputText` (String) (search snippet only, not fetched) — [SMUS flow nodes](https://docs.aws.amazon.com/sagemaker-unified-studio/latest/userguide/nodes.html)
- Guardrails: "Guardrails can only be applied when using `RetrieveAndGenerate` in a knowledge base node" — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html). "You can only include a guardrail when using RetrieveAndGenerate so you must include a modelId" — [Guardrails in flows](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-guardrails.html)
- The sample service-role policy for KB nodes grants only `bedrock:Retrieve` on `arn:aws:bedrock:…:knowledge-base/{KnowledgeBaseId}` — [Flows service role](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-permissions.html)
- **[THIRD-PARTY, contradicted]** A third-party guide says a KB "retrieval" node in Flows takes "optionally a metadata filter" (from a search summary) — [factualminds blog](https://www.factualminds.com/blog/amazon-bedrock-flows-workflow-orchestration/). The API reference above has no such field.
- **[UNCONFIRMED]** A re:Post question, "Integrating metadata filtering within Bedrock flows", returned HTTP 403 when fetched. The search snippet says an unofficial answer, about 660 days old, suggests "adding the filtered retrieval configuration to the specific knowledge base's query node". I could not verify this, and it conflicts with the API reference — [re:Post](https://repost.aws/questions/QUbOwKHpu_S2-9ydK1ByRbSA/integrating-metadata-filtering-within-bedrock-flows)
- For context outside Flows: the standalone Retrieve API returns results with content, location, metadata and score (search snippet) — [KnowledgeBaseRetrievalResult](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_KnowledgeBaseRetrievalResult.html). Citations come from RetrieveAndGenerate's `citations` field (search snippet) — [kb-test-retrieve-generate](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-generate.html)

### Inferences
- The project's per-request `date_numeric` filter has no equivalent in a KB node, static or dynamic. Neither does any other metadata filter, implicit filtering, or search-type override (hybrid/semantic), because no `vectorSearchConfiguration` is exposed.
- No citations output means generate mode cannot rebuild the container UI's `{label, url}` sources (GovDelivery links parsed from cited document paths). Two ways to keep citations:
  - Retrieve mode, then a Prompt node to generate, then a Lambda/inline-code node to build links from `retrievalResults`. This loses RetrieveAndGenerate's native citation spans, and the guardrail has to move to the Prompt node.
  - A Lambda node that calls `RetrieveAndGenerate` itself.
- The KB config has no `sessionId`, so a KB node cannot use RetrieveAndGenerate's conversational session.
- The docs say guardrails need "RetrieveAndGenerate", which implies generate mode calls RetrieveAndGenerate under the hood. Yet the sample role grants only `bedrock:Retrieve`. Generate mode probably also needs `bedrock:RetrieveAndGenerate` and `bedrock:InvokeModel` on the model. Test this.

### Gaps
- The exact JSON element shape of `retrievalResults` is not documented on any page I found. In particular I could not confirm whether it includes chunk metadata (e.g., `date_numeric`, source URI) or scores.
- What the KB node outputs when the guardrail intervenes (blocked message? any `INTERVENED` signal for downstream nodes?) is not documented. The project currently suppresses sources on `INTERVENED`.
- The doc history has no dates for when `numberOfResults`, reranking, orchestration and `promptTemplate` were added to the KB node.
- Not tested: whether the KB node works with *managed* KBs, which reject RetrieveAndGenerate per the project notes, and with S3 Vectors-backed standard KBs.

## 3. Can a flow choose the knowledge base at runtime, and how would you route among N knowledge bases?

### Takeaway
No. The KB is fixed per node (`knowledgeBaseId` is configuration, not an input). Routing among N KBs means one KB node per KB plus Condition-node branches, within these non-adjustable caps:
- 20 KB nodes per flow
- 5 Condition nodes per flow
- 5 conditions per Condition node
- 40 total nodes per flow

A truly dynamic KB ID needs a Lambda node that calls the KB APIs itself.

### Cited Findings
- `knowledgeBaseId` is a required configuration string; the node's only input is `retrievalQuery` — [KnowledgeBaseFlowNodeConfiguration API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_KnowledgeBaseFlowNodeConfiguration.html); [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- Condition semantics: "Conditions are evaluated in order. If more than one condition is satisfied, the earlier condition takes precedence." The `default` condition gets its own connection — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- Non-adjustable quotas: "(Flows) Knowledge base nodes per flow" 20; "(Flows) Condition nodes per flow" 5; "(Flows) Conditions per condition node" 5; "(Flows) Total nodes per flow" 40; "(Flows) Output nodes per flow" 20 — [Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- Input expressions are a JsonPath subset that must begin with `$.data`: `.name`, `[int]`, `[i,j]`, `[i:j]`, `*`. "If the whole input is a string, number, or boolean, the only expression that you can use … is `$.data`" — [Expressions](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-expressions.html)
- Alias-level parallelism: `FlowAliasConcurrencyConfiguration` "Determines how multiple nodes in a flow can run in parallel". `type` is `Automatic` ("Amazon Bedrock determines which nodes can be executed in parallel based on the flow definition and its dependencies") or `Manual`; `maxConcurrency` is 1–100 — [FlowAliasConcurrencyConfiguration API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_FlowAliasConcurrencyConfiguration.html); [AWS::Bedrock::FlowAlias](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-flowalias.html)
- In CloudFormation, `DefinitionSubstitutions` injects values (such as KB IDs) into `DefinitionString`/`DefinitionS3Location` at deploy time — [AWS::Bedrock::Flow](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-flow.html)

### Inferences
- **Pattern A (caller-labelled routing).** The input document is an Object, e.g. `{query, category, dateFrom, dateTo, userGroup}`. Condition nodes compare `$.data.category == "csms"` and similar, and each branch goes to its own KB node and Output node. This works, but the category must come from the caller or be computed upstream.
- **Pattern B (LLM classifier).** A Prompt node classifies the question, then a Condition node routes. `modelCompletion` is typed String, and string inputs only allow `$.data`. So the classifier must return an exact label for `==`, or a Lambda/inline-code node must parse JSON into an Object before fields can be read (see section 7).
- **Pattern C (fan-out and merge).** Send the query to several KB nodes, then merge with a multi-input Prompt or Lambda node. With `Automatic` concurrency these KB nodes may run in parallel. Fan-out behaviour is inferred from the concurrency docs, not tested.
- **Pattern D (dynamic).** A Lambda node calls `Retrieve`/`RetrieveAndGenerate` with a KB ID, filter and guardrail taken from the input, and returns `{answer, sources}` as an Object. This is the only Flows-native way to get a dynamic KB, filters and citations together. It moves the "configuration" back into Lambda code and environment variables.
- Capacity: 5 condition nodes × 5 conditions (plus defaults) gives roughly 25 branches. The 20-KB-node cap is the real ceiling, and a KB used in both retrieve and generate modes uses two nodes.
- No `in`/`contains` operator exists, so a check like "category ∈ user's permitted categories" can't be written as a condition. Compute a Boolean in Lambda/inline code first.

### Gaps
- Whether the `default` branch counts toward the 5-conditions-per-node quota is not documented.
- I did not verify that one node output can connect to several downstream nodes at once (fan-out). The docs imply it but don't show an example.

## 4. The Inline Code node: runtime, preview status, limits, network/SDK access, libraries

### Takeaway
**[PREVIEW] [REGION-LIMITED]** Python 3.12 runs in an isolated AWS-managed sandbox with **no internet access**. Limits:
- up to 5 inputs
- 5 inline code nodes per flow
- 25 running inline code nodes per account
- code up to 5 MB

It is not supported in asynchronous flow executions. Memory, time limits and the library list are not documented.

### Cited Findings
- Bedrock "executes your code in an isolated, AWS managed environment that isn't shared with anyone and doesn't have internet access." "Inline code node is in preview release for Amazon Bedrock and is subject to change." — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- Usage rules, verbatim from [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html):
  - "Inline code nodes aren't supported in asynchronous flow execution."
  - "the only programming language supported … is Python 3.12 (`Python_3`)"
  - "acts like an interactive Python session. Only the result of the last executed line is captured"
  - "`print` … isn't captured"
  - inputs are exposed as Python variables named after the node inputs
  - "up to five node inputs"
  - "up to five inline code nodes per flow"
  - "maximum of 25 running inline code nodes per AWS account"
  - "Your code can't exceed 5 MB."
- Quota "(Flows) Inline code nodes per flow" = 5, not adjustable — [Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- Preview launch (What's New, June 25, 2025; paraphrased by the fetch tool): the node runs Python scripts "without setting up Lambda functions for simple data processing". It is available in **US East (N. Virginia), US West (Oregon) and Europe (Frankfurt)** — [What's New](https://aws.amazon.com/about-aws/whats-new/2025/06/amazon-bedrock-flows-preview-persistent-long-running-execution-inline-code-support). Doc-history date: June 19, 2025 — [Doc history](https://docs.aws.amazon.com/bedrock/latest/userguide/doc-history.html)

### Inferences
- With no internet access the node presumably cannot reach Bedrock, S3 or any AWS endpoint, even with boto3. Treat it as a pure transformation step: parse LLM JSON into an Object, build source links from `retrievalResults`, compute routing Booleans. It cannot query a KB with a filter.
- Inline code doesn't work in async executions, so a flow that uses it must run through `InvokeFlow` (1-hour limit).

### Gaps
- Memory, CPU and per-execution timeout for inline code are not documented.
- The available libraries (stdlib only? any preinstalled packages? boto3?) are not documented.
- I found no confirmation that inline code expanded beyond us-east-1, us-west-2 and eu-central-1, or reached GovCloud, by Nov 2026.

## 5. The Lambda node: invocation contract, payload and response, timeouts

### Takeaway
The Lambda node sends a `messageVersion: "1.0"` event with the flow and alias ARNs plus each resolved input. Whatever the function returns becomes `functionResponse`, of any type. For flows created after 2024-11-22, Lambda is invoked with the **Flows service role**. Timeouts: a synchronous flow ends at 1 hour. In async executions a node can run 5 minutes (docs) or 15 minutes (What's New) **[CONFLICT]**, and the whole execution 24 hours.

### Cited Findings
- Node: `type: "LambdaFunction"`, `configuration.lambdaFunction.lambdaArn`, any number of named inputs (Any type), output `functionResponse` (Any) — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- Input event shape: `{"messageVersion":"1.0","flow":{"flowArn","flowAliasArn"},"node":{"name","inputs":[{"name","type","expression","value"}]}}`. `value` is "the whole input into the node after being resolved by the expression." Response: "When you write a Lambda function, you define the response returned by it. This response is returned to your flow as the output of the Lambda node." — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- "Previously, AWS Lambda and Amazon Lex resources were invoked using the Amazon Bedrock service principal. This behavior is changing for flows created after 2024-11-22 and the Amazon Bedrock Flows service role will be used". The role needs `lambda:InvokeFunction` on each function — [Flows service role](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-permissions.html)
- Timeouts: "When you run a flow by using the Amazon Bedrock console or with the InvokeFlow operation, the flow runs until it finishes or times out at one hour… When you run a flow execution… Individual nodes can run up to five minutes, and your entire flow can run for up to 24 hours." Lambda timeouts show up as `{"nodeName":"LambdaNode1","errorType":"ExecutionTimedOut","message":"Call to lambda function timed out"}` — [Flow executions](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-create-async.html)
- **[CONFLICT]** The What's New post (June 25, 2025; paraphrased) says long-running execution "extends step execution time to 15 minutes". It adds that workflows "previously had a two-minute idle timeout per step" — [What's New](https://aws.amazon.com/about-aws/whats-new/2025/06/amazon-bedrock-flows-preview-persistent-long-running-execution-inline-code-support). The current User Guide says 5 minutes per node — [Flow executions](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-create-async.html)
- Quota "(Flows) Lambda function nodes per flow" = 20, not adjustable — [Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)

### Inferences
- The event contains **no caller identity**: no IAM principal, user or session. It only carries the flow/alias ARNs and whatever the caller put into the input document (see section 9).
- The Lambda node is the escape hatch for everything the KB node lacks: dynamic KB ID, metadata filter (`date_numeric`), citations, explicit `ApplyGuardrail`. It can return an Object such as `{answer, sources}` straight to an Output node, which matches the frontend's existing `{answer, sources}` shape.

### Gaps
- The per-node timeout for *synchronous* `InvokeFlow` in Nov 2026 is not documented. Is the old 2-minute idle timeout still in effect?
- Event and response payload size limits, and whether Flows retries failed Lambda calls, are not documented in the pages I read.

## 6. Condition expressions and limits; DoWhile/loop limits; Iterator/Collector behaviour

### Takeaway
Conditions support `== != > >= < <=` (ordering only on Numbers) plus `and`/`or`/`not`. There are no string functions or membership tests. Each Condition node holds at most 5 conditions, and a flow at most 5 Condition nodes. DoWhile defaults to 10 iterations; the API allows 1–1000. Each flow has at most 1 Iterator and 1 Collector, and the Iterator is strictly sequential.

### Cited Findings
- Relational operators: `==` "(the data type must also be equal)" and `!=` for String/Number/Boolean; `>`, `>=`, `<`, `<=` for Number only. Logical operators `and`, `or`, `not`; parentheses recommended. Inputs can be compared with other inputs or with constants, e.g. `profit <= 1000` — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- Quotas (all not adjustable): Condition nodes per flow 5; Conditions per condition node 5; Iterator nodes per flow 1; Collector nodes per flow 1 — [Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- DoWhile (User Guide): "The loop executes at least once before evaluating the condition". "The loop continues as long as the condition evaluates to true, or the `maxIterations` is not exceeded". `maxIterations` "default value of 10 and only accepts positive numbers" — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- **[CONFLICT]** The API's `LoopControllerFlowNodeConfiguration` has `continueCondition` (required): "Specifies the condition that determines when the flow exits the DoWhile loop. The loop executes until this condition evaluates to true." `maxIterations` has a "Minimum value of 1. Maximum value of 1000." — [LoopControllerFlowNodeConfiguration API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_LoopControllerFlowNodeConfiguration.html). The wording (exit when true) contradicts the User Guide (continue while true).
- Iterator: "processed one by one and not in parallel with each other". Without a Collector, "The flow output node returns the final result for each input in a different response" — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- Trace events carry `iterationIndex` for nodes between an Iterator and a Collector — [Flow trace](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-trace.html)

### Inferences
- Routing on membership, substring or regex needs a Lambda or inline-code node that emits a Boolean or Number first. Examples: "is category in the user's permitted list", "does the question mention a date".
- The Iterator can't loop over KBs to query them in turn, because KB IDs are static per node. Even over static items it runs sequentially, which adds latency.

### Gaps
- The quotas page shows no DoWhile/loop-specific quota. The fetch tool reported 39 "(Flows)" quotas but itemized only 35, so a loop quota may exist among the 4 it missed.
- The rules for which nodes may sit inside a DoWhile body (e.g., KB nodes) were not checked.

## 7. The Prompt node: Amazon Nova models, structured/JSON output, guardrails, Prompt Management prompts, inference profiles

### Takeaway
Prompt nodes accept any Converse-compatible text model or inference profile, either inline (TEXT or CHAT templates; CHAT supports system prompts and `toolConfiguration`) or as a Prompt Management ARN. They support guardrails and model-specific request fields. Output is always a String (`modelCompletion`). No native "structured output / JSON schema" option is documented for the node.

### Cited Findings
- "Prompt node – You can use Prompt management with any text model supported for the Converse API." For KB nodes, see the KB supported-models page — [Flows supported Regions and models](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-supported.html)
- Inline prompt fields — [PromptFlowNodeInlineConfiguration API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_PromptFlowNodeInlineConfiguration.html):
  - `modelId`: "model or inference profile". The ARN pattern allows the `aws-us-gov`, `aws-eusc` and `aws-iso*` partitions.
  - `templateType`: `TEXT | CHAT`.
  - `templateConfiguration`.
  - `inferenceConfiguration`.
  - `additionalModelRequestFields`.
- CHAT template fields: `messages` (required), `system`, `inputVariables` (max 20), and `toolConfiguration` ("Configuration information for the tools that the model can use when generating a response") — [ChatPromptTemplateConfiguration API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_ChatPromptTemplateConfiguration.html)
- Prompt node output: `modelCompletion`, type String. Guardrail: "include the `guardrailConfiguration` field and specify the ID or ARN of the guardrail … and the version" — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html); [Guardrails in flows](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-guardrails.html)
- Prompt Management prompts are rendered with `bedrock:RenderPrompt` (for flows created after 2024-11-22; previously `bedrock:GetPrompt`) — [Flows service role](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-permissions.html)
- Inference profiles in prompts/flows since Sept 23, 2024; model-specific inference parameters since Oct 31, 2024; guardrails on prompt/KB nodes since Nov 7, 2024 — [Doc history](https://docs.aws.amazon.com/bedrock/latest/userguide/doc-history.html)
- Quota "(Flows) Prompt nodes per flow" = 20 (**adjustable**) — [Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)

### Inferences
- Amazon Nova text models should qualify for Prompt nodes because they are Converse models. The project's "Nova only" rule doesn't block Flows itself, but I did not verify each Nova model ID against Converse or Flows in us-east-1 and GovCloud (see Gaps).
- JSON output for routing has two options: instruct the model to emit JSON, or force a tool call through CHAT `toolConfiguration`. Either way the node emits a String. String inputs only allow `$.data`, so a parse step (inline code or Lambda) is needed before a Condition node can read fields. Alternatively, have the classifier output a bare label and compare it with `==`.

### Gaps
- Which Nova models (Micro, Lite, Pro, Premier, Nova 2 variants) work in Prompt nodes and as KB-node generation models in us-east-1 and GovCloud. The KB supported-models page only points to "Models at a glance"; I did not fetch the Nova model cards — [KB supported models](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-supported.html)
- When a CHAT prompt with `toolConfiguration` returns a tool-use block, how that appears in `modelCompletion` is undocumented.
- Whether Bedrock's newer structured-output / JSON-schema options can be passed through `additionalModelRequestFields` in a Prompt node is not confirmed.

## 8. Multi-turn conversation and memory, streaming, async/long-running executions, tracing

### Takeaway
Multi-turn is **[PREVIEW]** and works only through an **Agent node**; flows have no conversation memory for Prompt or KB nodes. `InvokeFlow` streams *per-node output events*, and no token-level streaming is documented. Async flow executions are **[PREVIEW]**: up to 24 h per execution, polling APIs, no inline code. Tracing covers node input/output, condition results, node actions (prompt, agent and Lambda nodes only) and agent dependency traces.

### Cited Findings
- "Amazon Bedrock Flows multi-turn conversation is in preview release". "To use a multi-turn conversation in a flow, you need an agent node connected to an Amazon Bedrock agent" (with User input enabled). The flow:
  1. emits a `FlowMultiTurnInputRequestEvent`, then a `FlowCompletionEvent` with `completionReason: "INPUT_REQUIRED"`;
  2. the caller resumes with `InvokeFlow` plus `executionId`, `nodeName` set to the agent node and `nodeInputName: "agentInputText"`;
  3. the flow finishes with `SUCCESS`.

  — [Multi-turn](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-multi-turn-invocation.html). Added Jan 22, 2025 — [Doc history](https://docs.aws.amazon.com/bedrock/latest/userguide/doc-history.html). Announcement: [What's New, Jan 2025](https://aws.amazon.com/about-aws/whats-new/2025/01/amazon-bedrock-flows-multi-turn-conversation-support) (title and date from search only)
- `InvokeFlow` request — [InvokeFlow API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_InvokeFlow.html):
  - fields: `enableTrace`, `executionId` (2–100 chars; "If you don't provide a value, Amazon Bedrock creates the identifier for you"), `inputs` ("Fixed number of 1 item"), `modelPerformanceConfiguration.performanceConfig.latency`;
  - the `executionId` comes back in header `x-amz-bedrock-flow-execution-id`.
- `InvokeFlow` response — same page:
  - the operation is described as "return the output of each node as a stream";
  - stream events: `flowOutputEvent`, `flowCompletionEvent`, `flowTraceEvent`, `flowMultiTurnInputRequestEvent` and typed exceptions;
  - "The AWS CLI doesn't support streaming operations in Amazon Bedrock, including `InvokeFlow`."
- Async executions — [Flow executions](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-create-async.html):
  - "Flow executions is in preview release".
  - APIs: `StartFlowExecution`, `GetFlowExecution`, `ListFlowExecutions`, `ListFlowExecutionEvents` (eventType `Flow` or `Node`), `GetExecutionFlowSnapshot`, `StopFlowExecution`.
  - Statuses: Running, Succeeded, Failed, TimedOut (24 h), Aborted.
  - Executions are "automatically deleted after 90 days".
  - Nodes run up to 5 min; the whole execution up to 24 h.
- The What's New post (June 25, 2025, paraphrased) says long-running executions are "available in all supported commercial regions where Flows operates" and come with console execution tracking — [What's New](https://aws.amazon.com/about-aws/whats-new/2025/06/amazon-bedrock-flows-preview-persistent-long-running-execution-inline-code-support)
- Trace: set `enableTrace: true`, and "Each `flowOutputEvent` in the response is returned alongside a `flowTraceEvent`". Documented trace events: condition-node result (`satisfiedConditions`), node input and node output (with `iterationIndex`) — [Flow trace](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-trace.html)
- `FlowTrace` union members: `conditionNodeResultTrace`, `nodeActionTrace`, `nodeDependencyTrace`, `nodeInputTrace`, `nodeOutputTrace` — [FlowTrace API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_FlowTrace.html)
- `FlowTraceNodeActionEvent`: "The service generates action events for calls made by prompt nodes, agent nodes, and AWS Lambda nodes". Fields: `serviceName`, `operationName`, `requestId`, `timestamp`, optional `operationRequest` and `operationResponse` (full JSON payloads) — [FlowTraceNodeActionEvent API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_FlowTraceNodeActionEvent.html)
- `FlowTraceDependencyEvent` carries `traceElements`, a union whose only member is `agentTraces` — [FlowTraceDependencyEvent API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_FlowTraceDependencyEvent.html); [TraceElements API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_TraceElements.html)
- Trace launched Nov 7, 2024; "Flows trace enhancements" added Sept 26, 2025 — [Doc history](https://docs.aws.amazon.com/bedrock/latest/userguide/doc-history.html)

### Inferences
- Chat history for follow-up questions must come from the caller (e.g., as a prompt variable in the input Object). Neither the Prompt node nor the KB node keeps session state, and the KB node exposes no RetrieveAndGenerate `sessionId`.
- The UI would get the final answer as one `flowOutputEvent`, not token by token. The docs never mention token streaming. If streaming matters, keep generation outside Flows.
- **KB nodes are not listed among nodes that emit action traces.** Per the docs, RetrieveAndGenerate citations can't be pulled out of the trace for a KB node. Prompt and Lambda nodes do expose full request/response payloads in the trace.
- Async executions (polling, minutes to hours) suit batch work such as count-question backfills or catalog builds. They don't suit the interactive Q&A path.

### Gaps
- Whether `InvokeFlow` emits partial tokens in practice was not tested. The docs only describe whole-node output events.
- Async executions and multi-turn in GovCloud: the What's New post says "commercial regions"; GovCloud was not confirmed.

## 9. How per-user attributes are passed in and enforced; is anything in Flows identity-aware?

### Takeaway
Nothing in Flows is identity-aware. `InvokeFlow` carries no user context. Every node calls its resources with the **flow's service role**, and the Lambda event carries no caller identity. Per-user attributes (group, permitted categories, date range) exist only if the backend puts them in the single input document, and they can only be enforced by Condition-node logic, or by Lambda code, over that caller-supplied data.

### Cited Findings
- `InvokeFlow` takes only `flowIdentifier`/`flowAliasIdentifier` in the URI, plus `enableTrace`, `executionId`, `inputs` (exactly 1) and `modelPerformanceConfiguration`. There is no identity or user-context field — [InvokeFlow API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_InvokeFlow.html)
- The Lambda event contains only `messageVersion`, `flow.flowArn`, `flow.flowAliasArn` and `node.name`/`node.inputs[]` — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- The service role is assumed by `bedrock.amazonaws.com` (recommended conditions: `aws:SourceAccount` and `AWS:SourceArn` = `arn:aws:bedrock:<region>:<acct>:flow/*`). Every model, prompt, KB, agent, bucket, guardrail, Lambda, Lex bot and KMS key used by the flow must be granted to that role. Since 2024-11-22, Lambda and Lex are invoked with this role — [Flows service role](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-permissions.html)
- The only nodes with attribute-style inputs are Agent (`promptAttributes`, `sessionAttributes`) and Lex (`requestAttributes`, `sessionAttributes`). The KB node accepts only `retrievalQuery` — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)

### Inferences
- The trust boundary is the backend (FastAPI). It has to authenticate the user, then do one of three things:
  - **Choose the flow or alias per permission tier.** Each tier gets its own flow whose role and KB nodes cover only the permitted KBs. IAM then limits which backend role can invoke which alias. This is the only option where an AWS-enforced boundary separates tiers.
  - **Pass `userGroup`/`permittedCategories` in the input.** Condition nodes then gate the branches. The data is only as trustworthy as the backend, and there's no `in` operator (section 6).
  - **Pass a signed token to a Lambda node.** The Lambda re-validates it and calls KB APIs with per-user filters.
- KB nodes can't filter, so **document-level permissions inside one KB cannot be enforced by a KB node**. You need separate KBs per access tier, routed by condition, or Lambda-based retrieval with filters.
- The one service role must reach every KB in the flow, so a misrouted branch can reach any of them. Splitting flows per tier limits this.

### Gaps
- I did not fetch the IAM action, resource-type and condition-key details for `bedrock:InvokeFlow` (e.g., per-alias resource ARNs) from the Service Authorization Reference.

## 10. Deployment and configuration: CloudFormation, CDK, substitutions, validation, versions/aliases, IAM, regions (incl. GovCloud)

### Takeaway
Flows are fully declarable in CloudFormation as `AWS::Bedrock::Flow`, `AWS::Bedrock::FlowVersion` and `AWS::Bedrock::FlowAlias`. The definition can be inline, a JSON string (≤512,000 chars) or an S3 object, with `${key}` `DefinitionSubstitutions`. CDK has no L2/alpha Flow construct; `@aws-cdk/aws-bedrock-alpha` covers Agents, Guardrails, Prompts, Inference Profiles and Knowledge Bases only, so CDK users write the L1 definition JSON. An alias points to exactly one version. Flows run in us-east-1 and both GovCloud (US) Regions.

### Cited Findings
- `AWS::Bedrock::Flow` — [AWS::Bedrock::Flow](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-flow.html):
  - Properties: `Definition` (FlowDefinition), `DefinitionString` (JSON, max 512000), `DefinitionS3Location`, `DefinitionSubstitutions`, `ExecutionRoleArn` (required), `Name` (required, `^([0-9a-zA-Z][_-]?){1,100}$`), `Description`, `CustomerEncryptionKeyArn`, `Tags`, `TestAliasTags`. Every property updates with no interruption.
  - `DefinitionSubstitutions`: "A map that specifies the mappings for placeholder variables in the prompt flow definition… Variables can be template parameter names, resource logical IDs, resource attributes, or a variable in a key-value map. Only supported with the `DefinitionString` and `DefinitionS3Location` fields." Syntax: `${key_name}` or `${variable_1,variable_2,...}`.
  - `GetAtt`: `Arn`, `Id`, `Status` (NotPrepared/Preparing/Prepared/Failed; "Send a PrepareFlow request to package the latest changes into the DRAFT version"; on Failed "check the error message in the `validations` field"), `Validations`, `Version`, `CreatedAt`, `UpdatedAt`.
- `AWS::Bedrock::FlowVersion` has only `FlowArn` and `Description`, and **both require replacement on update**. `Ref` returns `flowArn|version` — [AWS::Bedrock::FlowVersion](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-flowversion.html)
- `AWS::Bedrock::FlowAlias`: `FlowArn` (replacement), `Name`, `Description`, `RoutingConfiguration` ("Currently, you can only specify one", min 1 / max 1), `ConcurrencyConfiguration` and `Tags`. `Ref` returns `flowArn|aliasArn` — [AWS::Bedrock::FlowAlias](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-flowalias.html)
- CDK: `@aws-cdk/aws-bedrock-alpha` (v2.275.0-alpha.0, "experimental") "facilitates the deployment of Bedrock Agents, Guardrails, Prompts, Inference Profiles and Knowledge Bases". Its README sections are Agents, Guardrails, Prompts, Inference Profiles, Knowledge Bases and Mixins, with **no Flow constructs** — [aws-bedrock-alpha README](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-bedrock-alpha-readme.html). The community `generative-ai-cdk-constructs` Bedrock L2s are deprecated in favour of the alpha package (search snippet) — [PyPI](https://pypi.org/project/cdklabs.generative-ai-cdk-constructs/0.1.316/)
- Validation and prepare APIs exist with rate quotas: "(Flows) ValidateFlowDefinition requests per second" 2; "(Flows) PrepareFlow requests per second" 2; Create/Update/Delete for Flow/Alias/Version at 2 rps; Get/List at 10 rps — [Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- A console-created service role "will attach permissions dynamically if you add nodes … If you remove nodes, however, the permissions won't be deleted" — [Flows service role](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-permissions.html)
- Regions: ap-northeast-1/2/3, ap-south-1/2, ap-southeast-1/2, ca-central-1, eu-central-1/2, eu-north-1, eu-south-1/2, eu-west-1/2/3, sa-east-1, **us-east-1**, us-east-2, **us-gov-east-1, us-gov-west-1**, us-west-2 — [Flows supported Regions](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-supported.html)
- "Amazon Bedrock Flows and Prompt Management are now available in AWS GovCloud (US) and Europe (Stockholm) regions", posted Mar 11, 2025. No feature exclusions were listed — [What's New](https://aws.amazon.com/about-aws/whats-new/2025/03/amazon-bedrock-flows-prompt-management-govcloud/)
- Flow templates arrived Mar 27, 2025, and a CloudFormation-template mortgage-flow tutorial on Sept 2, 2025 — [Doc history](https://docs.aws.amazon.com/bedrock/latest/userguide/doc-history.html)
- **[UNCONFIRMED]** A search snippet says a Flows docs page on docs.aws.eu, dated Jan 7, 2026, is a draft for the AWS European Sovereign Cloud private preview (not fetched) — [docs.aws.eu flows-how-it-works](https://docs.aws.eu/es_es/bedrock/latest/userguide/flows-how-it-works.html)

### Inferences
- **Config-driven fit.** The flow graph can live as a JSON/YAML file in the repo and be fed to `CfnFlow` (`definition_string` plus `definition_substitutions`). KB IDs, guardrail ID/version and Nova model or inference-profile IDs would come from `iac/config/common.yml`. This fits the project's convention, but the values stay **static per deployment**, not per request. That `CfnFlow`/`CfnFlowVersion`/`CfnFlowAlias` exist follows from CDK generating an L1 class for every CloudFormation resource; I did not check them on the CDK pages.
- **Version churn.** A FlowVersion can't be updated in place, and versions per flow are capped at 10 (not adjustable). So each definition change needs a new version resource, and old versions have to be pruned or the quota stops deployments.
- An alias routes to exactly one version, so there is no built-in weighted canary.

### Gaps
- I did not fetch the CDK L1 class docs (`aws_cdk.aws_bedrock.CfnFlow` etc.).
- Whether CloudFormation fails the stack on flow-definition validation errors, or leaves `Status: Failed` with `Validations`, is not documented (`Validations` reads "Property description not available").
- I did not verify which preview features (inline code, async executions, multi-turn) are available in GovCloud.

## 11. Quotas and pricing

### Takeaway
Per-flow node quotas are small and mostly fixed. Per flow: 40 total nodes, 20 KB, 20 Prompt (adjustable), 20 Lambda, 20 Agent, 5 Condition with 5 conditions each, 5 inline code, 1 Iterator, 1 Collector, 10 versions and 10 aliases. Per account: 100 flows and 1,000 flow executions, both adjustable. Flows charges per node transition, $0.035 per 1,000 according to AWS's own pricing example. Model, KB, S3 and other usage is billed separately.

### Cited Findings
- Quotas, all "(Flows) …", default per supported Region; only those marked adjustable can be raised — [Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html):

  | Quota | Default | Adjustable |
  |---|---|---|
  | Total nodes per flow | 40 | No |
  | Agent nodes per flow | 20 | No |
  | Knowledge base nodes per flow | 20 | No |
  | Lambda function nodes per flow | 20 | No |
  | Output nodes per flow | 20 | No |
  | Prompt nodes per flow | 20 | **Yes** |
  | S3 retrieval nodes per flow | 10 | No |
  | S3 storage nodes per flow | 10 | No |
  | Condition nodes per flow | 5 | No |
  | Conditions per condition node | 5 | No |
  | Inline code nodes per flow | 5 | No |
  | Lex nodes per flow | 5 | No |
  | Input nodes per flow | 1 | No |
  | Iterator nodes per flow | 1 | No |
  | Collector nodes per flow | 1 | No |
  | Flow versions per flow | 10 | No |
  | Flow aliases per flow | 10 | No |
  | Flows per account | 100 | **Yes** |
  | Flow executions per account | 1,000 | **Yes** |

  Control-plane request rates are 2 rps for create, update, delete, prepare and validate, and 10 rps for get and list.
- Other documented limits:
  - Inline code: "maximum of 25 running inline code nodes per AWS account", code ≤5 MB — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
  - Alias `maxConcurrency` 1–100 — [FlowAliasConcurrencyConfiguration API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_FlowAliasConcurrencyConfiguration.html)
  - DoWhile `maxIterations` ≤1000 — [LoopControllerFlowNodeConfiguration API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_LoopControllerFlowNodeConfiguration.html)
  - `DefinitionString` ≤512,000 chars — [AWS::Bedrock::Flow](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-flow.html)
  - Sync flow 1 h; async node 5 min, async flow 24 h — [Flow executions](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-create-async.html)
- Pricing, from the official example ("News summarization"): "The number of node transition per flow execution is: 2+1+10*2 + 3 = 25 node transitions/flow execution… Total monthly bill is: 25 * 960 * $0.035/1000 = $0.84". "The bill will also include additional charges for AWS services used in the workflow execution", naming S3 usage in retrieval/storage nodes and foundation-model usage in prompt nodes — [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/) (the rate statement itself was not in the fetched text; the rate is derived from the example)
- **[THIRD-PARTY]** "$0.035 per 1,000 node transitions", with a node transition "counted each time a node in your workflow is executed" — [Tutorials Dojo cheat sheet](https://tutorialsdojo.com/amazon-bedrock-flows-cheat-sheet/). The charge began **Feb 1, 2025** (Japanese blog; the only source for the date) — [issoh.co.jp](https://www.issoh.co.jp/tech/details/3376/)

### Inferences
- A minimal Input → KB node → Output flow is about 3 transitions, around $0.0001 per question. Adding a classifier Prompt node and a Condition node makes it about 5 transitions, around $0.00018. Flows' own fee is negligible next to model and KB costs. The real costs are the extra LLM calls (e.g., a classifier) and the extra latency per node.
- Versions (10) and aliases (10) per flow, and nodes per flow (40), cannot be raised. These matter more for a growing multi-KB router than price does.

### Gaps
- Not found: an `InvokeFlow` requests-per-second quota, input/output payload size limits, a connections-per-flow quota, and a DoWhile quota. The fetch tool reported 39 "(Flows)" quotas but listed only 35.
- What "(Flows) Flow executions per account = 1,000" counts (concurrent async executions? stored executions?) is not defined.
- I did not find the official pricing-page sentence stating the rate and defining "node transition", or the official effective date.

## 12. Known limitations reported in AWS docs, re:Post and blogs that matter for RAG routing

### Takeaway
For this project the blocking limitations are in the KB node:
- no metadata filters, so the `date_numeric` date-range filter has nowhere to go;
- no citations output, so the GovDelivery source links can't be built;
- guardrails only in generate mode;
- one fixed KB per node.

Inline code, multi-turn and async are all still preview after 12–17 months. CDK has no Flow L2. I found no AWS source announcing filter or citation support for the KB node.

### Cited Findings
- KB node fields have no filter or retrieval configuration; output is a "string" or an "array of the retrieved results" — [KnowledgeBaseFlowNodeConfiguration API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_KnowledgeBaseFlowNodeConfiguration.html); [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
- Guardrail only with RetrieveAndGenerate, so a `modelId` is required — [Guardrails in flows](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-guardrails.html)
- Action-trace events cover only prompt, agent and Lambda nodes — [FlowTraceNodeActionEvent API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_FlowTraceNodeActionEvent.html)
- Preview status as of the current docs:
  - inline code "in preview" — [Node types](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html)
  - multi-turn "in preview" — [Multi-turn](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-multi-turn-invocation.html)
  - flow executions "in preview" — [Flow executions](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-create-async.html)
- Limitations that were later lifted:
  - The "two-minute idle timeout per step" and the need for "Lambda functions for basic data processing" before June 2025 — [What's New](https://aws.amazon.com/about-aws/whats-new/2025/06/amazon-bedrock-flows-preview-persistent-long-running-execution-inline-code-support)
  - Lambda/Lex invoked with the Bedrock service principal, and prompts rendered with `GetPrompt`, before 2024-11-22 — [Flows service role](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-permissions.html)
  - No loop node before Sept 2025; no guardrails or trace before Nov 2024 — [Doc history](https://docs.aws.amazon.com/bedrock/latest/userguide/doc-history.html)
- **[THIRD-PARTY / UNCONFIRMED, conflicting with the API]** A blog claims an optional metadata filter on the KB node — [factualminds blog](https://www.factualminds.com/blog/amazon-bedrock-flows-workflow-orchestration/). An unofficial re:Post answer (page returned 403) suggests putting a filtered retrieval configuration on the KB node — [re:Post](https://repost.aws/questions/QUbOwKHpu_S2-9ydK1ByRbSA/integrating-metadata-filtering-within-bedrock-flows)
- Missing citations elsewhere in Bedrock (Agents, not Flows): a boto3 issue reports an agent answering from a KB with no citations although the trace held `retrievedReferences` (search snippet) — [boto3 issue #4617](https://github.com/boto/boto3/issues/4617)
- No Flow constructs in `@aws-cdk/aws-bedrock-alpha` — [aws-bedrock-alpha README](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-bedrock-alpha-readme.html)

### Inferences
- **Parity check against the current backend**, which makes one RetrieveAndGenerate call with a per-request `date_numeric` filter, guardrail ID+version and citation-based sources:
  - A pure-Flows KB node keeps only the guardrail.
  - The date filter and citations need a Lambda node that calls RetrieveAndGenerate.
  - Once that Lambda is the core step, Flows mainly adds a managed, versioned DAG for routing. It does not make the RAG step configuration-only.
- Flows becomes more useful if the team accepts:
  - KB-per-category or per-permission-tier separation instead of metadata filters;
  - date filtering moved elsewhere (e.g., separate KBs per period, which is impractical, or a Lambda);
  - sources rebuilt from `retrievalResults` by inline code or Lambda (shape unverified).
- Because inline code, multi-turn and async executions are all still preview, a production design should avoid depending on them. That is especially true for GovCloud, where I couldn't confirm they are available.

### Gaps
- I found no AWS blog or What's New post from 2025–2026 announcing KB-node metadata filters, dynamic KB selection or citation outputs. That absence is a signal, but I did not read the full What's New archive.
- I could not read re:Post threads (403); community reports of KB-node behaviour (e.g., output shapes, guardrail-intervention output) remain unverified.
