# RAG S3Vector — Infrastructure

AWS CDK (Python) stack deploying the RAG pipeline: S3 document bucket, S3 Vectors index, Bedrock Guardrail, and two Lambda functions (ingestion + query).

## Prerequisites

- Python 3.12+
- Node.js (required by CDK CLI)
- AWS CLI configured with credentials
- CDK CLI: `npm install -g aws-cdk`
- Bedrock model access enabled in the AWS Console for:
  - `amazon.nova-embed-v1:0`
  - `anthropic.claude-3-5-sonnet-20241022-v2:0`

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

> **Note:** The S3 document bucket has `RemovalPolicy.RETAIN` — it will not be deleted on destroy.

## Configuration

| File | Purpose |
|------|---------|
| `config/common.yml` | Shared config: model IDs, Lambda settings, common tags |
| `config/dev.yml` | Dev environment overrides and tags |

To add a new environment, create `config/<env>.yml` and deploy with `--context env=<env>`.
