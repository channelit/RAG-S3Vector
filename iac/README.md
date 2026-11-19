# RAG S3Vector — Infrastructure

AWS CDK (Python) stack deploying the RAG pipeline: a documents bucket, the Bedrock knowledge bases that index it, and the flow and guardrail in front of them. One stack (`RagStack`) creates:

| Resource | Construct | Notes |
|----------|-----------|-------|
| Document bucket | `resource_s3.py` | versioned, private; each knowledge base's S3 data source reads its own folder of it (`source_prefix`) |
| S3 Vectors bucket | `resource_s3_vectors.py` | `AwsCustomResource` (no CDK L2 yet); holds one index per knowledge base |
| Bedrock Guardrail + pinned version | `resource_guardrail.py` | denied topics (politics, impoliteness), profanity list, all PII blocked in questions and answers, content filters; every block answers "Sorry we cannot answer this question." |
| **Standard Bedrock Knowledge Base** | `resource_knowledge_base.py` | own S3 Vectors index (`AMAZON_BEDROCK_*` non-filterable), service role, S3 data source on the documents bucket under `knowledge_base.source_prefix` — this is the KB the container UI queries via `RetrieveAndGenerate` (managed KBs reject that call) |
| **Summary Knowledge Base** | `resource_knowledge_base.py` | one more KB per `knowledge_base.additional` entry; `summary` holds the scraper's collection statistics (source prefix `csms-summary/1/`, `NONE` chunking: one file = one chunk) |
| **Bedrock Flow** + version + alias | `resource_flow.py` | classifier prompt → condition → one knowledge base node per route (`flow.routes`), each a `RetrieveAndGenerate` with the guardrail; callers invoke the alias |
| Fargate UI (disabled) | `resource_fargate.py` | wired to the KB + guardrail, commented out in `rag_stack.py` |

**How a document gets indexed.** It is written under a knowledge base's `source_prefix` in the documents bucket, and that knowledge base is synced. The scraper does both (`app/scraper/README.md`). Nothing else reads the bucket, so a file outside those prefixes is not indexed, and no Lambda function handles documents or questions. The one function in the stack is CDK's `AwsCustomResource` provider, which creates the vector bucket and the indexes during a deploy.

The guardrail is applied by its callers: the container UI passes `GUARDRAIL_ID`/`GUARDRAIL_VERSION` as `guardrailConfiguration` on its `RetrieveAndGenerate` call, and the flow's knowledge base nodes carry the same pair. A guardrail cannot be attached to a Knowledge Base itself — it is always supplied by the caller — so the stack prints a paste-ready `ContainerUiEnv` output with the KB ID, generation model and guardrail ID/version for `app/ui/container/.env.local`.

## Prerequisites

- Python 3.12+
- Node.js (required by CDK CLI)
- AWS CLI configured with credentials
- CDK CLI: `npm install -g aws-cdk`
- Bedrock model access enabled in the AWS Console for the models in `config/common.yml`:
  - `knowledge_base.embedding_model_id` and `knowledge_base.generation_model_id` (Knowledge Base + container UI)
  - `flow.classifier_model_id` and `flow.generation_model_id` (Bedrock Flow)

## First-time setup

```bash
cd iac
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Bootstrap CDK in your account/region (one-time per account):

```bash
cdk bootstrap --profile <AWS_PROFILE>
```

## Deploy

Deploy to `dev` (default — no extra flags needed):

```bash
cdk deploy --profile <AWS_PROFILE>
```

Deploy to a different environment:

```bash
cdk deploy --profile <AWS_PROFILE> --context env=prod
```

Override region:

```bash
cdk deploy --profile <AWS_PROFILE> --context region=us-west-2
```

## Destroy

```bash
cdk destroy --profile <AWS_PROFILE>
```

> **Note:** The S3 document bucket has `RemovalPolicy.DESTROY` — `cdk destroy` deletes it and every uploaded document. The Knowledge Base data source uses `data_deletion_policy=DELETE`, so its vectors are removed with it.

## After deploy: fill the Knowledge Bases

Both knowledge bases start empty. Copy the `ScraperEnv` output into `app/scraper/.env.local` and the `ContainerUiEnv` output into `app/ui/container/.env.local`, then run the scraper: it uploads the messages, syncs the messages knowledge base, writes the summary and syncs the summary knowledge base (`app/scraper/README.md`).

To sync a data source yourself, for example after the scraper ran with `--no-sync`:

```bash
aws bedrock-agent start-ingestion-job --profile <AWS_PROFILE> \
  --knowledge-base-id <KnowledgeBaseId> --data-source-id <KnowledgeBaseDataSourceId>
aws bedrock-agent list-ingestion-jobs --profile <AWS_PROFILE> \
  --knowledge-base-id <KnowledgeBaseId> --data-source-id <KnowledgeBaseDataSourceId>   # wait for COMPLETE
```

## The flow: classification → knowledge base

```
FlowInputNode ─► Classify ─► Route ─┬─ statistics ─► Answer_statistics ─► Output_statistics   (summary KB)
 (question)      (prompt)  (condition)└─ default ────► Answer_messages   ─► Output_messages     (CSMS messages KB)
```

The classifier's prompt is built from the route descriptions in `config/common.yml`, so a new category is configuration only:

1. If it has its own documents, add a knowledge base under `knowledge_base.additional` (a name, a `source_prefix` that overlaps no other, optionally `chunking: none`).
2. Add a route under `flow.routes` with a `description` (what the classifier chooses by) and the `knowledge_base` it answers from (`primary` or an `additional` key). Optional: `num_results`, `prompt_file`, `generation_model_id`.
3. `cdk deploy`, upload the documents, sync the new knowledge base.

Unrecognised classifier replies go to `flow.default_route`. Bedrock's limits allow 17 routes with this layout; more than four non-default routes are spread over chained condition nodes automatically. Every definition change publishes a new flow version and repoints the alias.

What a flow's knowledge base node cannot do: take a metadata filter (no date range) or return citations (no source links). The container UI's own `RetrieveAndGenerate` call has both. So the UI backend sends every question to the flow only to learn the route: for a route that reads the primary knowledge base (`FLOW_BACKEND_ROUTES` in the `ContainerUiEnv` output, `messages` today) it drops the flow once the route is chosen and answers with its own call, and for any other route (`statistics`) it returns the flow's answer. A route added in `common.yml` is therefore answered by the flow in the UI, unless it reads the primary knowledge base.

Try the deployed flow (the AWS CLI cannot call the streaming `InvokeFlow` API):

```bash
cd app/ui/container                       # .env.local needs FLOW_ID and FLOW_ALIAS_ID (ContainerUiEnv output)
python backend/flow_ask.py --trace "How many CSMS messages are there?"
```

The statistics route answers from the summary knowledge base, which is empty until the scraper has written the summary (`python -m scraper summary`, see `app/scraper/README.md`) and that knowledge base has been synced. The `ScraperEnv` output has the scraper's `.env.local` lines.

## Configuration

| File | Purpose |
|------|---------|
| `config/common.yml` | Shared config: model IDs, knowledge bases, flow routes, common tags |
| `config/prompts/` | Prompt text used by the flow: the classifier template and per-route answer templates |
| `config/dev.yml` | Dev environment overrides and tags |

To add a new environment, create `config/<env>.yml` and deploy with `--context env=<env>`.
