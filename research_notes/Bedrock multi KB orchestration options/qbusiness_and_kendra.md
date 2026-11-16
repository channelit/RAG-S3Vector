# Amazon Q Business and Amazon Kendra (GenAI Enterprise index) as permission-aware, multi-source Q&A options (state as of November 2026)

Research date: 2026-11-06. Sources are primary AWS docs or pages fetched on that date unless marked otherwise. "Inferences" are my reasoning, not AWS statements.

## Are Q Business and Kendra still available options? (status as of November 2026)

### Takeaway
Both services went into **Maintenance Mode on June 30, 2026** and **closed to new customers on July 30/31, 2026**. Existing customers still get bug fixes and security updates, but AWS is building no new features. AWS now points Kendra users to **Amazon Bedrock Managed Knowledge Base (BMKB)** and Q Business users to **Amazon Quick**. Unless this AWS account was already a customer before the cutoff, neither service can be adopted for a new build.

### Cited Findings
- AWS's "Service Availability Updates" post (dated **Jun 30, 2026**) lists Amazon Kendra, Amazon Q Business and Amazon Bedrock Agents (renamed "Amazon Bedrock Agents Classic") under **Maintenance**. They are "no longer available to new customers starting July 30, 2026". Customers already using them "can continue to do so", and AWS keeps operating and supporting them. The post names no replacement products. — [AWS What's New, Jun 30 2026](https://aws.amazon.com/about-aws/whats-new/2026/06/aws-service-availability/)
- Kendra: "put Amazon Kendra into Maintenance Mode, effective June 30, 2026 … no new feature or capability development … as of July 30, 2026, the service is no longer open to new customers". AWS "will continue to provide bug fixes and security updates for existing customers, however new feature requests will no longer be considered." — [Amazon Kendra availability change](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- Kendra's recommended successor: "migrate their Kendra applications and implement any new search applications on Amazon Bedrock Managed Knowledge Base (BMKB)". The page describes BMKB as a fully managed RAG service with built-in connectors, smart parsing, a managed hybrid-search vector store, RetrieveAndGenerate, and "multi-step reasoning across multiple knowledge bases (with an Agentic Retrieval API)". — [Kendra availability change](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- Q Business document history has two entries:
  - **June 30, 2026**: "will no longer be open to new customers starting on July 31, 2026. If you would like to use the service, please sign up prior to July 30."
  - **July 31, 2026**: "no longer open to new customers. For capabilities similar to Q Business, explore Amazon Quick."

  The two pages disagree slightly: the AWS-wide post says July 30, the Q Business doc history says July 31. — [Q Business document history](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/doc-history.html); [AWS What's New](https://aws.amazon.com/about-aws/whats-new/2026/06/aws-service-availability/)
- Q Business: "AWS will continue to provide bug fixes and security updates for existing customers, however new feature requests will no longer be considered." AWS recommends migrating to Amazon Quick, "the next evolution of Amazon Q Business". — [Q Business availability change](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html)
- "Customers who use anonymous access and API integration of Q Business into custom applications should contact AWS Support to discuss custom approaches for migrating these applications." — [Q Business availability change](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html)
- The Q Business FAQ still says "Quick Suite is the next evolution of Amazon Q Business" and "Existing Q Business customers can continue using their current service." — [Amazon Q Business FAQs](https://aws.amazon.com/q/business/faqs/)
- When fetched, the Q Business pricing page still listed prices and did not mention the closure. — [Amazon Q Business pricing](https://aws.amazon.com/q/business/pricing/)
- Neither availability page gives an end-of-support or shutdown date. — [Kendra availability change](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html); [Q Business availability change](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html)
- Every Q Business and Kendra doc page now carries a banner: "Amazon Q Business is no longer open to new customers…" or "Amazon Kendra is no longer open to new customers. For capabilities similar to Amazon Kendra, explore Amazon Bedrock Knowledge Bases." — [Kendra index types](https://docs.aws.amazon.com/kendra/latest/dg/hiw-index-types.html); [Q Business connector concepts](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/connector-concepts.html)

### Inferences
- For the CBP CSMS project, neither service is a realistic new foundation. If the account was not already a customer before July 30, 2026, it cannot sign up. Even if it was, building on a frozen service is a strategic risk, and AWS's own migration guides now route new work elsewhere: BMKB for Kendra, Quick for Q Business.
- Bedrock Agents (Classic) is in maintenance too. That matters for "multi-KB orchestration": AWS's stated replacement for multi-KB reasoning is BMKB's Agentic Retrieval API, not Agents.

### Gaps
- The docs don't define who counts as an "existing customer": the account, the payer account or the AWS Organization. They also don't say whether existing customers can still create new Q Business applications or Kendra indexes, or whether they can do so in new accounts.
- No shutdown or end-of-support date has been published.

## Q Business document-level access control and identity: how ACLs are ingested, how users are identified, group sync, and query-time enforcement

### Takeaway
Q Business is the only one of the three services (Q Business, Kendra, BMKB) where the service itself binds ACL filtering to an authenticated identity, using IAM Identity Center trusted identity propagation. **How ACLs are ingested:**
- Connectors crawl ACLs and identities into a "User Store".
- For S3, a single prefix-level ACL JSON file supplies them.
- **S3 defaults to open:** any prefix not listed in the ACL file is visible to all users.

**What it costs:**
- An identity provider wired into IAM Identity Center (or IAM federation).
- A per-user subscription.
- A sizeable token-exchange flow in the backend for any custom UI.

### Cited Findings
- **How connectors ingest ACLs.** Q Business connectors index the ACL attached to each document: the user's email address, local group names, and federated group names (for example SharePoint with Entra ID). This is stored in the Q Business User Store "to create user and group mappings and filter chat responses based on the end user's access to documents". ACL changes are picked up on each crawl ("re-sync your data source regularly"). — [Q Business connector concepts](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/connector-concepts.html)
- **ACL crawling is on by default and can't be undone.** "Amazon Q Business supports crawling ACLs for document security by default… Once you turn ACL and identity crawling on you won't be able to turn them off." Creating a data source with ACLs disabled requires specific IAM permissions. To index documents as public, they must already be public in the source system. — [Q Business connector concepts](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/connector-concepts.html)
- **Identity crawler.** It stores each source's principals (local user alias, local group, federated group) in the User Store. Q Business "internally maps the local user and group IDs attached to the document to the federated identities of users and groups". AWS frames this as "useful when your application environment is connected to multiple data sources with different authorization and authentication systems, but you want to create a unified, access-controlled chat experience". — [Q Business connector concepts](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/connector-concepts.html)
- **User Store risks.**
  - AWS says the User Store APIs (create/update/delete users and groups, mappings) should be treated as privileged operations, because "inadvertent mistakes … can result in unintentional and unacceptable changes in the accessibility of documents".
  - Reusing an email address for a new user requires deleting the old user first. Otherwise, if an older user has the same email but different IAM Identity Center attributes, that user's query calls "will be denied".

  — [Q Business connector concepts](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/connector-concepts.html)
- **S3 ACL format.**
  - The ACL configuration file is set in the console or as `aclConfigurationFilePath` in the `configuration` of `CreateDataSource`/`UpdateDataSource`, and it must live in the same bucket as the data.
  - Each entry has a `keyPrefix` (a path or a single file) and `aclEntries`. Each ACL entry has a `Name` (email or group), a `Type` (`USER` or `GROUP`) and an `Access` (`ALLOW` or `DENY`).
  - "**The system grants ALL users access to prefixes that do NOT appear in the ACL file.**"

  — [How the Q Business connector crawls Amazon S3 ACLs](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/s3-user-management.html)
- **Comparison with Quick (from AWS's migration guide):**
  - Q Business grants all users access to S3 prefixes not in the ACL file.
  - Quick "does not ingest documents that lack an associated ACL entry".
  - Quick supports both a global ACL file and per-document metadata ACL files, for S3, Confluence Cloud, SharePoint and Google Drive.
  - Quick ACLs must be enabled when the knowledge base is created, and the setting is permanent.

  — [Q Business availability change / migration guide](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html)
- **Identity options, with dates:**
  - IAM Identity Center integration (Apr 16, 2024).
  - IAM Federation (Aug 22, 2024).
  - Cross-region IAM Identity Center (Jul 25, 2024).
  - Anonymous access application environments (Apr 29, 2025).
  - Amazon Quick (QuickSight)-integrated application environments (Dec 3, 2024).

  — [Q Business document history](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/doc-history.html)
- The FAQ says users can connect "using either AWS IAM Identity Center or Identity Federation through IAM", with external SAML 2.0 identity providers such as Okta, Azure AD or Ping. — [Q Business FAQs](https://aws.amazon.com/q/business/faqs/)
- The identity types named in the migration guide are `AWS_IAM_IDC` and `AWS_QUICKSIGHT_IDP`. — [Q Business availability change](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html)
- **Query-time enforcement for custom apps.** "During data ingestion, Amazon Q Business preserves the authorization information—access control lists (ACLs)—from the data source so users can only request answers from the data they already have access to. Through IAM Identity Center, Amazon Q Business uses trusted identity propagation to ensure that an end user is authenticated…" Chat, ChatSync, SearchRelevantContent, ListConversations, ListMessages, DeleteConversation and PutFeedback "require identity-aware AWS Sig V4 credentials for the authenticated user". — [Making authenticated Q Business API calls using IAM Identity Center](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/making-sigv4-authenticated-api-calls.html)
- **With a Kendra index as the retriever, filtering is by email.** Q Business "uses user email ID to determine end user access to documents in an index… relays the user's identifying email ID to Amazon Kendra". If the Kendra data sources don't use email-based filtering, or the email is absent, Q Business answers only from public documents. — [Creating an index for a Q Business application](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/select-retriever.html); [Kendra index types](https://docs.aws.amazon.com/kendra/latest/dg/hiw-index-types.html)
- The FAQ says Q Business answers only from content the user is permitted to see, based on ACL permissions. — [Q Business FAQs](https://aws.amazon.com/q/business/faqs/)

### Inferences
- Q Business binds the ACL check to an authenticated identity. Kendra and BMKB instead trust whatever user ID the application passes (see the Kendra and comparison sections). That is a real security property in Q Business's favour.
- The CSMS UI today has no user login, only an ALTCHA captcha. Using Q Business ACLs would mean adding an identity provider, IAM Identity Center (or IAM federation), and a per-user subscription for every viewer.
- The S3 default-open behaviour is dangerous for a mixed-permission bucket. A restricted prefix missing from the ACL file would be visible to everyone. BMKB and Quick both fail closed instead.
- For the project's S3 + sidecar layout, restricted categories would need prefix-level entries in one ACL file per data source. AWS documents no per-object `_acl` sidecar for Q Business S3, unlike Kendra and Quick.

### Gaps
- I found no Q Business doc for per-document ACLs inside S3 `.metadata.json` sidecars, so per-object ACLs may not exist for the Q Business S3 connector. Kendra (`AccessControlList` in the metadata file) and Quick (document-level metadata ACL files) both document it.
- The S3 page doesn't say how group names in the S3 ACL file are resolved to users. It is presumably done through User Store group APIs or IAM Identity Center groups, but I did not verify this.
- I did not fetch the IAM-federation custom-app call flow (`create-application-iam`). It is unconfirmed how a custom backend passes the user's identity (email principal tag, etc.) for IAM-federated apps.
- The ChatSync API reference still lists `userId` and `userGroups` URI parameters with no deprecation note, while the IAM Identity Center docs require identity-aware credentials. Whether those parameters are honoured, ignored, or limited to some identity types is undocumented in what I read. — [ChatSync API](https://docs.aws.amazon.com/amazonq/latest/api-reference/API_ChatSync.html)

## Q Business connectors and indexes: native index vs Kendra retriever, multiple data sources, document attributes, and attribute filters (date ranges) at query time

### Takeaway
An application uses either a **native Q Business index** (Starter or Enterprise, sized in 20k-document units) or an **existing Kendra index as its retriever**. Choosing Kendra disables Q Business's own connectors and direct upload. An application can attach up to 50 data sources. Up to 50 document attributes can be mapped, including DATE and Number types, and a per-request `attributeFilter` on Chat/ChatSync supports range operators. A date-range filter like the project's `date_numeric` is therefore expressible, but only through the API.

### Cited Findings
- There are two index/retriever options:
  - The "Amazon Q Business native index and retriever".
  - An "Amazon Kendra index and retriever", for existing Kendra customers only: "The option to create an Amazon Kendra index is visible on the console only if you're already an Amazon Kendra user."
  - "If you use an Amazon Kendra index, you can't use Amazon Q Business data connectors or direct document upload for your application environment."

  — [Creating an index for a Q Business application](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/select-retriever.html)
- **Native index sizing.**
  - Enterprise: up to 50 units, deployed across three Availability Zones, for production.
  - Starter: up to 5 units, a single Availability Zone, for proofs of concept.
  - Each unit holds "20,000 documents or 200 MB, whichever is reached first".

  — [Creating an index for a Q Business application](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/select-retriever.html); [Q Business pricing](https://aws.amazon.com/q/business/pricing/)
- Q Business has supported Kendra GenAI Enterprise Edition indices since **Dec 4, 2024**. A Kendra GenAI index attached to Q Business can later be detached and reused with Bedrock. — [Q Business document history](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/doc-history.html); [Creating an index](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/select-retriever.html)
- **Quotas, none adjustable:** 50 applications per account, 50 data sources per application, 10 data accessors per application, 25 plugins per application, 20 actions per plugin. — [Q Business endpoints and quotas](https://docs.aws.amazon.com/general/latest/gr/amazonq.html)
- **Sync options.**
  - Sync modes: full, new/modified, new/modified/deleted, and change log.
  - Schedules: on demand, hourly, daily, weekly, monthly, or cron.
  - A "document deletion safeguard" percentage.
  - Credentials are held in Secrets Manager, with VPC and HTTPS web-proxy support.
  - All fields and attributes are capped at 2048 characters and truncated beyond that.

  — [Q Business connector concepts](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/connector-concepts.html)
- **Document attributes.**
  - Reserved attributes include `_created_at` and `_last_updated_at` (ISO 8601), `_source_uri`, `_data_source_id`, `_document_title`, `_category`, `_file_type`, `_authors` and `_data_source_type`. Custom attributes are also allowed.
  - "You can create and map up to 50 document attributes to index fields. Once created, you can't delete or rename any attributes."
  - Up to 30 fields can be marked searchable.
  - The data types are Date, Number, String and String list; all are searchable, filterable and boostable.
  - An index field's type can't be changed after creation.

  — [Document attributes in Q Business](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/doc-attributes.html)
- **Attribute filters at chat time.** "Filtering using document attributes in chat is only supported through the API." AWS's stated uses include restricting responses to authoritative sources, to file types or collections, and "to come from only documents that were generated after a specific date". — [Filtering chat responses using document attributes](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/metadata-filtering.html); [Document attributes](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/doc-attributes.html)
- ChatSync's `attributeFilter` supports `andAllFilters`, `orAllFilters`, `notFilter`, `equalsTo`, `containsAll`, `containsAny`, `greaterThan`, `greaterThanOrEquals`, `lessThan` and `lessThanOrEquals`. It "enables filtering of Amazon Q Business web experience responses based on document attributes or metadata fields." — [ChatSync API](https://docs.aws.amazon.com/amazonq/latest/api-reference/API_ChatSync.html)
- **2025 changes:**
  - Relevancy tuning (by created/modified date or storage location) replaced metadata boosting on new applications (Jul 1, 2025).
  - Agentic RAG was added (Aug 14, 2025).
  - "Clickable S3 links" in citations were added (Jul 22, 2025).

  — [Q Business document history](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/doc-history.html)

### Inferences
- The project's per-request date range could map to a custom DATE (or Number) attribute filtered with `greaterThanOrEquals`/`lessThanOrEquals` in ChatSync. That is a single enforcement point, as it is today.
- Attributes can never be deleted or renamed, so the schema must be designed up front.
- Rough sizing, from CLAUDE.md's figure of 30k+ CSMS messages since 2011 and 20k documents per unit: about 2–3 Enterprise units, more if attachments count as separate documents or the 200 MB text cap is hit first.

### Gaps
- The docs I read don't say whether one application can hold more than one index. Every page describes a single index or retriever per application.
- I did not verify how S3 sidecar metadata is shaped for Q Business (the metadata JSON schema for custom attributes, and the date format inside it).

## Which LLM does Q Business use, can the customer choose (e.g., Amazon Nova), and how do its guardrails compare with Bedrock Guardrails?

### Takeaway
Customers **cannot choose the model**. AWS says it uses "various foundation models from Amazon Bedrock", unnamed, so a "Nova-only" policy cannot be guaranteed. Q Business has its own admin controls instead of Bedrock Guardrails:
- response scope
- blocked phrases (up to 20)
- topic-level rules, optionally scoped to users and groups
- hallucination mitigation

None of the pages I read documents PII redaction, content-category filters, prompt-attack filters, or a way to attach a Bedrock Guardrail.

### Cited Findings
- The FAQ answers the model-choice question: "No, however, AWS uses various foundation models from Amazon Bedrock within Amazon Q Business." — [Q Business FAQs](https://aws.amazon.com/q/business/faqs/)
- Cross-region inference (Nov 19, 2024): Q Business "can now select the optimal region within your geography to process your inference request". — [Q Business document history](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/doc-history.html)
- **Global controls.**
  - Response settings:
    - let end users send queries directly to the LLM (enabled by default on new apps since Oct 31, 2024)
    - fall back to LLM knowledge
    - personalize responses from IAM Identity Center user attributes
    - hallucination mitigation
  - Chat orchestration across plugins.
  - Feature settings: file upload and Q Apps.
  - **Blocked phrases: "You can choose up to 20 words"**, with an optional custom message.
  - Controls can't be created or deleted, only updated, through `UpdateChatControlsConfiguration`, where `--response-scope` is `ENTERPRISE_CONTENT_ONLY | EXTENDED_KNOWLEDGE_ENABLED`.

  — [Using global controls in Q Business](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/guardrails-global-controls.html)
- Hallucination mitigation only works for RAG responses from text, can't be combined with chat orchestration, "will increase chat response latency", and was added Apr 10, 2025. — [Global controls](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/guardrails-global-controls.html); [Document history](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/doc-history.html)
- The FAQ: "Administrators can configure allowed and blocked topics as well as words." Admins can also restrict answers to enterprise documents and turn file uploads on or off. — [Q Business FAQs](https://aws.amazon.com/q/business/faqs/)
- In anonymous applications, "Topic rules using users and groups are not supported", and admin controls and guardrails "are read-only … except for blocked words". — [Anonymous access application environments](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/create-anonymous-application.html)
- Q Business chat guardrails (global and topic controls) and Actions are excluded from Quick's Bring Your Own Index (BYOI) migration and "will not transfer to Quick". — [Q Business availability change](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html)
- For contrast, BMKB lets the customer "choose the foundation model for response generation". — [Kendra availability change](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- For contrast, Bedrock's KB `Retrieve` request accepts a `guardrailConfiguration` (`guardrailId`, `guardrailVersion`) and returns `guardrailAction`. — [Bedrock Retrieve API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Retrieve.html)

### Inferences
- Q Business conflicts with a Nova-only policy: the model is AWS-chosen, unnamed, and may change.
- The project's Bedrock Guardrail can't be reused in Q Business, including its all-PII block (with NAME), its politics and impoliteness topics, and its fixed "Sorry…" message. Topic rules and up to 20 blocked words are a weaker, different control set. Bedrock-style PII masking would require custom pre- and post-processing, which defeats the point of a managed service.

### Gaps
- No AWS page I found names the models Q Business uses or confirms whether Amazon Nova is among them.
- I did not fetch the topic-specific controls page, so its limits (number of topics, example messages) and exact behaviour are unverified.
- Whether Q Business exposes any PII or content-safety filter beyond topics and words is unconfirmed. The global controls page lists none.

## Custom UI: calling Q Business APIs with per-user identity, anonymous access, citations, pricing tiers, and 2025–2026 pricing changes

### Takeaway
A custom frontend can call Chat, ChatSync and SearchRelevantContent with ACL-enforced per-user identity. The backend must run an OIDC → IAM Identity Center `CreateTokenWithIAM` → STS `AssumeRole` (with `ProvidedContexts`) exchange for every user; the SDK plugin that automates this is Java and JavaScript only. An **anonymous** mode (since Apr 29, 2025) allows unauthenticated Chat and ChatSync, but **forbids ACLs** and cannot share an application with authenticated users. Responses include structured citations.

**Pricing:**
- Lite: $3/user/month.
- Pro: $20/user/month.
- Index: $0.140 (Starter) or $0.264 (Enterprise) per unit-hour.
- Anonymous usage: 2 units per ChatSync call, sold in bundles of 30,000 units for $200.

I found no 2025–2026 price changes.

### Cited Findings
- **Identity-aware API flow.** These steps happen once:
  - an OIDC app in the identity provider
  - an IAM Identity Center trusted token issuer
  - a customer-managed IAM Identity Center application with a JWT-bearer grant
  - an IAM authentication method
  - the access scope `qbusiness:conversations:access`
  - an IAM role trusting `qbusiness.amazonaws.com` for `sts:AssumeRole` and `sts:SetContext`
  - `create-subscription` per user or group

  Then for each user:
  1. `CreateTokenWithIAM` with the user's identity provider ID token.
  2. `AssumeRole` with `ProvidedContexts=[{ProviderArn: arn:aws:iam::aws:contextProvider/IdentityCenter, ContextAssertion: <sts:identity_context claim>}]`.
  3. Call ChatSync with those credentials.

  The recommended "TIP plugin" workflow "is currently supported by the Java and JavaScript SDK". — [Making authenticated Q Business API calls using IAM Identity Center](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/making-sigv4-authenticated-api-calls.html)
- **Anonymous mode.** It is created with `--identity-type ANONYMOUS`. Its limits:
  - Only `Chat`, `ChatSync` and `PutFeedback` are supported, so not SearchRelevantContent and not GetDocumentContent.
  - No chat history, plugins, Q Apps or attachments, and no integrations or the Quick integration.
  - "Anonymous users and authenticated users are not supported on the same application environments."
  - "You must only ingest publicly available data sources without access control lists (ACLs)", such as Web Crawler data or S3 data without Q Business ACLs.
  - The hosted web experience is "only available for preview and testing purposes unless used within the context of an Amazon Q embedded implementation".

  — [Anonymous access application environments](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/create-anonymous-application.html)
- **ChatSync request.**
  - `userMessage`
  - `attributeFilter`
  - `chatMode`: `RETRIEVAL_MODE` (data-source-only answers, "No Answer Found" unless LLM knowledge is enabled), `CREATOR_MODE` (LLM-only or attached files) or `PLUGIN_MODE`
  - `attachments`: up to 5 files of up to 10 MB each
  - `conversationId` and `parentMessageId` for multi-turn chat

  — [ChatSync API](https://docs.aws.amazon.com/amazonq/latest/api-reference/API_ChatSync.html)
- **ChatSync citations.**
  - The response has `systemMessage` and a `sourceAttributions[]` array.
  - Each attribution carries `citationNumber`, `title`, `url`, `snippet`, `updatedAt`, `documentId`, `datasourceId`, `indexId`, and `textMessageSegments[]` (`beginOffset`, `endOffset`, `snippetExcerpt`, `sourceDetails`).
  - The API documents a `systemMessage` "Maximum length of 2048".

  — [ChatSync API](https://docs.aws.amazon.com/amazonq/latest/api-reference/API_ChatSync.html)
- **Subscriptions.**
  - **Lite $3/user/month**: permission-aware Q&A with responses up to about one page.
  - **Pro $20/user/month**: responses up to about seven pages, content creation, Q Apps, custom and managed plugins, Slack/Outlook/Word/Teams integrations, and Amazon Q in QuickSight (Reader Pro).

  — [Q Business pricing](https://aws.amazon.com/q/business/pricing/)
- **Index and media pricing.**
  - Starter index: **$0.140** per unit-hour, at most 5 units per application, one Availability Zone.
  - Enterprise index: **$0.264** per unit-hour, three Availability Zones.
  - Each unit includes 100 connector-hours per month and 20k documents or 200 MB.
  - Media: $0.003 per image, $0.006 per audio minute, $0.050 per video minute.

  — [Q Business pricing](https://aws.amazon.com/q/business/pricing/)
- **Anonymous pricing.** "Each ChatSync API call or embedded-chat prompt uses 2 units". Bundles are 30,000 units for $200; unused units don't roll over, and a new bundle is bought automatically when units run out. There is no free trial for anonymous API use. — [Q Business pricing](https://aws.amazon.com/q/business/pricing/)
- **Free trial:** 60 days for up to 50 Pro or Lite users per application, plus 1,500 index-hours. — [Q Business pricing](https://aws.amazon.com/q/business/pricing/)
- In the Quick migration, subscriptions are de-duplicated across Q Business applications that share an IAM Identity Center instance, so each user is charged once at their highest tier. — [Q Business availability change](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html)
- Amazon Q embedded (embedding the assistant in trusted websites) was added Oct 15, 2024. — [Q Business document history](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/doc-history.html)

### Inferences
- **Cost arithmetic** (730 h/month):
  - One Enterprise unit ≈ **$193/month**; one Starter unit ≈ $102/month.
  - Anonymous chat ≈ **$0.0133 per ChatSync call** ($200 ÷ 15,000 calls), or about $13 per 1,000 questions.
  - 50 Pro users ≈ $1,000/month; 500 Lite users ≈ $1,500/month.
- The CSMS backend is FastAPI (Python), and the TIP plugin is Java/JavaScript only. It would therefore have to implement the manual `CreateTokenWithIAM` + `AssumeRole` exchange.
- A mix of public CSMS content and restricted categories would need two Q Business applications: an anonymous one for public data and an IAM Identity Center one for restricted data. Anonymous mode forbids ACLs and can't share an application with authenticated users. That breaks the "one assistant" experience.
- Citations map naturally to the existing `{label, url}` sources shape (`title`, `url`). AWS's migration guidance gives no path for API-integrated custom UIs; it says to contact Support.
- The 2048-character `systemMessage` limit in the API reference seems to contradict the pricing page's "up to ~7 pages" for Pro. The two sources do not resolve this.

### Gaps
- I found no AWS record of Q Business price changes in 2025–2026. The pricing page shows no effective dates, and the anonymous consumption pricing presumably arrived with the Apr 2025 feature.
- Third-party blogs claim Quick Professional/Enterprise tiers carry a $250/account/month infrastructure fee. That is unverified against AWS, from [insearch.ai](https://insearch.ai/blog/amazon-q-business-vs-amazon-quick-suite), and out of scope.
- I did not verify the SearchRelevantContent request/response schema, for example whether it accepts `attributeFilter` or returns scores.

## Q Business Q Apps, plugins and actions: config-driven extensibility

### Takeaway
Q Business offered no-code Q Apps and built-in, custom and managed plugins, with automatic chat orchestration. These are now frozen under maintenance. They are excluded from the Quick BYOI migration, and Q Apps must be rebuilt as Quick Flows. None of them is relevant to the CSMS RAG need, and none is a durable investment.

### Cited Findings
- **Timeline:**
  - Q Apps preview Apr 30, 2024; GA Jul 10, 2024.
  - Custom plugins Apr 30, 2024.
  - Updated plugins experience and Quick (QuickSight) plugin for structured data Dec 3, 2024.
  - Q Apps support for all plugins Dec 3, 2024.
  - Data-collection Q Apps Nov 26, 2024.
  - Chat orchestration controls Feb 4, 2025.

  — [Q Business document history](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/doc-history.html)
- **Chat orchestration** "automatically routes chat requests to plugins, integrating enterprise data and relevant actions within a single chat response". It detects read-only requests ("like checking ticket counts") and write actions, and it is optimized for English. — [Global controls](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/guardrails-global-controls.html)
- Q Apps and custom/managed plugins come with the **Pro** subscription only. — [Q Business pricing](https://aws.amazon.com/q/business/pricing/)
- Limits: 25 plugins per application and 20 actions per plugin, not adjustable. The Europe (Ireland) and Asia Pacific (Sydney) regions lack Q Apps, Q Actions and audio/video. — [Q Business endpoints and quotas](https://docs.aws.amazon.com/general/latest/gr/amazonq.html)
- **Migration to Quick:**
  - "Q Apps, Actions, and Amazon Q Business chat guardrails are not included in the BYOI capability."
  - Q Apps "must be migrated to Quick Flows".
  - "Some Q App features like forms are not yet available in Quick Flows."
  - Connectors without a native Quick equivalent go through MCP: actions only, not knowledge-base indexing, with a 60-second timeout.

  — [Q Business availability change](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html)
- Anonymous applications support neither plugins nor Q Apps. — [Anonymous access application environments](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/create-anonymous-application.html)

### Inferences
- These configuration-first extensibility features are real, but they are tied to the Q Business web experience and Pro seats, and they are in maintenance. They don't reduce custom code for a custom FastAPI/React RAG UI.

### Gaps
- I did not verify the custom-plugin definition format (for example an OpenAPI schema) or the auth options.

## Kendra GenAI Enterprise index: document-level ACLs, user context filtering, use as a Bedrock Knowledge Base, connectors, cost, regions

### Takeaway
The Kendra GenAI Enterprise index is the "highest accuracy" Kendra index, built on hybrid search and a re-ranker, and it can be reused by Q Business and by Bedrock KBs. Its limits:
- Its access control is reduced: attribute-based user filtering only, with no token or `UserContext` UserId/Groups, and `CreateAccessControlConfiguration` disabled.
- It runs only in us-east-1 and us-west-2, and only on English content.
- Kendra doesn't authenticate the caller's identity.

AWS's Bedrock docs say nothing about ACLs when the GenAI index sits behind a Bedrock KB. Bedrock's new `userContext` is documented only for **managed** KBs, and Bedrock now recommends BMKB over Kendra-GenAI KBs. Kendra is also closed to new customers.

### Cited Findings
- **Capabilities.** The index offers "the highest accuracy for the Retrieve API operation and for Retrieval Augmented Generation (RAG) use cases", using hybrid search (keyword and vector), semantic embedding and re-ranker models. It can be used "in an Amazon Bedrock knowledge base as a managed retriever" and "with Amazon Q Business". It has "smaller, more granular capacity units and a lower starting price". — [Kendra index types](https://docs.aws.amazon.com/kendra/latest/dg/hiw-index-types.html)
- **Feature support with Retrieve:** full support for confidence buckets, filtering, faceting, relevance tuning, custom document enrichment, custom metadata and capacity adjustment. Data source connectors and user context filtering are only **partially** supported. — [Kendra index types](https://docs.aws.amazon.com/kendra/latest/dg/hiw-index-types.html)
- **GenAI index limitations:**
  - "only available in US East (N. Virginia) and US West (Oregon)".
  - "only support English language content".
  - "support only v2.0 Amazon Kendra data source connectors".
  - "you can only use user attributes to filter search results by user context".
  - It doesn't support "token-based user access control or user ID and group–based user access control".
  - "The CreateAccessControlConfiguration API operation is disabled".

  — [Kendra index types](https://docs.aws.amazon.com/kendra/latest/dg/hiw-index-types.html)
- **Query API on GenAI indices.** "you can only use `ATTRIBUTE_FILTER` to filter search results by user context"; `USER_TOKEN` returns a `ValidationException`. `AttributeFilter` should be used "to enable document filtering for end users using `_email_id` or include public documents (`_email_id=null`)". — [Kendra Query API](https://docs.aws.amazon.com/kendra/latest/APIReference/API_Query.html)
- **User-attribute filtering in general.** The user-context page describes filtering on the built-in `_user_id` and `_group_id(s)` attributes in `AttributeFilter`, with up to 100 group IDs. Documents without an ACL are public.
  - "User context filtering isn't an authentication or authorization control for your content. It doesn't do user authentication on the user and groups sent to the Query API. It is up to your application to ensure that the user and group information … is authenticated and authorized."
  - S3 sources take a per-document `AccessControlList` in the `.metadata.json` file (up to 200 entries), or a JSON ACL file.
  - Group membership can be mapped with `PutPrincipalMapping`, or resolved from IAM Identity Center through `UserGroupResolutionConfiguration`.

  — [Kendra: Filtering on user context](https://docs.aws.amazon.com/kendra/latest/dg/user-context-filter.html)
- The Query API names the attribute `_email_id`, while the user-context page names `_user_id` and `_group_ids`. The docs don't reconcile the two. — [Kendra Query API](https://docs.aws.amazon.com/kendra/latest/APIReference/API_Query.html); [User context filter](https://docs.aws.amazon.com/kendra/latest/dg/user-context-filter.html)
- **Bedrock KB backed by a Kendra GenAI index:**
  - The Bedrock page now opens with: "For optimized retrieval accuracy and a managed experience, we recommend Amazon Bedrock Managed Knowledge Base."
  - The listed benefits are reusing indexed content across Bedrock apps without re-ingesting, and Bedrock tooling on top of Kendra retrieval.
  - Neither the overview nor the create page mentions ACLs, user context, or identity pass-through.
  - Data sources "can't [be created] using Amazon Bedrock API operations": they must be created in the Bedrock console or with Kendra's `CreateDataSource`.

  — [Build a Bedrock KB with a Kendra GenAI index](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-build-kendra-genai-index.html); [Create a Bedrock KB with a Kendra GenAI index](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-kendra-genai-index-create.html)
- **Bedrock `Retrieve` now has a `userContext` field** (`userId` only), "used for access control filtering to ensure that retrieval results only include documents the user is authorized to access". The results can include a `kendraDocumentLocation`. — [Bedrock Retrieve API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Retrieve.html); [UserContext type](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_UserContext.html)
- **That `userContext` is documented for managed KBs only.** It is described under "ACL-aware retrieval on **managed** knowledge bases":
  - `userId` "is always the user's universal email address associated with the underlying data source".
  - Without `userContext`, ACL-enabled sources return zero results.
  - Documents with missing ACLs are "not returned to any user".
  - Deny overrides allow.
  - No backfill when real-time verification drops results.
  - Identity-provider credentials are cached for up to 1 hour.
  - It "provides ACL-aware filtering, not authorization… does not authenticate end users".
  - Connectors with ACL guidance: SharePoint, OneDrive, Google Drive, Confluence, Salesforce, Amazon S3 and Custom.

  — [ACL-aware retrieval on managed knowledge bases](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-acl.html)
- **Pricing for GenAI Enterprise Edition:**
  - Base index: **$0.32/hour**, including 1 storage unit (20k documents or 200 MB) and 1 query unit (0.1 QPS, about 8,000 queries/day).
  - Extra storage unit: $0.25/hour. Extra query unit: $0.07/hour.
  - Connectors: **$30 per index per month**, including up to 500 sync-hours.
  - Free tier: 750 hours in the first 30 days.
  - For comparison, Enterprise Edition is $1.40/hour base and Developer Edition $1.125/hour.

  — [Amazon Kendra pricing](https://aws.amazon.com/kendra/pricing/)
- **Connector counts:** Kendra has "32+ connectors", BMKB 7 (S3, Confluence, SharePoint, Web Crawler, Google Drive, OneDrive, Custom). Both cap Retrieve at 100 results. — [Kendra availability change / migration guide](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- **Features BMKB lacks:** query suggestions, faceted search, custom synonyms, spell checking, incremental learning and Lambda-based document enrichment. BMKB also doesn't support the `startsWith` or `stringContains` filters. — [Kendra availability change](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)

### Inferences
- With a Kendra GenAI index, per-user filtering is an application-supplied attribute filter (`_email_id`, or `_user_id`/`_group_ids`), not an authenticated check. In that respect it is no stronger than BMKB's `userContext`, and weaker than Q Business's IAM Identity Center binding.
- Behind a Bedrock KB there is no documented way to pass that filter or identity. The Bedrock pages are silent, and `userContext` is documented for managed KBs. I would not assume Kendra ACLs are enforced through Bedrock `Retrieve`/`RetrieveAndGenerate` on a Kendra-GenAI KB.
- **Monthly cost:** base ≈ $233.60 plus $30 connectors ≈ **$264 per index-month** at minimum capacity (730 h). That is a fixed floor regardless of query volume.
- The GenAI index exists only in us-east-1 and us-west-2, so it has no GovCloud option.

### Gaps
- No AWS doc confirms or denies whether Bedrock `Retrieve`/`RetrieveAndGenerate` on a **Kendra-GenAI-backed** KB honours `userContext` or Kendra ACLs.
- It is also undocumented whether a Bedrock `vectorSearchConfiguration.filter` on such a KB is passed through to Kendra's `AttributeFilter` (for example on `_email_id`).
- I did not verify whether `RetrieveAndGenerate` (as opposed to `Retrieve`) accepts `userContext` for managed KBs.

## Is there AWS guidance comparing Q Business vs Bedrock Knowledge Bases for custom RAG apps with permissions?

### Takeaway
I found no neutral AWS comparison page. The de facto AWS guidance as of 2026 is the pair of migration guides:
- Kendra → BMKB, including "access control workarounds" and connector gaps.
- Q Business → Amazon Quick, which has no documented path for API-integrated custom UIs ("contact AWS Support").

Bedrock's own Kendra-GenAI page also points to BMKB. For a custom UI that prefers configuration over code, AWS's current direction is Bedrock KBs, specifically BMKB with ACL-aware connectors, not Q Business or Kendra.

### Cited Findings
- Kendra's migration guide maps Kendra APIs to BMKB:
  - Kendra `retrieve` maps to `bedrock-agent-runtime.retrieve`, and `AttributeFilter` maps to `filter`.
  - `BatchPutDocument` is "Not directly supported (use S3 upload + ingestion)".
  - Before cutover, verify that "access control workarounds correctly restrict unauthorized access".
  - BMKB metadata sidecars are capped at **10 KB**, with STRING, NUMBER and BOOLEAN types.
  - Unsupported sources should be exported to S3 with metadata sidecars on a schedule.

  — [Kendra availability change / migration guide](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- **BMKB as described in the same guide:**
  - Embeddings: Titan Text v2, Cohere v3/v4 and Nova Multimodal Embeddings, all at 1024 dimensions.
  - Hybrid search always.
  - Chunking: default, fixed, hierarchical or none, with no semantic chunking.
  - The examples call `retrieve_and_generate` against a managed KB with `managedSearchConfiguration`.

  — [Kendra availability change](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- In a non-IAM-Identity-Center Quick migration, "all Amazon Quick users automatically receive access to connected Q Business indexes", and "you lose the per-user and per-group access distinctions that Q Business enforced". The workaround is to split content into separate knowledge bases per access level and share them through Spaces. BYOI allows "a maximum of two Amazon Q Business indexes per region", and that quota "cannot be increased". — [Q Business availability change](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/qbusiness-availability-change.html)
- Bedrock now says of Kendra-GenAI KBs: "we recommend Amazon Bedrock Managed Knowledge Base". — [Build a Bedrock KB with a Kendra GenAI index](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-build-kendra-genai-index.html)
- **Conflict with project notes.** CLAUDE.md records that RetrieveAndGenerate "is rejected by managed KBs ('not supported for managed knowledge bases')". AWS's Kendra migration guide shows `retrieve_and_generate` working with BMKB and lists "Native RetrieveAndGenerate API". The ACL-aware retrieval page documents `userContext` only on `Retrieve`. — [Kendra availability change](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html); [ACL-aware retrieval](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve-acl.html)

### Inferences
- On "multi-source + permissions", Q Business had the most complete package: ACL-crawling connectors (up to 50 data sources per app), a User Store unifying identities across sources, and authenticated enforcement. It required IAM Identity Center or federation and per-seat pricing, allowed no model choice, used its own guardrails, and is now closed.
- Kendra GenAI had many connectors, but its ACL support was reduced, it is English-only in two regions, and it is also closed.
- For this project, the live options for "permissions per user group with config over code" are now:
  - **BMKB with ACL-aware connectors and `Retrieve` `userContext`.** The app must authenticate users; S3 ACL files are supported; it fails closed.
  - **Separate standard KBs per access tier**, with the app choosing which KBs a user may query. That is close to Quick's own "segment content into separate knowledge bases" workaround.
- The contradiction between CLAUDE.md and AWS docs about RetrieveAndGenerate on managed KBs should be re-tested.

### Gaps
- I did not search for older (2024–2025) AWS decision guides or blogs comparing Q Business with Bedrock KBs, such as "Choosing a generative AI service". Any such guidance predates the 2026 maintenance announcement.
- I did not fetch the Q Business supported-connectors list, so how many native connectors it has, and which crawl ACLs, is unverified. Kendra's "32+" and BMKB's "7" are sourced above.

## Can either service answer count or aggregate questions ("how many messages about X")?

### Takeaway
**Q Business: no.** It is RAG chat over retrieved passages, and I found no documented aggregate or count feature for documents. Counting is possible only through plugins on structured systems or the Quick (QuickSight) plugin. **Kendra: partially, natively.** The `Query` API returns `TotalNumberOfResults` and facet counts per attribute value, but that counts query matches (mentions), not topic relevance, and Kendra is closed. BMKB has no faceting.

### Cited Findings
- Kendra `Query` returns `TotalNumberOfResults`: "The total number of items found by the search. However, you can only retrieve up to 100 items. For example, if the search found 192 items, you can only retrieve the first 100." Results come back at most 100 per page. — [Kendra Query API](https://docs.aws.amazon.com/kendra/latest/APIReference/API_Query.html)
- Kendra `Facets` input: "Amazon Kendra returns a count for each field key specified." `FacetResults` contains `DocumentAttributeValueCountPairs` (`Count`, value), which can be nested. — [Kendra Query API](https://docs.aws.amazon.com/kendra/latest/APIReference/API_Query.html)
- The GenAI index fully supports faceting with both Retrieve and Query. — [Kendra index types](https://docs.aws.amazon.com/kendra/latest/dg/hiw-index-types.html)
- "Kendra supports document attribute facets … displaying up to 10 facet values per facet with document counts. BMKB's architecture does not support faceted search." The suggested BMKB workaround is metadata filters, which "does not provide dynamic facet counts". — [Kendra availability change](https://docs.aws.amazon.com/kendra/latest/dg/kendra-availability-change.html)
- In Q Business, chat orchestration identifies read-only requests "like checking ticket counts" and routes them to plugins, that is, to external systems such as ticketing tools, not the document index. — [Global controls](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/guardrails-global-controls.html)
- The Quick plugin (Dec 3, 2024) provides "insights from structured data through Amazon Quick". — [Q Business document history](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/doc-history.html)
- In the EU and Sydney regions, Q Business can "perform tabular search on small tables". — [Q Business endpoints](https://docs.aws.amazon.com/general/latest/gr/amazonq.html)

### Inferences
- Kendra's `TotalNumberOfResults` and facets are the kind of keyword/mention counting that CLAUDE.md has already ruled out ("counts mentions, not topics"). Exact counts by attribute (year, country, has-attachments) via facets would have matched the planned "Filter" step, but Kendra is closed to new customers.
- Q Business would need a structured catalog, such as a QuickSight dataset via the Quick plugin. That is the planned catalog approach again, with less control and an unknown model writing the numbers.
- Neither service removes the need for the planned count path.

### Gaps
- I did not verify whether Q Business's Agentic RAG (Aug 2025) can do aggregation, or whether Kendra facets work on DATE/LONG attributes for per-month counts.

## AWS GovCloud (US) availability and FedRAMP status (secondary)

### Takeaway
**Q Business is not offered in GovCloud.** Its endpoints exist only in us-east-1, us-west-2, eu-west-1 and ap-southeast-2, and I found no FedRAMP authorization for it. **Kendra** has been FedRAMP High in GovCloud (US-West) since 2022 and FedRAMP Moderate in US East/West. However, its **GenAI index is only in us-east-1 and us-west-2**, and Kendra is closed to new customers.

### Cited Findings
- Q Business endpoints: us-east-1, us-west-2, eu-west-1 and ap-southeast-2 only, with no GovCloud region listed. EU and Sydney lack some features (Q Apps, Q Actions, audio/video). — [Q Business endpoints and quotas](https://docs.aws.amazon.com/general/latest/gr/amazonq.html)
- Q Business "is a HIPAA eligible service". The FAQ doesn't mention FedRAMP or GovCloud and refers readers to the Services by Region page. — [Q Business FAQs](https://aws.amazon.com/q/business/faqs/)
- "Amazon Kendra is now authorized as FedRAMP High in AWS GovCloud (US-West) Region" (Nov 2022). Source: search-result snippet; I did not open the page. — [AWS What's New, Nov 2022](https://aws.amazon.com/about-aws/whats-new/2022/11/amazon-kendra-fedramp-high-compliant/)
- Kendra's compliance page lists FedRAMP (High in GovCloud US-West, Moderate in US East/West). Source: search-result snippet; not opened. — [Compliance validation for Amazon Kendra](https://docs.aws.amazon.com/kendra/latest/dg/kendra-compliance.html)
- The GenAI Enterprise index is "only available in US East (N. Virginia) and US West (Oregon)". — [Kendra index types](https://docs.aws.amazon.com/kendra/latest/dg/hiw-index-types.html)
- For context only: AWS announced FedRAMP High for Amazon Bedrock (Aug 2024), and FedRAMP High / DoD IL-4/5 for Bedrock models in GovCloud (May 2025). Source: search-result titles; not opened. — [Bedrock FedRAMP High](https://aws.amazon.com/about-aws/whats-new/2024/08/amazon-bedrock-achieves-fedramp-high-authorization); [Bedrock models in GovCloud](https://aws.amazon.com/about-aws/whats-new/2025/05/amazon-bedrock-models-fedramp-high-dod-il-4-5-govcloud)

### Inferences
- If CBP ever needs GovCloud or FedRAMP High hosting for restricted categories:
  - Q Business is out, for both region and authorization reasons.
  - Kendra's FedRAMP-High GovCloud presence covers only the older Enterprise/Developer editions, not the GenAI index.
  - Bedrock is the AWS GenAI path with GovCloud/FedRAMP High coverage.
- Whether Bedrock KBs, S3 Vectors and Nova models are available in GovCloud needs separate checking.

### Gaps
- I did not open AWS "Services in Scope by Compliance Program" to confirm the current FedRAMP status of Q Business or Kendra.
- I did not check whether Bedrock Knowledge Bases, BMKB, S3 Vectors or Nova models are available in GovCloud.
