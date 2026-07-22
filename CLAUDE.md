# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CBP CSMS ("Cargo Systems Messaging Service") Intelligent Retrieval and Compliance Assistant — a RAG system using AWS Bedrock (embeddings + LLM) and S3 Vectors as the vector store, deployed with AWS CDK (Python). Documents are uploaded to an S3 bucket, automatically ingested via Lambda, and queried through a second Lambda that applies a Bedrock Guardrail.

## Architecture

```
S3 Document Bucket
      │  (ObjectCreated event)
      ▼
Ingestion Lambda ──► Bedrock embed model ──► S3 Vectors (index)
   │
   └─ archive/*.pdf → ArchivePdfHandler: extract hyperlinks from the PDF,
                       fetch + text-extract each linked HTML page, then embed/index that

Query Lambda ──► Bedrock embed model ──► S3 Vectors query (topK + numeric date pre-filter)
              └──► Bedrock LLM (Llama prompt format) + Guardrail ──► answer + sources
              ▲
              │ invoked via Lambda Function URL (CloudFront UI) or boto3 lambda.invoke() (local container UI)
```

Two independent frontends both call the same Query Lambda, nothing else:
- `app/ui/s3-static/index.html` — a single self-contained static page (USWDS via CDN), deployed to S3 + CloudFront by CDK (`resource_ui.py`). CloudFront routes `/api/*` to the Query Lambda's Function URL.
- `app/ui/container/` — a FastAPI + React app (`backend/main.py` invokes the Query Lambda directly via `boto3`). Built as a Docker image and run **locally only** via `docker-compose.yml`; the matching Fargate deployment (`resource_fargate.py`) is fully wired up but commented out in `rag_stack.py` — UI is not deployed to Fargate.

## Structure

```
iac/                              # AWS CDK (Python)
├── app.py                        # entry point; env via --context env=<name> (default "dev")
├── config/
│   ├── common.yml                 # model IDs, naming, lambda/fargate sizing, common tags
│   ├── dev.yml                    # per-env overrides, deep-merged onto common.yml
│   └── loader.py                  # load_config(env), resource_name(config, base) → "{prefix}-{base}-{suffix}"
└── stacks/rag_stack.py           # wires resources/*.py together; one CfnOutput per resource
    resources/
    ├── resource_s3.py            # document bucket (versioned, DESTROY)
    ├── resource_s3_vectors.py    # vector bucket + index via AwsCustomResource (S3 Vectors has no CDK L2 yet)
    ├── resource_guardrail.py     # CfnGuardrail + pinned CfnGuardrailVersion
    ├── resource_iam.py           # shared Lambda role (bedrock:InvokeModel, ApplyGuardrail, s3vectors:*)
    ├── resource_lambda.py        # both Lambdas; ingestion has pip-install bundling, query does not
    ├── resource_ui.py            # S3 + CloudFront static site, /api/* → query Lambda Function URL
    └── resource_fargate.py       # ECS Fargate + ALB for the container UI — defined but not deployed

app/
├── ingestion/
│   ├── handler.py                 # lambda_handler: routes archive/*.pdf to ArchivePdfHandler, else chunks/embeds/writes text directly
│   ├── archive_pdf_handler.py     # ArchivePdfHandler class; has a `python archive_pdf_handler.py <pdf>` local test mode (no AWS)
│   └── requirements.txt           # pypdf (bundled into the Lambda zip at deploy time)
├── query/handler.py               # lambda_handler: embed → S3 Vectors query with numeric-timestamp pre-filter → LLM → answer+sources
├── scraper/                       # containerized batch app: downloads CBP CSMS messages (live feed + archive PDFs)
│   ├── scraper/                   #   and uploads to S3 one at a time with Bedrock Knowledge Base .metadata.json sidecars
│   └── README.md                  #   full source map, metadata schema, and usage — read this before touching the scraper
└── ui/
    ├── s3-static/index.html       # CloudFront-deployed static UI
    └── container/                 # local-only container UI (Dockerfile, docker-compose.yml, backend/, frontend/)
```

## Key conventions

- **Config-driven naming/models**: nothing is hardcoded — model IDs, memory/timeout, and resource name parts all come from `iac/config/common.yml` (overridden per-env by `<env>.yml`). Check `common.yml` before assuming a model ID; it has drifted from what's described in `iac/README.md` before.
- **S3 Vectors metadata for filtering**: every vector's metadata carries both `document_date` (ISO string, for display/fallback filtering) and `document_timestamp` (Unix int) — S3 Vectors' `$gte`/`$lte` filters only work on Number fields, so the numeric field is what the query Lambda actually pre-filters on. `text` and `chunk_id` are registered as `nonFilterableMetadataKeys` on the index (`resource_s3_vectors.py`).
- **LLM prompt format is model-specific**: `query/handler.py` builds a raw Llama chat-template string (`format_llama_prompt`) and reads `result["generation"]` — this is coupled to whatever `bedrock.llm_model_id` is currently a Llama model in `common.yml`. Changing the LLM to a non-Llama model requires updating the request/response shape, not just the config value.
- **Archive PDF routing**: `ArchivePdfHandler.should_handle(key)` matches keys under `archive/` ending in `.pdf`. These PDFs aren't indexed for their own text — they're treated as a list of links; each linked HTML page is fetched and indexed instead, with `pdf_source` (parent PDF's S3 key) and `link_index` kept in metadata.
- **Ingestion Lambda bundling**: only the ingestion function pip-installs `requirements.txt` into the deployment package at synth/deploy time (`resource_lambda.py` `BundlingOptions`); the query Lambda has no third-party deps and is deployed as plain source.
- **Two ingestion pipelines, don't cross them**: the S3 Vectors path (documents bucket → ingestion Lambda) and the Bedrock Knowledge Base path (`app/scraper` → a KB source bucket with `.metadata.json` sidecars) are separate. The scraper must not upload into the `cits-rag-s3vector-documents-*` bucket — every object (sidecars included) would fire the ingestion Lambda.
- **CSMS URL mechanics** (used by `app/scraper`): modern message IDs are GovDelivery bulletin IDs, URL = `https://content.govdelivery.com/accounts/USDHSCBP/bulletins/{id-in-hex}`; legacy IDs (`YY-NNNNNN`, pre-July-2019) have no computable URL and are discovered from CBP archive PDFs.

## Development Commands

### Infrastructure (CDK)

```bash
cd iac
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cdk synth                                          # synthesize CloudFormation
cdk deploy --profile <AWS_PROFILE>                 # deploy to dev
cdk deploy --profile <AWS_PROFILE> --context env=prod
cdk destroy --profile <AWS_PROFILE>
```

Before first deploy in an account/region: `cdk bootstrap --profile <AWS_PROFILE>`.

Bedrock model access must be enabled in the AWS Console under **Bedrock → Model access** for whatever `embedding_model_id` / `llm_model_id` are currently set to in `iac/config/common.yml`.

> Note: the S3 document bucket is created with `RemovalPolicy.DESTROY` in `resource_s3.py` — `cdk destroy` will delete uploaded documents along with it (the `iac/README.md` claim that it's `RETAIN` is stale).

### Local container UI (`app/ui/container/`)

Runs the FastAPI/React UI locally against real AWS (Lambda, Bedrock, Guardrails, S3 Vectors) — no local mocking, LocalStack is not supported (doesn't implement Bedrock/S3 Vectors).

```bash
cd app/ui/container
cp .env.local.example .env.local     # set QUERY_LAMBDA_NAME and AWS_PROFILE
docker compose up --build            # http://localhost:8000, mounts ~/.aws read-only
docker compose down
```

Frontend-only iteration (Vite dev server, without rebuilding the Docker image):

```bash
cd app/ui/container/frontend
npm install
npm run dev
```

### CSMS scraper (`app/scraper/`)

```bash
cd app/scraper
cp .env.local.example .env.local          # set S3_BUCKET_NAME (KB source bucket)
docker compose build
docker compose run --rm scraper current                      # live feed (~100 latest)
docker compose run --rm scraper archive 2021-2025 --limit 200
python -m scraper message 69302472 --dry-run                 # no AWS needed, writes to ./out
```

### Smoke-testing the Query Lambda directly

```bash
aws lambda invoke \
  --function-name cits-rag-s3vector-query \
  --cli-binary-format raw-in-base64-out \
  --payload '{"query": "What documents are available?"}' \
  --profile <AWS_PROFILE> \
  response.json && cat response.json
```

### Local test of ArchivePdfHandler (no AWS required)

```bash
cd app/ingestion
python archive_pdf_handler.py path/to/file.pdf [--max-links 10]
```

Downloads no S3/Bedrock — reads a local PDF, extracts hyperlinks, fetches each linked page, and prints extracted/chunked text to stdout.

### Listing available Bedrock models

```bash
aws bedrock list-foundation-models \
  --profile <AWS_PROFILE> \
  --query 'modelSummaries[?contains(modelId, `embed`)].modelId' \
  --output table
```
