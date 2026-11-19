# Native Amazon Bedrock Knowledge Bases capabilities for multi-category, multi-store, permission-aware RAG (state as of 2026-11-06)

Scope note for the report writer: AWS now has two KB families. The **customer-managed** ("custom"/"standard", `type: VECTOR`) KB is what this project runs today (S3 Vectors index, S3 data source, `.metadata.json` sidecars, `RetrieveAndGenerate`). The **Bedrock Managed Knowledge Base** (`type: MANAGED`, GA 2026-06-17) is a separate product with its own connectors, ACL-aware retrieval and a multi-KB `AgenticRetrieveStream` API. Several AWS pages contradict each other on details; conflicts are flagged inline. Every finding was read from the cited page during this session unless marked "(search excerpt)", meaning it came from a search-result summary and the page itself was not opened.

## 1. Multiple data sources per KB: types, per-source metadata, mixing categories, quotas and metadata size limits

### Takeaway
A customer-managed KB allows at most **5 data sources** (not adjustable) and 100 KBs per account. A managed KB allows **200 data sources** (adjustable) and 10,000 KBs per account. On a customer-managed KB, new non-S3 connectors can no longer be created from 2026-09-30, so new categories there effectively mean S3 or Custom data sources. For an S3 Vectors-backed KB the binding metadata limit is **1 KB of custom metadata and 35 keys per vector**, far below the 10 KB sidecar-file limit.

### Cited Findings
- **Customer-managed KB quotas** (all "Adjustable: No"): 5 data sources per KB; 100 KBs per account; 5,000,000 files to add/update per ingestion job (and 5,000,000 to delete); 50 MB per file with text content; 100 GB per ingestion job. Concurrent ingestion jobs: 5 per account, 1 per KB, 1 per data source. User query size: 1,000 characters. `IngestKnowledgeBaseDocuments`: 25 files per call, 6 MB total payload. BDA parser and FM parser: 1,000 files maximum each — [AWS General Reference: Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- **Customer-managed request rates** (not adjustable): Retrieve 20 rps; RetrieveAndGenerate 20 rps; RetrieveAndGenerateStream 20 rps; GenerateQuery 2 rps; Rerank 10 rps; StartIngestionJob 0.1 rps — [AWS General Reference: Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- **Managed KB quotas**: 10,000 KBs per account per Region (not adjustable); 200 data sources per KB (adjustable); 50 concurrent ingestion jobs per KB; 10 TB raw storage per KB (adjustable); 10,000 query characters per Retrieve or AgenticRetrieveStream; Retrieve 600 RPM per KB (burst 25 RPS) — [Service quotas for managed knowledge bases](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-quotas.html)
- **Conflict on the AgenticRetrieveStream rate**: the managed-KB quotas page gives "300" requests per minute per account — [kb-managed-quotas](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-quotas.html). The General Reference gives "60" (adjustable) — [AWS General Reference](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- **Connectors on customer-managed KBs are shrinking**: "Starting September 30, 2026, the creation of new connectors for Confluence, Microsoft SharePoint, Salesforce, and Web Crawler will no longer be supported on customer-managed knowledge bases. Existing connectors of these types will continue to function… we recommend Amazon Bedrock Managed Knowledge Base." The remaining listed types are Amazon S3 and Custom — [Connect a data source to your knowledge base](https://docs.aws.amazon.com/bedrock/latest/userguide/data-source-connectors.html)
- In CloudFormation, the Confluence, SharePoint, Salesforce and Web crawler connectors for self-managed KBs are each marked "in preview release and is subject to change" — [CFN DataSourceConfiguration](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-bedrock-datasource-datasourceconfiguration.html)
- The AWS comparison table lists customer-managed connectors as "S3 and Custom". It lists managed connectors as "7 native connectors (S3, SharePoint, Confluence, Web Crawler, Google Drive, OneDrive, Custom)" — [Build a managed knowledge base](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html)
- The newer managed-KB create page lists 12 connectors: Amazon S3, Box, Confluence Cloud, Confluence Data Center, SharePoint Online, Google Drive, OneDrive, Salesforce, ServiceNow, Zendesk, Web Crawler and Custom — [Create a managed knowledge base](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html). The September 2026 announcement adds Salesforce and Zendesk (search excerpt) — [What's New 2026-09](https://aws.amazon.com/about-aws/whats-new/2026/09/amazon-bedrock-managed-knowledge-base-salesforce-zendesk-native-data-source-connectors/)
- **Multimodal**: "Multimodal content (images, audio, and video files) is only supported with Amazon S3 and custom data sources. Other data source types will skip multimodal files during ingestion." — [data-source-connectors](https://docs.aws.amazon.com/bedrock/latest/userguide/data-source-connectors.html)
- **Per-data-source settings**: each `CreateDataSource` call carries its own `dataSourceConfiguration`, an optional `vectorIngestionConfiguration` (parsing, chunking, custom transformation Lambda) and a `dataDeletionPolicy` — [data-source-connectors](https://docs.aws.amazon.com/bedrock/latest/userguide/data-source-connectors.html). "You can't change the chunking strategy after connecting to the data source." — [S3 connector](https://docs.aws.amazon.com/bedrock/latest/userguide/s3-data-source-connector.html)
- **S3 connector specifics**:
  - Inclusion prefixes are supported.
  - "Currently only General Purpose S3 buckets are supported."
  - The bucket must be in the same Region as the KB.
  - The bucket may be in another AWS account (`bucketOwnerAccountId`).
  - Incremental sync handles added, modified and deleted content.

  Source: [Connect to Amazon S3 for your knowledge base](https://docs.aws.amazon.com/bedrock/latest/userguide/s3-data-source-connector.html)
- **Sidecar format**: `fileName.extension.metadata.json` sits in the same folder as the document. "The file must not exceed the limit of 10 KB." `includeForEmbedding: true` means "The metadata key-value pair is concatenated to the chunk text before embedding (for example, `key1: value1\n\nchunk text`)" while not appearing in returned chunk text. `false`, or the simplified `{"metadataAttributes": {"tag": "value"}}` format, stores the value for filtering only — [S3 connector](https://docs.aws.amazon.com/bedrock/latest/userguide/s3-data-source-connector.html)
- **Supported attribute types**: implicit-filter schemas list `STRING`, `NUMBER`, `BOOLEAN` and `STRING_LIST` — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html). The Kendra-to-managed-KB migration guide says managed-KB sidecars are max 10 KB and "Each attribute must be typed as STRING, NUMBER, or BOOLEAN" — [Kendra availability change / migration guide](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html). The two pages disagree on whether lists are allowed for managed KBs.
- **S3 Vectors-backed KB metadata cap**: "When using Amazon S3 Vectors with Amazon Bedrock Knowledge Bases, you can attach up to 1 KB of custom metadata (including both filterable and non-filterable metadata) and 35 metadata keys per vector… If the metadata exceeds these limits, the ingestion job will throw an exception when populating the vector index." — [Prerequisites for your own vector store (S3 Vectors tab)](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html); the same 1 KB / 35 keys appears in [Using S3 Vectors with Bedrock KBs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-bedrock-kb.html)
- **Native S3 Vectors limits**, larger than what a KB exposes:
  - total metadata per vector up to 40 KB (filterable plus non-filterable)
  - filterable metadata per vector up to 2 KB
  - up to 50 metadata keys per vector
  - up to 10 non-filterable keys per index
  - QueryVectors top-K up to 10,000
  - up to 100 filter constraints per query on an `ENHANCED` index
  - ListVectors up to 1,000 per page, with up to 16 parallel segments
  - up to 2 billion vectors per index; 10,000 indexes per bucket

  Source: [S3 Vectors limitations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html)
- **Hierarchical chunking and tables can hit the S3 Vectors cap**: parent-child relationships, and the "broader context that Amazon Bedrock Knowledge Bases attaches for tables and figures in parsed markdown content", are stored as non-filterable metadata in S3 Vectors and "can exceed the maximum metadata size limits" — [knowledge-base-setup](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html)
- **Reserved metadata**: "For custom knowledge bases, metadata fields prefixed with `x-amz-bedrock` are reserved by the service. For fully managed knowledge bases, reserved metadata fields use an underscore prefix (for example, `_source_uri`, `_data_source_id`)." — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html)
- **Local evidence (this repo)**:
  - The KB index declares `AMAZON_BEDROCK_TEXT` and `AMAZON_BEDROCK_METADATA` as non-filterable — `iac/resources/resource_knowledge_base.py`, line 57.
  - `kb_report.py` treats keys prefixed `x-amz-bedrock-kb-` as system keys and reads `x-amz-bedrock-kb-source-uri` from inside `AMAZON_BEDROCK_METADATA` — `app/ui/container/backend/kb_report.py`, lines 46–48 and 213–216.
- **Supported document formats** (customer-managed KB, S3 or attachments): .txt, .md, .html, .doc/.docx, .csv, .xls/.xlsx, .pdf, each up to 50 MB. JPEG/PNG up to 3.75 MB for S3 or custom multimodal — [knowledge-base-ds](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-ds.html)

### Inferences
- Within one customer-managed KB, the S3-native way to add categories is one data source per S3 prefix (up to 5), or one data source with a `category` sidecar attribute. Five is a hard ceiling for "one data source per category". Past that, categories have to be metadata values, or separate KBs (max 100 per account).
- The 1 KB / 35-key cap leaves little room for per-document ACL lists in metadata (e.g., a long `allowed_groups` list) next to the existing CSMS fields. The project already trims `related_countries` for this reason.
- A data-source discriminator for filtering exists as reserved metadata (`x-amz-bedrock-kb-*` on customer-managed KBs; `_data_source_id` on managed KBs). An explicit `category` sidecar attribute is more portable and documented.

### Gaps
- No AWS page fetched states whether `x-amz-bedrock-kb-data-source-id` is filterable on an S3 Vectors-backed customer-managed KB. Verify empirically.
- Whether managed-KB sidecars accept `STRING_LIST` attributes is unclear: the Kendra guide lists only STRING/NUMBER/BOOLEAN, and the managed-KB filter docs were not fetched in full.
- Managed-KB metadata size per document/vector was not found on the managed-KB quota page.

## 2. Metadata filtering in Retrieve / RetrieveAndGenerate, per-store support, limits, and use for access control

### Takeaway
Customer-managed KBs support `equals`, `notEquals`, numeric range operators, `in`, `notIn`, `startsWith`, `stringContains`, `listContains`, `andAll` and `orAll`. The `startsWith` and `stringContains` filters are unavailable on S3 Vectors and on managed KBs, and `in`, `notIn` and `listContains` are "best supported" on OpenSearch Serverless. AWS's own guidance is that metadata-filter access control is **logical, not IAM-enforced isolation**. Anyone holding `bedrock:Retrieve` on the KB can bypass it, so filters must be injected server-side, and hard boundaries need separate KBs.

### Cited Findings
- **Operators and value types**:
  - `equals` / `notEquals`: string, number or boolean
  - `greaterThan`, `greaterThanOrEquals`, `lessThan`, `lessThanOrEquals`: number
  - `in` / `notIn`: string list, "currently best supported with Amazon OpenSearch Serverless and Neptune Analytics GraphRAG vector stores"
  - `stringContains`: "currently best supported with Amazon OpenSearch Serverless"; Neptune supports the string variant only
  - `listContains`: "currently best supported with Amazon OpenSearch Serverless vector stores"
  - `startsWith`: "only supported for Amazon OpenSearch Serverless vector stores"
  - logical `andAll` / `orAll`: each a "List of up to 5 filter types"; groups can be nested "one level of embedding"

  Source: [Configure and customize queries and response generation](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html)
- **S3 Vectors in a KB**: "If your knowledge base uses a vector index in an S3 vector bucket, you cannot use the `startsWith` and `stringContains` filters." — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html)
- **Managed KB**: "The `startsWith` and `stringContains` metadata filters are not supported. Use `equals`, `greaterThan`, `lessThan`, `in`, or `notIn` operators instead." — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html). Managed-KB Retrieve uses `retrievalConfiguration.managedSearchConfiguration` (`numberOfResults`, `filter`) instead of `vectorSearchConfiguration` — [Create a managed knowledge base](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html); [Kendra migration guide](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- **Native S3 Vectors operators**: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$startsWith` (requires `ENHANCED`), `$in`, `$nin`, `$exists`, `$and`, `$or`. On array metadata `$eq` "returns true if the input value matches any element in the array" — [S3 Vectors metadata filtering](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-metadata-filtering.html)
- **S3 Vectors index modes, relevant to this project's date filter**:
  - "Pre-filtering applies to vector indexes whose index mode is `ENHANCED`. Vector buckets created on or after September 30, 2026 create `ENHANCED` indexes. In a vector bucket created before that date, indexes have the index mode `CLASSIC`."
  - "On a `CLASSIC` index, queries with filters may return fewer than top K results when the vector index contains very few matching results."
  - An existing index can be moved to `ENHANCED`.
  - On `ENHANCED`, a filter may use up to 100 constraints, and each `$in` value counts as one.

  Source: [S3 Vectors metadata filtering](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-metadata-filtering.html)
- **Other stores' filter caveats**:
  - OpenSearch Serverless needs the `faiss` engine for filtering (not `nmslib`) — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html).
  - Aurora: "Without iterative scans, selective metadata filters can return fewer results than expected because filtering is applied after the HNSW index scan" (pgvector ≥ 0.8.0 iterative scan recommended).
  - MongoDB Atlas: "Metadata filtering doesn't work by default and requires additional setup".
  - OpenSearch Managed: custom filter fields need `keyword` (or a `text` field with a `keyword` subfield), else a "Rewrite first" error.

  Source for the last three: [knowledge-base-setup](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html)
- **Built-in permission caveat**: "All data that you sync from your data source becomes available to anyone with `bedrock:Retrieve` permissions to retrieve the data. This can also include any data with controlled data source permissions." — [S3 connector](https://docs.aws.amazon.com/bedrock/latest/userguide/s3-data-source-connector.html)
- **AWS Architecture Blog (2026-06-22), multi-tenant RAG with Verified Permissions**: Cedar policies decide which department tags a user may see, and a middleware Lambda builds the `RetrieveAndGenerate` metadata filter. The post states:
  - "This pattern provides filter-level (logical) isolation, not IAM-enforced (infrastructure) isolation."
  - "If the middleware logic that constructs the filter were to fail open, documents from other groups would be exposed."
  - "A brief window exists between document upload and sidecar creation."
  - For cross-tenant boundaries, "provision a dedicated knowledge base per tenant with IAM-enforced resource boundaries", with filters layered inside.

  Source: [Secure multi-tenant RAG with Amazon Bedrock and Verified Permissions](https://aws.amazon.com/blogs/architecture/secure-multi-tenant-rag-with-amazon-bedrock-and-verified-permissions/)
- **AWS ML Blog (2024)**: "With metadata filters on access IDs, a user can only chat with documents that have metadata associated with their access ID. The access ID associated with their authentication when the chat is initiated can be passed as a filter." (search excerpt; the post uses Cognito) — [Access control for vector stores using metadata filtering with Knowledge Bases for Amazon Bedrock](https://aws.amazon.com/blogs/machine-learning/access-control-for-vector-stores-using-metadata-filtering-with-knowledge-bases-for-amazon-bedrock). A 2025-04-07 AWS ML Blog post on S3 folder structure plus metadata filtering for multi-tenancy in one KB was found only via a mirror (not fetched) — [mirror](https://aws-news.com/article/2025-04-07-multi-tenancy-in-rag-applications-in-a-single-amazon-bedrock-knowledge-base-with-metadata-filtering)
- **Native document-level ACLs (managed KBs only)**:
  - "ACL-aware retrieval": permissions (allowed and denied users and groups) are ingested with content, and at query time "you supply a user context".
  - Identity is email: "the email you pass in the user context must exactly match the email associated with the user in each connected data source."
  - Deny overrides allow; retrieval "fails closed".
  - Real-time ACL re-verification covers SharePoint, OneDrive, Google Drive, Confluence, Confluence Data Center, Box, Zendesk and Salesforce, and partially ServiceNow; not S3, Custom or Web Crawler.
  - "ACL awareness is not authorization… You must not rely on this feature as a sole access control mechanism without upstream authentication."

  Source: [Access Control Lists awareness enablement](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-acl.html)
- **S3 ACLs in a managed KB**:
  - Set `aclEnabled: true` in `connectorParameters`, and use either a global ACL JSON file (`keyPrefix` → `aclEntries`) or a per-document `.metadata.json` with an `accessControlList`.
  - Entries are `Name` (user email), `Type` ("Must be `USER`") and `Access` (`ALLOW`/`DENY`).
  - "Documents without an associated ACL entry are not ingested."
  - "Global ACL file changes require reindexing of the affected prefix."

  Source: [Document-level access controls (S3, managed KB)](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-ds-s3-acl.html)
- **IAM resource scoping exists per KB**: the agentic-retrieval policy example grants `bedrock:Retrieve` and `bedrock:GetDocumentContent` on `arn:aws:bedrock:{region}:{account-id}:knowledge-base/*` — [Use agentic retrieval](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html)

### Inferences
- Metadata-filter permissions on the current S3 Vectors customer-managed KB are workable if:
  - only the backend role holds `bedrock:Retrieve` / `bedrock:RetrieveAndGenerate` on the KB;
  - the backend derives the filter from the authenticated identity;
  - the filter is always ANDed with the user's date filter (`andAll`).

  This is a code concern in the backend, not configuration in the KB.
- For permission tiers on S3 Vectors, a `category` / `access_tier` STRING attribute filtered with `in: [user's allowed tiers]` is the safer shape:
  - Native S3 Vectors `$in` is supported.
  - On `ENHANCED`, each value is one of 100 constraints.

  `listContains` on a list-valued `allowed_groups` attribute is documented as best on OpenSearch Serverless, and nothing documents how a KB translates it for S3 Vectors.
- If the project's KB vector bucket predates 2026-09-30, its index is `CLASSIC`. Narrow `date_numeric` ranges or permission filters can then silently return fewer than `numberOfResults` chunks. Moving to `ENHANCED`, or recreating the bucket, gives true pre-filtering.
- For IAM-enforced isolation between categories with different permissions: one KB per permission tier. Callers get IAM grants only on the KB ARNs they may use, and one S3 Vectors index per KB (AWS's best practice).
- Managed-KB S3 ACLs list individual user emails only (`Type: USER`), with no group entries for S3. Group-based permissions on S3 content would still need metadata filters, or a connector with crawled groups.

### Gaps
- No AWS doc found that states the maximum serialized size of a `RetrievalFilter`, or the maximum number of `in` list values, for customer-managed KBs. The only numbers found are "up to 5" per logical group (user guide) and S3 Vectors' 100 constraints on `ENHANCED`.
- Not verified whether KB `listContains` / `equals` against a `STRING_LIST` attribute works on S3 Vectors. Test it.
- The ACL-aware Retrieve request syntax for managed KBs (`kb-test-retrieve-acl`) was not fetched. Only `userContext` on AgenticRetrieveStream is confirmed.

## 3. Implicit (model-generated) metadata filtering

### Takeaway
Implicit filtering exists (`implicitFilterConfiguration`: a metadata schema plus a model ARN), but AWS documents it as supported by **Anthropic Claude models**. No Nova model is listed, so under the Nova-only rule it is not usable as documented.

### Cited Findings
- "Amazon Bedrock Knowledge Base generates and applies a retrieval filter based on the user query and a metadata schema." "Implicit metadata filtering is supported by Anthropic Claude models." Fields: `metadataAttributes` (key, type STRING/NUMBER/BOOLEAN/STRING_LIST, description) and `modelArn` — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html)
- `implicitFilterConfiguration` is a member of `KnowledgeBaseVectorSearchConfiguration`, which is used in both Retrieve and RetrieveAndGenerate requests — [API: KnowledgeBaseVectorSearchConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_KnowledgeBaseVectorSearchConfiguration.html)

### Inferences
- Under the Nova-only constraint, natural-language dates, countries or categories in a question have to be turned into filters by the application (e.g., a Nova planner call building a `RetrievalFilter`). The KB does not do it natively.

### Gaps
- AWS does not document how an implicit filter combines with an explicit `filter` in the same request (AND vs. override). Not found.

## 4. Query decomposition, reranking, numberOfResults limits and search type on S3 Vectors

### Takeaway
`numberOfResults` is 1–100. Query decomposition is a single enum on `orchestrationConfiguration`. The only reranker models are **Amazon Rerank 1.0** (not available in us-east-1) and **Cohere Rerank 3.5**; neither is a Nova model. S3 Vectors-backed KBs are **semantic-only** (no hybrid).

### Cited Findings
- `numberOfResults`: "Valid Range: Minimum value of 1. Maximum value of 100." — [API: KnowledgeBaseVectorSearchConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_KnowledgeBaseVectorSearchConfiguration.html). Default is 5. With hierarchical chunking it counts child chunks, so fewer results may return — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html)
- The managed KB Retrieve API is also capped at "100 results" — [Kendra migration guide](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- **Query decomposition**: `orchestrationConfiguration.queryTransformationConfiguration.type = QUERY_DECOMPOSITION`. It "may result in multiple queries being executed against your Knowledge Base" — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html). "If you use query decomposition, the `numberOfRerankedResults` can be up to five times the `numberOfResults`." — [kb-test-retrieve-generate](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-generate.html)
- **Rerankers**: Amazon Rerank 1.0 (`amazon.rerank-v1:0`) in ap-northeast-1, ca-central-1, eu-central-1 and us-west-2. Cohere Rerank 3.5 (`cohere.rerank-v3-5:0`) in those plus us-east-1. "The Amazon Rerank 1.0 model is not supported in the US East (N. Virginia) AWS Region." — [Supported Regions and models for reranking](https://docs.aws.amazon.com/bedrock/latest/userguide/rerank-supported.html)
- `rerankingConfiguration` (`VectorSearchRerankingConfiguration`) accepts model, extra request fields, metadata attributes to exclude during reranking, and `numberOfRerankedResults` — [kb-test-retrieve-generate](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-generate.html). The Rerank API is limited to 10 rps — [Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- **Managed KBs** include a "built-in managed semantic reranker… at no extra cost" — [kb-build-managed](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html). But "If you create a knowledge base with a custom embedding model, the managed reranker is not available for that knowledge base." — [kb-managed-create](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html)
- **Search type (conflict)**:
  - The user guide says "Hybrid search is only supported for Amazon RDS, Amazon OpenSearch Serverless, and MongoDB vector stores that contain a filterable text field… the query uses semantic search" otherwise — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html).
  - The API reference names only OpenSearch Serverless for `HYBRID` — [API: KnowledgeBaseVectorSearchConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_KnowledgeBaseVectorSearchConfiguration.html).
  - S3 Vectors: "Semantic search only: S3 Vectors supports semantic search but not hybrid search capabilities." — [s3-vectors-bedrock-kb](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-bedrock-kb.html)
- **Managed KB search**: "Agentic and semantic hybrid retrieval" — [kb-build-managed](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html); "always performs hybrid search (keyword plus semantic) and does not offer semantic-only search mode" — [Kendra migration guide](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)

### Inferences
- Nova-only means no reranker. Amazon Rerank 1.0 is an Amazon model but not Nova-branded, so it needs an explicit decision, and it is absent from us-east-1. The managed reranker is undisclosed and is lost anyway if a Nova embedding model is chosen (custom embedding).
- On S3 Vectors, exact-term queries (message IDs, HTS codes) rely on embeddings alone. `includeForEmbedding: true` for key identifiers is the native way to make them affect similarity.

### Gaps
- Which model performs query decomposition (the generation model or an internal one) is not documented on the pages fetched.

## 5. RetrieveAndGenerate / RetrieveAndGenerateStream with Amazon Nova models: support, inference profiles, guardrails, citations, sessions, prompt templates

### Takeaway
**High-risk finding:** current Bedrock model cards list "Knowledge base" as **Not Supported** for **Nova Pro** and **Nova 2 Lite**. The Nova Lite and Nova Micro cards do not mention it. The Claude Sonnet 4.5 card lists it as Supported. The KB "supported models" page now only defers to these cards. Community examples show `amazon.nova-pro-v1:0` being used as a `RetrieveAndGenerate` modelArn, so the docs and practice may disagree. This must be tested in the target account and Region before building on RAG with Nova. Apart from model support, R&G offers guardrails (input and output only), citations, `sessionId` multi-turn, custom prompt templates and inference profiles.

### Cited Findings
- The KB supported-models page now says only: "To see which models support Knowledge Bases, please refer to Models at a glance and choose the model you are interested in." Inference profiles can be used "for parsing data or when generating responses" — [Supported models and Regions for KBs](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-supported.html)
- **Nova Pro** (`amazon.nova-pro-v1:0`; geo profiles `us.`, `eu.`, `apac.`; no global profile):
  - Supported: Guardrails, Agents, Flows, Prompt management, prompt caching.
  - Not Supported: "Knowledge base", Structured outputs, Count tokens.
  - Also listed: In-Region us-gov-west-1; lifecycle "Active"; "EOL no sooner than: Dec 05, 2025".

  Source: [Nova Pro model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html)
- **Nova 2 Lite** (`amazon.nova-2-lite-v1:0`; `us.`, `eu.`, `jp.` and `global.` profiles; 1M context):
  - Supported: Guardrails, client-side tool calling.
  - Not Supported: "Knowledge base", Agents, Flows, Structured outputs.
  - No GovCloud Region listed; "EOL no sooner than: Dec 02, 2026".

  Source: [Nova 2 Lite model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html)
- **Nova Lite** (`amazon.nova-lite-v1:0`) and **Nova Micro** (`amazon.nova-micro-v1:0`): both cards list Supported as Response streaming, Guardrails and Client-side tool calling, and Not Supported as Structured outputs and Watermarking. Knowledge base is in neither column. Both are listed In-Region in us-gov-west-1 — [Nova Lite card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html); [Nova Micro card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-micro.html)
- **Calibration**: the Claude Sonnet 4.5 card lists "Knowledge base" under Supported — [Claude Sonnet 4.5 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-4-5.html)
- **Counter-evidence** (search excerpts, not AWS-authoritative): a third-party blog and an AWS ML blog reportedly use `arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0` in `retrieve_and_generate`. A re:Post question discusses a Bedrock KB with Nova Lite — [AWS ML Blog: just-in-time KB](https://aws.amazon.com/blogs/machine-learning/build-a-just-in-time-knowledge-base-with-amazon-bedrock/); [re:Post](https://repost.aws/questions/QUC8zFxKaTR-CmPQAlcwQsJA/handling-large-topic-summarization-in-amazon-bedrock-knowledge-base-with-opensearch-and-nova-lite)
- **modelArn**: "The ARN of the foundation model or inference profile to use for generation." Request fields:
  - `retrievalConfiguration`, `orchestrationConfiguration`, `generationConfiguration`
  - `sessionId` ("Use the same value as a previous session to continue that session and maintain context")
  - `sessionConfiguration` (custom KMS key)

  The response returns a `sessionId` for reuse — [kb-test-retrieve-generate](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-generate.html)
- **Citations**: the response has `output` plus `citations[]`. Each citation has `generatedResponsePart.textResponsePart` (with a `span`) and `retrievedReferences` (chunk content, document metadata, and the source URI/URL). In streaming, "The `citation` member has been deprecated" in favour of `generatedResponse` and `retrievedReferences` — [kb-test-retrieve-generate](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-generate.html)
- **Guardrails**:
  - Set via `generationConfiguration.guardrailConfiguration {guardrailId, guardrailVersion}` — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html).
  - "Guardrails are applied only to the input and the generated response from the LLM. They are not applied to the references retrieved from Knowledge Bases at runtime."
  - `guardrailAction` reports intervention.

  Source for the last two: [kb-test-retrieve-generate](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-generate.html)
- **Prompt templates**: `generationConfiguration.promptTemplate.textPromptTemplate`, plus a customizable orchestration prompt. Placeholders: `$search_results$` (required), `$output_format_instructions$` ("required… for citations"), `$query$`, `$current_time$`. Without a custom template a default system prompt with generic example content is used — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html)
- **Inference parameters**: `textInferenceConfig` (temperature, topP, maxTokens, stopSequences) plus `additionalModelRequestFields`. Unknown keys in `additionalModelRequestFields` raise an exception — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html)
- **Nova Multimodal Embeddings limit**: "When using Nova Multimodal Embeddings, RAG functionality is restricted to text content only. For full multimodal support including audio and video processing, use BDA with text embedding models." — [kb-test-retrieve-generate](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-generate.html)

### Inferences
- If testing confirms Nova models are rejected by `RetrieveAndGenerate`, the Nova-compatible path is `Retrieve` (no generation model) followed by `Converse` with Nova (Guardrails supported per the cards). That reintroduces the two-step design CLAUDE.md currently rules out, which is a user decision.
- Nova Pro, Lite and Micro have us-gov-west-1 In-Region availability. Nova 2 Lite has no GovCloud. Relevant if a CBP deployment must run in GovCloud.

### Gaps
- No authoritative AWS statement found that lists exactly which Nova models `RetrieveAndGenerate` accepts in Nov 2026. The model cards are the only primary source, and they are incomplete for Nova Lite and Micro.
- The Nova Premier card could not be read (the fetch returned an empty page).
- Whether R&G works with Nova via `global.` / `us.` inference profiles was not confirmed.

## 6. Querying multiple KBs: native multi-KB in one call?

### Takeaway
For **customer-managed** KBs there is no native multi-KB query: `Retrieve` and `RetrieveAndGenerate` take a single `knowledgeBaseId`. For **managed** KBs, `AgenticRetrieveStream` queries **up to 5 managed KBs in one call**, with per-retriever filters, a generated answer with citations, a guardrail (only with an explicitly named model), user context for ACLs, and AgentCore Memory sessions.

### Cited Findings
- `knowledgeBaseConfiguration` in RetrieveAndGenerate requires `knowledgeBaseId`, "The ID of the knowledge base to query" (singular) — [kb-test-retrieve-generate](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-generate.html)
- **AgenticRetrieveStream**:
  - `retrievers`: "You can specify up to 5 retrievers, each pointing to a managed knowledge base by its ID. Each retriever can optionally include metadata filters and a maximum number of results."
  - "Agentic retrieval currently supports only managed knowledge bases."
  - Speculative retrieval: "For multiple knowledge bases, this performs a probe search to help route queries to the appropriate retrievers."
  - The result event holds deduplicated `results`, plus `generatedResponse.answer` and `citations` (`startIndex`, `endIndex`, `references[].resultIndex`).
  - `userContext` "for access control filtering"; `memoryConfiguration` (AgentCore Memory `sessionBinding` with `actorId`/`sessionId`).

  Source: [Use agentic retrieval](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html)
- **Agentic retrieval model and guardrails**:
  - `foundationModelType` is `MANAGED` (service-selected) or `CUSTOM` with `modelArn`.
  - "A guardrail is supported only when foundationModelType is CUSTOM."
  - "Only the BLOCK action is supported. The MASK action is not supported."
  - Guardrails with `ANONYMIZE` PII actions fail validation.

  Source: [kb-test-agentic-retrieve](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-agentic-retrieve.html)
- The Kendra migration guide describes the managed KB as able "to do multi-step reasoning across multiple knowledge bases (with an Agentic Retrieval API)" — [Kendra availability change](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- Managed KBs integrate with an AgentCore Gateway (customer-managed: "Not supported") — [kb-build-managed](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html)
- Bedrock Agents can be associated with knowledge bases (`AssociateAgentKnowledgeBase`, per-KB instructions, `knowledgeBaseState`) (search excerpt) — [Augment response generation for your agent with knowledge base](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-kb-add.html). The Nova Pro card lists Agents as Supported and Nova 2 Lite lists it as Not Supported — [Nova Pro card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-pro.html); [Nova 2 Lite card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html)

### Inferences
- With customer-managed KBs, multi-category retrieval without an orchestrator means either one KB with categories as metadata (filtered per request) or app-side fan-out with merging. Fan-out across KBs and stores is orchestration code.
- `AgenticRetrieveStream` is the only native "one call, many KBs" option. It pulls the design toward managed KBs, and toward a non-Nova `MANAGED` model unless a Nova `CUSTOM` model is allowed (unknown). Its guardrail rule fits the project's BLOCK-style PII guardrail.

### Gaps
- Which models are accepted for `foundationModelType: CUSTOM` in agentic retrieval (in particular Nova) is not documented on the page fetched.
- The quota on knowledge bases per Bedrock Agent was not verified this session.

## 7. Customer-managed vs managed KBs: what a managed KB is in 2026 and the trade-offs

### Takeaway
The Bedrock Managed Knowledge Base (GA 2026-06-17, surfaced under AgentCore in the console) owns the vector store, parsing, embedding (managed model by default) and reranking. It adds 12 native connectors, ACL-aware retrieval, agentic multi-KB retrieval, resource policies and much higher quotas. The trade-offs: no choice of vector store (S3 Vectors, OpenSearch, Aurora and the rest are customer-managed-only) and no direct index access. A managed embedding/reranking model of undisclosed provenance can be swapped for Nova Multimodal Embeddings, but then the managed reranker is lost. AWS docs conflict on whether `RetrieveAndGenerate` works on managed KBs; the project has observed it rejected.

### Cited Findings
- **Launch**: "a fully managed retrieval-augmented generation (RAG) service", GA June 17, 2026, in US East (N. Virginia), US West (Oregon), Asia Pacific (Sydney, Tokyo), Europe (Dublin, Frankfurt, London) and AWS GovCloud (US-West). AgentCore integration has "auto-generated permissions and built-in observability" — [What's New 2026-06](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-managed-knowledge-base/)
- **Comparison table, managed vs customer-managed**:
  - Agentic retrieval: Supported / Not supported
  - Data store: "Managed completely by Bedrock" / customer-chosen
  - Embedding: "built-in managed model… at no extra cost", or "any Bedrock embedding model with float32 and 1024 dimensions" / any Bedrock model
  - Reranker: "built-in managed semantic reranker… at no extra cost" / none
  - Parsing: "Built-in parser for multimodal file types" / Default, FM or BDA
  - Infrastructure management: "None required" / "You provision and maintain your vector DB, with direct access to it"

  Source: [Build a managed knowledge base](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html)
- **Custom embeddings for managed KBs**: Titan Text Embeddings V2, Cohere Embed English v3, Multilingual v3, Embed v4, and "Amazon Nova Multimodal Embeddings" (1024 dims, float32). A multimodal custom embedding is TwelveLabs Marengo Embed 3.0 only. "You cannot change the embedding model type after creating the knowledge base." The API uses `knowledgeBaseConfiguration.type: MANAGED` with `managedKnowledgeBaseConfiguration.embeddingModelType: MANAGED|CUSTOM`. Data sources use `type: MANAGED_KNOWLEDGE_BASE_CONNECTOR` — [Create a managed knowledge base](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html)
- **Query API (conflict)**:
  - "After you create and sync a managed knowledge base, use the `Retrieve` API to query it… specify `managedSearchConfiguration`" — [kb-managed-create](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html).
  - The Kendra migration guide shows `retrieve_and_generate` against a managed KB with `managedSearchConfiguration`, and claims "the ability to generate responses (with a Retrieve and Generate API)" — [Kendra availability change](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html).
  - This repo's CLAUDE.md records `RetrieveAndGenerate` being rejected ("not supported for managed knowledge bases").
- **Chunking (conflict)**: "built-in (default) or fixed-size" — [kb-build-managed](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html). The console lists Default, Fixed-size and No chunking — [kb-managed-create](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html). The Kendra guide adds Hierarchical and says "semantic chunking is not supported for managed knowledge bases" — [Kendra guide](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- **Managed KB capabilities**:
  - ACL-aware retrieval — [kb-managed-acl](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-acl.html)
  - Resource policies, listed as "Resource policies for managed knowledge bases" (cross-account), with Put/Get/DeleteResourcePolicy quotas — [kb-build-managed](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html); [Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- **Managed KB gaps vs Kendra**: "BMKB's architecture does not support faceted search", and there are no query suggestions, synonyms, spell check or document-enrichment hooks — [Kendra migration guide](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- AWS now steers new work to managed KBs. The S3 connector, Kendra GenAI index and multimodal pages all carry "For optimized retrieval accuracy and a managed experience, we recommend Amazon Bedrock Managed Knowledge Base." — [S3 connector](https://docs.aws.amazon.com/bedrock/latest/userguide/s3-data-source-connector.html)

### Inferences
- A managed KB would natively give multi-category handling (200 data sources), permissioned S3 categories (ACL files by user email), multi-KB queries (agentic) and IaC (CloudFormation `MANAGED`). Costs: moving off S3 Vectors; losing direct index access, which the planned count path relies on to scan the KB's S3 Vectors index; a possibly non-Nova managed embedding, reranker or agentic model unless overridden; and the open R&G question.
- Choosing Nova Multimodal Embeddings (custom) keeps the embedding Nova-compliant but disables the managed reranker.

### Gaps
- Managed-KB pricing (storage, query) was not retrieved.
- The provenance of the managed embedding, reranker and agentic models is not disclosed on the pages read.
- Whether managed KBs expose any index-scan or list API usable for counts beyond `ListKnowledgeBaseDocuments` / `GetDocumentContent` was not verified.

## 8. Structured-data KBs (Redshift / GenerateQuery) and Kendra GenAI index: capabilities, ACLs, cost, relevance to count/aggregate questions

### Takeaway
Structured KBs convert natural language to SQL over **Amazon Redshift** (provisioned or serverless; data in Redshift or the Glue Data Catalog). That is the only native KB path that can compute exact aggregates such as COUNT and GROUP BY, but it means running Redshift, and topic matching becomes SQL predicates. A Kendra GenAI index as a KB backend is effectively closed: Kendra went into maintenance mode on 2026-06-30 and stopped accepting new customers on 2026-07-30.

### Cited Findings
- Structured KBs "convert user queries into language that is suitable for extracting data from supported structured data stores". They are queried via Retrieve or RetrieveAndGenerate. `GenerateQuery` "converts natural language queries into SQL queries" for use in your own workflow — [Build a KB with a structured data store](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-build-structured.html)
- **Structured KB setup**:
  - Query engine: Amazon Redshift (provisioned cluster or serverless workgroup).
  - Storage: a Redshift database or the AWS Glue Data Catalog (`AWS_DATA_CATALOG` table names).
  - Auth: IAM, a database user (provisioned only), or Secrets Manager.
  - Query configs: `executionTimeoutSeconds`, table and column descriptions, INCLUDE/EXCLUDE, `curatedQueries` (NL→SQL examples).
  - "The generation context is non-deterministic"; "Inclusions and exclusions aren't a substitute for guardrails."

  Source: [Create a KB connected to a structured data store](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-structured-create.html)
- Retrieval configurations other than "Orchestration and generation" "are only applicable to unstructured data sources", so there are no metadata filters or reranking on structured KBs — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html). GenerateQuery quota: 2 rps — [Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- **Structured KB Regions** include US East (N. Virginia), US East (Ohio), US West (Oregon) and AWS GovCloud (US-West) — [knowledge-base-supported](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-supported.html)
- **Kendra GenAI index**: "Reuse your indexed content across multiple Amazon Bedrock applications without rebuilding indexes or re-ingesting data". The page carries the managed-KB recommendation banner — [Kendra GenAI index KB](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-build-kendra-genai-index.html)
- **Kendra status**: "put Amazon Kendra into Maintenance Mode, effective June 30, 2026… as of July 30, 2026, the service is no longer open to new customers." AWS recommends migrating to the Bedrock Managed Knowledge Base — [Amazon Kendra availability change](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- In the CloudFormation `KnowledgeBaseConfiguration`, `SqlKnowledgeBaseConfiguration` updates with "No interruption" and `KendraKnowledgeBaseConfiguration` requires replacement — [CFN KnowledgeBaseConfiguration](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-bedrock-knowledgebase-knowledgebaseconfiguration.html)

### Inferences
- For counts, a structured KB over a one-row-per-message catalog table (in Redshift, or Glue Data Catalog via Redshift) would answer exact counts on structured columns: date, country, attachments, category. "Messages about X" would become keyword predicates (LIKE), which CLAUDE.md has already ruled out as the main mechanism. It also adds Redshift Serverless (plus Glue/Lake Formation if using the Data Catalog).
- Neither vector KB family offers a count or facet API: the Retrieve cap is 100 and managed KBs have no faceted search. Native S3 Vectors `QueryVectors` (top-K up to 10,000, with pre-filtering on `ENHANCED`) and `ListVectors` remain the closest native primitives for a count path, used outside the KB APIs.
- Kendra GenAI index document-level ACLs are moot for a new deployment, because Kendra no longer accepts new customers.

### Gaps
- Which models generate SQL in structured KBs (including whether Nova can be specified) was not found on the pages fetched.
- Row-level security (beyond Redshift's own permissions) for structured KBs was not documented on the pages read.
- Pricing for structured KBs was not retrieved.

## 9. Bedrock Data Automation (BDA) and other parsers for new document categories

### Takeaway
On customer-managed KBs, parsing is set per data source: the default text parser, BDA, or a foundation-model parser (Claude, **Nova** or Llama 4 vision models). BDA and FM parsers extract figures, tables and images, but the docs describe them as content parsers, not metadata extractors. Category metadata still comes from sidecars or a custom transformation Lambda. Both parsers are capped at 1,000 files, and BDA is still described as preview in one doc.

### Cited Findings
- **Parser options**: the default parser handles text only and is free. BDA is "fully-managed… without the need to provide any additional prompting", priced per page or image. FM parsers have a customizable prompt and token pricing. If BDA or FM is chosen, "the method that you choose will be used to parse all .pdf files in your data source". FM parser total file size must be ≤ 100 GB. BDA and FM parsers can store extracted figures and images in an S3 destination returned in source attribution — [Parsing options](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-advanced-parsing.html)
- **Status and models (conflict on preview)**: "The Amazon Bedrock Data Automation parser is supported in US West (Oregon) and is in preview and subject to change." FM parser families are "Claude vision models, Nova vision models, LLama 4 vision models" — [knowledge-base-supported](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-supported.html). The parsing page itself carries no preview note — [kb-advanced-parsing](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-advanced-parsing.html)
- **Quotas**: "(Knowledge Bases) Maximum number of files for BDA parser: 1,000" and "Maximum number of files for Foundation Models as a parser: 1,000" (not adjustable). BDA itself: documents up to 500 MB and 3,000 pages; 40 blueprints per project — [Bedrock quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- **Multimodal**: BDA "Converts multimedia to text representations" (ASR for audio, scene summaries for video, OCR for images), while Nova Multimodal Embeddings embeds media natively. RetrieveAndGenerate over media "is supported when using BDA processing or when the knowledge base contains text content" — [Build a KB for multimodal content](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-multimodal.html)
- Managed KBs use a "Managed parser" (`SMART_PARSING`) by default, with optional advanced indexing for visuals, audio and video — [kb-managed-create](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html)

### Inferences
- For new CSMS-adjacent categories (e.g., PDFs with tables), a Nova vision model as FM parser keeps parsing within the Nova-only rule. BDA is an AWS service, not a Nova model, so whether it is allowed is a policy call.
- The 1,000-file parser cap makes BDA or FM parsing unsuitable for a 30k-message backfill in one data source. Use them only for small, visually rich categories.

### Gaps
- Whether the 1,000-file BDA/FM cap is per ingestion job or per data source is not stated.
- Whether BDA blueprints can populate KB filterable metadata during ingestion: not documented on the pages read. Assume no; use sidecars or a custom transformation Lambda.

## 10. Supported vector stores in 2026 and their filtering / hybrid-search support

### Takeaway
Customer-managed KBs support Amazon S3 Vectors, OpenSearch Serverless, OpenSearch Managed Clusters, Aurora PostgreSQL (RDS), Neptune Analytics (GraphRAG), Pinecone, Redis Enterprise Cloud and MongoDB Atlas. Hybrid search is limited to OpenSearch Serverless, Aurora/RDS and MongoDB (docs conflict). The richest filter operators are on OpenSearch Serverless. S3 Vectors is the cheapest but is semantic-only and has the tightest metadata. Managed KBs use a Bedrock-owned store with hybrid search.

### Cited Findings
- **Vector store tabs** listed: OpenSearch Serverless, OpenSearch Managed Clusters, S3 Vectors, Aurora (RDS), Neptune Analytics graphs (GraphRAG), Pinecone, Redis Enterprise Cloud, MongoDB Atlas — [knowledge-base-setup](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html)
- **Store constraints**:
  - "Amazon OpenSearch Serverless and Amazon OpenSearch Managed clusters are the only vector stores that support storing binary vectors."
  - OpenSearch Managed: "OpenSearch domains that are behind a VPC are not supported for your Knowledge Base."
  - Aurora: "The Aurora cluster must reside in the same AWS account."
  - S3 Vectors: float only; Cosine or Euclidean; dimensions 1–4096; up to 10 non-filterable keys, including `AMAZON_BEDROCK_TEXT` and `AMAZON_BEDROCK_METADATA`.

  Source: [knowledge-base-setup](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html)
- **S3 Vectors** gives "Sub-second cold query latency and as low as 100 millisecond warm query latency". "Best practice is to create a separate vector store for each knowledge base to ensure data synchronization." The Delete/Retain data deletion policies apply — [s3-vectors-bedrock-kb](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-bedrock-kb.html)
- **Filter support by store**: richest on OpenSearch Serverless (`startsWith`, `stringContains`, `listContains`); Neptune partial; S3 Vectors lacks `startsWith`/`stringContains`; Aurora needs a JSONB custom-metadata column with a GIN index (or one column per attribute) — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html); [knowledge-base-setup](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html)
- **Hybrid support (conflict)** is as in section 4 — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html) vs [API reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_KnowledgeBaseVectorSearchConfiguration.html)
- **Embedding models** for customer-managed KBs: Titan Embeddings G1 Text, Titan Text Embeddings V2 (256/512/1024; float or binary; also us-gov-east-1 and us-gov-west-1), Cohere Embed English v3 and Multilingual v3. The vector-type table also lists "Amazon Nova Multimodal Embeddings: Floating-point, 1024" — [knowledge-base-supported](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-supported.html)

### Inferences
- "Possibly other vector stores" in the requirement means separate customer-managed KBs, since the vector store is fixed per KB (`StorageConfiguration` change requires replacement). Combining stores in one query therefore means app-side fan-out (section 6).
- If permission filters need `listContains` / `startsWith`, or hybrid keyword matching for message IDs matters, OpenSearch Serverless is the most capable store, at a much higher baseline cost than S3 Vectors.

### Gaps
- Per-store hybrid support for OpenSearch Managed Clusters and Aurora is inconsistent across docs; needs testing.
- Region availability of Nova Multimodal Embeddings for KBs was not captured.

## 11. CloudFormation / CDK support: how much of "add a category" can be pure IaC

### Takeaway
`AWS::Bedrock::KnowledgeBase` supports `VECTOR`, `KENDRA`, `SQL` and **`MANAGED`** types. `AWS::Bedrock::DataSource` supports `S3`, `CUSTOM`, `REDSHIFT_METADATA`, the preview SaaS connectors and `MANAGED_KNOWLEDGE_BASE_CONNECTOR`. So adding a KB or a data source (prefix, chunking, parsing) is pure IaC; this project already does it with the CDK L1 `CfnKnowledgeBase` and S3 Vectors. Request-time behaviour (filters, permissions, routing, prompt templates, guardrail choice) is not KB configuration; it lives in caller code. The exceptions are managed-KB ACL files and S3 sidecars, which are data.

### Cited Findings
- `KnowledgeBaseConfiguration.Type` "Allowed values: `VECTOR | KENDRA | SQL | MANAGED`" ("Choose `MANAGED` to create a managed knowledge base"). Changing Type, or the Vector/Kendra/Managed sub-configs, requires replacement; `SqlKnowledgeBaseConfiguration` updates with no interruption — [CFN KnowledgeBaseConfiguration](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-bedrock-knowledgebase-knowledgebaseconfiguration.html)
- `StorageConfiguration` updates require replacement. "Redis Enterprise Cloud vector stores are currently unsupported in CloudFormation." — [CFN AWS::Bedrock::KnowledgeBase](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-knowledgebase.html)
- `DataSourceConfiguration.Type` "Allowed values: `S3 | CONFLUENCE | SALESFORCE | SHAREPOINT | WEB | CUSTOM | REDSHIFT_METADATA | MANAGED_KNOWLEDGE_BASE_CONNECTOR`" (replacement on change). Self-managed Confluence, SharePoint, Salesforce and Web crawler are "in preview release". Managed connectors are configured through `ManagedKnowledgeBaseConnectorConfiguration` — [CFN DataSourceConfiguration](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-bedrock-datasource-datasourceconfiguration.html)
- **Local evidence**: the project's CDK uses `CfnKnowledgeBase` with `type="VECTOR"`, `embedding_data_type="FLOAT32"`, `storage_configuration.type="S3_VECTORS"`, and a data source with `type="S3"` — `iac/resources/resource_knowledge_base.py`, lines 123–154.
- Guardrails are supplied per request (`guardrailConfiguration`), not attached to a KB — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html). That matches CLAUDE.md: "A guardrail cannot be attached to a KB itself".

### Inferences
- **Config-only today** (customer-managed, S3 Vectors):
  - new data sources (≤ 5 per KB), each with its own inclusion prefix, chunking or parsing
  - new KBs per permission tier (≤ 100), each with its own S3 Vectors index and IAM role
  - new sidecar attributes (`category`, `access_tier`) within 1 KB / 35 keys

  Mapping a user to an allowed category filter, or choosing which KB(s) to query, needs backend logic unless the managed-KB ACL plus `AgenticRetrieveStream` path is adopted. That path makes per-user scoping and multi-KB selection a property of the KB and data, not of code.

### Gaps
- Whether CloudFormation covers managed-KB retrieval instructions (`retrieval-instruction` resources), resource policies and ACL configuration was not verified.
- The CDK L2 constructs for managed KBs were not checked.
