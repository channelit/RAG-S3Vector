# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CBP CSMS ("Cargo Systems Messaging Service") Intelligent Retrieval and Compliance Assistant — a RAG system on Amazon Bedrock Knowledge Bases, with S3 Vectors as the vector store, deployed with AWS CDK (Python). A scraper uploads the public CSMS messages to an S3 bucket, knowledge bases index them, and questions are answered with `RetrieveAndGenerate` and a Bedrock Guardrail.

## Architecture

```
app/scraper ──► S3 documents bucket ──► Bedrock Knowledge Bases ──► S3 Vectors (one index per KB)
 (uploads, then    csms/1/          ──►   messages KB (primary)
  starts the       csms-summary/1/  ──►   summary KB (the scraper's collection statistics)
  KB sync)

Container UI backend ──► Bedrock Flow classifier ─┬─ messages   ──► own RetrieveAndGenerate (messages KB, date filter) + Guardrail ──► answer + sources
                                                  └─ statistics ──► the flow's answer (summary KB) + Guardrail ──► answer, no sources
Bedrock Flow         ──► classifier ──► the KB for the question's category + Guardrail ──► answer
```

**Knowledge bases are the only ingestion path** (user's decision, 2026-11-16: "all files should directl flow KB S3.. no need for lambda"). A document is indexed when it sits under a knowledge base's source prefix and that knowledge base is synced; the scraper does both. There is no ingestion Lambda, no query Lambda and no hand-upload path, so a file outside the source prefixes is indexed by nothing. For a new kind of document, add a `knowledge_base.additional` entry (and a flow route); don't add a Lambda or a second index. The older Lambda pipeline (an ingestion Lambda fired by every upload, a query Lambda with a public Function URL, their own index and a static page) was removed from the stack code and from the deployed stack on 2026-11-16. The only Lambda function left in the stack is CDK's `AwsCustomResource` provider, which creates the vector bucket and the KB indexes during a deploy.

**Leftovers of the Lambda pipeline in the documents bucket** (the user decides whether to delete them): outside the KB prefixes, and so indexed by nothing, are six files uploaded by hand in June 2026 (three CSMS messages saved as text and three ACE CATAIR PDFs) and `csms/69302472/` (an early scraper upload; the same message is in `csms/1/`). The scraper can fetch the three messages by ID (`scraper message 42906418 67270895 67834313`, checked with `--dry-run`); the CATAIR PDFs are not CSMS messages and would need their own knowledge base. The pipeline's code (`app/ingestion/`, `app/query/`, `app/ui/s3-static/` and `resource_lambda.py`, `resource_iam.py`, `resource_ui.py` under `iac/resources/`) and the repo's copy of those three messages (`app/data/`) were deleted from the repo on 2026-11-16 at the user's request; they are in git history up to commit `24d5566`.

One frontend:
- `app/ui/container/` — a FastAPI + React app. In `backend/main.py` each question goes first to the Bedrock Flow (`FLOW_ID`/`FLOW_ALIAS_ID`), whose classifier picks the route (user's decision, 2026-11-17: "send UI questions to classifier and then back"). The backend reads the route from the flow's trace (the `Answer_<route>` node starting, about 0.6 s in):
  - **A route in `FLOW_BACKEND_ROUTES`** (`messages`; the `ContainerUiEnv` output lists the routes that read the primary KB) is answered by the backend's own single `bedrock-agent-runtime` `retrieve_and_generate` call against the Bedrock Knowledge Base (`KNOWLEDGE_BASE_ID` in `.env.local`, model in `BEDROCK_MODEL_ARN`, guardrail via `GUARDRAIL_ID`/`GUARDRAIL_VERSION` — ID, not name — as `generationConfiguration`; sources are suppressed when `guardrailAction` is `INTERVENED`). The backend closes the flow's stream when it has the route, but Bedrock still finishes the flow's own messages answer (Nova Pro + guardrail) and that answer is discarded (CloudWatch, 2026-11-17). See open decision 4 in Next steps.
  - **Any other route** (`statistics`) returns the flow's answer, with no sources and no date filter. When the user set a date range, the response's `note` says that the range does not apply, and the frontend shows it under the answer.
  - **No route:** without `FLOW_ID`/`FLOW_ALIAS_ID`, or when the flow fails before choosing a route, the question gets the backend's own call. If the flow fails after choosing a route the backend doesn't answer, the result is a 502.

  The response is `{answer, sources, route, note}`. There is no custom system prompt and no S3 access. The single `retrieve_and_generate` call for message questions is deliberate (user's choice, 2026-09-04). It replaced a Converse tool loop (commit `a80e68c`) and a two-step retrieve + converse version, so don't reintroduce managed-KB, Lambda-based or tool-loop query paths here. The planned count path (see Next steps) would run alongside it, not replace it. **RetrieveAndGenerate is rejected by managed KBs** ("not supported for managed knowledge bases") — the KB must be a standard one (e.g. S3 Vectors-backed). The UI date range is enforced in exactly one place: a `date_numeric` (YYYYMMDD int, from the scraper's `.metadata.json` sidecars) metadata filter in the backend's own retrieval configuration, applied natively by the KB's vector store — no post-filter, no fallback, no other date source. Answers from the flow (statistics) do not use it. Sources come from the response citations as `{label, url}`: CSMS message text links to its public GovDelivery bulletin (ID in hex, parsed from the cited document path), attachments to their sidecar `attachment_url` when the KB exposes sidecar metadata. Self-hosted ALTCHA proof-of-work captcha (on by default, `ALTCHA_ENABLED=false` turns it off; there is no separate ALTCHA server): `/api/config` tells the frontend whether it's on, and the widget fetches challenges from the relative path `/api/altcha/challenge`, where the backend creates them with the `altcha` PyPI lib. The captcha is solved once per browser session: `POST /api/altcha/verify` checks the solved payload with the same lib and `ALTCHA_HMAC_KEY` (signature + solution + expiry + in-memory single-use guard) and returns a stateless HMAC-signed session token (`ALTCHA_SESSION_SECONDS`, default 3600). `/api/query` requires that `captcha_token` (a raw `altcha` payload is still accepted for direct API use); when the key is unset a random per-process key is used, which only works for a single worker/replica. The frontend imports the `altcha` npm web component, disables Submit until a token is held, keeps the token in `sessionStorage`, hides the widget while it is valid, and shows it again when a query returns 400/403. Built as a Docker image and run **locally only** via `docker-compose.yml`; the matching Fargate deployment (`resource_fargate.py`) is fully wired up but commented out in `rag_stack.py` — UI is not deployed to Fargate.

**Bedrock Flow: classification → knowledge base** (user's decision, 2026-11-13). `iac/resources/resource_flow.py` deploys a flow that classifies each question and answers it from the knowledge base for that category. It is deployed (since 2026-11-16). The container UI has sent every question to it since 2026-11-17 and answers the `messages` route itself (see the frontend above). `backend/flow_ask.py` asks it directly.

```
FlowInputNode ─► Classify ─► Route ─┬─ statistics ─► Answer_statistics ─► Output_statistics   (summary KB: the scraper's collection statistics)
 (question)      (prompt)  (condition)└─ default ────► Answer_messages   ─► Output_messages     (primary KB: CSMS messages)
```

- `flow.routes` in `common.yml` maps each category to a knowledge base, and the classifier's prompt is built from the route descriptions. A new category is a `knowledge_base.additional` entry (when it has its own documents) plus a route; nothing else changes.
- Each `Answer_*` node is a knowledge base node in generate mode: one `RetrieveAndGenerate` with `flow.generation_model_id` and the stack guardrail. A reply the condition doesn't recognise goes to `flow.default_route`.
- **A flow's knowledge base node takes no metadata filter and returns no citations**, so answers that come through the flow have no date range and no source links. That is why the container backend answers the `messages` route with its own call and takes only the other routes' answers from the flow. In the UI, a new route on its own knowledge base is answered by the flow, while a route on the primary knowledge base is answered by the backend (it is listed in `FLOW_BACKEND_ROUTES`).
- Callers invoke the alias (`FlowId` / `FlowAliasId` outputs), which points at a published version. `backend/flow_ask.py` is the smoke test.

**Count questions.** Counts over the whole collection (total, per year or month, per country mentioned, with attachments, dates covered, latest messages) are answered by the flow's `statistics` route, from documents the scraper computes (`app/scraper/scraper/summary.py`), in the container UI too. Counts by topic ("how many messages about X?") are not supported anywhere: the statistics documents say so, and the plan for them is in [Next steps](#next-steps-count-questions-planned-not-built).

## Structure

```
iac/                              # AWS CDK (Python)
├── app.py                        # entry point; env via --context env=<name> (default "dev")
├── config/
│   ├── common.yml                 # model IDs, knowledge bases, flow routes, naming, fargate sizing, common tags
│   ├── dev.yml                    # per-env overrides, deep-merged onto common.yml
│   ├── prompts/                   # prompt text for the flow: classifier template (<<ROUTES>>, {{question}}) and per-route answer templates
│   └── loader.py                  # load_config(env), resource_name(config, base) → "{prefix}-{base}-{suffix}"
└── stacks/rag_stack.py           # wires resources/*.py together; one CfnOutput per resource
    resources/
    ├── resource_s3.py            # document bucket (versioned, DESTROY)
    ├── resource_s3_vectors.py    # vector bucket via AwsCustomResource (S3 Vectors has no CDK L2 yet); each KB adds its own index
    ├── resource_guardrail.py     # CfnGuardrail (politics/impoliteness topics, profanity, all-PII block incl. NAME, fixed "Sorry…" message) + pinned version
    ├── resource_knowledge_base.py # standard Bedrock KBs, each with its own S3 Vectors index (AMAZON_BEDROCK_* non-filterable keys), service role
    │                              #   and S3 data source on the documents bucket: the primary one (knowledge_base, container UI) plus one per
    │                              #   knowledge_base.additional entry (summary = the scraper's collection statistics, NONE chunking)
    ├── resource_flow.py          # Bedrock Flow + version + alias + service role: classifier prompt → condition → one KB node per flow.routes entry
    └── resource_fargate.py       # ECS Fargate + ALB for the container UI — defined but not deployed

app/
├── scraper/                       # containerized batch app: downloads CBP CSMS messages (live feed + archive PDFs)
│   ├── scraper/                   #   and uploads to S3 one at a time with Bedrock Knowledge Base .metadata.json sidecars, then syncs
│   │                              #   the messages KB (kb_index.py); summary.py then writes the collection statistics documents for the summary KB
│   └── README.md                  #   full source map, metadata schema, and usage — read this before touching the scraper
└── ui/
    └── container/                 # local-only container UI (Dockerfile, docker-compose.yml, backend/, frontend/)
        ├── backend/kb_report.py   # read-only report: KB document status + sidecar metadata vs. what the index actually stores
        └── backend/flow_ask.py    # ask the deployed flow one question (InvokeFlow; --trace shows the route taken)
```

## Key conventions

- **Config-driven naming/models**: nothing is hardcoded — model IDs, memory/timeout, and resource name parts all come from `iac/config/common.yml` (overridden per-env by `<env>.yml`). Check `common.yml` before assuming a model ID; it has drifted from what's described in `iac/README.md` before.
- **One ingestion path: knowledge bases.** `app/scraper` uploads under a KB source prefix with `.metadata.json` sidecars (`csms/1/` for messages, `csms-summary/1/` for the summary), then starts that KB's sync and waits for it (`sync_knowledge_base` in `scraper/kb_index.py`). So one scrape command takes a message from CBP into the index: upload, messages KB sync, summary rebuild, summary KB sync. Checked end to end on 2026-11-16, after the Lambda pipeline was removed from the stack: `docker compose run --rm scraper all --since 2026-08-01` uploaded 143 messages, the sync indexed them and their 11 attachments, and the summary was rebuilt for 243 messages. That run also reports `failed=1`, and so will every `all` run that covers 2026: ref 67154332 in the 2026 archive PDF is a TIN bulletin, not a CSMS message, and the PDF gives it no Sent date, so each run fetches it and rejects it. The messages sync needs `KNOWLEDGE_BASE_ID` and `KB_DATA_SOURCE_ID`; `--no-sync` skips it and `--reindex` replaces it with direct ingestion of each message. The KBs' S3 data sources are defined on the documents bucket, each on its own prefix (`resource_knowledge_base.py`), and nothing else reads the bucket.
- **Knowledge bases**: `knowledge_base` in `common.yml` is the primary KB (routes call it `primary`). Its construct IDs and names are fixed, so never rename them: CloudFormation would replace the KB and drop its index. Each `knowledge_base.additional.<key>` creates `<Key>KnowledgeBase*` resources and `<Key>KnowledgeBaseId` / `...DataSourceId` / `...IndexName` outputs. Source prefixes must not overlap (synth fails if they do). Chunking is fixed when a data source is created.
- **Flow routes**: a route name is the classifier's reply, a condition name and part of two node names, so it is lowercase letters, digits and single underscores. Don't call a route `summary`: with that name the classifier sent "give me a summary of…" requests to it (5 of 6 in testing), which is why the route is `statistics` while its KB is `summary`. Route descriptions decide the routing, so re-check classification after editing them (48 tuning questions and 26 held-out ones all routed correctly with Nova Micro on 2026-11-13). Bedrock allows 17 routes with this layout; condition nodes are chained automatically past four non-default routes. The flow version is republished when the definition, the guardrail version or a KB it reads changes.
- **Collection summary** (`app/scraper/scraper/summary.py`): every number is computed by code from the stored messages; each document is one chunk (under 12,000 characters) and states what it does not contain (topic counts, a country within one month, combined counts for several countries). `flow.routes.statistics.num_results` must stay at or above the number of summary documents (2 + one per year of messages), so the model always sees all of them. The scraper writes it only when `SUMMARY_PREFIX` is set, which must match `knowledge_base.additional.summary.source_prefix`.
- **Models that work in this account** (checked 2026-11-13, us-east-1): `us.anthropic.claude-sonnet-4-6`, the `knowledge_base.generation_model_id` default, is rejected by both `Converse` and `RetrieveAndGenerate` ("Model use case details have not been submitted": the Anthropic use-case form). The local container UI therefore runs on `us.meta.llama3-3-70b-instruct-v1:0`, set in its `.env.local`. `RetrieveAndGenerate` on the KB with the guardrail works with Nova Pro, Nova Lite, Nova Micro, Nova 2 Lite and Claude Haiku 4.5; Nova Premier v1 is end-of-life. The flow uses Nova Micro (classifier) and Nova Pro (answers; the one Nova model whose card lists Flows as supported).
- **Guardrail state** (checked 2026-11-16): the pinned version is **3**, the repo's strict policy. The flow uses it, and `ContainerUiEnv` prints it. Version 1, the June policy that anonymized EMAIL/PHONE/NAME and had no topics, was deleted when the 2026-11-16 deploy replaced it (version 2 was created and removed by a deploy that rolled back the same day). Under the strict policy the guardrail blocks any question or answer that names a country (detected as ADDRESS) and, in some phrasings, a CSMS number (detected as PHONE: "CSMS #69415934" was flagged, "CSMS # 69415934" in a table was not). Seen through the deployed flow: "How many messages mention Brazil?" is refused at the question, and "What does the guidance say about tariffs on patented pharmaceuticals?" is refused at the answer, which names the United Kingdom and four other countries. EMAIL blocks too: an answer about Harmonized System Update 2627 (CSMS 70435061) was refused on 2026-11-16 because the message text carries CBP's own contact addresses (`traderemedy@cbp.dhs.gov`, `HTSAdmin@cbp.dhs.gov`) and its CSMS number, which was detected as PHONE. Whether ADDRESS, PHONE and EMAIL stay blocked is the user's decision; URL was already left out for the same kind of reason.
- **UI colours: CBP Style Guide palette only** (https://us-cbp.github.io/cbp-style-guide/docs/foundation/colors.html). The stylesheet is `app/ui/container/frontend/src/index.css`, with every colour as a `--cbp-*` token at the top; USWDS components used on the page are recoloured there, including the focus ring (no USWDS default colours such as the bright-blue `#2491ff` ring). Focus rings use `--cbp-primary`, or `--cbp-primary-light` inside `.cbp-header` / `.cbp-identifier`. The only values not in the guide are white, the `#003865` hover shade and neutral rgba shadows. Don't add other palettes.
- **Rules of Behavior gate**: a native `<dialog>` modal (`.rob-modal`) blocks the page until ACCEPT, remembered per browser tab in `sessionStorage` (`rulesOfBehaviorAccepted`). It is client-side only — the APIs do not check it. The text is plain text in `app/ui/container/frontend/src/rules-of-behavior.txt` (bundled with a Vite `?raw` import, because the backend's SPA fallback would answer a runtime fetch with `index.html`).
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

Bedrock model access must be enabled in the AWS Console under **Bedrock → Model access** for the models set in `iac/config/common.yml`: `knowledge_base.embedding_model_id` and `generation_model_id`, `flow.classifier_model_id` and `generation_model_id`.

> Note: the S3 document bucket is created with `RemovalPolicy.DESTROY` in `resource_s3.py` — `cdk destroy` will delete uploaded documents along with it (the `iac/README.md` claim that it's `RETAIN` is stale).

### Local container UI (`app/ui/container/`)

Runs the FastAPI/React UI locally against real AWS (Bedrock Knowledge Base, Bedrock, Guardrails) — no local mocking, LocalStack is not supported (doesn't implement Bedrock/S3 Vectors).

```bash
cd app/ui/container
cp .env.local.example .env.local     # set KNOWLEDGE_BASE_ID, AWS_PROFILE (optionally GUARDRAIL_ID)
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
docker compose run --rm scraper all --since 2026-01-01       # feed + all archives, one command
docker compose run --rm scraper current                      # live feed (100 latest, hard cap)
docker compose run --rm scraper archive 2021-2025 --limit 200
python -m scraper message 69302472 --dry-run                 # no AWS needed, writes to ./out
docker compose run --rm scraper summary                      # rebuild the collection statistics from everything in S3 (+ sync the summary KB)
python -m scraper summary --dry-run                          # same from ./out, no AWS
```

Scrape runs that upload messages sync the messages KB themselves when `KNOWLEDGE_BASE_ID` and `KB_DATA_SOURCE_ID` are set (`--no-sync` skips it; `--reindex` ingests each message directly instead), and rebuild the summary when `SUMMARY_PREFIX` is set (`--no-summary` skips it).

### Bedrock Knowledge Bases

`cdk deploy` creates the standard KB (`knowledge_base` section of `common.yml`) and prints `KnowledgeBaseId` / `KnowledgeBaseDataSourceId`, plus the summary KB (`knowledge_base.additional.summary`) as `SummaryKnowledgeBaseId` / `SummaryKnowledgeBaseDataSourceId`. Both start empty. Point both `.env.local` files at the stack, then run the scraper, which fills and syncs both:

```bash
# app/ui/container/.env.local: paste the ContainerUiEnv output (KNOWLEDGE_BASE_ID, BEDROCK_MODEL_ARN, GUARDRAIL_ID, GUARDRAIL_VERSION, FLOW_ID, FLOW_ALIAS_ID, FLOW_BACKEND_ROUTES)
# app/scraper/.env.local:      paste the ScraperEnv output (S3_BUCKET_NAME, S3_PREFIX, KNOWLEDGE_BASE_ID, KB_DATA_SOURCE_ID, SUMMARY_PREFIX, SUMMARY_KNOWLEDGE_BASE_ID, SUMMARY_KB_DATA_SOURCE_ID)
cd app/scraper && docker compose run --rm scraper all --since 2026-01-01   # uploads, syncs the messages KB, writes the summary, syncs the summary KB

# To sync a data source yourself (for example after a --no-sync run):
aws bedrock-agent start-ingestion-job --profile <AWS_PROFILE> \
  --knowledge-base-id <KnowledgeBaseId> --data-source-id <KnowledgeBaseDataSourceId>
aws bedrock-agent list-ingestion-jobs --profile <AWS_PROFILE> \
  --knowledge-base-id <KnowledgeBaseId> --data-source-id <KnowledgeBaseDataSourceId>   # wait for COMPLETE
```

A guardrail cannot be attached to a KB itself; the caller supplies it. The stack's guardrail (ID + pinned version) is what the container UI's `RetrieveAndGenerate` call and the flow's knowledge base nodes use — `knowledge_base.generation_model_id` in `common.yml` is the container UI's generation model and what the (disabled) Fargate task role is scoped to. Keep it in sync with the fallback default model in `backend/main.py` (both `us.anthropic.claude-sonnet-4-6` today).

Report what the KB has actually indexed and which sidecar attributes are queryable (read-only; reconciles the KB document list, the S3 sidecars, and the vectors in the index):

```bash
cd app/ui/container
python backend/kb_report.py                          # table; add --format json|csv -o <file>, --no-vectors to skip the index scan
```

The KBs embed with `knowledge_base.embedding_model_id` (Titan Text v2, on-demand). The old managed KB `QFZ5VF1FZN` is not managed by CDK and can be deleted from the console once the new one answers.

### Bedrock Flow

Ask the deployed flow a question (the AWS CLI cannot call `InvokeFlow`, a streaming API). `--trace` prints the classifier's reply and the condition that matched:

```bash
cd app/ui/container                                  # .env.local needs FLOW_ID and FLOW_ALIAS_ID
python backend/flow_ask.py --trace "How many CSMS messages are there?"
python backend/flow_ask.py --alias-id TSTALIASID "What changed for Entry Type 13?"   # the working draft instead of the published version
```

To add a category, edit `iac/config/common.yml` only: a knowledge base under `knowledge_base.additional` and a route under `flow.routes` (`iac/README.md` has the steps).

### Listing available Bedrock models

```bash
aws bedrock list-foundation-models \
  --profile <AWS_PROFILE> \
  --query 'modelSummaries[?contains(modelId, `embed`)].modelId' \
  --output table
```

## Next steps: count questions (planned, not built)

**Status, 2026-11-16.** The user chose a simpler first version than the design below (2026-11-13): the scraper writes collection statistics into a second KB, and a Bedrock Flow routes count questions to it (see Architecture). It is deployed, and the summary KB holds the statistics for the 243 stored messages (sent 2026-05-14 to 2026-11-16, as of 2026-11-16). It covers counts by sent date, country and attachments. The design below is still the plan for what that version cannot do: counts by topic, counts over an arbitrary date range, and combinations such as a country within one month.

Open decisions for the flow (user):
1. Decided 2026-11-17 (user): the container backend calls the flow for every question. It takes the flow's answer for `statistics` and answers `messages` with its own call, keeping the date filter and sources (see Architecture).
2. Keep ADDRESS, PHONE and EMAIL in the guardrail's blocked PII types? They block country names, CSMS numbers and CBP's own contact addresses (see Key conventions), which the statistics answers and many message answers contain.
3. `knowledge_base.generation_model_id` is still Claude Sonnet 4.6, which this account cannot invoke. Submit the Anthropic use-case form, or switch the default to a Nova model (they pass the `RetrieveAndGenerate` test).
4. Stop the flow writing an answer the UI discards? For a `messages` question the backend needs only the route, but closing the `InvokeFlow` stream does not stop the flow: its `Answer_messages` node still runs. On 2026-11-17, 7 UI questions (5 statistics, 2 messages) produced 7 Nova Pro invocations. The cost is one Nova Pro `RetrieveAndGenerate` plus a guardrail check per ordinary UI question, about half a cent. The latency cost is zero. Removing it means changing the flow, for example a second, classifier-only flow built from the same `flow` config, then a deploy.

The deployed flow was invoked end to end on 2026-11-16 with eight questions. All eight took the expected route. The total, the June 2026 count, the attachment count, the dates covered and the ten latest messages matched the summary documents, and a question about ACE maintenance was answered from the messages KB. The other two were refused by the guardrail (decision 2). Later that day, after the Lambda pipeline was removed and 143 newer messages were scraped, seven more questions took the expected routes. The five statistics answers matched the rebuilt summary (243 messages, 56 in September 2026, 18 with attachments, 2026-05-14 to 2026-11-16, the ten latest), a question about a message sent that day was answered from the messages KB, and one about Harmonized System Update 2627 was refused by the guardrail (decision 2 again).

**Requirement** (user, 2026-11-02): users will ask count questions. Examples: "how many CSMS messages are there?", "how many in 2025 / mentioning Brazil / with attachments?", and "how many messages about X?" for **any** topic, not one from a fixed list.

The container UI's query path cannot answer these today:
- `retrieve_and_generate` only sees the top `KB_NUM_RESULTS` chunks (default 8; KB retrieval returns at most 100).
- S3 Vectors has no count API.

So the model counts the chunks it was shown, or guesses.

**Recommended design: a count path alongside the existing call.** Ordinary questions keep the single `retrieve_and_generate` call unchanged.

1. **Route.** One planner call returns `{intent: answer|count|list, topic, terms, date_from, date_to, countries, has_attachments, group_by}`. It uses Claude Haiku 5.5 (`anthropic.claude-haiku-5-5` on Bedrock) through the Anthropic SDK's `AnthropicBedrockMantle` client, with structured output and effort `low`. `answer` goes to `retrieve_and_generate`. Dates in the question are intersected with the UI date range.
2. **Filter** the catalog (one row per message; where it comes from is below) exactly on dates, countries and attachments. With no topic, that count is the answer and no more model calls are made.
3. **Rank** every message left in scope by embedding similarity to the topic, using Titan v2 (the KB's embedding model), plus keyword hits on `terms`. Ranking the whole scope rather than a top-K is what gets past the 100-result cap.
4. **Check.** Haiku marks candidates `about` / `related` / `no`:
   - about 50 per call, up to 4 calls in parallel, working down the ranking
   - stop when a batch has ≤ 1 match
   - check every message when ≤ 300 are in scope
   - cap at 1,500

   Verdicts are cached per (catalog version, topic, message), so repeat questions give identical numbers.
5. **Answer from a template.** Code computes every number; the model never writes one.
   - Always state coverage, e.g. "**3** messages about ACE outages (15 more related: scheduled maintenance) in this assistant's collection of 100 messages, sent May 14 – Aug 2, 2026".
   - Return the top 20 counted messages as sources ("showing 20 of N") in the same `{answer, sources}` shape, so the frontend doesn't change.
   - Run `ApplyGuardrail` on the question and on the answer, since this path doesn't go through `retrieve_and_generate`'s guardrail.

Estimates: 2–5 s and well under a cent per count question at Haiku 5.5's list price ($0.10 / $0.50 per million input/output tokens; Bedrock's rate may differ).

**Where the catalog comes from. Recommended: the KB's own index.** The backend pages through the KB's S3 Vectors index the way `backend/kb_report.py` `scan_index` does (`list_vectors` with `returnMetadata`, plus `returnData` for the embeddings). It groups chunks by `message_id` and refreshes after each KB sync. Each chunk already carries the sidecar fields, its text (`AMAZON_BEDROCK_TEXT`) and its Titan v2 embedding. So counts match exactly what the KB has indexed, which is what ordinary answers can find, and the scraper doesn't change. Costs:
- The backend reads S3 Vectors directly (`ListVectors` / `GetVectors` on the KB index).
- It relies on the KB's `AMAZON_BEDROCK_*` keys.
- `related_countries` is trimmed by the 1 KB sidecar limit.
- The scan grows with the archive. If it gets slow, save it as a snapshot after each sync.

*Alternative:* the scraper writes `catalog/csms-catalog.sqlite` and gets a `catalog rebuild` command. Each row holds the ID, dates, subject, full country list, attachments, first ~600 characters and a 512-d Titan v2 embedding. `catalog/` is outside every KB source prefix, so nothing indexes it, and this catalog can count messages the KB hasn't synced yet.

**Ruled out as the main mechanism** (don't re-propose):
- *Keyword counting.* Tried in commit `a80e68c` (2026-09-01: a Converse tool loop whose `count_messages` tool did substring matching over a ListVectors manifest), then replaced. It counts mentions, not topics ("issue" matches "Issuer"), and the number depends on which words get picked.
- *Fixed topic tags.* They only cover topics listed in advance. Fine as an add-on for a few common categories.
- *Similarity cut-off without a check.* Scores aren't comparable across topics, so any threshold gives an arbitrary number.
- *Tool-using agent instead of the KB call.* It does the same steps less predictably, and the model writes the numbers.
- *Bedrock structured-data KB* (Redshift text-to-SQL). Keyword `LIKE` matching only, plus Redshift Serverless, Glue and Lake Formation to run.
- *Stats document in the KB.* Pre-computed totals only, and silently missing when retrieval doesn't surface it. Built anyway on 2026-11-13 at the user's direction, as the flow's `statistics` route: a dedicated KB holds only the statistics documents and the route retrieves all of them, which removes the "silently missing" problem. It is still pre-computed totals only.

**Open decisions (user):**
1. Planner/checker model: Haiku 5.5 is recommended (enable it under Bedrock → Model access).
2. Broad topics past the cap (e.g. "about ACE" across all years): say "at least N" (recommended, since every number is then backed by a checked list) or estimate from a sample.
3. Accept two rule changes to the container backend: it reads more than `retrieve_and_generate` (the KB index, or the catalog object), and count questions make extra model calls.
4. Backfill depth: counts only cover what's ingested. On 2026-11-16 the collection held 243 messages (sent 2026-05-14 – 2026-11-16); CBP has published 30k+ since 2011.

**First step:** prototype against the messages already indexed, with about 20 hand-checked count questions (totals, per month, by country, and 10+ topics including ACE outages). That measures accuracy, latency and cost before the real build. When it ships, move this into Architecture and update `.env.local.example`, `common.yml` and the `ContainerUiEnv` output.
