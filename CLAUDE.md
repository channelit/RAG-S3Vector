# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Custom RAG system using AWS Bedrock (embeddings + LLM) and S3 Vectors as the vector store, deployed with AWS CDK (Python). Documents are uploaded to S3, automatically ingested via Lambda, and queried through a second Lambda that applies Bedrock Guardrails.

## Architecture

```
S3 Document Bucket
      │  (ObjectCreated event)
      ▼
Ingestion Lambda ──► Bedrock Titan Embed ──► S3 Vectors (index)

Query Lambda ──► Bedrock Titan Embed ──► S3 Vectors query
              └──► Bedrock Claude + Guardrail ──► answer + sources
```

- **Embedding model**: `amazon.nova-embed-v1:0` (1024 dimensions, cosine distance; supports MRL for smaller output sizes)
- **LLM**: `anthropic.claude-3-5-sonnet-20241022-v2:0`
- **Guardrail**: blocks hate/violence/PROMPT_ATTACK; anonymizes email/phone/name; blocks SSN/credit card

## Structure

```
iac/                          # AWS CDK (infrastructure)
├── app.py                    # CDK entry point
├── cdk.json                  # context: region, project_name
├── requirements.txt
└── stacks/
    └── rag_stack.py          # single stack: all resources

app/                          # Lambda application code
├── ingestion/handler.py      # chunk → embed → put_vectors
└── query/handler.py          # embed → query_vectors → invoke LLM
```

S3 Vectors is not yet covered by CDK L2 constructs; the vector bucket and index are created via `AwsCustomResource` (SDK calls during `cdk deploy`/`cdk destroy`).

## Development Commands

```bash
cd iac
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Synthesize CloudFormation template
cdk synth

# Deploy (requires AWS credentials + CDK bootstrap)
cdk deploy --context account=<ACCOUNT_ID>

# Destroy
cdk destroy
```

Before first deploy in an account/region:
```bash
cdk bootstrap aws://<ACCOUNT_ID>/<REGION>
```

Bedrock model access must be enabled in the AWS Console under **Bedrock → Model access** for `amazon.nova-embed-v1:0` and `anthropic.claude-3-5-sonnet-20241022-v2:0`.
