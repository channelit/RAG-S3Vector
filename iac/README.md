# RAG S3Vector — Infrastructure

AWS CDK (Python) stack deploying the RAG pipeline. One stack (`RagStack`) creates:

| Resource | Construct | Notes |
|----------|-----------|-------|
| Document bucket | `resource_s3.py` | versioned, private; every `ObjectCreated` fires the ingestion Lambda |
| S3 Vectors bucket + Lambda index | `resource_s3_vectors.py` | `AwsCustomResource` (no CDK L2 yet); `text`/`chunk_id` non-filterable |
| Bedrock Guardrail + pinned version | `resource_guardrail.py` | denied topics (politics, impoliteness), profanity list, all PII blocked in questions and answers, content filters; every block answers "Sorry we cannot answer this question." |
| Lambda role | `resource_iam.py` | InvokeModel, ApplyGuardrail, s3vectors:* |
| Ingestion + Query Lambdas | `resource_lambda.py` | query Lambda also gets a Function URL |
| **Standard Bedrock Knowledge Base** | `resource_knowledge_base.py` | own S3 Vectors index (`AMAZON_BEDROCK_*` non-filterable), service role, S3 data source on the documents bucket under `knowledge_base.source_prefix` — this is the KB the container UI queries via `RetrieveAndGenerate` (managed KBs reject that call) |
| Static UI | `resource_ui.py` | S3 + CloudFront, `/api/*` → query Lambda Function URL |
| Fargate UI (disabled) | `resource_fargate.py` | wired to the KB + guardrail, commented out in `rag_stack.py` |

The guardrail is applied in two places: the query Lambda passes `GUARDRAIL_ID`/`GUARDRAIL_VERSION` to `InvokeModel`, and the container UI passes the same pair as `guardrailConfiguration` on its `RetrieveAndGenerate` call. A guardrail cannot be attached to a Knowledge Base itself — it is always supplied by the caller — so the stack prints a paste-ready `ContainerUiEnv` output with the KB ID, generation model and guardrail ID/version for `app/ui/container/.env.local`.

## Prerequisites

- Python 3.12+
- Node.js (required by CDK CLI)
- AWS CLI configured with credentials
- CDK CLI: `npm install -g aws-cdk`
- Bedrock model access enabled in the AWS Console for the models in `config/common.yml`:
  - `bedrock.embedding_model_id` and `bedrock.llm_model_id` (Lambda pipeline)
  - `knowledge_base.embedding_model_id` and `knowledge_base.generation_model_id` (Knowledge Base + container UI)

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

## After deploy: sync the Knowledge Base

The KB starts empty. Sync its S3 data source, then copy the `ContainerUiEnv` output into `app/ui/container/.env.local`:

```bash
aws bedrock-agent start-ingestion-job --profile <AWS_PROFILE> \
  --knowledge-base-id <KnowledgeBaseId> --data-source-id <KnowledgeBaseDataSourceId>
aws bedrock-agent list-ingestion-jobs --profile <AWS_PROFILE> \
  --knowledge-base-id <KnowledgeBaseId> --data-source-id <KnowledgeBaseDataSourceId>   # wait for COMPLETE
```

## Configuration

| File | Purpose |
|------|---------|
| `config/common.yml` | Shared config: model IDs, Lambda settings, common tags |
| `config/dev.yml` | Dev environment overrides and tags |

To add a new environment, create `config/<env>.yml` and deploy with `--context env=<env>`.
