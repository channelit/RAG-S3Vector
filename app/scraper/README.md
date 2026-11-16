# CSMS Scraper

Containerized batch app that downloads CBP **Cargo Systems Messaging Service (CSMS)** messages — current and historical — and uploads them to S3 **one message at a time** (local files are deleted right after each upload), formatted for an **AWS Bedrock Knowledge Base** S3 data source with `.metadata.json` sidecars. After a run that uploaded messages it syncs that Knowledge Base, so the new messages are indexed without a separate step, and rebuilds the **collection summary**: a few statistics documents (message counts by date, country and attachments) for a second Knowledge Base, so that "how many messages…" questions have an exact answer to retrieve.

## Sources (verified August 2026)

| Mode / source | Coverage | How it works |
|---|---|---|
| **`all`** | everything the sources below cover, in one run | live feeds **+** every archive PDF posted on the landing page (preset fallback); dedupes and applies `--since`/`--until` — the recommended way to backfill a date range |
| `current` — GovDelivery widget feed (`USDHSCBP_WIDGET_2/0.json`) | last **100** messages, live (hard cap — no pagination; ~2–3 months of volume) | JSON feed of subject / date / bulletin URL |
| `current` — account RSS feed (`public.govdelivery.com/accounts/USDHSCBP/feed.rss`) | last **~25** USDHSCBP bulletins of every topic — typically only a handful are CSMS | RSS 2.0; non-CSMS items (Newsroom, media releases, TIN/CAMS/PGA) are filtered out by title. Almost always a subset of the widget feed — unioned in as redundancy, and as a fallback if the widget JSONP format changes |
| `archive 2011-2015` | Sept 2011 – Dec 2015 (legacy IDs `YY-NNNNNN`) | PDF hyperlinks point directly at migrated GovDelivery bulletins |
| `archive 2016-2020` | Jan 2016 – Oct 2020 | PDF hyperlinks are `lnks.gd` short links, resolved one-by-one via their meta-refresh page |
| `archive 2021-2025` | Jan 2021 – Dec 2025 | Message IDs parsed from the PDF text table; URL computed from the ID |
| `archive latest-month` / `--discover` | rolling PDF for the current year (posted ~2 months behind — Aug 2026 edition covers through May 2026) | same text-table parsing; `--discover` scrapes the [archive landing page](https://www.cbp.gov/document/publications/csms-archive) for the current PDF set |

Key mechanics: modern CSMS message numbers **are** GovDelivery bulletin IDs, and the public URL is the ID in hex (`CSMS # 69302472` → `.../accounts/USDHSCBP/bulletins/42178c8`). Every bulletin page — including migrated 2011-era ones — keeps its original `CSMS# <id> - <subject>` title and original sent dateline, so the bulletin HTML is the single authoritative metadata source; archive PDFs are used for discovery — though table-format editions also supply each row's **Sent** date, which `--since`/`--until` runs use to skip out-of-range messages without fetching them (it also becomes the sidecar's date fallback when a bulletin page has no parseable dateline).

Coverage note: the feed's 100-message cap and the rolling archive's posting lag normally overlap (feed reaches ~2–3 months back; the rolling PDF trails ~2 months), which is why `all` unions both — run it periodically to stay gap-free.

## What gets uploaded

For each message (example ID `69302472`, prefix `csms/`):

```
csms/69302472/csms-69302472.txt                       # subject + sent date + source URL + body text
csms/69302472/csms-69302472.txt.metadata.json         # Bedrock KB sidecar
csms/69302472/attachments/01-section-301-hts-list.pdf # attachments, original files
csms/69302472/attachments/01-section-301-hts-list.pdf.metadata.json
```

Upload order is: each sidecar before its document, and the main `.txt` document **last** — its presence in S3 marks the message complete, and it is also the skip-check key for re-runs (S3 is the only state store; nothing persists locally).

### Metadata sidecars

Message document:

```json
{
  "metadataAttributes": {
    "doc_type": "csms_message",
    "message_id": "69302472",
    "subject": "GUIDANCE: Section 301 Duties on Certain Products from Brazil",
    "source_url": "https://content.govdelivery.com/accounts/USDHSCBP/bulletins/42178c8",
    "sent_date": "2026-07-21",
    "date_numeric": 20260721,
    "timestamp": 1784669160,
    "related_countries": ["Brazil"]
  }
}
```

Attachment (PDF under a parent message) — carries the **parent message's metadata**:

```json
{
  "metadataAttributes": {
    "doc_type": "csms_attachment",
    "message_id": "69302472",
    "parent_message_id": "69302472",
    "parent_subject": "GUIDANCE: Section 301 Duties on Certain Products from Brazil",
    "parent_source_url": "https://content.govdelivery.com/accounts/USDHSCBP/bulletins/42178c8",
    "attachment_filename": "Section 301 HTS LIST07172026_508c.pdf",
    "attachment_url": "https://content.govdelivery.com/attachments/USDHSCBP/2026/07/21/file_attachments/3721364/Section%20301%20HTS%20LIST07172026_508c.pdf",
    "attachment_index": 1,
    "sent_date": "2026-07-21",
    "date_numeric": 20260721,
    "timestamp": 1784669160,
    "related_countries": ["Brazil"]
  }
}
```

- `date_numeric` (YYYYMMDD) and `timestamp` (Unix seconds) are **numbers**, so KB retrieval filters support `greaterThan`/`lessThan` range queries.
- `related_countries` is a string list detected from subject + body (curated trade-country matcher; "United States" is deliberately excluded — it matches everything).
- Legacy messages keep their original IDs (e.g. `15-000970`) as strings.

## Collection summary (statistics documents)

A vector search only sees the few chunks it retrieves, so it cannot count messages. `scraper/summary.py` pre-computes the counts instead. It reads every stored message (the main `.txt` document and its sidecar) and writes these documents under `SUMMARY_PREFIX`, each with a small sidecar (`doc_type: csms_summary`):

```
csms-summary/1/csms-summary-overview.md     # totals, dates covered, per year, top 20 countries, 10 most recent messages
csms-summary/1/csms-summary-year-2026.md    # one per year: per month, and countries mentioned that year
csms-summary/1/csms-summary-countries.md    # every country or region, all years
```

- **Every number is computed by code** from what is stored. The documents also say what they do not contain: counts by topic ("how many messages about X"), counts for a country within one month, and combined counts for several countries (one message can mention several, so those counts overlap).
- **One document is one chunk.** The summary Knowledge Base's data source uses `NONE` chunking, so each file is written to be retrieved whole and is kept under 12,000 characters.
- **Countries are detected again from the stored text**, not read from the sidecar, because the sidecar's `related_countries` list is trimmed to fit 1 KB. Attachments are the files stored under each message's `attachments/`. Dates are the sidecar's UTC `sent_date`.
- **It is rebuilt from scratch each time** (S3 is the only state) and documents from earlier runs that are no longer produced are deleted. An empty listing never overwrites an existing summary.

When it runs:

| Trigger | What happens |
|---|---|
| `all` / `current` / `archive` / `message` uploaded at least one message, and `SUMMARY_PREFIX` is set | summary rebuilt after the run (`--no-summary` skips it) |
| `python -m scraper summary` | rebuilt on demand (`--no-sync` writes the documents without syncing the Knowledge Base) |
| `python -m scraper summary --dry-run -o out` | no AWS: reads the messages kept in `out/` and writes `out/csms-summary/` |

With `SUMMARY_KNOWLEDGE_BASE_ID` and `SUMMARY_KB_DATA_SOURCE_ID` set, the scraper then runs an ingestion job on the summary data source and waits for it (the caller needs `bedrock:StartIngestionJob` and `bedrock:GetIngestionJob`). Without them it only writes the documents. `SUMMARY_PREFIX` must not overlap `S3_PREFIX`; the scraper refuses to run the summary if it does.

## Usage

### Docker (recommended)

```bash
cd app/scraper
cp .env.local.example .env.local   # set S3_BUCKET_NAME (+ AWS_PROFILE)

docker compose build

# ONE command, feed + archives, within a date range (recommended)
docker compose run --rm scraper all --since 2026-01-01

# Live feeds (widget JSON, last ~100 messages, + account RSS)
docker compose run --rm scraper current

# Backfill an archive era, capped at 200 new messages per run
docker compose run --rm scraper archive 2021-2025 --limit 200

# Everything CBP currently posts on the archive landing page
docker compose run --rm scraper archive --discover

# One specific message
docker compose run --rm scraper message 69302472

# Rebuild the collection summary from everything already in S3
docker compose run --rm scraper summary
```

A run that uploads at least one message then syncs the Knowledge Base and rebuilds the summary, so one command takes a message from CBP to both indexes. `--no-sync` and `--no-summary` skip those steps (see [Bedrock Knowledge Base setup notes](#bedrock-knowledge-base-setup-notes)).

### Local (no Docker)

```bash
cd app/scraper
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Dry run: no AWS needed; files are written to ./out and kept
python -m scraper message 69302472 --dry-run
python -m scraper current --limit 5 --dry-run
python -m scraper summary --dry-run          # statistics documents for what is in ./out

# Real upload
S3_BUCKET_NAME=my-kb-bucket AWS_PROFILE=terraform python -m scraper current
```

### HTTP trigger mode (`serve`)

For deployments where the scraper is triggered via a URL (e.g. Kubernetes):

```bash
docker compose up scraper-api                # compose service with port 8080 published
python -m scraper serve --port 8080          # or: docker compose run --rm -p 8080:8080 scraper serve
```

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness/readiness probe |
| `GET /status` | state of the current/last run (`idle` / `running` / `succeeded` / `failed`) |
| `POST /scrape` | trigger a run; returns `202` + `run_id`, or `409` if a run is already in progress |
| `POST /reindex` | rewrite the KB vectors of documents already in S3 (see [Re-indexing](#re-indexing-the-knowledge-base)); same `202`/`409` semantics |
| `POST /summary` | rebuild the [collection summary](#collection-summary-statistics-documents); body `{}` or `{"no_sync": true}`; same `202`/`409` semantics |

`POST /scrape` bodies mirror the CLI — `mode` is `current` / `archive` / `message`, everything else is optional:

```json
{"mode": "all", "since": "2026-01-01"}
{"mode": "current", "limit": 5}
{"mode": "archive", "sources": ["2021-2025"], "limit": 200}
{"mode": "archive", "discover": true}
{"mode": "message", "targets": ["69302472"], "dry_run": true}
{"mode": "message", "targets": ["69302472"], "force": true, "reindex": true}
{"mode": "current", "no_sync": true, "no_summary": true}
```

`POST /reindex` bodies (all fields optional):

```json
{}                                        every document under S3_PREFIX
{"targets": ["69302472", "69298180"]}     only these messages
{"limit": 10, "dry_run": true}            list documents + sidecar dates, touch nothing
```

Runs execute one at a time in a background thread (the pipeline is deliberately sequential); poll `GET /status` for completion. Invalid arguments are rejected with `400` before a run starts.

### Re-indexing the Knowledge Base

Use this when documents were indexed before their sidecars carried dates (or before the KB honoured sidecar metadata): a date-range query can never match those vectors. Re-indexing needs `KNOWLEDGE_BASE_ID` and `KB_DATA_SOURCE_ID` (IDs, not names) and calls the Bedrock direct-document APIs (`DeleteKnowledgeBaseDocuments`, `IngestKnowledgeBaseDocuments`, `GetKnowledgeBaseDocuments`; the caller needs those `bedrock:` permissions):

1. **Delete** the document's current vectors from the KB.
2. **Re-ingest** the same S3 object with its `.metadata.json` sidecar attached as the document metadata, so the new vectors carry `date_numeric` / `sent_date` / `message_id` / ….

Batches of 10 (the API limit); each batch is polled until it settles. Documents whose sidecar has **no** `date_numeric` are reported and skipped — re-indexing can't invent a date, re-scrape them with `--force --reindex`.

```bash
python -m scraper reindex --dry-run              # list documents + their sidecar dates
python -m scraper reindex --limit 10             # trial on the first 10 documents
python -m scraper reindex                        # everything under S3_PREFIX
python -m scraper reindex 69302472 69298180      # specific messages
python -m scraper message 69302472 --force --reindex     # re-scrape (fresh sidecar) + re-index
python -m scraper all --since 2026-01-01 --force --reindex   # rewrite a whole date range
```

`reindex` mode does **not** contact CBP — it only lists S3, reads each sidecar for its date, and talks to Bedrock. `--reindex` on a scrape mode re-indexes each message right after its files are uploaded, so a `--force --reindex` run rewrites both the S3 objects and their vectors in one pass.

### Useful flags

| Flag | Meaning |
|---|---|
| `--limit N` | stop after N **new** messages uploaded (skips don't count) |
| `--since / --until YYYY-MM-DD` | date-range filter on sent date; out-of-range messages with a known date (feed `pub_date` or an archive PDF's Sent column) are skipped **without** fetching, and whole archive PDFs whose filename years can't intersect the range are skipped in `all` mode |
| `--no-discover` (`all`) | use the built-in archive presets instead of scraping the landing page |
| `--force` | re-process messages already in S3 |
| `--reindex` | after uploading each message, delete + re-ingest its documents in the Bedrock KB (replaces the sync at the end of the run) |
| `--no-sync` | do not sync the Bedrock KB after the run |
| `--no-summary` | do not rebuild the collection summary after the run |
| `--dry-run -o DIR` | no AWS; write and keep files locally |
| `--list` (archive) | print discovered message refs without processing |
| `--delay SECONDS` | politeness delay between HTTP requests (default 0.7) |

## Bedrock Knowledge Base setup notes

- The CDK stack (`iac/resources/resource_knowledge_base.py`) creates a standard KB whose **S3 data source** reads the bucket under `knowledge_base.source_prefix` (`csms/1/` — must match `S3_PREFIX` here); sidecars are picked up automatically by the `<name>.metadata.json` convention (each must stay under **1 KB** for the S3 Vectors-backed KB — the sync job silently *ignores* documents whose sidecar exceeds 1024 bytes; `app/ui/container/backend/kb_report.py` lists them). The stack outputs `KnowledgeBaseId` / `KnowledgeBaseDataSourceId` for `KNOWLEDGE_BASE_ID` / `KB_DATA_SOURCE_ID`.
- The stack also creates a second KB for the collection summary (`knowledge_base.additional.summary`, source prefix `csms-summary/1/` — must match `SUMMARY_PREFIX` here). Its `ScraperEnv` output is a paste-ready copy of every line this scraper needs in `.env.local`.
- Both KBs read from the documents bucket (`cits-rag-s3vector-documents-*`), so that is where the scraper uploads. Each KB indexes only what is under its own source prefix, and nothing else in the stack reads the bucket: a file outside those prefixes is not indexed.
- After a run that uploaded messages, the scraper starts a KB **sync** (one ingestion job on the data source) and waits for it, when `KNOWLEDGE_BASE_ID` and `KB_DATA_SOURCE_ID` are set (the caller needs `bedrock:StartIngestionJob` and `bedrock:GetIngestionJob`). Without them it only uploads, and the data source has to be synced separately. `--no-sync` skips the sync. `--reindex` replaces it: each document is pushed through the direct-ingestion API (with its sidecar metadata) right after its upload. `POST /reindex` does the same for documents already in S3.
- A sync that fails or is still running after 15 minutes ends the run with exit code 1. The uploaded messages stay in S3, and the next sync indexes them.

## Politeness / operational notes

- Sequential, single-connection fetching with a configurable delay (default 0.7 s), retries with exponential backoff on 429/5xx.
- cbp.gov rejects generic client user-agents with 403; the app sends a browser-style UA (configurable via `USER_AGENT`).
- Full-archive backfills are large (30k+ messages since 2011) — use `--limit` to chunk runs; re-runs skip everything already in S3 via `HEAD` checks.
- The 2016–2020 era costs one extra request per message for `lnks.gd` resolution.
