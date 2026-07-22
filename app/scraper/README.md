# CSMS Scraper

Containerized batch app that downloads CBP **Cargo Systems Messaging Service (CSMS)** messages — current and historical — and uploads them to S3 **one message at a time** (local files are deleted right after each upload), formatted for an **AWS Bedrock Knowledge Base** S3 data source with `.metadata.json` sidecars.

## Sources (verified July 2026)

| Mode / source | Coverage | How it works |
|---|---|---|
| `current` — GovDelivery widget feed (`USDHSCBP_WIDGET_2/0.json`) | last ~100 messages, live | JSON feed of subject / date / bulletin URL |
| `archive 2011-2015` | Sept 2011 – Dec 2015 (legacy IDs `YY-NNNNNN`) | PDF hyperlinks point directly at migrated GovDelivery bulletins |
| `archive 2016-2020` | Jan 2016 – Oct 2020 | PDF hyperlinks are `lnks.gd` short links, resolved one-by-one via their meta-refresh page |
| `archive 2021-2025` | Jan 2021 – Dec 2025 | Message IDs parsed from the PDF text table; URL computed from the ID |
| `archive latest-month` / `--discover` | rolling monthly PDFs | same text-table parsing; `--discover` scrapes the [archive landing page](https://www.cbp.gov/document/publications/csms-archive) for the current PDF set |

Key mechanics: modern CSMS message numbers **are** GovDelivery bulletin IDs, and the public URL is the ID in hex (`CSMS # 69302472` → `.../accounts/USDHSCBP/bulletins/42178c8`). Every bulletin page — including migrated 2011-era ones — keeps its original `CSMS# <id> - <subject>` title and original sent dateline, so the bulletin HTML is the single authoritative metadata source; archive PDFs are used for discovery only.

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

## Usage

### Docker (recommended)

```bash
cd app/scraper
cp .env.local.example .env.local   # set S3_BUCKET_NAME (+ AWS_PROFILE)

docker compose build

# Live feed (last ~100 messages)
docker compose run --rm scraper current

# Backfill an archive era, capped at 200 new messages per run
docker compose run --rm scraper archive 2021-2025 --limit 200

# Everything CBP currently posts on the archive landing page
docker compose run --rm scraper archive --discover

# One specific message
docker compose run --rm scraper message 69302472
```

### Local (no Docker)

```bash
cd app/scraper
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Dry run: no AWS needed; files are written to ./out and kept
python -m scraper message 69302472 --dry-run
python -m scraper current --limit 5 --dry-run

# Real upload
S3_BUCKET_NAME=my-kb-bucket AWS_PROFILE=terraform python -m scraper current
```

### Useful flags

| Flag | Meaning |
|---|---|
| `--limit N` | stop after N **new** messages uploaded (skips don't count) |
| `--since / --until YYYY-MM-DD` | date-range filter on sent date |
| `--force` | re-process messages already in S3 |
| `--dry-run -o DIR` | no AWS; write and keep files locally |
| `--list` (archive) | print discovered message refs without processing |
| `--delay SECONDS` | politeness delay between HTTP requests (default 0.7) |

## Bedrock Knowledge Base setup notes

- Point the KB **S3 data source** at the bucket with inclusion prefix `csms/`; sidecars are picked up automatically by the `<name>.metadata.json` convention (each must stay <10 KB — enforced by the app).
- **Do not** upload into the existing `cits-rag-s3vector-documents-*` bucket: its `ObjectCreated` notification feeds the S3 Vectors ingestion Lambda, which would try to ingest every sidecar too.
- After a scraper run, start a KB **sync/ingestion job** to index the new objects.

## Politeness / operational notes

- Sequential, single-connection fetching with a configurable delay (default 0.7 s), retries with exponential backoff on 429/5xx.
- cbp.gov rejects generic client user-agents with 403; the app sends a browser-style UA (configurable via `USER_AGENT`).
- Full-archive backfills are large (30k+ messages since 2011) — use `--limit` to chunk runs; re-runs skip everything already in S3 via `HEAD` checks.
- The 2016–2020 era costs one extra request per message for `lnks.gd` resolution.
