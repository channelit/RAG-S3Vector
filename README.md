# RAG-S3Vector

Question-answering assistant for CBP CSMS (Cargo Systems Messaging Service) messages. A scraper downloads the public messages into S3, Amazon Bedrock Knowledge Bases index them in S3 Vectors, and a FastAPI/React UI answers questions from them with a Bedrock Guardrail applied.

## Architecture

```
app/scraper ──► S3 documents bucket ──► Bedrock Knowledge Bases ──► S3 Vectors
 (uploads, then    csms/1/          ──►   messages KB                (one index per
  starts the       csms-summary/1/  ──►   summary KB: message         knowledge base)
  KB sync)                                counts the scraper computes

[local docker-compose UI] ──► RetrieveAndGenerate on the messages KB + Guardrail ──► answer + sources
Bedrock Flow              ──► classifies the question ──► the KB for its category + Guardrail ──► answer
```

Every document is indexed by a knowledge base: the scraper uploads it into that knowledge base's folder and starts the sync. There is no other ingestion path, so a file outside those folders is not indexed.

CDK deploys: the documents bucket, the S3 Vectors bucket, the knowledge bases, the Bedrock Flow and the Bedrock Guardrail.
**The container UI is not deployed to AWS (Fargate is disabled) — run it locally with docker-compose.**

More detail: [`iac/README.md`](iac/README.md) (deploy), [`app/scraper/README.md`](app/scraper/README.md) (scraper), [`new-architecture.md`](new-architecture.md) (design and plans).

---

## Local UI

Run the web container locally while the knowledge base, Bedrock and Guardrails remain in real AWS.

**Prerequisites:** Docker Desktop, AWS credentials configured, the stack deployed and the messages knowledge base filled by the scraper.

### 1. Create your local env file

```bash
cd app/ui/container
cp .env.local.example .env.local
# Edit .env.local — set KNOWLEDGE_BASE_ID and AWS_PROFILE (or explicit keys)
```

The only value you must set is `KNOWLEDGE_BASE_ID`. The stack's `ContainerUiEnv` output is a paste-ready copy of it, together with the generation model and the guardrail ID and version.

### 2. Build and start

```bash
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000). The container mounts `~/.aws` read-only so boto3 can reach AWS. Each question is one `RetrieveAndGenerate` call: the knowledge base retrieves the passages and Bedrock writes the answer from them, with the guardrail applied.

### 3. Stop

```bash
docker compose down
```

### Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Container exits at start with `KeyError: 'KNOWLEDGE_BASE_ID'` | `.env.local` not created or variable not set |
| `NoCredentialsError` | `~/.aws` not populated or wrong `AWS_PROFILE` in `.env.local` |
| `502` from `/api/query` (`Knowledge Base query failed: …`) | The message carries the AWS error: a wrong `KNOWLEDGE_BASE_ID`, a model this account cannot invoke (`BEDROCK_MODEL_ARN`), or missing Bedrock permissions |
| Container exits immediately | Check `docker compose logs ui` |

> **Note:** Guardrails, embeddings, and the LLM all run in AWS. LocalStack is not supported — it does not implement Bedrock or S3 Vectors.

---

## Ask the deployed flow

```shell
cd app/ui/container          # .env.local needs FLOW_ID and FLOW_ALIAS_ID (ContainerUiEnv output)
python backend/flow_ask.py --trace "How many CSMS messages are there?"
```

## List available Bedrock embedding models

```shell
aws bedrock list-foundation-models \
  --profile terraform \
  --query 'modelSummaries[?contains(modelId, `embed`)].modelId' \
  --output table
```
