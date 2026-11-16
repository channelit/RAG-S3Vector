# Permission enforcement, identity propagation and config-driven KB routing for Amazon Bedrock RAG (state as of 6 Nov 2026)

Scope: AWS-recommended patterns for (1) per-user / per-group access control in Bedrock RAG apps spanning several knowledge bases (KBs) or document categories, and (2) configuration-driven routing of questions to the right KB, including AWS reference solutions that are configured rather than coded. Project lens: CBP CSMS assistant (FastAPI backend, one `retrieve_and_generate` call on a standard S3 Vectors-backed KB, `date_numeric` filter, Bedrock Guardrail, anonymous UI with proof-of-work captcha, a Nova planner step, **Amazon Nova models only**).

Source-quality legend: everything cites a URL. "(search summary; not fetched)" means the claim comes from a search-result digest of that page, not from reading the page; treat it as lower confidence. The Service Authorization Reference HTML page (`list_amazonbedrock.html`) redirected to the reference index during this session, so IAM action/condition-key facts were read from AWS's machine-readable service reference JSON (`v1.5`, last modified 2026-11-06 05:01 UTC), which is the programmatic form of the same reference.

## 1. Permission patterns (one KB per boundary + IAM, shared KB + server-side filters, Kendra/Q Business ACLs, S3 Access Grants/Lake Formation): security properties and what AWS recommends

### Takeaway
AWS guidance has settled on a **layered** model. Use separate KBs ("silo") with IAM-enforced scoping only for hard, compliance-grade boundaries. Within a boundary, use a shared KB ("pool") with metadata filters that the **server builds from the verified identity**. AWS describes that second layer as "filter-level (logical) isolation, not IAM-enforced (infrastructure) isolation", and says it fails open if the filter-building code is wrong.

Native ACL engines are not a good fit for this project:
- **Kendra:** RBAC support exists in AWS's GAAB solution only through Kendra.
- **Q Business:** closed to new customers.
- **Bedrock Managed Knowledge Base:** its new ACL awareness is described by AWS as "ACL-aware filtering, not authorization".
- **S3 Access Grants:** appears only as an application-implemented check. No native KB integration was found.

### Cited Findings

**(a) One KB per permission boundary + IAM**
- AWS maps the SaaS silo/pool/bridge models onto Bedrock KBs (blog dated 16 Dec 2024, by Levi, Mitchell and Nikoo) — [AWS ML Blog: Multi-tenant RAG with Amazon Bedrock Knowledge Bases](https://aws.amazon.com/blogs/machine-learning/multi-tenant-rag-with-amazon-bedrock-knowledge-bases/):
  - **Silo** is a separate S3 bucket + KB + vector collection per tenant. It "offers the highest level of tenant isolation", is the most expensive option, and allows per-tenant KMS keys.
  - Silo is "favorable for your largest tenants with specific isolation requirements".
  - **Pool** is one shared stack and is "particularly suitable to accommodate many small tenants".
- The same post quotes these quotas (Dec 2024): "a maximum of 100 knowledge bases are supported in each AWS account"; one concurrent ingestion job per KB and five per account; 5 million documents per data source; 100 GB per job — [AWS ML Blog, Dec 2024](https://aws.amazon.com/blogs/machine-learning/multi-tenant-rag-with-amazon-bedrock-knowledge-bases/). The aws-samples bedrock-chat README also cites a "default limit of 100 knowledge bases per account" as the reason it shares one KB across bots ("multi-tenant mode") — [aws-samples/bedrock-chat](https://github.com/aws-samples/bedrock-chat).
- The AWS Architecture Blog (22 Jun 2026; Dorasamy, Hamza, Wolański) — [Secure multi-tenant RAG with Amazon Bedrock and Verified Permissions](https://aws.amazon.com/blogs/architecture/secure-multi-tenant-rag-with-amazon-bedrock-and-verified-permissions/):
  - It states: "This pattern provides filter-level (logical) isolation, not IAM-enforced (infrastructure) isolation."
  - It warns: "If the middleware logic that constructs the filter were to fail open, documents from other groups would be exposed."
  - For cross-tenant isolation with a compliance boundary, it recommends a dedicated KB per tenant with IAM-enforced boundaries, with the filter pattern layered inside each tenant.
- The AWS ML Blog (31 Aug 2026; Belsian, Mitchell, Elkharbotly) suggests per-tenant KBs only for "a small number of large tenants with strict separation needs". It says querying several KBs in one call is for combining knowledge domains for one user, not for tenant isolation — [Build multi-tenant agentic chat applications ... with Amazon Bedrock Managed Knowledge Base](https://aws.amazon.com/blogs/machine-learning/build-multi-tenant-agentic-chat-applications-on-enterprise-data-with-amazon-bedrock-managed-knowledge-base/).
- Bedrock IAM support: identity-based policies, resource-level permissions, condition keys, "ABAC (tags in policies): Yes" and temporary credentials are all supported. Resource-based policies exist only for guardrails and guardrail inference profiles, and Bedrock has no ACLs — [Bedrock User Guide: How Amazon Bedrock works with IAM](https://docs.aws.amazon.com/bedrock/latest/userguide/security_iam_service-with-iam.html).
- From the service reference — [AWS service reference JSON for Bedrock](https://servicereference.us-east-1.amazonaws.com/v1/bedrock/bedrock.json) (machine-readable form of the [Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonbedrock.html)):
  - `bedrock:Retrieve` is authorized against the `knowledge-base` resource type (`arn:${Partition}:bedrock:${Region}:${Account}:knowledge-base/${KnowledgeBaseId}`).
  - That resource type supports `aws:ResourceTag/${TagKey}`, so Retrieve can be scoped by KB ARN or by KB tag (ABAC).
  - `bedrock:RetrieveAndGenerate` lists **no resource types and no condition keys**. It cannot be scoped to a KB ARN by itself.
- AWS's own KB prerequisite policy grants `bedrock:RetrieveAndGenerate` on `"Resource": ["*"]`, with a separate `bedrock:Retrieve` statement — [Bedrock User Guide: KB prerequisite permissions](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-prereq-permissions-general.html) (search summary; not fetched). A third-party course note shows Retrieve + RetrieveAndGenerate both on one KB ARN — [KodeKloud notes](https://notes.kodekloud.com/docs/Introduction-to-Amazon-Bedrock/Security/Controlling-Access-to-Bedrock-Using-IAM-Part-2/page.md). That conflicts with the service reference, which lists no resource type for RetrieveAndGenerate.
- Cognito identity pools can map user-pool claims (`cognito:groups`, `cognito:preferred_role`, `cognito:roles`) to IAM roles — [Amazon Cognito: Using role-based access control](https://docs.aws.amazon.com/cognito/latest/developerguide/role-based-access-control.html) (search summary; not fetched):
  - Rule match types are Equals / NotEqual / StartsWith / Contains, and the first matching rule wins.
  - There are up to 25 rules per provider, and that limit is not adjustable.
  - Each role's trust policy must restrict assumption to that identity pool's authenticated users.

**(b) One shared KB + server-side metadata filters**
- AWS ML Blog (7 Apr 2025; Warner, Gorgen, Lin) — [Multi-tenancy in RAG applications in a single Amazon Bedrock knowledge base with metadata filtering](https://aws.amazon.com/blogs/machine-learning/multi-tenancy-in-rag-applications-in-a-single-amazon-bedrock-knowledge-base-with-metadata-filtering):
  - "developers must implement proper metadata filtering in their application code."
  - "Failure to enforce appropriate metadata-based filtering could result in unauthorized access to sensitive documents."
  - Filtering is "a critical security boundary and should be consistently applied across all queries."
  - It recommends one consolidated KB with an S3 folder hierarchy rather than one KB per customer, to avoid "unnecessary complexity and hit service limitations".
  - Caveat: its diagram shows the frontend sending the filter.
- AWS ML Blog (31 Aug 2026) is the most explicit AWS statement on client trust — [Managed KB multi-tenant blog](https://aws.amazon.com/blogs/machine-learning/build-multi-tenant-agentic-chat-applications-on-enterprise-data-with-amazon-bedrock-managed-knowledge-base/):
  - The app "derives the user's identity on the server rather than trusting a value sent by the client".
  - The filter value is "built on the server from the verified JWT, not from the request body".
  - Server-side derivation is "the security boundary".
  - On model-inferred filters: "that inference is a relevance feature, not an access control."
  - Its isolation design tags each document `user_id` = Cognito `sub` and applies an `equals` filter on every query.
- AWS Architecture Blog (22 Jun 2026) reference architecture — [Verified Permissions blog](https://aws.amazon.com/blogs/architecture/secure-multi-tenant-rag-with-amazon-bedrock-and-verified-permissions/):
  - Cognito JWTs carry `cognito:groups` (dept-a/b/c). Requests pass AWS WAF, then API Gateway.
  - Layer 1: a Lambda authorizer asks Amazon Verified Permissions (AVP) whether the caller may call the API.
  - Layer 2: a middleware Lambda asks AVP which departments the caller may query, then builds the metadata filter for `RetrieveAndGenerate`.
  - The design is deny-by-default when the authorization service is unavailable.
  - "Externalized Cedar policies in Verified Permissions are auditable, version-controlled, and updatable at runtime."
  - "Each layer operates independently. If one layer is misconfigured, the other layer still enforces access control."
  - Ingestion: S3 → EventBridge → SQS → a Lambda writes `.metadata.json` sidecars, then a scheduled ingestion job runs. Guardrails check that responses are grounded.
- AWS ML Blog (2 Jul 2024; Mitchell, Agarwal, Pecora) — [Access control for vector stores using metadata filtering with Knowledge Bases for Amazon Bedrock](https://aws.amazon.com/blogs/machine-learning/access-control-for-vector-stores-using-metadata-filtering-with-knowledge-bases-for-amazon-bedrock):
  - Cognito user pools authenticate users.
  - Before applying a `patient_id` filter, a Lambda validates the requested IDs against a DynamoDB association table: "This step validates that the doctor is authorized to access the requested patient...".
  - Changing access only requires a DynamoDB update, not new metadata files.
  - It recommends Amplify over its Streamlit demo for production.
- AWS Security Blog (18 Sep 2025; Riggs Goodman III) — [Authorizing access to data with RAG implementations](https://aws.amazon.com/blogs/security/authorizing-access-to-data-with-rag-implementations):
  - LLMs "should be considered untrusted entities because they do not implement authorization as part of a response".
  - Any data in a prompt "could be returned to the principal".
  - Verify "directly at the data source rather than relying on intermediate systems".
  - "Only scopes the user is authorized to will be passed to the LLM."
  - Metadata filtering is a baseline, not strong authorization, because vector stores sync periodically and complex group memberships are hard to express as filters.
- Implicit (model-generated) metadata filtering "is supported by Anthropic Claude models" — [Bedrock User Guide: Configure and customize queries](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html). It is therefore not available under a Nova-only rule, and AWS calls inferred filters a relevance feature in any case (see the 31 Aug 2026 blog above).

**Filter mechanics on the current stack (Bedrock KB + S3 Vectors)**
- KB retrieval filter operators — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html):
  - Available: `equals`, `notEquals`, `greaterThan(OrEquals)`, `lessThan(OrEquals)`, `in`, `notIn`, `startsWith`, `stringContains`, `listContains`.
  - Logical operators: `andAll` / `orAll`, each combining "up to 5 filter types", with one level of nesting.
  - `in` / `notIn` are "currently best supported with Amazon OpenSearch Serverless and Neptune Analytics GraphRAG vector stores". `listContains` is "currently best supported with Amazon OpenSearch Serverless vector stores".
  - "If your knowledge base uses a vector index in an S3 vector bucket, you cannot use the `startsWith` and `stringContains` filters."
  - Managed KBs also do not support `startsWith` / `stringContains`.
- Native S3 Vectors filtering — [Amazon S3 User Guide: S3 Vectors metadata filtering](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-metadata-filtering.html):
  - Operators: `$eq`, `$ne`, `$gt`/`$gte`/`$lt`/`$lte`, `$in`, `$nin`, `$exists`, `$and`, `$or`, and `$startsWith` (ENHANCED only).
  - `$eq` against an **array** value "returns true if the input value matches any element in the array". For example, `{"category": {"$eq": "documentary"}}` matches `["documentary","romance"]`.
  - **Index mode matters:**
    - ENHANCED indexes pre-filter before the vector search.
    - "Vector buckets created on or after September 30, 2026 create ENHANCED indexes"; older buckets have CLASSIC indexes.
    - On CLASSIC, search and filter run together, and "queries with filters may return fewer than top K results when the vector index contains very few matching results".
    - ENHANCED allows up to 100 filter constraints per query, and an index's mode can be changed.

**(c) ACL engines: Kendra, Q Business / Amazon Quick, Bedrock Managed Knowledge Base**
- The AWS solution "Generative AI Application Builder on AWS" (GAAB) supports RBAC only with Kendra — [GAAB: Advanced knowledge base settings](https://docs.aws.amazon.com/solutions/latest/generative-ai-application-builder-on-aws/advanced-knowledge-base-settings.html):
  - Cognito group names must "exactly match the groups configured in your Amazon Kendra index ACLs".
  - GAAB "extracts the appropriate claims from the user authentication token and creates an Attribute Filter".
  - "For Amazon Bedrock Knowledge Base, RBAC is not supported, but you can use metadata filters to achieve some level of filtering."
- Amazon Q Business — [Amazon Q Business availability change](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html):
  - "Amazon Q Business is no longer open to new customers. AWS will continue to provide bug fixes and security updates for existing customers, however new feature requests will no longer be considered." AWS recommends Amazon Quick.
  - "Customers who use anonymous access and API integration of Q Business into custom applications should contact AWS Support."
  - Quick supports document-level ACLs for S3, Confluence Cloud, SharePoint and Google Drive KBs. ACLs must be enabled when the KB is created and that setting is permanent.
  - Quick "does not ingest documents that lack an associated ACL entry".
  - In non-Identity-Center mode, every Quick user gets access to connected indexes, so content must be split into KBs by access level.
- Bedrock Managed Knowledge Base ACL awareness — [Bedrock User Guide: ACL-aware retrieval on managed knowledge bases](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-acl.html):
  - The caller passes `userContext.userId`, which is "always the user's universal email address".
  - "ACL awareness provides ACL-aware filtering, not authorization. Bedrock Managed Knowledge Base does not authenticate end users — your application must authenticate users and pass verified identity context."
  - Without `userContext`, ACL-enabled data sources return zero results. Documents with no ACL are returned to no one. Deny overrides allow.
  - Results are not backfilled when access checks remove some.
  - "Third-party identity provider credentials are cached for up to 1 hour", and ACL changes are eventually consistent within minutes.
  - Connectors with ACL guides: SharePoint, OneDrive, Google Drive, Confluence, Salesforce, Amazon S3, Custom.
- `AgenticRetrieveStream.userContext` "is used for access control filtering to ensure that retrieval results only include documents the user is authorized to access" — [Bedrock API Reference: AgenticRetrieveStream](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetrieveStream.html).
- A third-party post reports a `CheckIngestedDocumentAcl` debugging API added 9 Sep 2026 to Managed KB. No AWS primary source was found for it — [Classmethod](https://dev.classmethod.jp/en/articles/amazon-bedrock-knowledge-base-document-acl-debugging/) (search summary; not fetched).

**(d) S3 Access Grants / Lake Formation / Identity Center**
- AWS's RAG authorization pattern with S3 Access Grants is implemented by the app, not by the KB — [AWS Security Blog, Sep 2025](https://aws.amazon.com/blogs/security/authorizing-access-to-data-with-rag-implementations):
  - The app exchanges the user's token with IAM Identity Center and assumes a role for the user.
  - It fetches that user's grants from S3 Access Grants.
  - It checks each returned chunk against those grant scopes before the chunk reaches the LLM.
- No AWS page was found showing native Bedrock KB integration with S3 Access Grants or trusted identity propagation — [search result set](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-grants.html) (search summary; absence of evidence only).

### Inferences
- **Shape for CSMS:** the public CSMS corpus can stay in today's shared KB. Any category that needs a real compliance boundary should get its own KB, reached with per-group credentials. Inside each KB, the backend should always send `andAll[ date_numeric range, <access clause built from verified groups> ]`. That is AWS's "dedicated KB for hard isolation, filter inside" layering.
- **IAM and RetrieveAndGenerate:** the service reference lists no resource type for `RetrieveAndGenerate`. IAM-enforced per-KB isolation of the single R&G call therefore depends on whether R&G also checks `bedrock:Retrieve` on the KB ARN. If it does not, the IAM-enforced path has to be `Retrieve` (scopable) followed by `Converse` (Nova), which changes the single-call design. This needs testing (see Gaps).
- **Access attribute design on S3 Vectors:** the simplest attribute is likely a single-valued `access_category` string matched with `equals`, or `orAll` of `equals` (up to 5), against the user's allowed categories. Avoid `stringContains` and `startsWith`, which are unsupported on S3 vector buckets. `in` and `listContains` are only "best supported" on OpenSearch Serverless. S3 Vectors' native `$eq` matches inside arrays, so a list attribute plus `equals` may work, but Bedrock's operator translation is undocumented. Test before relying on it.
- **Index mode risk:** a KB index created before 30 Sep 2026 (likely the case for this project, whose KB report dates from Sept 2026) is probably CLASSIC. A restrictive access filter could then return fewer than `KB_NUM_RESULTS` chunks. This is a recall problem, not a leak. Check the index mode and consider switching to ENHANCED.
- **Nova-only rule:** because implicit filtering is Claude-only, the existing Nova planner is the right place to extract *relevance* filters such as dates and countries. *Access* clauses must be appended by code after the planner and never generated by a model. This matches AWS's "relevance feature, not an access control".
- **Managed KB ACLs vs this project:** Managed KB is the only AWS-native per-user ACL engine left for new builds. It does not fit this project: CSMS documents are scraped public bulletins in S3, and the project notes say managed KBs reject `RetrieveAndGenerate`.

### Gaps
- No AWS Prescriptive Guidance page specific to multi-tenant or multi-group RAG on Bedrock KBs was found. The guidance above comes from AWS blogs (ML, Architecture, Security).
- Current KB-per-account quota: the 100 figure is from Dec 2024 sources. Check Service Quotas.
- Whether `RetrieveAndGenerate` enforces `bedrock:Retrieve` on the KB ARN was not confirmed. Test with a role that lacks Retrieve on the target KB.
- How `in` / `listContains` / `equals`-on-list behave on S3 Vectors-backed standard KBs is not documented.
- No evidence of Lake Formation applying to unstructured Bedrock KBs.
- Which models Amazon Quick uses, and whether customers can choose them (e.g., pin Nova), was not found.

## 2. Can IAM restrict which KB a caller queries, which metadata filter it must use, and whether a guardrail is applied?

### Takeaway
IAM can restrict *which KB* (for `Retrieve`), *which flow alias*, *which agent alias* and *which prompt* a principal can use, by ARN or resource tag. There is **no condition key for metadata filters or retrieval configuration**, no `bedrock:KnowledgeBaseArn` key, and `RetrieveAndGenerate` has neither resource-level permissions nor condition keys. Mandatory filters therefore cannot be enforced by IAM.

The `bedrock:GuardrailIdentifier` key enforces a guardrail only on InvokeModel/Converse-family calls. AWS warns that it breaks `RetrieveAndGenerate` / `InvokeAgent`. The AWS-native way to make a guardrail always apply is the 2026 **account-level or organization-level enforced guardrail**.

### Cited Findings
- **All Bedrock condition keys** (service reference v1.5): `aws:RequestTag/${TagKey}`, `aws:ResourceTag/${TagKey}`, `aws:TagKeys`, `bedrock:BearerTokenType`, `bedrock:DataRetentionMode`, `bedrock:GuardrailIdentifier`, `bedrock:InferenceProfileArn`, `bedrock:InlineAgentName`, `bedrock:ModelArn`, `bedrock:ProjectArn`, `bedrock:PromptRouterArn`, `bedrock:ServiceTier`, `bedrock:ThirdPartyKnowledgeBaseCredentialsSecretArn`. None of them refers to a KB ARN in the request or to retrieval filters — [AWS service reference JSON for Bedrock](https://servicereference.us-east-1.amazonaws.com/v1/bedrock/bedrock.json).
- **Per-action resources and condition keys** (same source):

  | Action | Resource types | Action condition keys |
  |---|---|---|
  | `Retrieve` | `knowledge-base` (supports `aws:ResourceTag`) | none |
  | `RetrieveAndGenerate` | none | none |
  | `InvokeFlow` | `flow-alias` (supports `aws:ResourceTag`) | none |
  | `InvokeAgent` | `agent-alias` (supports `aws:ResourceTag`) | none |
  | `InvokeInlineAgent` | — | `bedrock:InlineAgentName` |
  | `ApplyGuardrail` | `guardrail`, `guardrail-profile` | none |
  | `GetPrompt` / `RenderPrompt` | `prompt`, `prompt-version` | — |
  | `InvokeModel` | many model resource types | `bedrock:GuardrailIdentifier`, `bedrock:InferenceProfileArn`, `bedrock:ModelArn`, `bedrock:ProjectArn`, `bedrock:PromptRouterArn`, `bedrock:ServiceTier`, `aws:RequestTag`, `aws:TagKeys` |

  The service reference has no separate IAM action for `RetrieveAndGenerateStream`.
- **Operation → IAM action mapping** (same source):
  - `Converse` authorizes `InvokeModel`, `ApplyGuardrail`, `InvokeTool`, `CallWithBearerToken`.
  - `RetrieveAndGenerate` and `RetrieveAndGenerateStream` authorize `RetrieveAndGenerate`.
  - `AgenticRetrieveStream` authorizes `AgenticRetrieveStream` + `Retrieve`.
  - `GenerateQuery` authorizes `GenerateQuery` + `GetKnowledgeBase`.
- **Guardrail enforcement via IAM** — [Bedrock User Guide: Enforce the use of specific guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-permissions-id.html):
  - Supported APIs: Converse, ConverseStream, InvokeModel, InvokeModelWithResponseStream.
  - Pattern: Allow with `StringEquals`/`ArnLike` on `bedrock:GuardrailIdentifier` (pinned version `:1`, any numeric `:*`, or including DRAFT `guardrail-id*`), paired with an explicit Deny using `StringNotEquals`/`ArnNotLike`, plus Allow `bedrock:ApplyGuardrail` on the guardrail.
  - Limitations (verbatim): "A user should not use the same role with additional permissions to invoke Bedrock APIs like `RetrieveAndGenerate`, `InvokeAgent`, and `InvokeInlineAgent` that make `InvokeModel` calls on behalf of the user. This can lead to access denied errors even when the guardrail is specified in the request because these APIs make multiple `InvokeModel` calls, and some of these calls don't include a guardrail."
  - "A user can bypass applying a guardrail in their prompt by using guardrail input tags. However, the guardrail is always applied on the response."
  - Guardrail and role must be in accounts of the same AWS organization.
- **Account-level and organization-level guardrail enforcement** — [Bedrock User Guide: Apply cross-account safeguards with Amazon Bedrock Guardrails enforcements](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-enforcements.html):
  - Account level: "Designate a particular version of a guardrail within an AWS account for all Amazon Bedrock model invocations from that account". It is set per Region with `PutEnforcedGuardrailConfiguration`.
  - Organization level: AWS Organizations Bedrock policies (`BEDROCK_POLICY`). These are declarative and resolve to one effective policy per account; they are "not a union of every attachment in the tree".
  - Organization, account and request guardrails all apply: "a union of all guardrails, with the most restrictive control taking precedence".
  - "Selective content guarding" decides whether caller input tags are honored. It defaults to **Comprehensive**, which evaluates everything regardless of tags.
  - Model include/exclude lists are supported; AWS's example excludes `amazon.titan-embed-text-v2:0`.
  - Supported safeguards: content filters, denied topics, word filters, sensitive-information filters, contextual grounding. The automated reasoning policy "is unsupported for guardrail enforcements and will cause runtime failures".
  - Verification steps test InvokeModel, InvokeModelWithResponseStream, Converse and ConverseStream. `DeleteGuardrail` is blocked while a guardrail is used for enforcement.
- **GA status conflict:** AWS What's New (April 2026) announces general availability of cross-account safeguards — [What's New, Apr 2026](https://aws.amazon.com/about-aws/whats-new/2026/04/bedrock-guardrails-cross-account-safeguards) (search summary; not fetched). The AWS Organizations Bedrock-policies page reportedly still says "preview" — [AWS Organizations: Amazon Bedrock policies](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_bedrock.html) (search summary; not fetched).

### Inferences
- **Container UI (single R&G call):** do not attach a `bedrock:GuardrailIdentifier` Deny to the backend role, because AWS documents AccessDenied failures for R&G. Keep the request-level guardrail in `generationConfiguration`. Where the account allows it, add an account-level enforced guardrail as a baseline the app cannot bypass. Comprehensive guarding also closes the "input tags" bypass. Excluding Titan embedding models, as AWS's example does, avoids guarding embeddings.
- **"Which KB" per group via IAM** requires per-group credentials at call time:
  - Cognito identity-pool role mapping from `cognito:groups`, or backend `sts:AssumeRole` with session tags; and
  - policies on `bedrock:Retrieve` scoped to KB ARNs, or ABAC on `aws:ResourceTag/<key>` matching `${aws:PrincipalTag/<key>}`.
  - The exact ABAC policy form is an inference from Bedrock's documented ABAC support and the `knowledge-base` resource's tag support. It is not taken from an AWS worked example.
- **Mandatory filters** cannot be expressed in IAM. They must be enforced in backend code, or in an external policy engine (e.g., AVP/Cedar) whose decision the backend turns into the filter, as in AWS's Verified Permissions architecture.

### Gaps
- Whether the account/org-level enforced guardrail also covers the internal model calls made by `RetrieveAndGenerate`, Agents, Flows and `AgenticRetrieveStream`. The doc says "all Amazon Bedrock model invocations" but only shows InvokeModel/Converse tests.
- Whether `RetrieveAndGenerate` checks `bedrock:Retrieve` on the KB (repeated from section 1).
- No AWS worked example was found of ABAC with `aws:PrincipalTag` on `knowledge-base` resources.

## 3. Identity: the simplest AWS-native way to add login + groups to a FastAPI/React app on Fargate/ALB (Cognito, ALB OIDC, CloudFront/Lambda@Edge, AgentCore Identity, IAM Identity Center TIP)

### Takeaway
The lowest-code AWS-native option is a **Cognito user pool with groups** plus an ALB **`authenticate-cognito`** action on an HTTPS listener in front of the Fargate service. The backend:
1. Verifies the ALB-signed `x-amzn-oidc-data` JWT (ES256, with the `signer` checked against the ALB ARN) and takes the user's `sub` from it.
2. Gets the user's groups from the Cognito access token, which carries `cognito:groups`.
3. Maps groups to allowed KBs and categories from configuration (DynamoDB, or AVP/Cedar).

IAM Identity Center trusted identity propagation (TIP) is heavier and targets Q/Quick and S3 Access Grants. AgentCore Identity matters only if the app moves onto AgentCore Runtime or Gateway.

### Cited Findings
- **ALB authentication** — [ELB User Guide: Authenticate users using an Application Load Balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/listener-authenticate-users.html):
  - The ALB supports OIDC IdPs directly and, through Cognito user pools, social IdPs and corporate identities (SAML/OIDC/OAuth).
  - `authenticate-cognito` and `authenticate-oidc` "are supported only with HTTPS listeners".
  - `OnUnauthenticatedRequest`: `authenticate` (redirect), `allow`, or `deny` (401 for AJAX; the doc suggests `deny` for SPAs that poll).
  - The default session timeout is 7 days. Login must complete within 15 minutes.
  - Logout means expiring the ALB cookie and redirecting to the IdP logout endpoint.
- **Claims headers** (same ALB doc):
  - `x-amzn-oidc-data` carries the user claims (from the IdP **userinfo** endpoint) as a JWT signed with ES256. Key lookup is at `https://public-keys.auth.elb.{region}.amazonaws.com/{key-id}`, with separate endpoints for GovCloud.
  - "you must verify the signature of `x-amzn-oidc-data` and confirm that the `signer` field in the JWT header matches your Application Load Balancer's ARN."
  - `x-amzn-oidc-accesstoken` ("The access token from the token endpoint, in plain text") and `x-amzn-oidc-identity` are "Legacy unsigned headers ... cannot be independently verified by your application".
  - The ALB "does not pass the ID token information".
  - AWS recommends restricting targets to traffic from the ALB's security group, and points to the `aws-jwt-verify` library.
- **Regions:** ALB Cognito integration is listed for commercial Regions (including US East and US West). No GovCloud Region appears in that list, while GovCloud public-key endpoints are documented for verifying signed claims — [ALB doc](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/listener-authenticate-users.html).
- **CloudFront in front of the ALB:** forward all request headers, query strings and cookies, and use HTTPS/443 end to end for OIDC — [ALB doc](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/listener-authenticate-users.html).
- **Cognito access token** — [Cognito Developer Guide: Understanding the access token](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html):
  - It contains `cognito:groups` ("An array of the names of user pool groups that have your user as a member").
  - It is RS256-signed with the user pool's JWKS: "Don't trust the claims in an access token until you verify the signature."
  - Validate `iss` against the user pool. Token lifetime is configurable from 5 minutes to 1 day.
  - A pre token generation Lambda (Essentials/Plus feature plans) can add scopes or claims.
  - Machine-to-machine tokens omit `cognito:groups`.
- **What AWS reference designs use:**
  - The Verified Permissions architecture uses Cognito JWTs with `cognito:groups` — [AWS Architecture Blog, Jun 2026](https://aws.amazon.com/blogs/architecture/secure-multi-tenant-rag-with-amazon-bedrock-and-verified-permissions/).
  - The Managed KB blog uses the verified Cognito JWT `sub` — [AWS ML Blog, Aug 2026](https://aws.amazon.com/blogs/machine-learning/build-multi-tenant-agentic-chat-applications-on-enterprise-data-with-amazon-bedrock-managed-knowledge-base/).
  - GAAB uses Cognito for its web UI and API, with a Lambda authorizer that returns an IAM policy "based on the Amazon Cognito group the authenticating user belongs to" (stored in DynamoDB) — [GAAB GitHub](https://github.com/aws-solutions/generative-ai-application-builder-on-aws).
  - bedrock-chat uses Cognito with optional Google or custom OIDC federation (which disables self sign-up), a `--disable-self-register` flag and `allowedSignUpEmailDomains` — [aws-samples/bedrock-chat](https://github.com/aws-samples/bedrock-chat).
- **AgentCore** — [AgentCore Gateway: Managed KB connector target](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-managed-kb.html):
  - Gateways accept inbound IAM or custom-JWT authorization; Runtime supports SigV4 or JWT validated against an OIDC discovery URL with allowed audiences and clients — [AWS ML Blog: Introducing AgentCore Identity](https://aws.amazon.com/blogs/machine-learning/introducing-amazon-bedrock-agentcore-identity-securing-agentic-ai-at-scale/) (search summary; not fetched).
  - For Managed KB targets, "The Gateway does not populate `userContext` from the caller's IAM identity — your application must supply it explicitly". The *calling application (not the model)* must include it.
  - Policy in AgentCore (Cedar) became generally available on 3 Mar 2026 and authorizes Gateway tool calls — [What's New, Mar 2026](https://aws.amazon.com/about-aws/whats-new/2026/03/policy-amazon-bedrock-agentcore-generally-available) (search summary; not fetched). Attaching a policy blocks everything by default — [AWS Security Blog: why AgentCore Policy chose Cedar](https://aws.amazon.com/blogs/security/why-policy-in-amazon-bedrock-agentcore-chose-cedar-for-securing-agentic-workflows/) (search summary; not fetched).
- **IAM Identity Center:**
  - Q Business/Quick migrations with per-user ACLs require Identity Center-based identity in the same account and Region — [Q Business availability change](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html).
  - The S3 Access Grants RAG pattern exchanges tokens with Identity Center — [AWS Security Blog, Sep 2025](https://aws.amazon.com/blogs/security/authorizing-access-to-data-with-rag-implementations).

### Inferences
- **Getting groups behind the ALB:** the ALB doc's claim example (sub/name/email from userinfo) suggests `x-amzn-oidc-data` may not contain `cognito:groups`. The access token in `x-amzn-oidc-accesstoken` arrives in an unsigned header, but the token is itself a Cognito RS256 JWT. Verifying it against the user pool JWKS should therefore give trustworthy groups. The fallback is a `cognito-idp:AdminListGroupsForUser` lookup keyed on the verified `sub`. Both are untested inferences.
- **Local `docker compose` (no ALB):** a single code path that works both locally and on Fargate is probably simpler. The React app signs in with Cognito managed login (Amplify), sends the access token as a bearer token, and FastAPI verifies signature, `iss`, `client_id`, `token_use=access` and `exp`, then reads `cognito:groups`. The ALB `authenticate-cognito` action then becomes optional hardening on the (currently commented-out) Fargate path.
- **Captcha:** the ALTCHA captcha could remain for an anonymous public tier (public KB only). Restricted categories would require login, so the group→KB map gains a default "anonymous" row.
- **Deployment Region:** if CBP deploys in GovCloud, ALB `authenticate-cognito` is not listed there. Use `authenticate-oidc` with an OIDC IdP, or app-level token verification.

### Gaps
- CloudFront + Lambda@Edge authentication patterns were not researched in this session.
- Whether Cognito's userinfo response (and so `x-amzn-oidc-data`) includes groups was not confirmed.
- Cognito identity-pool "attributes for access control" (principal tags for ABAC) was not fetched.
- AgentCore Identity official docs on inbound JWT claim mapping were not fetched.

## 4. Configuration-driven (low-code) routing building blocks: Prompt Management, Flows (+ aliases), a KB registry (AppConfig/SSM/DynamoDB), intelligent prompt routing, semantic routing, Agents, Managed-KB agentic retrieval

### Takeaway
AWS provides configuration artifacts for:
- **Prompts:** versioned Prompt Management prompts.
- **Workflows:** Flows with condition nodes and IAM by flow alias.
- **Model choice:** Intelligent Prompt Routing, limited to models of one family; Nova Lite and Nova Pro are supported.
- **Multi-KB retrieval:** the 2026 Managed-KB `AgenticRetrieveStream`, where KBs are listed as "retrievers" with descriptions and set by an administrator on an AgentCore Gateway target.

No AWS service offers a declarative "KB registry with `allowed_groups` and filter templates". That remains a thin custom component, typically a DynamoDB/SSM config table plus, optionally, AVP Cedar policies. Flows' KB node has **no filter field**, so permission-aware retrieval inside Flows needs a Lambda or inline-code node.

### Cited Findings
- **Prompt Management** — [Bedrock User Guide: Prompt management](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-management.html); [service reference JSON](https://servicereference.us-east-1.amazonaws.com/v1/bedrock/bedrock.json):
  - Prompts carry variables, variants (alternative message/model/inference configuration) and saved versions.
  - Prompts are used at runtime either by "Specify the prompt when running model inference" or through a Flow prompt node.
  - IAM: `GetPrompt` / `RenderPrompt` act on the `prompt` and `prompt-version` (`prompt/${PromptId}:${PromptVersion}`) resources, both of which support tags.
- **Flows: condition node** — [Bedrock User Guide: Node types for your flow](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html):
  - Uses relational operators (`==`, `!=`, `>`, `>=`, `<`, `<=`) and logical operators (`and`, `or`, `not`).
  - "Conditions are evaluated in order. If more than one condition is satisfied, the earlier condition takes precedence." A `default` condition is supported.
  - Other nodes: Agent (`agentAliasArn`), Lambda (its event includes `flowArn`/`flowAliasArn`), Lex, S3 storage/retrieval, Iterator/Collector, DoWhile (`maxIterations` default 10).
  - Inline code node: preview, Python 3.12 only, at most 5 per flow, 5 inputs and 25 running per account, not supported in async flows.
- **Flows: KB node configuration** — [Bedrock API Reference: KnowledgeBaseFlowNodeConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_KnowledgeBaseFlowNodeConfiguration.html):
  - Fields: `knowledgeBaseId` (required, ≤10 characters), `modelId`, `guardrailConfiguration`, `inferenceConfiguration`, `numberOfResults` (1–100), `orchestrationConfiguration`, `promptTemplate`, `rerankingConfiguration`.
  - There is **no retrieval or metadata-filter field**.
  - "Guardrails can only be applied when using `RetrieveAndGenerate` in a knowledge base node" — [flows-nodes](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html).
- **Flows: IAM:** `InvokeFlow` is authorized on the `flow-alias` resource (`flow/${FlowId}/alias/${FlowAliasId}`), which supports `aws:ResourceTag` — [service reference JSON](https://servicereference.us-east-1.amazonaws.com/v1/bedrock/bedrock.json).
- **Intelligent prompt routing** — [Bedrock User Guide: Understanding intelligent prompt routing](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html):
  - It provides "a single serverless endpoint to efficiently route requests between different foundational models within the same model family".
  - Supported models include **Nova Lite (`amazon.nova-lite-v1:0`) and Nova Pro (`amazon.nova-pro-v1:0`)** plus Llama 3.x. Default routers use Nova and Llama families.
  - "You must choose exactly two models within the same family."
  - It is "only optimized for English prompts" and "can't adjust routing decisions or responses based on application-specific performance data".
  - The `bedrock:PromptRouterArn` condition key exists on InvokeModel — [service reference JSON](https://servicereference.us-east-1.amazonaws.com/v1/bedrock/bedrock.json).
  - It routes between models, not between KBs.
- **Routing strategies** — AWS ML Blog (9 Apr 2025; Seifi, Chugh), [Multi-LLM routing strategies for generative AI applications on AWS](https://aws.amazon.com/blogs/machine-learning/multi-llm-routing-strategies-for-generative-ai-applications-on-aws/):
  - **Static routing** through separate UI components.
  - **LLM-assisted (classifier) routing**: "it introduces additional costs and latency", and keeping the classifier current can be demanding.
  - **Semantic routing** embeds reference prompts: "having adequate coverage for all possible task categories in your reference prompt set is crucial".
  - **Hybrid**: semantic routing for broad categories, then a classifier LLM.
  - At that time it described Intelligent Prompt Routing as Claude and Llama only and "can reduce costs by up to 30%". The current docs (above) list Nova.
- **Bedrock Agents** — [Bedrock API Reference: SessionState](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_SessionState.html):
  - `InvokeAgent` `sessionState.knowledgeBaseConfigurations` is "An array of configurations, each of which applies to a knowledge base attached to the agent". This is the hook for supplying per-invocation KB settings from the server.
  - In multi-agent collaboration, `sessionAttributes` "will be forwarded to all agent collaborators", while `promptSessionAttributes` are used only by the supervisor.
- **Managed-KB agentic retrieval across KBs** — [Bedrock API Reference: AgenticRetrieveStream](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetrieveStream.html) and [AgenticRetriever](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetriever.html):
  - It "Retrieves information from one or more knowledge bases using an agentic approach ... decompose complex queries into sub-queries".
  - `retrievers[]` (minimum 1) each holds `configuration` (a union, e.g., `knowledgeBase.knowledgeBaseId`) and a `description` of the retriever's purpose.
  - Model: `foundationModelType`, where `MANAGED` means "the service selects the optimal model for you".
  - Other settings: `maxAgentIteration`, reranking, `generateResponse`, `policyConfiguration.bedrockGuardrailConfiguration`, a versioned `retrievalInstructionConfiguration` (`retrievalInstructionId` + `version`), optional AgentCore Memory with `metadataFilters`, and `userContext`.
  - Results report a `sourceRetriever` identifier and citations. Trace actions include `retrieve`, `fullDocumentExpansion`, `codeExecution` and `memoryRetrieve`.
- **Managed-KB availability and AgentCore Gateway target** — [AgentCore Gateway: Managed KB connector target](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-managed-kb.html):
  - Agentic retrieval "is available only on the Managed Knowledge Base" — [AWS ML Blog: Agentic retrieval for Amazon Bedrock Managed Knowledge Base](https://aws.amazon.com/blogs/machine-learning/agentic-retrieval-for-amazon-bedrock-managed-knowledge-base/) (search summary; not fetched).
  - The AgentCore connector "is supported only for Amazon Bedrock Managed Knowledge Bases".
  - `CUSTOM` model type means "a Bedrock model ARN you supply".
  - Retrievers "are configured by the administrator on the target, not supplied by the agent". The agent sends only `messages` unless `parameterOverrides` expose more fields, such as a Retrieve `filter`.
- **Config-registry precedents in AWS samples:**
  - GAAB's deployment includes "Systems Manager Parameter Store" and a DynamoDB "LLM configuration table" for use cases — [GAAB: Cost](https://docs.aws.amazon.com/solutions/latest/generative-ai-application-builder-on-aws/cost.html).
  - GAAB's KB filters are set as JSON "when deploying a use case" — [GAAB: Advanced knowledge base settings](https://docs.aws.amazon.com/solutions/latest/generative-ai-application-builder-on-aws/advanced-knowledge-base-settings.html).
  - AWS's 2024 sample keeps authorization mappings in a DynamoDB table — [AWS ML Blog, Jul 2024](https://aws.amazon.com/blogs/machine-learning/access-control-for-vector-stores-using-metadata-filtering-with-knowledge-bases-for-amazon-bedrock).
  - AVP Cedar policies are "updatable at runtime" — [AWS Architecture Blog, Jun 2026](https://aws.amazon.com/blogs/architecture/secure-multi-tenant-rag-with-amazon-bedrock-and-verified-permissions/).

### Inferences
- **The config-driven router this evidence supports** is a registry plus code:
  - Each registry row: `kb_id`, `description`, `allowed_groups`, `access_filter_template`, `guardrail_id`/`version`, `model_arn` (Nova), and Prompt Management prompt ARN/version.
  - Flow: the Nova planner returns `{intent, categories, filters}`. Code intersects `categories` with the categories the verified groups allow, builds `andAll[date range, access clause, planner filters]`, and issues one `retrieve_and_generate` per selected KB (or the count path).
  - Store the registry in DynamoDB or SSM/AppConfig. Use AVP only if group→category rules need audit or versioning.
- **Semantic routing** over the registry `description` fields (Titan v2 embeddings, as the KB already uses) is a cheap first-pass classifier. A hybrid with the Nova planner follows AWS's "hybrid" strategy.
- **Flows** fit only if a visual, versioned DAG is wanted. Their KB nodes cannot carry per-user filters, and guardrails apply only on the generate path. A Lambda node calling `Retrieve` with the server-built filter would bring the code back.
- **Intelligent prompt routing** could cut generation cost (Nova Lite ↔ Nova Pro) but does not choose KBs. Whether `RetrieveAndGenerate`'s `modelArn` accepts a prompt-router ARN is untested.
- **Managed-KB agentic retrieval** is AWS's closest "configure the KBs and descriptions, the service routes" product. It conflicts with the project constraints: Managed-KB only, no `RetrieveAndGenerate`, and the `MANAGED` model may not be Nova unless `CUSTOM` accepts a Nova ARN.

### Gaps
- The Flows versions/aliases user-guide page was not fetched; only the alias resource and ARN are confirmed.
- Prompt Management's supported-models list (Nova) was not fetched.
- AWS AppConfig for GenAI routing configuration was not researched.
- Whether `AgenticRetrieveStream` `CUSTOM` accepts Nova models.
- The fields of the `KnowledgeBaseConfiguration` object in Agents `SessionState` (e.g., a filter) were not fetched.
- Bedrock Agents and multi-agent collaboration support for Nova was not checked.
- re:Invent 2024/2025 session material was not reviewed.

## 5. AWS reference solutions that are configured rather than coded (GAAB, bedrock-chat, aws-genai-llm-chatbot; plus Q Business/Quick)

### Takeaway
- **GAAB** (wizard-configured use cases; Bedrock KB or Kendra; Nova Pro in its cost examples; Cognito; RBAC only through Kendra) **retires on 28 Feb 2027**.
- **aws-genai-llm-chatbot** was **archived on 10 Sep 2026**.
- **aws-samples/bedrock-chat** is the active one: v3, Nova models, KB import/sharing, Cognito groups that gate bot creation and publishing, OIDC federation. It does not document per-group KB access control.
- **Q Business** is closed to new customers, and its successor Amazon Quick is an end-user product rather than an embeddable API.

None of these delivers "per-group KB access + Nova-only + standard S3 Vectors KB + custom FastAPI/React UI" as configuration alone.

### Cited Findings
- **GAAB status:** "Generative AI Application Builder on AWS will be retired on February 28, 2027." "Existing deployments will continue to run." Deployments may fail if service APIs change after support ends, and the notice points to Bedrock AgentCore as a native alternative — [GAAB GitHub](https://github.com/aws-solutions/generative-ai-application-builder-on-aws).
- **GAAB features** — [GAAB: Cost](https://docs.aws.amazon.com/solutions/latest/generative-ai-application-builder-on-aws/cost.html):
  - Text use cases with optional RAG use the "Amazon Bedrock Nova Pro model". There is a Bedrock Agent use case with Bedrock KB + Guardrails, an "MCP Server" use case on AgentCore Gateway, "Agent Builder" on AgentCore Runtime, and a "Workflow Builder" supervisor with Agent Builder agents.
  - "The solution does not manage or provision any resources related to Amazon Bedrock Knowledge Bases."
  - Note: the GitHub README summary did not list the AgentCore-based use cases, but the cost documentation does.
- **GAAB access control:** Cognito authenticates users; a Lambda authorizer issues IAM policies by Cognito group — [GAAB GitHub](https://github.com/aws-solutions/generative-ai-application-builder-on-aws). RBAC is supported only with Kendra (group names must match Kendra ACLs), and Bedrock KBs get static metadata filters per use case — [GAAB: Advanced knowledge base settings](https://docs.aws.amazon.com/solutions/latest/generative-ai-application-builder-on-aws/advanced-knowledge-base-settings.html).
- **bedrock-chat** — [aws-samples/bedrock-chat](https://github.com/aws-samples/bedrock-chat):
  - Not archived; "V3 released"; deployed with CDK (`npx cdk deploy --all`, or `bin.sh` via CodeBuild in about 35 minutes) and configured through `cdk.json` / `parameter.ts`.
  - Models include `amazon-nova-pro`, `amazon-nova-lite` and `amazon-nova-micro`.
  - Existing Bedrock KBs can be imported, and "multi-tenant mode, where a Knowledge Base with common settings is shared among multiple bots" is the default.
  - Groups: `Admin`, `CreatingBotAllowed` ("only allowed users are able to create customized bots"), `PublishAllowed` (publish a bot as a standalone API with its own WAF).
  - Bot store; Cognito with Google or custom OIDC; IP and country restrictions. Guardrails are not mentioned on the README.
- **aws-genai-llm-chatbot:** "This repository was archived by the owner on Sep 10, 2026. It is now read-only." — [aws-samples/aws-genai-llm-chatbot](https://github.com/aws-samples/aws-genai-llm-chatbot).
- **Q Business / Quick:** Q Business is closed to new customers with no new features. Customers using "anonymous access and API integration of Q Business into custom applications should contact AWS Support". Q Business guardrails are not carried over by Quick's bring-your-own-index (BYOI) feature — [Q Business availability change](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html).

### Inferences
- Adopting any of these would replace the project's custom UI and query path, which the project's notes rule out (single `retrieve_and_generate` call by design).
- The reusable ideas are:
  - GAAB's Cognito-group → policy authorizer;
  - bedrock-chat's group-gated features and shared-KB "multi-tenant mode";
  - the AVP blog's two-layer authorization.
- GAAB's retirement and the chatbot sample's archiving argue against building on either.

### Gaps
- Whether bedrock-chat can restrict a bot (and so its KB) to specific Cognito groups.
- bedrock-chat guardrail and KB-filter support.
- Whether GAAB supports multiple KBs per use case.

## 6. Guardrails across multiple KBs: one vs per-category guardrails, ApplyGuardrail for non-RAG paths, contextual grounding

### Takeaway
Keep one baseline guardrail, with an account- or organization-level enforced guardrail where possible. Add per-category guardrails by passing a different `guardrailId`/`guardrailVersion` per request; AWS's KB docs explicitly allow "multiple guardrails tailored to different use cases". Paths that do not call `RetrieveAndGenerate`, such as the planned count path, should call `ApplyGuardrail` on both input and output. Contextual grounding needs a grounding source, a query and the content to guard, within fixed size limits.

### Cited Findings
- **Guardrails on KB queries:** "You can create multiple guardrails tailored to different use cases and apply them across multiple request and response conditions". In `RetrieveAndGenerate` the guardrail goes in `generationConfiguration.guardrailConfiguration` (`guardrailId`, `guardrailVersion`) — [kb-test-config](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html).
- **Guardrails in Flows and agentic retrieval:**
  - Flows prompt nodes and KB nodes accept `guardrailConfiguration`; on KB nodes it applies only on the `RetrieveAndGenerate` path — [flows-nodes](https://docs.aws.amazon.com/bedrock/latest/userguide/flows-nodes.html).
  - `AgenticRetrieveStream` accepts `policyConfiguration.bedrockGuardrailConfiguration` — [AgenticRetrieveStream](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetrieveStream.html).
- **Contextual grounding** — [Bedrock User Guide: Use contextual grounding check](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html):
  - It checks **grounding** and **relevance**, with thresholds from 0 to 0.99, and needs a grounding source, a query and the content to guard.
  - Limits: "a maximum of 100,000 characters for grounding source, 1,000 characters for query, and 5,000 characters for response".
  - With `ApplyGuardrail`, mark blocks with the `grounding_source` / `query` / `guard_content` qualifiers. Blocks qualified only as `grounding_source` or `query` are skipped by the other policies unless also marked `guard_content`.
  - Classic tier supports English, French and Spanish. Standard tier handles conversational/reasoning content but "requires that your guardrail use cross-Region inference".
  - Streaming caveat: an irrelevant response may be flagged only after it has been streamed.
- **Enforced guardrails** combine as a union with the most restrictive control winning, and contextual grounding is supported under enforcement — [guardrails-enforcements](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-enforcements.html).
- **IAM for ApplyGuardrail:** authorized on the `guardrail` / `guardrail-profile` resources; the `Converse` operation also authorizes `ApplyGuardrail` — [service reference JSON](https://servicereference.us-east-1.amazonaws.com/v1/bedrock/bedrock.json).
- **Precedent:** AWS's Verified Permissions reference architecture uses guardrail checks that responses are grounded in the retrieved context — [AWS Architecture Blog, Jun 2026](https://aws.amazon.com/blogs/architecture/secure-multi-tenant-rag-with-amazon-bedrock-and-verified-permissions/).

### Inferences
- **Guardrail selection belongs in the registry.** For example, restricted categories could get a stricter PII or denied-topic guardrail while the public corpus keeps the current one. The org/account enforced guardrail then supplies a floor the app cannot bypass.
- **Count path:** its answers are code-generated templates, so grounding checks add little to the numeric parts. `ApplyGuardrail` with INPUT on the question and OUTPUT on the final answer is the essential part.
- **Data residency:** the Standard grounding tier's cross-Region inference requirement should be checked against CBP data-residency rules.

### Gaps
- Whether enforced guardrails also cover `RetrieveAndGenerate`'s internal invocations.
- `ApplyGuardrail` overall input-size quotas, beyond the grounding limits, were not fetched.

## 7. AWS guidance on aggregate/count questions over a document corpus (brief)

### Takeaway
AWS's native answer for aggregates is the structured-data KB (`GenerateQuery` / text-to-SQL with Redshift as the engine), which the project has already ruled out. The access-control principle still applies to any count path: counts must be computed only over documents the caller is allowed to see, using the same server-side group→category rule.

### Cited Findings
- **`GenerateQuery`** — [Bedrock User Guide: Generate a query for structured data](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-generate-query.html) (search summary; not fetched):
  - It takes `TEXT_TO_SQL` mode with a `KNOWLEDGE_BASE` type and uses Amazon Redshift as the query engine, over data in Redshift or the Glue Data Catalog (e.g., S3).
  - Quota of 2 requests per second.
  - Structured retrieval uses cross-Region inference, so prompts and outputs may leave the source Region.
  - The AWS ML Blog says the generated SQL can include joins and aggregation — [Build conversational interfaces for structured data using Amazon Bedrock Knowledge Bases](https://aws.amazon.com/blogs/machine-learning/build-conversational-interfaces-for-structured-data-using-amazon-bedrock-knowledge-bases/) (search summary; not fetched).
  - IAM: the `GenerateQuery` operation authorizes `GenerateQuery` + `GetKnowledgeBase` — [service reference JSON](https://servicereference.us-east-1.amazonaws.com/v1/bedrock/bedrock.json).
- **Retrieval caps:** a KB node returns at most 100 results (`numberOfResults` 1–100) — [KnowledgeBaseFlowNodeConfiguration](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_KnowledgeBaseFlowNodeConfiguration.html). AgentCore's Managed-KB `Retrieve` tool also caps `numberOfResults` at 1–100 — [AgentCore Gateway Managed KB target](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-managed-kb.html).
- **Agentic retrieval traces:** the `AgenticRetrieveStream` response schema includes a `codeExecution` trace action over documents. Its semantics are not described in the API reference — [AgenticRetrieveStream](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_AgenticRetrieveStream.html).
- **Authorization principle:** "Only scopes the user is authorized to will be passed to the LLM" — [AWS Security Blog, Sep 2025](https://aws.amazon.com/blogs/security/authorizing-access-to-data-with-rag-implementations).

### Inferences
- The planned catalog-based count path should filter catalog rows by the caller's allowed categories before filtering, ranking or checking. Otherwise a question such as "how many restricted messages mention X" leaks that restricted documents exist.

### Gaps
- No AWS guidance was found on Athena or SQL over a document-metadata catalog for RAG counts.
- The behavior of `codeExecution` in agentic retrieval is unverified.
