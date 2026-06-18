# RAG-S3Vector

Custom RAG system using AWS Bedrock (embeddings + LLM) and S3 Vectors as the vector store. Documents are uploaded to S3, ingested via Lambda, and queried through a FastAPI/React UI with Bedrock Guardrails applied.

---

## Local UI testing

Run the web container locally while Lambda, Bedrock, and Guardrails remain in real AWS. No code changes required.

**Prerequisites:** Docker Desktop, AWS credentials configured, Query Lambda deployed.

### 1. Create your local env file

```bash
cd app/ui/container
cp .env.local.example .env.local
# Edit .env.local — set QUERY_LAMBDA_NAME and AWS_PROFILE (or explicit keys)
```

The only value you must set is `QUERY_LAMBDA_NAME`. Find it in the AWS Console (Lambda) or from CDK deploy output — it follows the pattern `cits-rag-s3vector-query`.

### 2. Build and start

```bash
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000). The container mounts `~/.aws` read-only so boto3 can reach AWS — queries flow: local container → Lambda → Bedrock + S3 Vectors → Guardrails → response.

### 3. Stop

```bash
docker compose down
```

### Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `Missing environment variable: QUERY_LAMBDA_NAME` | `.env.local` not created or variable not set |
| `NoCredentialsError` | `~/.aws` not populated or wrong `AWS_PROFILE` in `.env.local` |
| `502` from `/api/query` | Lambda not deployed, or wrong function name |
| Container exits immediately | Check `docker compose logs ui` |

> **Note:** Guardrails, embeddings, and the LLM all run in AWS. LocalStack is not supported — it does not implement Bedrock or S3 Vectors.

---

## Lambda smoke test

```shell
aws lambda invoke \
  --function-name cits-rag-s3vector-query \
  --cli-binary-format raw-in-base64-out \
  --payload '{"query": "What documents are available?"}' \
  --profile terraform \
  response.json && cat response.json
```

## List available Bedrock embedding models

```shell
aws bedrock list-foundation-models \
  --profile terraform \
  --query 'modelSummaries[?contains(modelId, `embed`)].modelId' \
  --output table
```
