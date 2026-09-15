# infra — Bedrock Guardrail (boto3)

Standalone, config-driven management of the CSMS assistant's Amazon Bedrock
Guardrail, independent of the CDK stack. The policy is YAML; the script only
translates it into `CreateGuardrail` / `UpdateGuardrail` calls.

Requirements covered:

| Requirement | How it is enforced                                             | Config section                    |
|-------------|----------------------------------------------------------------|-----------------------------------|
| Politics    | Denied topic **Politics**                                      | `denied_topics`                   |
| Profanity   | AWS-managed **PROFANITY** word list (+ optional custom words)  | `word_filters`                    |
| Rudeness    | Denied topic **Rudeness** + **INSULTS** content filter (HIGH)  | `denied_topics`, `content_filters`|

Baseline harmful-content filters and the PII policy are included too so the
result matches the CDK guardrail in `iac/resources/resource_guardrail.py`.
Set `pii.enabled: false` to drop PII blocking.

## Layout

```
infra/
├── guardrail.py          # CLI: apply | publish | show | test | delete
├── requirements.txt
└── config/
    ├── guardrail.yml     # the policy (base)
    ├── dev.yml           # per-env overrides, deep-merged onto guardrail.yml
    └── prod.yml
```

Overrides merge like `iac/config`: mappings merge recursively, lists replace
the base list wholesale.

## Usage

```bash
cd infra
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python guardrail.py apply --dry-run                     # show the API payload, call nothing
python guardrail.py apply --profile <AWS_PROFILE>       # create, or update the DRAFT
python guardrail.py apply --publish --profile <P>       # ...and publish a numbered version
python guardrail.py publish --profile <P>               # publish the DRAFT (skipped if unchanged)
python guardrail.py show --profile <P>                  # id / arn / status / versions
python guardrail.py test --profile <P>                  # run the `tests:` cases from config
python guardrail.py test --profile <P> "Who should I vote for?" --source INPUT
python guardrail.py delete --profile <P>                # asks for confirmation
python guardrail.py --env prod apply --publish --profile <P>
```

`apply` and `publish` print `GUARDRAIL_ID` / `GUARDRAIL_VERSION` lines ready to
paste into `app/ui/container/.env.local` or the query Lambda environment.

Publishing is idempotent: each version's description carries a fingerprint of
the policy, and `publish` skips creating a new version when the latest one
already has the same fingerprint.

## Editing the policy

- Denied topic definitions are capped by Bedrock at 200 characters, topic
  names at 100 and each example at 100. The script validates these before
  calling AWS.
- Content filter strengths: `NONE`, `LOW`, `MEDIUM`, `HIGH`.
- PII entries are either a bare entity type (uses `pii.default_action`) or
  `{type: NAME, action: ANONYMIZE}`.
- `tests:` cases run through `ApplyGuardrail`; `expect` is `BLOCK` or `ALLOW`
  and `source` defaults to `INPUT`.

## IAM

The caller needs `bedrock:CreateGuardrail`, `UpdateGuardrail`,
`GetGuardrail`, `ListGuardrails`, `CreateGuardrailVersion`,
`DeleteGuardrail`, `TagResource`, and `bedrock:ApplyGuardrail` (for `test`).
