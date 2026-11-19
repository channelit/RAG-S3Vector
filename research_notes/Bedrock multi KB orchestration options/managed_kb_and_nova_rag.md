# Amazon Bedrock Managed Knowledge Base (BMKB), AgenticRetrieveStream, and Amazon Nova support for RetrieveAndGenerate (state as of 6 Nov 2026)

Scope note for the report writer:
- **Two KB families.** "Managed KB" / "BMKB" means `knowledgeBaseConfiguration.type: MANAGED`. "Customer-managed" / "standard" / "self-managed" means `type: VECTOR`; this project's current KB is that type, on S3 Vectors.
- **What was read this session.** Every finding below comes from the cited page, read in this session, unless it is marked as follows:
  - "(sibling notes)": read by a parallel researcher, recorded in `knowledge_bases_native.md` in this folder, and not re-read here.
  - "(search excerpt)": the page itself was not opened.
  - "(local repo)": from this repository's files.
- **How AWS text was read.** Quotes come from pages fetched through a summarising fetch tool. Short exact wording was preserved wherever the tool returned the page verbatim, which covers all API references and most User Guide pages.
- **Conflicts and unverified points** are flagged inline.

## 1. Managed KB data model: custom `.metadata.json` sidecar metadata (e.g., a Number `date_numeric`) and per-request range filters in Retrieve / AgenticRetrieveStream; metadata limits

### Takeaway
Yes, with caveats. The managed-KB S3 connector reads per-document `.metadata.json` sidecars (max 10 KB, typed attributes). AWS's own example is a YYYYMMDD NUMBER (`"created_date": 20221205`), the same shape as this project's `date_numeric`. Both query APIs take a standard `RetrievalFilter`:
- `Retrieve` via `retrievalConfiguration.managedSearchConfiguration.filter`
- `AgenticRetrieveStream` via each retriever's `retrievalOverrides.filter`

`startsWith` and `stringContains` are not supported on managed KBs. The managed-KB note names `greaterThan` and `lessThan` but is silent on `greaterThanOrEquals` and `lessThanOrEquals`; only the Kendra migration guide says those map directly. So test inclusive range operators, or use `greaterThan (from-1)` / `lessThan (to+1)` on the integer. Undocumented for managed KBs, so test: list-valued attributes (`STRING_LIST`, e.g. `related_countries`), the untyped sidecar shape this project writes, and per-document key limits.

### Cited Findings
- **The managed S3 connector supports sidecar metadata.** Supported features include "Document metadata fields through separate metadata files" and "Incremental content syncs for added, updated, and deleted content" — [Amazon S3 connector (managed KB)](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-s3.html)
- **Sidecar naming, size and format.** "For each document, create a file named `filename.extension.metadata.json` in the same Amazon S3 path. The metadata file must not exceed 10 KB." AWS's example uses the **typed** form:
  ```json
  {"metadataAttributes": {
     "company":      {"value": {"type": "STRING", "stringValue": "BioPharm Innovations"}},
     "created_date": {"value": {"type": "NUMBER", "numberValue": 20221205}},
     "author":       {"value": {"type": "STRING", "stringValue": "Lisa Thompson"}}}}
  ```
  For supported types and operators the page points to the general "Metadata and filtering" page. Source: [kb-managed-ds-s3](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-s3.html)
- **Separate metadata prefix (minor conflict).** The connector has an optional top-level parameter `metadataFilesPrefix`, described as "The Amazon S3 prefix where document metadata files (.metadata.json) are stored". The console calls it "**Metadata files prefix**". This sits awkwardly with the sentence that sidecars live "in the same Amazon S3 path" — [kb-managed-ds-s3](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-s3.html)
- **Kendra-to-BMKB migration guide on metadata.** "In BMKB, metadata is defined via .metadata.json sidecar files stored alongside source documents in S3, with a maximum size of 10 KB per file. Each attribute must be typed as STRING, NUMBER, or BOOLEAN." No `STRING_LIST` is mentioned — [Amazon Kendra availability change / migration guide](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- **Managed-KB filter restrictions.** "The `startsWith` and `stringContains` metadata filters are not supported. Use `equals`, `greaterThan`, `lessThan`, `in`, or `notIn` operators instead." Also: "For fully managed knowledge bases, reserved metadata fields use an underscore prefix (for example, `_source_uri`, `_data_source_id`). You cannot override reserved metadata fields" — [Configure and customize queries (kb-test-config)](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html)
- **Generic filter grammar.** This applies to the shared `RetrievalFilter` type and is not managed-specific:
  - number-only range operators `greaterThan`, `greaterThanOrEquals`, `lessThan`, `lessThanOrEquals`
  - `andAll` / `orAll` each take a "List of up to 5 filter types", with "one level of embedding"

  Source: [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html)
- **Kendra guide's operator mapping (only source for inclusive operators).** The guide's "Metadata Filter Operator Mapping" lists `GreaterThanOrEquals → greaterThanOrEquals` and `LessThanOrEquals → lessThanOrEquals` as "Direct mapping". It also repeats that "BMKB does not support startsWith or stringContains" — [Kendra migration guide](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- **Retrieve on a managed KB.** "After you create and sync a managed knowledge base, use the `Retrieve` API to query it. In the `retrievalConfiguration` field, specify `managedSearchConfiguration`. The `vectorSearchConfiguration` field applies only to custom knowledge bases." — [Create a managed knowledge base](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html). Retrieve's `managedSearchConfiguration` holds `filter`, `numberOfResults`, `rerankingConfiguration` and `rerankingModelType` — [API: Retrieve](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Retrieve.html)
- **AgenticRetrieveStream filters are per retriever.** The structure is `retrievers[].configuration.knowledgeBase` (`KnowledgeBaseRetrieverConfiguration`):
  - `knowledgeBaseId`: max length 10, pattern `[0-9a-zA-Z]+`
  - `retrievalOverrides`: "Overrides for retrieval behavior such as filters and result limits"
    - `filter`: a `RetrievalFilter` union
    - `maxNumberOfResults`: "Valid Range: Minimum value of 1"; no maximum documented

  Sources: [API: KnowledgeBaseRetrieverConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_KnowledgeBaseRetrieverConfiguration.html); [API: RetrievalOverrides](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_RetrievalOverrides.html). The user guide: "Each retriever can optionally include metadata filters and a maximum number of results." — [Use agentic retrieval](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html)
- **Custom connector metadata.** Inline attributes are typed, e.g. `{"key": "department", "value": {"stringValue": "HR", "type": "STRING"}}`. Alternatively `metadata.type: S3_LOCATION` points at a `.metadata.json` — [Custom connector ACLs (managed KB)](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-custom-acl.html)
- **AWS sample: server-side metadata filter.** An AWS ML Blog post (31 Aug 2026) calls `AgenticRetrieveStream` "with an explicit equals filter on `user_id`". "The application builds the filter value on the server from the verified JWT, not from the request body." — [Build multi-tenant agentic chat applications … with Amazon Bedrock Managed Knowledge Base](https://aws.amazon.com/blogs/machine-learning/build-multi-tenant-agentic-chat-applications-on-enterprise-data-with-amazon-bedrock-managed-knowledge-base/)
- **This project's sidecars (local repo).**
  - Format: the untyped short form `{"metadataAttributes": {"key": "string" | number | boolean | ["list"]}}`.
  - Fields: `date_numeric` (`int(YYYYMMDD)`), `timestamp`, `sent_date`, `message_id`, `doc_type`, `source_url` / `attachment_url`, and the list attribute `related_countries`.
  - Size: capped at 1,024 bytes, because "the S3 Vectors-backed KB's sync job silently *ignores* documents whose sidecar exceeds 1024 bytes".

  Source: `app/scraper/scraper/kb_metadata.py` (local repo)

### Inferences
- **`date_numeric` carries over directly to a managed KB** as a NUMBER attribute. The UI date range can be enforced natively in both APIs:
  - `Retrieve`: `managedSearchConfiguration.filter`
  - `AgenticRetrieveStream`: the same filter copied into **every** retriever's `retrievalOverrides.filter`. There is no request-level filter, so the backend must inject it per retriever.
- **Safe inclusive range without `>=` / `<=`.** Because `date_numeric` is an integer, `x >= from` is equivalent to `x > from - 1`, and `x <= to` to `x < to + 1`. This works even when `from - 1` is not a valid date (e.g. 20260500).
- **Sidecar size.** The 10 KB managed sidecar limit (vs. 1 KB on the S3 Vectors-backed KB) would remove the need to trim `related_countries`. That holds only if the managed store has no lower per-chunk limit, which is undocumented.
- **Format risk.** The managed connector documents only the typed `{"value": {"type": …}}` form, and the Kendra guide lists only STRING/NUMBER/BOOLEAN. The scraper's untyped sidecars and the `related_countries` list may need converting.
- **Country filters may not be native.** The managed-KB operator note does not mention `listContains`. A multi-valued country filter would then have to live in the app's own catalog or count path, or the countries would need re-encoding.
- **`metadataFilesPrefix`** could keep sidecars under a separate prefix (e.g. `kb-metadata/`). That relates to the CLAUDE.md clean-up item about the ingestion Lambda indexing scraper uploads. The "same path" wording conflicts, so test before relying on it.

### Gaps
- No managed-KB page states:
  - a maximum number of metadata keys per document
  - per-chunk or per-vector metadata limits
  - whether some keys can be made non-filterable
- No managed-KB page explicitly confirms `greaterThanOrEquals` / `lessThanOrEquals`, `listContains`, `STRING_LIST`, or the untyped sidecar form. Test all of them against a managed KB.
- `includeForEmbedding` (customer-managed sidecar option) is not mentioned for managed KBs.
- Undocumented: whether filters also constrain the agent's "full document expansion" (`GetDocumentContent`), and whether the planner can add, change or drop customer-supplied filters.

## 2. Which query APIs work on managed KBs (official statement vs. conflicting pages), and what citations look like

### Takeaway
The API references are unambiguous: **`RetrieveAndGenerate` and `RetrieveAndGenerateStream` "cannot be used with managed knowledge bases"**. Use `Retrieve` or `AgenticRetrieveStream`, plus `GetDocumentContent` for full documents. This matches the project's observed "not supported for managed knowledge bases" error.

The Kendra-to-BMKB migration guide contradicts this. It shows `retrieve_and_generate` with `managedSearchConfiguration` and claims a "Native RetrieveAndGenerate API". It is stale or inconsistent on other points too, so treat it as wrong on this one. Confusingly, the R&G request model still contains `managedSearchConfiguration` and `userContext` fields.

Citation shapes differ by API:
- `Retrieve` returns ranked chunks with `location`, `metadata` and `score`, and no generation.
- `AgenticRetrieveStream` returns an answer with span citations that point by index into its `results`. Those results carry `metadata` and `sourceRetriever`, but no `location` object.

### Cited Findings
- **RetrieveAndGenerate.** "**Note** This API cannot be used with managed knowledge bases. Use AgenticRetrieveStream or Retrieve with managed knowledge bases." — [API: RetrieveAndGenerate](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_RetrieveAndGenerate.html)
- **RetrieveAndGenerateStream.** Same note, plus "The AWS CLI doesn't support streaming operations in Amazon Bedrock, including `InvokeModelWithResponseStream`." It requires the `bedrock:RetrieveAndGenerate` permission — [API: RetrieveAndGenerateStream](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_RetrieveAndGenerateStream.html)
- **API-model oddity.** Both R&G request syntaxes include `retrievalConfiguration.managedSearchConfiguration` and a top-level `userContext {userId}`, despite the note — [API: RetrieveAndGenerate](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_RetrieveAndGenerate.html)
- **Managed-KB user guide.** "use the `Retrieve` API to query it… specify `managedSearchConfiguration`" — [kb-managed-create](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html). "Agentic retrieval currently supports only managed knowledge bases." — [kb-test-agentic-retrieve](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html)
- **Conflicting page: the Kendra migration guide.** Claims BMKB has "the ability to generate responses (with a Retrieve and Generate API)". Its architecture table lists "RAG support | … | Native RetrieveAndGenerate API". Its "Using RetrieveAndGenerate for RAG" sample calls `bedrock_runtime.retrieve_and_generate(...)` with `managedSearchConfiguration` and a Claude 3 Sonnet `modelArn` — [Kendra migration guide](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- **Signs that guide is stale.**
  - It says BMKB "currently supports seven data source connectors". The managed-KB create page lists 12 (S3, Box, Confluence Cloud, Confluence Data Center, SharePoint Online, Google Drive, OneDrive, Salesforce, ServiceNow, Zendesk, Web Crawler, Custom) — [Kendra guide](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html); [kb-managed-create](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html)
  - Its `create_knowledge_base` sample passes `embeddingModelArn` without `embeddingModelType`. The create page says "When `embeddingModelType` is omitted, it defaults to `MANAGED`. When using `MANAGED`, you must not specify `embeddingModelArn` or `embeddingModelConfiguration`." — [kb-managed-create](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html)
- **Retrieve response shape.** `retrievalResults[]` carries:
  - `content` (`text`, `byteContent`, `row`, `audio`, `video`, `type`)
  - `documentId`
  - `location` (`s3Location.uri`, `webLocation.url`, `sharePointLocation.url`, `confluenceLocation.url`, `googleDriveLocation.url`, `oneDriveLocation.url`, `salesforceLocation.url`, `customDocumentLocation.id`, …)
  - `metadata` (map)
  - `score`

  The response also has `guardrailAction` (`INTERVENED | NONE`) and `nextToken`. Retrieve now accepts a top-level `guardrailConfiguration {guardrailId, guardrailVersion}`. Source: [API: Retrieve](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Retrieve.html). AWS's agentic-retrieval blog's comparison table says Retrieve supports guardrails — [Agentic retrieval for Amazon Bedrock Managed Knowledge Base](https://aws.amazon.com/blogs/machine-learning/agentic-retrieval-for-amazon-bedrock-managed-knowledge-base/)
- **AgenticRetrieveStream result shape.** The final event holds:
  - `result.generatedResponse.answer`
  - `result.generatedResponse.citations[] {startIndex, endIndex, references[] {resultIndex}}`
  - `result.results[] {content {byteContent, mimeType, text}, metadata, sourceRetriever {identifier}}`
  - `result.nextToken`

  Source: [API: AgenticRetrieveStream](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetrieveStream.html). `endIndex` is exclusive, and `resultIndex` "indexes into the `results` array on the same result event". "When the same chunk is retrieved by multiple sub-queries, it appears only once in the final results." — [kb-test-agentic-retrieve](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html)
- **Agentic scores.** Relevance scores appear only in trace events, not directly in results, and deduplication applies only to the final result event — [Agentic retrieval blog (23 Jul 2026)](https://aws.amazon.com/blogs/machine-learning/agentic-retrieval-for-amazon-bedrock-managed-knowledge-base/)

### Inferences
- **The container UI's single call can't move as-is.** The `retrieve_and_generate` call cannot target a managed KB. Moving to BMKB means one of:
  - (a) `AgenticRetrieveStream` with service-side generation
  - (b) `Retrieve` plus a separate generation call (Converse with Nova), which is the two-step design CLAUDE.md currently rules out
- **Source links in agentic mode** must come from `results[resultIndex].metadata`: the app's own sidecar fields (`message_id`, `source_url`, `attachment_url`) or the reserved `_source_uri`. There is no `location` object, and which metadata keys are echoed back is undocumented, so verify empirically. The current GovDelivery-link logic in `backend/main.py` would need adapting.

### Gaps
- No AWS page explains why the R&G request model includes `managedSearchConfiguration` while the service rejects managed KBs (vestigial field, or a planned feature).
- The exact metadata keys returned on managed-KB `Retrieve` / `AgenticRetrieveStream` results are not documented. Examples: whether custom sidecar attributes are echoed back, and whether `_source_uri` appears.

## 3. AgenticRetrieveStream: request/response, KB listing and descriptions, KB limit, answer generation, model choice (incl. Nova), guardrails, userContext, latency and cost

### Takeaway
`AgenticRetrieveStream` is a streaming loop: plan → (speculative) retrieve → optional full-document expansion → evaluate → (optionally) answer. It runs over **up to 5 managed KBs**, each a "retriever" with a free-text `description` that the planner uses for routing. Each retriever can carry its own filter and result cap. The service generates a cited answer by default (`generateResponse`, default `true`). Other inputs:
- multi-turn `messages`
- AgentCore Memory sessions
- reviewed, versioned "retrieval instructions" (persona, answer format, answer policy, retrieval guidance)
- `userContext.userId` (email) for ACLs

Model choice: `MANAGED` (service default, model undisclosed) or `CUSTOM`. `CUSTOM` takes a Bedrock foundation-model or inference-profile ARN, or a "Mantle" model with a Bedrock project ID. **No AWS page lists which CUSTOM models are accepted, and Nova is never mentioned.**

Guardrails work only with `CUSTOM` (BLOCK only, no ANONYMIZE). Cost: $4 per 1,000 calls plus $1 per 1,000 underlying retrieves with the managed model, or token pricing plus $1 per 1,000 retrieves with your own model. AWS rates its latency "Highest". Not available in GovCloud.

### Cited Findings
- **Purpose.** "Agentic retrieval uses a foundation model to intelligently decompose complex queries into sub-queries and iteratively retrieve relevant information from your knowledge bases." "The operation returns results through a stream that includes retrieval results, trace events for visibility into the process, and a generated response synthesized from the results by default, which can be turned off." — [API: AgenticRetrieveStream](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetrieveStream.html)
- **Request body** (`POST /agenticRetrieveStream`). Source: [API: AgenticRetrieveStream](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetrieveStream.html)
  - Required:
    - `agenticRetrieveConfiguration`
    - `messages[] {content {text}, role}` (min 1)
    - `retrievers[] {configuration {knowledgeBase {knowledgeBaseId, retrievalOverrides}}, description}` (min 1)
  - Optional:
    - `generateResponse`
    - `memoryConfiguration`
    - `nextToken`
    - `policyConfiguration.bedrockGuardrailConfiguration {guardrailId, guardrailVersion}`
    - `retrievalInstructionConfiguration {retrievalInstructionId, version}`
    - `userContext {userId}`
- **`agenticRetrieveConfiguration` fields.** Sources: [API: AgenticRetrieveConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetrieveConfiguration.html); [API: FoundationModelConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_FoundationModelConfiguration.html)
  - `foundationModelType`: `CUSTOM | MANAGED`. "CUSTOM uses a specified model, MANAGED uses the service default."
  - `foundationModelConfiguration`: "Required when foundationModelType is CUSTOM". Its `type` is `BEDROCK_FOUNDATION_MODEL | MANTLE_FOUNDATION_MODEL`.
  - `maxAgentIteration`: integer, "Minimum value of 0"
  - `rerankingModelType`: `CUSTOM | MANAGED | NONE`. "If not specified, defaults to MANAGED for managed embedding knowledge bases and NONE for custom embedding knowledge bases."
  - `rerankingConfiguration.bedrockRerankingConfiguration.modelConfiguration.modelArn`
- **Model ARN format.** The Bedrock model ARN pattern accepts `bedrock` or `sagemaker` ARNs with an optional resource-type prefix (e.g. `foundation-model/…` or `inference-profile/…`) or bare IDs — [API: BedrockFoundationModelModelConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_BedrockFoundationModelModelConfiguration.html). The Mantle variant adds `projectId`: "The Amazon Bedrock project ID used for billing and usage attribution… the service uses the default project" (pattern `proj_…|default`) — [API: MantleFoundationModelModelConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_MantleFoundationModelModelConfiguration.html)
- **Nova is not on Mantle.** The Nova Pro, Nova Lite and Nova 2 Lite cards each list `bedrock-mantle` as **not supported**, with only `bedrock-runtime` supported — [Nova Pro card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html); [Nova Lite card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html); [Nova 2 Lite card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html)
- **MANAGED model.** "When you set `foundationModelType` to `MANAGED`, the service selects the optimal model for you." No model is named — [API: AgenticRetrieveStream](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetrieveStream.html). The 23 Jul 2026 AWS blog does not name the managed model or mention Nova in its visible text — [Agentic retrieval blog](https://aws.amazon.com/blogs/machine-learning/agentic-retrieval-for-amazon-bedrock-managed-knowledge-base/)
- **Model ownership and permissions.** "The customer provides and owns the foundation model, embedding model, and reranking model used during agentic retrieval if provided. Your IAM credentials are used to invoke these models." Required IAM:
  - `bedrock:AgenticRetrieveStream` on `*`
  - `bedrock:Retrieve` and `bedrock:GetDocumentContent` on `arn:aws:bedrock:{region}:{account-id}:knowledge-base/*`
  - `bedrock:InvokeModelWithResponseStream` on `*`
  - with guardrails, additionally `bedrock:GetGuardrail` and `bedrock:ApplyGuardrail`

  Source: [kb-test-agentic-retrieve](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html)
- **Number of KBs.** "You can specify up to 5 retrievers, each pointing to a managed knowledge base by its ID." — [kb-test-agentic-retrieve](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html)
- **Routing by description.** `AgenticRetriever.description` is "A description of the retriever's purpose" (optional) — [API: AgenticRetriever](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetriever.html). The blog: "The planner reads those descriptions to route each sub-query to the most relevant KB." "Vague descriptions lead to vague routing." — [Agentic retrieval blog](https://aws.amazon.com/blogs/machine-learning/agentic-retrieval-for-amazon-bedrock-managed-knowledge-base/)
- **Speculative retrieval.** "An initial retrieval that runs before the first planning step to reduce latency. For a single knowledge base, this retrieves results using the raw user query. For multiple knowledge bases, this performs a probe search to help route queries to the appropriate retrievers." — [kb-test-agentic-retrieve](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html)
- **Process steps:**
  - session-history load (AgentCore Memory)
  - planning, which "follows the instruction's `retrievalGuidance`" when an instruction is applied
  - retrieval
  - full document expansion via "the GetDocumentContent API"
  - response generation, which "When `generateResponse` is set to `true` (the default)… synthesizes a natural-language answer", streamed as `responseEvent` text chunks
  - a final result event with deduplicated results, the answer and citations

  Source: [kb-test-agentic-retrieve](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html)
- **Trace events.** The user guide lists Planning, Retrieval, Speculative retrieval, Full document expansion and Session history load — [kb-test-agentic-retrieve](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html). The API's trace actions additionally include an undocumented `codeExecution {documents[] {documentId, sourceRetriever}}` action, alongside `retrieve`, `memoryRetrieve` and `fullDocumentExpansion`. They also carry `failures`, `warnings`, `retrievalMetadata[] {identifier, retrievalType}` and `retrievalResponse[]` — [API: AgenticRetrieveStream](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetrieveStream.html)
- **Guardrails.**
  - "A guardrail is supported only when foundationModelType is CUSTOM. Passing a guardrail with the default MANAGED type, or without setting foundationModelType, fails validation… applying a guardrail means naming an explicit model by its modelArn."
  - "only the `BLOCK` action is supported. The `MASK` action is not supported."
  - Guardrails whose sensitive-information policy uses `ANONYMIZE` "fail validation even when `foundationModelType` is `CUSTOM`."

  Source: [kb-test-agentic-retrieve](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html)
- **userContext.** "Contains information about the user making the request. This is used for access control filtering…" It has only `userId` (required string) — [API: UserContext](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_UserContext.html)
- **Memory configuration.** Source: [kb-test-agentic-retrieve](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html)
  - `memoryId` plus `sessionBinding {actorId, sessionId}` and/or `retrievalConfigs`. "A `memoryConfiguration` that sets only a `memoryId` is not valid."
  - With `sessionBinding`, `messages` must carry only the current user query.
  - `persistenceMode` is `DEFAULT` (requires `generateResponse=true`) or `NONE`.
  - `retrievalConfigs` "currently accepts at most one entry", with at most 5 `metadataFilters`.
- **Retrieval instructions** (a configuration-over-code lever). "A retrieval instruction steers how agentic retrieval searches your knowledge bases and how it answers. You create the instruction once, Amazon Bedrock reviews it, and then you reference it from your requests." Its fields `persona`, `answerFormat` and `answerPolicy` shape the answer. It must be `ACTIVE`; version pinning is optional (default `DRAFT`). A missing or inactive instruction fails with `ValidationException` "before any events are streamed" — [kb-test-agentic-retrieve](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html). Quotas: 50 instructions per account per Region, 50 versions each, 24,000 total characters (all adjustable) — [kb-managed-quotas](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-quotas.html)
- **Rate quota (conflict).** "Maximum AgenticRetrieveStream requests per minute, per account | 300 | Yes" and "Maximum query input characters per Retrieve or AgenticRetrieveStream request (English text) | 10,000" — [kb-managed-quotas](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-quotas.html). This conflicts with the AWS General Reference, which gives 60 RPM (sibling notes) — [AWS General Reference: Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- **Documentation gap on limits.** The agentic page says "For quotas on retrievers per request, results per retrieval call, and maximum agent iterations, see Service quotas for managed knowledge bases". That quotas page lists none of the three — [kb-test-agentic-retrieve](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html); [kb-managed-quotas](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-quotas.html)
- **Latency, accuracy and tuning (AWS ML Blog, 23 Jul 2026).** Source: [Agentic retrieval blog](https://aws.amazon.com/blogs/machine-learning/agentic-retrieval-for-amazon-bedrock-managed-knowledge-base/)
  - The comparison table rates latency as Retrieve "Lowest", AgenticRetrieveStream "Highest".
  - "It costs more and takes longer because it makes multiple model calls, but it finds evidence a single search can miss."
  - MuSiQue multi-hop: "20 percent absolute recall improvement over single-shot retrieval". "Single-hop questions show smaller gains (under five points)."
  - Guidance: "Use **3** for a single KB and 4–5 for multi-KB or comparative queries" (`maxAgentIteration`).
  - "Streaming is always on"; agentic retrieval works only with managed KBs.
- **Pricing.** Managed model: "$4.00 per 1,000 Agentic Retrieve API calls + $1.00 per 1,000 underlying Retrieve API calls". With your own LLM: "$1.00 per 1,000 underlying Retrieve API calls" plus the model provider's price for query planning. AWS's example: a 50 GB SharePoint index with 100,000 agentic calls (two underlying retrievals each) costs $850 per month — [Amazon Bedrock pricing (Managed Knowledge Bases tab)](https://aws.amazon.com/bedrock/pricing/). The blog says the same: "Agentic retrieval is priced per call, and the model you choose for the orchestration sets the rate." — [Agentic retrieval blog](https://aws.amazon.com/blogs/machine-learning/agentic-retrieval-for-amazon-bedrock-managed-knowledge-base/)
- **GovCloud.** In AWS GovCloud (US-West): "Service-managed embedding, reranking, and agentic retrieval models" are not supported, and "Agentic retrieval is not available." — [Managed KB supported Regions](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-regions.html)

### Inferences
- **Under the Nova-only rule, `MANAGED` is out.** Its model is undisclosed, and `MANAGED` also cannot carry the project's guardrail. The only compliant configuration is:
  - `foundationModelType: CUSTOM`
  - `foundationModelConfiguration.type: BEDROCK_FOUNDATION_MODEL` with a Nova ARN, e.g. `arn:aws:bedrock:us-east-1:<acct>:inference-profile/us.amazon.nova-pro-v1:0`
  - `policyConfiguration` with the stack's guardrail. Its PII policy is BLOCK, so it should pass validation; an ANONYMIZE guardrail would not.

  Whether the service accepts Nova here is undocumented and must be tested. Nova supports response streaming, which the required `InvokeModelWithResponseStream` permission implies is needed.
- **One model does everything.** A single `foundationModelConfiguration` drives planning, evaluation and answer generation. With Nova, Nova writes the answer.
- **Reranker under Nova-only.** On a managed-embedding KB the default reranker is the undisclosed managed one. A strict Nova-only reading would set `rerankingModelType: NONE` (or pick a CUSTOM Bedrock reranker, none of which are Nova).
- **Config-driven category routing.** The 5-retriever cap plus per-retriever descriptions fit "multiple categories as separate KBs":
  - descriptions and KB IDs live in config
  - the backend selects at most 5 KBs the user may access
  - the backend injects the date filter into each one
- **Rough cost per question at AWS list prices,** assuming 3 underlying retrieves: CUSTOM ≈ $0.003 plus Nova tokens; MANAGED ≈ $0.004 + $0.003 = $0.007. Latency will exceed a single `Retrieve` and is likely above today's single R&G call. AWS publishes no numbers.

### Gaps
- No AWS page lists the models accepted for `foundationModelType: CUSTOM`, or confirms Nova or inference-profile ARNs. Test empirically (sketch in section 8).
- The identity of the `MANAGED` planning model is not disclosed.
- `codeExecution` trace actions are not explained anywhere. They might matter for aggregate or count questions; unverified.
- Not documented:
  - default and maximum `maxAgentIteration`
  - maximum `maxNumberOfResults`
  - p50/p95 latency figures
  - whether the guardrail evaluates retrieved content or only input and output
- Conflict between 300 RPM (managed-KB quotas page) and 60 RPM (General Reference) is unresolved; check Service Quotas in the target account.

## 4. Managed KB ACLs: S3 ACL file and per-document ACL format, users vs. groups, identity source, documents without ACLs, "not authorization" caveat, recommended controls

### Takeaway
ACL-aware retrieval filters by an **email** supplied by the caller (`userContext.userId`). Group support depends on the connector:
- **SaaS connectors** (SharePoint, OneDrive, Google Drive, Confluence, Box, Zendesk, Salesforce, ServiceNow): groups are crawled and resolved by the service.
- **S3 and Custom:** ACL entries must be `Type: USER`. There are no groups, and there is no real-time re-verification.

Missing ACLs fail closed: on ACL-enabled S3 the document is never ingested, and on other connectors it is never returned. Callers that omit `userContext` get zero results from ACL-enabled sources. AWS states this "is not authorization": the app must authenticate users and pass verified identity. ACLs are unavailable in GovCloud.

### Cited Findings
- **What is ingested.** "Bedrock Managed Knowledge Base ingests the permissions (allowed users, denied users, allowed groups, denied groups) alongside document content. At query time, you supply a user context…" — [Access Control Lists awareness enablement](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-acl.html)
- **Caveat (verbatim).** "Bedrock Managed Knowledge Base provides *ACL-aware filtering*, not a security boundary. Bedrock Managed Knowledge Base does not authenticate end users — your application is responsible for authenticating users and passing verified identity context… You must not rely on this feature as a sole access control mechanism without upstream authentication." — [kb-managed-acl](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-acl.html)
- **Identity model.** Source: [kb-managed-acl](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-acl.html)
  - "the email you pass in the user context must exactly match the email associated with the user in each connected data source. There is no alias resolution or cross-identity-provider mapping."
  - "Groups… are identified by however the source connector represents them… and are matched against the group memberships crawled from that data source."
  - "At query time, Bedrock Managed Knowledge Base resolves which groups a user belongs to based on this crawled data automatically."
  - "Group memberships are as fresh as the last sync."
  - Users in very large groups may see ACL propagation lag after a sync.
- **Connector matrix.**
  - Real-time ACL verification: SharePoint, OneDrive, Google Drive, Confluence, Confluence Data Center, Box, Zendesk, Salesforce; partial for ServiceNow.
  - Amazon S3 and Custom: pre-retrieval filter supported, real-time "Not supported" ("customer-provided… is the source of truth").
  - Web Crawler: "Not supported".

  Source: [kb-managed-acl](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-acl.html)
- **Failure behaviour.** Fails closed on group-resolution failure, verification timeout or internal error. "Error responses indicate an ACL resolution failure so you can distinguish it from a query that genuinely matched no documents." — [kb-managed-acl](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-acl.html). The S3 page adds that *misconfiguration* is silent: "ACL misconfigurations do not produce explicit errors during retrieval… affected documents are silently omitted" — [S3 document-level access controls](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-s3-acl.html)
- **Customer responsibilities.** Authenticating end users, consistent email identity ("If emails differ across systems, ACL matching fails silently"), and email lifecycle management (re-assigned addresses) — [kb-managed-acl](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-acl.html)
- **S3 ACL format.**
  - Set `"aclEnabled": true` and `"aclConfiguration": {"globalAccessControlListS3Uri": "s3://bucket/acl/global-acl.json"}`.
  - Global file: `[{"keyPrefix": "s3://bucket/finance/", "aclEntries": [{"Name": "user1@example.com", "Type": "USER", "Access": "ALLOW"}]}]`.
  - Per-document alternative: `{"metadataAttributes": {}, "accessControlList": [{"Name": …, "Type": "USER", "Access": "ALLOW" | "DENY"}]}`.
  - "`Type` — Must be `USER`." "Deny overrides allow."
  - "Per-document metadata takes precedence over the global ACL file."
  - "The ACL configuration file must be stored in the same Amazon S3 bucket as your data source content."
  - "Changes to the global file require reindexing the affected prefix."
  - "**For ACL-enabled Amazon S3 data sources, documents without an associated ACL entry are not ingested.**"

  Source: [kb-managed-ds-s3-acl](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-s3-acl.html). `aclEnabled` "cannot be changed after creation" — [kb-managed-ds-s3](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-s3.html)
- **Custom connector ACLs.** Supplied per document in `IngestKnowledgeBaseDocuments` under `metadata.accessControlList`:
  - inline (`metadata.type: IN_LINE_ATTRIBUTE`, lowercase `name` / `type` / `access`), or
  - from an S3 `.metadata.json` (`S3_LOCATION`, capitalised fields)
  - "`type` — Must be `USER`."
  - "you cannot mix an inline ACL with S3-based metadata attributes"

  Source: [kb-managed-ds-custom-acl](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-custom-acl.html)
- **Query-time behaviour.** Source: [ACL-aware retrieval on managed knowledge bases](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-acl.html)
  - "The `userId` is always the user's universal email address associated with the underlying data source."
  - "If you do not provide `userContext` in a Retrieve request, ACL-enabled data sources return zero results. Non-ACL data sources in the same knowledge base return results normally."
  - "Missing permissions are treated as restricted, not public."
  - Partial results are not backfilled.
  - "Third-party identity provider credentials are cached for up to 1 hour." "Changes to access control permissions are eventually consistent. Updates typically take effect within a few minutes."
- **Where `userContext` appears.** It exists on `Retrieve`, `AgenticRetrieveStream` and `GetDocumentContent`, and on the R&G request models, which reject managed KBs anyway — [API: Retrieve](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Retrieve.html); [API: AgenticRetrieveStream](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetrieveStream.html); [API: GetDocumentContent](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_GetDocumentContent.html)
- **GovCloud.** "Document-level access control (ACLs). The `aclEnabled` setting and ACL filtering at query time are not available." in us-gov-west-1 — [kb-managed-regions](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-regions.html)
- **AWS pattern for tenant isolation (Aug 2026).** A shared KB, Cognito for authentication, and a server-side metadata filter from the verified JWT. The post says isolation can use "a metadata filter or… document-level access control lists (ACLs) evaluated by the service". It recommends per-tenant KBs only for "a small number of large tenants with strict separation requirements" — [AWS ML Blog, 31 Aug 2026](https://aws.amazon.com/blogs/machine-learning/build-multi-tenant-agentic-chat-applications-on-enterprise-data-with-amazon-bedrock-managed-knowledge-base/)

### Inferences
- **Group-restricted categories on S3** (this project's content source) cannot use native group ACLs. Options:
  - (a) Expand each group to member emails in the global ACL file, per category prefix. The app regenerates the file and resyncs or reindexes the prefix whenever membership changes. Every document needs an entry, or it isn't ingested.
  - (b) Server-side metadata filters, e.g. an `access_group` STRING with `in: [user's verified groups]`, as in AWS's Aug 2026 sample.
  - (c) One KB per permission tier, with IAM scoping on `bedrock:Retrieve` for KB ARNs. `AgenticRetrieveStream` can then target only the user's allowed KBs (≤5).
- **Recommended layering for "not authorization".** Authenticate upstream (Cognito, ALB OIDC or IAM Identity Center). Only the backend role holds Retrieve/AgenticRetrieveStream permissions, and the backend derives `userId` or filters from verified tokens. This matches what AWS recommends: authentication upstream, with verified identity passed down.
- **No ACL hardening in GovCloud.** A GovCloud deployment would rely entirely on filters or separate KBs.

### Gaps
- No documented maximum number of ACL entries per document or prefix, and no maximum global ACL file size.
- No API accepts group claims at query time (`UserContext` has only `userId`), and no way to supply group membership for S3 or Custom sources was found.
- Whether ACLs and metadata filters combine with AND semantics is implied by "pre-retrieval filtering" but not explicitly stated.

## 5. Managed KB models: embedding model and reranker, Nova Multimodal Embeddings, consequences

### Takeaway
By default a managed KB uses a **service-managed embedding model and managed semantic reranker**, both undisclosed and both $0. Alternatively the customer picks a custom 1024-d float32 Bedrock embedding:
- Titan Text Embeddings V2
- Cohere Embed English v3, Multilingual v3 or v4
- **Amazon Nova Multimodal Embeddings**
- TwelveLabs Marengo Embed 3.0 (the only multimodal option)

The embedding choice is fixed at creation. **A custom embedding disables the managed reranker.** The reranker then defaults to `NONE`, or a customer-chosen Bedrock reranker can be named at query time. GovCloud requires a custom embedding and has no managed reranker.

### Cited Findings
- **What AWS manages.** "including embedding and reranking with service-managed models by default. You can optionally provide your own Bedrock embedding model at creation time or your own reranking model at query time." The comparison table lists:
  - Managed Embedding model: "Comes with built-in managed model optimized for accuracy and performance at no extra cost"
  - Custom Embedding model: "Choose any Bedrock embedding model with float32 and 1024 dimensions"
  - Managed Reranking: "Comes with built-in managed semantic reranker… at no extra cost"

  Source: [Build a managed knowledge base](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html)
- **Custom embedding options and rules.** Source: [kb-managed-create](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html)
  - Supported custom models: "Amazon Titan Text Embeddings V2, Cohere Embed English v3, Cohere Embed Multilingual v3, Cohere Embed v4, Amazon Nova Multimodal Embeddings". You "must specify the model dimensions (1024) and float32 embedding data type".
  - Multimodal: "TwelveLabs Marengo Embed 3.0… is the only supported multimodal embedding model" (requires a multimodal storage destination).
  - "You cannot change the embedding model type after creating the knowledge base."
  - "**If you create a knowledge base with a custom embedding model, the managed reranker is not available for that knowledge base.**"
  - API: `{"type": "MANAGED", "managedKnowledgeBaseConfiguration": {"embeddingModelType": "CUSTOM", "embeddingModelArn": "…", "embeddingModelConfiguration": {"bedrockEmbeddingModelConfiguration": {"dimensions": 1024}}}}`
- **Reranker defaults.** "defaults to MANAGED for managed embedding knowledge bases and NONE for custom embedding knowledge bases" — [API: AgenticRetrieveConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetrieveConfiguration.html). Retrieve's `managedSearchConfiguration` accepts `rerankingModelType` and a `bedrockRerankingConfiguration {modelConfiguration.modelArn, numberOfRerankedResults, metadataConfiguration}` — [API: Retrieve](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Retrieve.html)
- **Pricing.** Managed parser, embeddings and re-ranking are "$0", and choosing your own embedding or re-ranking model incurs additional charges — [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)
- **Available rerankers.** The only Bedrock rerankers are Amazon Rerank 1.0 (not in us-east-1) and Cohere Rerank 3.5 (sibling notes) — [Supported Regions and models for reranking](https://docs.aws.amazon.com/bedrock/latest/userguide/rerank-supported.html)
- **GovCloud.** "You must provide your own Amazon Bedrock embedding model when you create a knowledge base, and your own reranking model at query time if you want reranking." — [kb-managed-regions](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-regions.html)
- **Parsing.** Managed KBs use a "Managed parser" (`parsingStrategy: SMART_PARSING`) by default — [kb-managed-create](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html)

### Inferences
- **Strict Nova-only means `CUSTOM` with Nova Multimodal Embeddings,** a different embedding from the current KB's Titan Text v2, so the content must be re-ingested. That forfeits the managed reranker. The remaining reranker choices (Amazon Rerank 1.0, Cohere 3.5) are not Nova, so a strict reading means no reranking.
- **The managed parser's internals are undisclosed** and may use non-Nova models. Raise this with the user as part of the Nova-only decision.

### Gaps
- Provenance of the managed embedding, reranker and SMART_PARSING models is not disclosed.
- Undocumented whether a custom-embedding managed KB still performs hybrid (keyword + semantic) search. The Kendra guide says BMKB "always performs hybrid search", but doesn't address custom embeddings.
- Availability of Nova Multimodal Embeddings in us-gov-west-1 was not checked.

## 6. Managed KB vector storage: AWS-managed? Can the customer list or scan vectors or chunks? Is there a document-listing API usable for counting?

### Takeaway
The store is **fully Bedrock-managed**: no customer-visible S3 Vectors index, no `ListVectors` / `GetVectors` equivalent, and only a KMS key option. The planned count path, which scans the KB's own S3 Vectors index the way `kb_report.py` does, **does not transfer to a managed KB**.

What remains:
- `ListKnowledgeBaseDocuments`: per-data-source identifiers, status and `updatedAt`, up to 1,000 per page. Enough for a total "documents indexed" count, but it returns no metadata.
- `GetDocumentContent`: full RAW or EXTRACTED content per document via a 5-minute pre-signed URL.
- `Retrieve`: capped at 100 results; no faceted search or facet counts.

A count/catalog path would have to come from the scraper-side catalog or S3 sidecars. That is the "Alternative" already described in CLAUDE.md.

### Cited Findings
- **Comparison table, data store and infrastructure rows.** Source: [kb-build-managed](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html)
  - Managed: "Auto-scaling datastore of embeddings, text, metadata and raw files. Managed completely by Bedrock."
  - Customer-managed: "Customers choose, provision, scale, and update vector and text datastores"
  - Infrastructure management, managed: "None required"
  - Infrastructure management, customer-managed: "You provision and maintain your vector DB, with direct access to it"
- **Encryption.** "You can also optionally provide a KMS key for encryption of the managed vector store." — [kb-managed-create](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html)
- **ListKnowledgeBaseDocuments.**
  - Request: `POST /knowledgebases/{kbId}/datasources/{dsId}/documents`; `maxResults` 1–1000; `nextToken`.
  - Response: `documentDetails[] {dataSourceId, identifier {s3.uri | custom.id, dataSourceType}, knowledgeBaseId, status, statusReason, updatedAt}`. No metadata attributes.
  - The page does not say whether it applies to managed KBs.

  Source: [API: ListKnowledgeBaseDocuments](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_ListKnowledgeBaseDocuments.html)
- **GetDocumentContent.** "Retrieves the content of an ingested document from a knowledge base. Returns a pre-signed URL…" `outputFormat` is `RAW` ("returns the original file") or `EXTRACTED` ("returns parsed text as JSON"). It accepts `userContext`, and "The URL expires after 5 minutes." — [API: GetDocumentContent](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_GetDocumentContent.html)
- **No counting support.** "Maximum results | 100 passages (Retrieve API) | 100 results (Retrieve API)"; "BMKB's architecture does not support faceted search". Its suggested metadata-filter workaround "does not provide dynamic facet counts" — [Kendra migration guide](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- **Document lifecycle (Aug 2026 AWS blog).**
  - Statuses: the post names `STARTING`, `TEXT_INDEXED` and `INDEXED`. Treating a document as searchable at `STARTING` returns empty results, so readiness should be marked at `TEXT_INDEXED`. The ordering is inferred from the post's timings, not stated as a lifecycle.
  - Observed timings: text was queryable in about 2–3 s; PDFs reached `TEXT_INDEXED` in 5–30 s and `INDEXED` in about 90 s ("not a service-level commitment").
  - "Each IngestKnowledgeBaseDocuments call accepts up to 10 documents."
  - "There is no partial update."

  Source: [AWS ML Blog, 31 Aug 2026](https://aws.amazon.com/blogs/machine-learning/build-multi-tenant-agentic-chat-applications-on-enterprise-data-with-amazon-bedrock-managed-knowledge-base/)
- **The project's planned count path (local repo).** It pages through "the KB's S3 Vectors index the way `backend/kb_report.py` `scan_index` does (`list_vectors` with `returnMetadata`, plus `returnData` for the embeddings)" — `CLAUDE.md`, "Next steps: count questions" (local repo)

### Inferences
- **Moving the container UI to a managed KB invalidates the recommended catalog source.** Neither vectors nor chunk metadata can be read. The catalog would have to be:
  - built by the scraper from its own sidecars and messages (the CLAUDE.md "Alternative" `catalog/csms-catalog.sqlite`, with embeddings from a Nova embedding model under Nova-only), or
  - rebuilt by reading the S3 sidecars directly, which the project owns
- **Reconciling the catalog with the KB.** `ListKnowledgeBaseDocuments` statuses can confirm which documents the KB has indexed, so counts are reported only over ingested messages.
- **Expensive fallback for the checker step.** `GetDocumentContent(EXTRACTED)` could fetch full message text, but that is one call per document plus a pre-signed download.

### Gaps
- Not documented: whether `ListKnowledgeBaseDocuments` and `GetKnowledgeBaseDocuments` are supported on managed KBs, and their rate quotas there. The Aug 2026 blog tracks managed-KB document status, which suggests they are.
- No `GetDocumentContent` quota was found for managed KBs.

## 7. Managed KB pricing, quotas, Regions (incl. GovCloud), CloudFormation/CDK, connectors, sync behaviour

### Takeaway
**Pricing.**
- Storage: $5 per GB of raw data per month.
- Retrieve: $1 per 1,000 calls.
- Agentic: $4 per 1,000 calls plus $1 per 1,000 underlying retrieves.
- Managed parse, embed and rerank: free.

**Quotas.** 10,000 KBs per account per Region; 200 data sources per KB; 10 TB per KB; Retrieve 600 RPM per KB; AgenticRetrieveStream 300 RPM per account (conflicting with 60).

**Regions.** Nine, including **GovCloud (US-West), which lacks third-party connectors, ACLs, managed models, agentic retrieval and the AgentCore Gateway target**.

**Infrastructure as code.** CloudFormation supports `AWS::Bedrock::KnowledgeBase` `Type: MANAGED` (replacement on change) and `AWS::Bedrock::DataSource` `Type: MANAGED_KNOWLEDGE_BASE_CONNECTOR`. CDK's L1 `CfnKnowledgeBase` exposes `managedKnowledgeBaseConfiguration` (type changed in v2.261.0, 2 Jul 2026).

**Connectors and sync.** Twelve connectors. Sync is incremental, with optional daily, weekly or monthly schedules.

### Cited Findings
- **Pricing (Managed Knowledge Bases tab).** Source: [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)
  - Index storage "$5.00 per GB of raw data / month"
  - Document parsing (managed parser) "$0"; embeddings (managed) "$0"; re-ranking (managed) "$0"
  - Standard retrieval "$1.00 per 1,000 API calls"
  - Agentic retrieval "$4.00 per 1,000 Agentic Retrieve API calls + $1.00 per 1,000 underlying Retrieve API calls"
  - No separate connector or sync charge is listed. AgentCore Gateway and CloudWatch are billed at standard rates.
  - AWS examples: 50 GB SharePoint index with 100,000 standard queries = $350 per month; with 100,000 agentic calls = $850 per month.
  - GovCloud pricing for KBs is not listed.
- **Pricing (conflict).** A third-party article claimed the pricing page carried no managed-KB rates (search excerpt); the page fetched this session does carry them — [ecorpit (third party)](https://ecorpit.com/bedrock-managed-knowledge-base-vs-self-managed-rag-2026/)
- **Quotas.** Source: [Service quotas for managed knowledge bases](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-quotas.html)

  | Quota | Value | Adjustable |
  | --- | --- | --- |
  | Managed KBs per account per Region | 10,000 | No |
  | Data sources per KB | 200 | Yes |
  | Concurrent ingestion jobs per KB | 50 | No |
  | Raw data storage per KB | 10 TB | Yes |
  | Query characters per Retrieve / AgenticRetrieveStream | 10,000 | No |
  | Retrieve RPM per KB | 600 (burst 25 RPS) | Yes |
  | AgenticRetrieveStream RPM per account | 300 | Yes |
  | Retrieval instructions per account per Region | 50 | Yes |
  | Versions per retrieval instruction | 50 | Yes |
  | Total characters across a retrieval instruction's fields | 24,000 | Yes |

  The sync page refers to an "Ingestion job file size" quota that this table does not list — [kb-managed-sync](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-sync.html)
- **Regions.** us-east-1, us-west-2, eu-west-1, eu-west-2, eu-central-1, ap-northeast-1, ap-southeast-1, ap-southeast-2, us-gov-west-1. GovCloud restrictions:
  - "Only the Amazon S3 connector and the Custom data source are available"
  - no ACLs
  - no service-managed embedding, reranking or agentic models ("Agentic retrieval is not available")
  - no AgentCore Gateway target

  Source: [Managed KB supported Regions](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-regions.html)
- **Regions (minor conflict).** The GA What's New (17 Jun 2026) lists eight Regions without Singapore (sibling notes) — [What's New 2026-06](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-managed-knowledge-base/)
- **CloudFormation, knowledge base.** `KnowledgeBaseConfiguration.Type` "Allowed values: `VECTOR | KENDRA | SQL | MANAGED`… Choose `MANAGED` to create a managed knowledge base." `ManagedKnowledgeBaseConfiguration`: "Contains configuration details for a knowledge base that uses a vector store fully managed by Amazon Bedrock." Both "Update requires: Replacement" — [CFN: AWS::Bedrock::KnowledgeBase KnowledgeBaseConfiguration](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-bedrock-knowledgebase-knowledgebaseconfiguration.html)
- **CloudFormation, data source.** `DataSourceConfiguration.Type` allowed values include `MANAGED_KNOWLEDGE_BASE_CONNECTOR` (Replacement). `ManagedKnowledgeBaseConnectorConfiguration` is "No interruption". The self-managed S3/SharePoint/Confluence/Web properties say "To configure this data source for managed knowledge bases, use managedKnowledgeBaseConnectorConfiguration" — [CFN: AWS::Bedrock::DataSource DataSourceConfiguration](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-bedrock-datasource-datasourceconfiguration.html)
- **CDK.** `aws_bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty` includes `managedKnowledgeBaseConfiguration` with:
  - `embeddingModelType`, `embeddingModelArn`
  - `embeddingModelConfiguration.bedrockEmbeddingModelConfiguration` (`dimensions`, `embeddingDataType`, …)
  - `serverSideEncryptionConfiguration.kmsKeyArn`
  - `supplementalDataStorageConfiguration`

  "Type last changed: v2.261.0 · 2 Jul 2026" — [CDK: CfnKnowledgeBase.KnowledgeBaseConfigurationProperty](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty.html). A re:Post question titled "bedrock managed knowledge bases when will cloud formation type and cdk support be available" suggests support arrived after GA (search excerpt) — [re:Post](https://www.repost.aws/questions/QUsDSeiOHHQuKbGAQh6dWR8w/bedrock-managed-knowledge-bases-when-will-cloud-formation-type-and-cdk-support-be-available)
- **Connectors.** "Amazon S3, Box, Confluence Cloud, Confluence Data Center, Microsoft SharePoint Online, Google Drive, Microsoft OneDrive, Salesforce, ServiceNow, Zendesk, Web Crawler, Custom connector" — [kb-managed-create](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html). The older comparison table still says "7 native connectors" — [kb-build-managed](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html)
- **S3 connector specifics.** Source: [kb-managed-ds-s3](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-s3.html)
  - Filters: `inclusionPrefixes`, `exclusionPrefixes`, `inclusionPatterns` / `exclusionPatterns` (regex)
  - `maxFileSizeInMegaBytes` (default "500")
  - cross-account buckets supported
  - the bucket "must be a General Purpose bucket in the same AWS Region"
  - "For managed knowledge bases, `CreateDataSource` is asynchronous: the data source status transitions from `CREATING` to `AVAILABLE`"
- **Sync.** Source: [Sync a data source (managed)](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-sync.html)
  - "Syncing is incremental, so Amazon Bedrock only processes added, modified, or deleted documents since the last sync."
  - Schedules via `syncSchedule` in `managedKnowledgeBaseConnectorConfiguration`: On-demand (default), `daily` (system-chosen off-peak time), `weekly {dayOfWeek}`, `monthly {dayOfMonth: dayNumber 1–28 | lastDayOfMonth}`.
  - Manual sync uses `StartIngestionJob`; monitoring uses `GetIngestionJob` / `ListIngestionJobs`.
- **Console location.** Managed KBs are created under "Amazon Bedrock AgentCore > Built-in tools > Knowledge Base", and creation takes 2–5 minutes — [kb-managed-create](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html)

### Inferences
- **Cost at this project's scale is small.** At the 100 messages (plus attachments) reported in Sept 2026, storage is likely well under 1 GB (≈ <$5/month). Queries cost $0.001 per Retrieve, or about $0.004–0.007 per agentic question. Back-fill to 30k+ messages scales storage roughly linearly with raw bytes.
- **IaC fits the project's CDK (Python) setup.** Use L1 `CfnKnowledgeBase(type=MANAGED)` plus one `CfnDataSource(type=MANAGED_KNOWLEDGE_BASE_CONNECTOR)` per category prefix (≤200), which needs aws-cdk-lib ≥ 2.261.0. That is likely simpler than the current S3 Vectors `AwsCustomResource`. Changing the embedding model or KB type means replacement and full re-ingestion.
- **`exclusionPrefixes`** (e.g. `catalog/`) would keep non-content files out of the KB, mirroring the CLAUDE.md clean-up item.
- **GovCloud.** A CBP GovCloud deployment would get only S3/Custom connectors, `Retrieve` with a custom embedding, and no agentic retrieval or ACLs. Most BMKB differentiators disappear there.

### Gaps
- GovCloud pricing for managed KBs is not published on the pricing page fetched.
- CloudFormation support for retrieval instructions and managed-KB resource policies was not checked.
- The "Ingestion job file size" quota for managed KBs is referenced but not listed.

## 8. Amazon Nova with RetrieveAndGenerate (customer-managed KB): exact status and how to verify

### Takeaway
**The AWS documentation conflicts, and the most defensible answer is "probably works for Nova Micro, Lite and Pro on a customer-managed KB, possibly only with a custom prompt template; Nova 2 Lite is unconfirmed; verify before committing".**
- Against: Bedrock model cards list "Knowledge base" as **Not Supported** for Nova Pro and Nova 2 Lite, and the Nova Lite/Micro cards omit the row entirely.
- For: the Amazon Nova User Guide documents using Nova with Bedrock Knowledge Bases, and singles out only **Nova Premier** as "not yet available via the RetrieveAndGenerate API". Even for Premier it gives a workaround: supply `generationConfiguration.promptTemplate`.
- Nova Premier and Nova 2 Pro no longer appear in Bedrock's "Models at a glance".
- In every case R&G works only on customer-managed (`VECTOR`) KBs, never on managed KBs (section 2).

### Cited Findings
- **Nova Pro card** (`amazon.nova-pro-v1:0`; geo profiles `us.`, `eu.`, `apac.`; no global profile; us-gov-west-1 In-Region supported; "Model lifecycle: Active"; "EOL no sooner than: Dec 05, 2025"). Source: [Nova Pro model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html)
  - Supported: Intelligent prompt routing, Response streaming, Guardrails, Model evaluation, Prompt management, Flows, Agents, implicit and explicit prompt caching.
  - Not Supported: Structured outputs, Abuse detection, Prompt optimization, Count tokens, **Knowledge base**, Watermarking.
  - APIs: Invoke and Converse yes; Responses and Chat Completions no.
- **Nova 2 Lite card** (`amazon.nova-2-lite-v1:0`; `us.`, `eu.`, `jp.` and `global.amazon.nova-2-lite-v1:0`; no us-gov-west-1 row; "EOL no sooner than: Dec 02, 2026"; reasoning "off by default"). `bedrock-mantle` not supported. Source: [Nova 2 Lite model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html)
  - Supported: Response streaming, Abuse detection, Guardrails, Prompt optimization, Client-side tool calling.
  - Not Supported: Intelligent prompt routing, Count tokens, **Knowledge base**, Structured outputs, Model evaluation, Prompt management, Flows, Agents, Watermarking.
- **Nova Lite card** (`amazon.nova-lite-v1:0`; `us.`, `ca.`, `eu.`, `apac.` profiles; us-gov-west-1 In-Region supported). Supported: Response streaming, Guardrails, Client-side tool calling. Not Supported: Structured outputs, Watermarking. **"Knowledge base" appears in neither list** — [Nova Lite model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html). Nova Micro has the same pattern (sibling notes) — [Nova Micro model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-micro.html)
- **"Models at a glance" (Amazon row).** "Amazon Nova Multimodal Embeddings, Nova 2 Lite, Nova 2.5 Sonic, Nova 2 Sonic, Nova Canvas, Nova Lite, Nova Micro, Nova Pro, Nova Reel" plus Titan models. **No Nova Premier and no Nova 2 Pro** — [Models at a glance](https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html). The Premier and Nova 2 Pro model-card URLs returned empty pages this session — [Nova Premier card URL](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-premier.html)
- **KB supported-models page.** It now only says to check "Models at a glance" (sibling notes) — [Supported models and Regions for KBs](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-supported.html)
- **Nova User Guide, positive.** "To use Amazon Nova models with Bedrock Knowledge bases, you must first create a knowledge base and then connect to your data repository… Next, you can test your knowledge base with queries and responses." — [Using Amazon Bedrock Knowledge Bases (Nova User Guide)](https://docs.aws.amazon.com/nova/latest/userguide/rag-br-knowledge.html)
- **Nova User Guide, Premier exception.** "Amazon Nova Premier is not yet available via the RetrieveAndGenerate API. To use the RetrieveAndGenerate API with Amazon Nova Premier, you need to provide a custom prompt when calling the RetrieveAndGenerate API. This is done by supplying the `promptTemplate` in the `generationConfiguration` argument" — [Building a custom RAG system with Amazon Nova](https://docs.aws.amazon.com/nova/latest/userguide/rag-building.html)
- **R&G API reference.** It "generates responses… using the specified foundation model or inference profile". It lists no model allow-list, and its samples use only Claude ARNs (e.g. `anthropic.claude-v2:1`, `us.anthropic.claude-3-5-sonnet…` inference profile) — [API: RetrieveAndGenerate](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_RetrieveAndGenerate.html)
- **Prompt-template placeholders.** `$search_results$` (required), `$output_format_instructions$` ("Without this placeholder, the response won't contain citations"), `$query$`, `$current_time$`. "When you don't provide a custom prompt template, Amazon Bedrock uses a default system prompt…" — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html)
- **Counter-evidence (not verified by this session).** A sibling search found an AWS ML Blog post ("just-in-time knowledge base") and third-party code reportedly using `amazon.nova-pro-v1:0` as the R&G `modelArn` (search excerpt) — [AWS ML Blog: Build a just-in-time knowledge base](https://aws.amazon.com/blogs/machine-learning/build-a-just-in-time-knowledge-base-with-amazon-bedrock/)
- **No What's New post found.** This session's searches found no dated What's New post announcing (or withdrawing) Nova support in Knowledge Bases R&G — [search results led only to the Nova User Guide pages above](https://docs.aws.amazon.com/nova/latest/userguide/rag-building.html)
- **Project context (local repo).** The container backend's generation model default is `us.anthropic.claude-sonnet-4-6`, and the planned count path names Claude Haiku 5.5. Both conflict with a Nova-only rule — `CLAUDE.md` (local repo)

### Inferences
- **Reading the conflict.** The model cards' "Knowledge base" row most likely means "selectable in the KB console with a built-in default prompt template", not "rejected by the API". That would square the cards with the Nova User Guide, whose only exception (Premier) is solved by a custom prompt. This reading is unproven.
- **Implications for the project.**
  - Keep the R&G call, but always pass an explicit `textPromptTemplate` containing `$search_results$` and `$output_format_instructions$`, so citations keep working.
  - Use a `us.` geo inference profile for Nova Pro, Lite or Micro.
  - Nova 2 Lite (the newest model and the only Nova with a global profile) is the least certain; test it separately.
  - A GovCloud deployment would have to use In-Region Nova Pro or Lite (Nova 2 Lite isn't listed there).
- **Empirical verification.** Run against the existing customer-managed S3 Vectors KB; it changes nothing. Use the same profile and Region as `.env.local`:
  ```bash
  KB=<KnowledgeBaseId>; ACCT=<account-id>; GR=<GuardrailId>; GV=<GuardrailVersion>
  for M in us.amazon.nova-pro-v1:0 us.amazon.nova-lite-v1:0 us.amazon.nova-micro-v1:0 us.amazon.nova-2-lite-v1:0 global.amazon.nova-2-lite-v1:0; do
    echo "== $M"
    aws bedrock-agent-runtime retrieve-and-generate --region us-east-1 --profile <AWS_PROFILE> \
      --input '{"text":"What did CBP announce about ACE outages?"}' \
      --retrieve-and-generate-configuration "{
        \"type\":\"KNOWLEDGE_BASE\",
        \"knowledgeBaseConfiguration\":{
          \"knowledgeBaseId\":\"$KB\",
          \"modelArn\":\"arn:aws:bedrock:us-east-1:$ACCT:inference-profile/$M\",
          \"retrievalConfiguration\":{\"vectorSearchConfiguration\":{\"numberOfResults\":8,
            \"filter\":{\"andAll\":[{\"greaterThanOrEquals\":{\"key\":\"date_numeric\",\"value\":20260501}},
                                   {\"lessThanOrEquals\":{\"key\":\"date_numeric\",\"value\":20260831}}]}}},
          \"generationConfiguration\":{\"guardrailConfiguration\":{\"guardrailId\":\"$GR\",\"guardrailVersion\":\"$GV\"}}
        }}" \
      --query '{out:output.text, cites:length(citations[].retrievedReferences[]), guard:guardrailAction}'
  done
  ```
  Pass criteria: HTTP 200, non-empty `output.text`, at least one `retrievedReferences`, and `guardrailAction` present.

  Re-run any failing model with `"generationConfiguration": {"promptTemplate": {"textPromptTemplate": "… $search_results$ … $output_format_instructions$ …"}, "guardrailConfiguration": {…}}`. Also try the In-Region ARN `arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0`, which tells "model unsupported" apart from "profile unsupported". A `ValidationException` naming the model means unsupported.

  The calling role needs `bedrock:RetrieveAndGenerate`, `bedrock:Retrieve`, and `bedrock:InvokeModel` on the profile and its destination-Region foundation models. That last permission list is general Bedrock knowledge and was not re-verified this session.
- **Agentic retrieval with Nova (managed KB only).** The CLI note says streaming operations aren't supported, so test from boto3 with `agentic_retrieve_stream(...)`:
  - `agenticRetrieveConfiguration = {"foundationModelType": "CUSTOM", "foundationModelConfiguration": {"type": "BEDROCK_FOUNDATION_MODEL", "bedrockFoundationModelConfiguration": {"modelConfiguration": {"modelArn": "arn:aws:bedrock:us-east-1:<acct>:inference-profile/us.amazon.nova-pro-v1:0"}}}, "rerankingModelType": "NONE", "maxAgentIteration": 3}`
  - `policyConfiguration = {"bedrockGuardrailConfiguration": {"guardrailId": "…", "guardrailVersion": "…"}}`
  - one retriever with `retrievalOverrides.filter`

  Iterate the event stream for `traceEvent`, `responseEvent` and `result`. This is a sketch: the boto3 event-stream key name was not verified.

### Gaps
- No primary AWS statement in Nov 2026 settles R&G support per Nova model. The cards (Not Supported, or omitted) and the Nova User Guide (supported, Premier excepted) conflict, and only an empirical test settles it.
- Nova Premier's status is unclear: whether it was retired from Bedrock or merely dropped from "Models at a glance". No lifecycle page was fetched.
- No AWS-authored sample was verified this session that calls R&G with a Nova `modelArn`. The "just-in-time KB" blog evidence is a search excerpt.

## 9. If Nova is unsupported in RetrieveAndGenerate: the documented Retrieve + Converse pattern, citations, guardrails and grounding with Nova

### Takeaway
AWS documents two Nova RAG patterns:
- **"Using a retriever as a tool"** (recommended): Converse `toolConfig` with the KB `Retrieve` API as the tool
- **custom instructions** (prompt-stuffing retrieved results)

Nova cards list **Guardrails as supported**, and Converse supports Guardrails' **contextual grounding check** through `guardContent` qualifiers (`grounding_source`, `query`). That gives grounding and relevance scoring, not citations. Converse's document-citation feature exists (`DocumentBlock.citations`), but no AWS page found says Nova supports it. So a Nova Retrieve + Converse path must build citations itself: number the chunks, ask Nova to cite `[n]`, and map back to `Retrieve` locations or metadata. This reintroduces the two-step design CLAUDE.md currently excludes, and is a user decision.

### Cited Findings
- **Nova RAG patterns.** "When Using Amazon Nova within any RAG system there are two general approaches: **Using a retriever as a tool** (Recommended): You can define your retriever for use as a tool in the ToolParameter of the converse API or Invokemodel API. For example, you can define the Bedrock Retrieve API or any other retriever as a 'tool'." and "**Using Custom Instructions for RAG systems**". The page shows a `toolSpec` JSON schema, the `toolUse` response (`stopReason: tool_use`) and the `toolResult` message format — [Building a custom RAG system with Amazon Nova](https://docs.aws.amazon.com/nova/latest/userguide/rag-building.html)
- **Nova feature support.** Guardrails: Supported on the Nova Pro, Nova Lite and Nova 2 Lite cards. Client-side tool calling: Supported on Nova Lite and Nova 2 Lite. Converse API: supported on all three — [Nova Pro card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html); [Nova Lite card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html); [Nova 2 Lite card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html)
- **Contextual grounding with Converse.** Source: [Contextual grounding check](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html)
  - Mark content with `guardContent.text.qualifiers`:
    - `["grounding_source"]`: used as reference only, not evaluated by other policies
    - `["query"]`
    - `["guard_content"]`, or combined forms such as `["grounding_source", "guard_content"]`, which also apply the other policies
  - "the model response is required to perform the contextual grounding checks and so the checks will only be performed on output and not on the prompt."
  - Limits: "a maximum of 100,000 characters for grounding source, 1,000 characters for query, and 5,000 characters for response."
  - Thresholds 0–0.99. "Classic tier does not support conversational use cases." "Standard tier requires that your guardrail use cross-Region inference."
  - Streaming caveat: an irrelevant response may be "only marked as irrelevant after the whole response is streamed".
  - `ApplyGuardrail` supports the same qualifiers, plus an unqualified block for the content to guard.
- **Converse citations exist; model support isn't stated.** `DocumentBlock` has `citations` ("Configuration settings that control how citations should be generated for this specific document") and `context` ("Contextual information about how the document should be processed or interpreted by the model when generating citations"). No model-support statement is given — [API: DocumentBlock](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_DocumentBlock.html). `CitationsConfig` has a single `enabled` boolean (search excerpt) — [API: CitationsConfig](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_CitationsConfig.html)
- **R&G guardrails cover only input and output.** "Guardrails are applied only to the input and the generated response from the LLM. They are not applied to the references retrieved from Knowledge Bases at runtime." (sibling notes) — [kb-test-retrieve-generate](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-generate.html)

### Inferences
- **A Nova-compatible two-call design** that keeps today's semantics:
  1. `Retrieve` with the UI date filter: `vectorSearchConfiguration` on the current KB, or `managedSearchConfiguration` on a managed KB.
  2. Build a numbered context block (chunk text plus `message_id` / `source_url` from metadata).
  3. `Converse` with a Nova inference profile, the stack guardrail, and `guardContent` blocks qualified `grounding_source` (the context) and `query` (the question), with a system prompt requiring `[n]` citations.
  4. Parse the `[n]` markers and map them to `Retrieve` `location` / `metadata` to produce `{label, url}` sources.
  5. Suppress sources when the guardrail intervenes, as the current code does for `INTERVENED`.
- **This design trades away** R&G's built-in citation spans and session handling. It gains model independence and works on both KB families: on managed KBs `Retrieve` is supported, and there are no ACL implications beyond `userContext`.
- **Grounding-check limits.** The 100,000-character grounding-source limit comfortably fits about 8–20 KB chunks. The 5,000-character response cap means long answers would need truncation, or a check on the first segment.
- **Where the "retriever as a tool" pattern fits.** It lets Nova decide when to retrieve, which suits multi-category routing. But the model, not code, then chooses whether and what to retrieve. That is the predictability concern recorded in earlier research for tool loops (CLAUDE.md rules out tool-loop query paths).

### Gaps
- No AWS page found states whether Amazon Nova models honour Converse `DocumentBlock.citations` / `CitationsConfig`; test empirically.
- The Converse guardrail request fields (`guardrailConfig`) were not re-read this session; only the qualifier usage above was verified.
- No AWS page was found that publishes a Nova-specific RAG prompt template with citation markup. The Nova User Guide links "prompting guidance for RAG" (`prompting-tools-rag.html`), which was not fetched.
