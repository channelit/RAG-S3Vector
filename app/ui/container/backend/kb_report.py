"""Report what the Bedrock Knowledge Base has actually indexed, and which
metadata attributes were published with each document and can be queried.

Three sources are reconciled per document:

  1. the KB's own document list (``ListKnowledgeBaseDocuments``) — index status
     per S3 object (INDEXED / FAILED / ...);
  2. the ``<object>.metadata.json`` sidecar in S3 — what the scraper *intended*
     to publish (``metadataAttributes``);
  3. the vectors in the KB's S3 Vectors index (``ListVectors`` with metadata) —
     what is *actually* stored per chunk, i.e. the filterable keys that a
     ``retrievalConfiguration`` metadata filter can use.

A document's metadata counts as "published accurately" when every sidecar
attribute is present on its indexed chunks with the same value.

Usage (from app/ui/container, reads .env.local for KNOWLEDGE_BASE_ID, AWS_PROFILE
and optionally KB_DATA_SOURCE_ID — defaults to the KB's only data source):

    python backend/kb_report.py                       # table on stdout
    python backend/kb_report.py --format json -o kb_report.json
    python backend/kb_report.py --format csv  -o kb_report.csv
    python backend/kb_report.py --no-vectors          # skip the index scan (faster)

Read-only: never writes to S3, the index or the KB.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

SIDECAR_SUFFIX = ".metadata.json"
# Keys Bedrock adds itself; not from the sidecar, but still filterable
SYSTEM_KEY_PREFIX = "x-amz-bedrock-kb-"
# Non-filterable keys registered on the index (see iac/resources/resource_knowledge_base.py)
NON_FILTERABLE = {"AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"}


@dataclass
class DocReport:
    uri: str
    status: str
    status_reason: str
    updated_at: str
    doc_type: str = ""
    message_id: str = ""
    filename: str = ""
    sidecar_found: bool = False
    sidecar_bytes: int = 0
    sidecar: dict[str, Any] = field(default_factory=dict)
    chunks: int = 0
    indexed_keys: list[str] = field(default_factory=list)
    missing_keys: list[str] = field(default_factory=list)      # in sidecar, not in index
    mismatched: dict[str, Any] = field(default_factory=dict)    # key -> {"sidecar": v, "indexed": v}
    metadata_ok: bool | None = None                             # None = not checked (no vectors)


# ----------------------------------------------------------------------------- helpers

def load_env_file(path: Path) -> None:
    """KEY=VALUE lines; never overrides variables already set in the environment."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def split_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    return parsed.netloc, parsed.path.lstrip("/")


def normalise(value: Any) -> Any:
    """S3 Vectors returns numbers as float and lists stringified; compare loosely."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    return str(value)


def display(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def paginate(call, result_key: str, **kwargs):
    token = None
    while True:
        response = call(**kwargs, **({"nextToken": token} if token else {}))
        yield from response.get(result_key, [])
        token = response.get("nextToken")
        if not token:
            break


# ----------------------------------------------------------------------------- collectors

def kb_targets(agent, kb_id: str, ds_id: str) -> tuple[str, str, str, list[str]]:
    """(vector bucket, index name, source bucket, inclusion prefixes)"""
    kb = agent.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]
    storage = kb["storageConfiguration"]
    if storage["type"] != "S3_VECTORS":
        sys.exit(f"KB {kb_id} storage is {storage['type']}; this report only reads S3 Vectors indexes")
    # arn:aws:s3vectors:<region>:<acct>:bucket/<bucket>/index/<index>
    _, bucket, _, index = storage["s3VectorsConfiguration"]["indexArn"].split(":")[-1].split("/")
    ds = agent.get_data_source(knowledgeBaseId=kb_id, dataSourceId=ds_id)["dataSource"]
    s3cfg = ds["dataSourceConfiguration"]["s3Configuration"]
    source_bucket = s3cfg["bucketArn"].split(":::")[-1]
    return bucket, index, source_bucket, s3cfg.get("inclusionPrefixes", [])


def list_documents(agent, kb_id: str, ds_id: str) -> list[DocReport]:
    docs = []
    for d in paginate(agent.list_knowledge_base_documents, "documentDetails",
                      knowledgeBaseId=kb_id, dataSourceId=ds_id, maxResults=1000):
        uri = d["identifier"]["s3"]["uri"]
        docs.append(DocReport(
            uri=uri,
            status=d["status"],
            status_reason=d.get("statusReason", ""),
            updated_at=d["updatedAt"].isoformat() if hasattr(d["updatedAt"], "isoformat") else str(d["updatedAt"]),
            filename=uri.rsplit("/", 1)[-1],
        ))
    return sorted(docs, key=lambda x: x.uri)


def s3_objects_not_in_kb(s3, source_bucket: str, prefixes: list[str], docs: list[DocReport]) -> list[dict[str, Any]]:
    """Documents present in S3 under the data source's prefixes that the KB has
    no record of — e.g. skipped during sync because the sidecar was oversized."""
    known = {d.uri for d in docs}
    sizes: dict[str, int] = {}
    paginator = s3.get_paginator("list_objects_v2")
    for prefix in prefixes or [""]:
        for page in paginator.paginate(Bucket=source_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                sizes[obj["Key"]] = obj["Size"]
    missing = []
    for key, size in sorted(sizes.items()):
        if key.endswith(SIDECAR_SUFFIX) or key.endswith("/"):
            continue
        uri = f"s3://{source_bucket}/{key}"
        if uri in known:
            continue
        missing.append({"uri": uri, "bytes": size, "sidecar_bytes": sizes.get(key + SIDECAR_SUFFIX)})
    return missing


def attach_sidecars(s3, docs: list[DocReport]) -> None:
    for doc in docs:
        bucket, key = split_s3_uri(doc.uri)
        try:
            obj = s3.get_object(Bucket=bucket, Key=key + SIDECAR_SUFFIX)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                continue
            raise
        body = obj["Body"].read()
        doc.sidecar_found = True
        doc.sidecar_bytes = len(body)
        try:
            doc.sidecar = json.loads(body).get("metadataAttributes", {}) or {}
        except json.JSONDecodeError:
            doc.sidecar = {"_error": "sidecar is not valid JSON"}
        doc.doc_type = str(doc.sidecar.get("doc_type", ""))
        doc.message_id = str(doc.sidecar.get("message_id", ""))


def doc_identity(attrs: dict[str, Any]) -> tuple[str, str, str]:
    """Stable key linking a chunk's metadata back to its sidecar/document."""
    return (
        str(attrs.get("doc_type", "")),
        str(display(normalise(attrs.get("message_id", "")))),
        str(attrs.get("attachment_filename", "")),
    )


def scan_index(s3vectors, vector_bucket: str, index: str, docs: list[DocReport]) -> dict[str, Counter]:
    """Group every chunk's metadata onto its document; return key usage stats."""
    by_identity = {doc_identity(d.sidecar): d for d in docs if d.sidecar_found}
    by_uri = {d.uri: d for d in docs}
    seen: dict[str, dict[str, Any]] = defaultdict(dict)   # doc.uri -> merged indexed metadata
    key_docs: dict[str, set[str]] = defaultdict(set)
    key_types: dict[str, Counter] = defaultdict(Counter)
    orphan_chunks = 0

    for vec in paginate(s3vectors.list_vectors, "vectors",
                        vectorBucketName=vector_bucket, indexName=index, returnMetadata=True, maxResults=500):
        meta = vec.get("metadata") or {}
        doc = None
        # Prefer the source URI Bedrock records inside AMAZON_BEDROCK_METADATA
        try:
            inner = json.loads(meta.get("AMAZON_BEDROCK_METADATA") or "{}")
            uri = inner.get("x-amz-bedrock-kb-source-uri") or inner.get("source")
            doc = by_uri.get(uri) if uri else None
        except (TypeError, json.JSONDecodeError):
            pass
        if doc is None:
            doc = by_identity.get(doc_identity(meta))
        if doc is None:
            orphan_chunks += 1
            continue
        doc.chunks += 1
        for k, v in meta.items():
            if k in NON_FILTERABLE:
                continue
            seen[doc.uri].setdefault(k, v)
            key_docs[k].add(doc.uri)
            key_types[k][type(v).__name__] += 1

    for doc in docs:
        indexed = seen.get(doc.uri)
        if indexed is None:
            continue
        doc.indexed_keys = sorted(indexed)
        if not doc.sidecar_found:
            continue
        for k, v in doc.sidecar.items():
            if k not in indexed:
                doc.missing_keys.append(k)
            elif normalise(v) != normalise(indexed[k]):
                doc.mismatched[k] = {"sidecar": v, "indexed": display(indexed[k])}
        doc.metadata_ok = not doc.missing_keys and not doc.mismatched

    return {
        "key_docs": Counter({k: len(v) for k, v in key_docs.items()}),
        "key_types": key_types,
        "orphans": Counter({"chunks": orphan_chunks}),
    }


# ----------------------------------------------------------------------------- output

def build_summary(docs: list[DocReport], stats: dict | None, targets: tuple,
                  s3_missing: list[dict[str, Any]]) -> dict[str, Any]:
    vector_bucket, index, source_bucket, prefixes = targets
    summary: dict[str, Any] = {
        "source_bucket": source_bucket,
        "inclusion_prefixes": prefixes,
        "vector_bucket": vector_bucket,
        "index": index,
        "documents": len(docs),
        "by_status": dict(Counter(d.status for d in docs)),
        "by_doc_type": dict(Counter(d.doc_type or "(no sidecar)" for d in docs)),
        "sidecar_missing": [d.uri for d in docs if not d.sidecar_found],
        "s3_not_in_kb": s3_missing,
        "not_indexed": [
            {"uri": d.uri, "status": d.status, "reason": d.status_reason}
            for d in docs if d.status != "INDEXED"
        ],
    }
    if stats:
        keys = stats["key_docs"]
        summary["chunks"] = sum(d.chunks for d in docs)
        summary["orphan_chunks"] = stats["orphans"]["chunks"]
        summary["queryable_keys"] = {
            k: {
                "documents": n,
                "type": "/".join(sorted(stats["key_types"][k])),
                "source": "bedrock" if k.startswith(SYSTEM_KEY_PREFIX) else "sidecar",
            }
            for k, n in sorted(keys.items())
        }
        summary["metadata_accurate"] = sum(1 for d in docs if d.metadata_ok)
        summary["metadata_inaccurate"] = [
            {"uri": d.uri, "missing": d.missing_keys, "mismatched": d.mismatched}
            for d in docs if d.metadata_ok is False
        ]
        summary["indexed_without_vectors"] = [
            d.uri for d in docs if d.status == "INDEXED" and d.chunks == 0
        ]
    return summary


def print_table(docs: list[DocReport], summary: dict[str, Any], with_vectors: bool) -> None:
    head = ["message_id", "doc_type", "file", "status", "date_numeric", "sidecar_B"]
    if with_vectors:
        head += ["chunks", "metadata_ok"]
    rows = []
    for d in docs:
        row = [
            d.message_id, d.doc_type, d.filename[:48], d.status,
            display(d.sidecar.get("date_numeric", "")), d.sidecar_bytes if d.sidecar_found else "-",
        ]
        if with_vectors:
            row += [d.chunks, {True: "yes", False: "NO", None: "?"}[d.metadata_ok]]
        rows.append([str(c) for c in row])
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(head)]
    line = "  ".join(h.ljust(w) for h, w in zip(head, widths))
    print(line)
    print("-" * len(line))
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))

    print()
    print(f"Source:  s3://{summary['source_bucket']}/  prefixes={summary['inclusion_prefixes']}")
    print(f"Index:   {summary['vector_bucket']}/{summary['index']}")
    print(f"Docs:    {summary['documents']}  status={summary['by_status']}  types={summary['by_doc_type']}")
    if summary["sidecar_missing"]:
        print(f"No sidecar ({len(summary['sidecar_missing'])}): " + ", ".join(summary["sidecar_missing"]))
    for item in summary["not_indexed"]:
        print(f"NOT INDEXED  {item['uri']}  [{item['status']}] {item['reason']}")
    if summary["s3_not_in_kb"]:
        print(f"In S3 but unknown to the KB ({len(summary['s3_not_in_kb'])}) — usually skipped at sync "
              f"(sidecar over the size limit) or not yet synced:")
        for item in summary["s3_not_in_kb"]:
            print(f"  {item['uri']}  {item['bytes']} B, sidecar {item['sidecar_bytes']} B")
    if with_vectors:
        print(f"Chunks:  {summary['chunks']}  (orphans not matched to a document: {summary['orphan_chunks']})")
        print(f"Metadata published accurately: {summary['metadata_accurate']}/{summary['documents']}")
        for item in summary["metadata_inaccurate"]:
            print(f"  INACCURATE {item['uri']}  missing={item['missing']} mismatched={item['mismatched']}")
        for uri in summary["indexed_without_vectors"]:
            print(f"  INDEXED but no vectors found: {uri}")
        print()
        print("Queryable metadata keys (usable in retrievalConfiguration filters):")
        for k, info in summary["queryable_keys"].items():
            print(f"  {k:<45} {info['type']:<10} {info['documents']:>4} docs  ({info['source']})")


def write_json(path: Path | None, docs: list[DocReport], summary: dict[str, Any]) -> None:
    payload = {"summary": summary, "documents": [asdict(d) for d in docs]}
    text = json.dumps(payload, indent=2, default=str)
    if path:
        path.write_text(text)
    else:
        print(text)


def write_csv(path: Path | None, docs: list[DocReport]) -> None:
    sidecar_keys = sorted({k for d in docs for k in d.sidecar})
    head = ["uri", "status", "status_reason", "updated_at", "sidecar_found", "sidecar_bytes",
            "chunks", "metadata_ok", "missing_keys", "mismatched"] + [f"meta.{k}" for k in sidecar_keys]
    out = open(path, "w", newline="") if path else sys.stdout
    try:
        writer = csv.writer(out)
        writer.writerow(head)
        for d in docs:
            writer.writerow([
                d.uri, d.status, d.status_reason, d.updated_at, d.sidecar_found, d.sidecar_bytes,
                d.chunks, d.metadata_ok, ";".join(d.missing_keys), json.dumps(d.mismatched) if d.mismatched else "",
            ] + [display(d.sidecar.get(k, "")) for k in sidecar_keys])
    finally:
        if path:
            out.close()


# ----------------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kb-id", default=None, help="defaults to $KNOWLEDGE_BASE_ID")
    parser.add_argument("--data-source-id", default=None, help="defaults to $KB_DATA_SOURCE_ID")
    parser.add_argument("--env-file", type=Path, default=Path(__file__).resolve().parent.parent / ".env.local")
    parser.add_argument("--format", choices=["table", "json", "csv"], default="table")
    parser.add_argument("-o", "--output", type=Path, help="write json/csv here instead of stdout")
    parser.add_argument("--no-vectors", action="store_true",
                        help="skip scanning the S3 Vectors index (no chunk counts / accuracy check)")
    args = parser.parse_args()

    load_env_file(args.env_file)
    kb_id = args.kb_id or os.environ.get("KNOWLEDGE_BASE_ID")
    if not kb_id:
        parser.error("KNOWLEDGE_BASE_ID is required (env, .env.local or --kb-id)")

    session = boto3.Session(
        profile_name=os.environ.get("AWS_PROFILE") or None,
        region_name=os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or None,
    )
    agent = session.client("bedrock-agent")
    s3 = session.client("s3")

    ds_id = args.data_source_id or os.environ.get("KB_DATA_SOURCE_ID")
    if not ds_id:
        # Fall back to the KB's only data source (the CDK stack creates exactly one)
        sources = list(paginate(agent.list_data_sources, "dataSourceSummaries", knowledgeBaseId=kb_id))
        if len(sources) != 1:
            parser.error(f"KB {kb_id} has {len(sources)} data sources; pass --data-source-id or set KB_DATA_SOURCE_ID")
        ds_id = sources[0]["dataSourceId"]

    targets = kb_targets(agent, kb_id, ds_id)
    docs = list_documents(agent, kb_id, ds_id)
    attach_sidecars(s3, docs)
    s3_missing = s3_objects_not_in_kb(s3, targets[2], targets[3], docs)
    stats = None if args.no_vectors else scan_index(session.client("s3vectors"), targets[0], targets[1], docs)
    summary = build_summary(docs, stats, targets, s3_missing)

    if args.format == "table":
        print_table(docs, summary, with_vectors=stats is not None)
        if args.output:
            args.output.write_text(json.dumps({"summary": summary, "documents": [asdict(d) for d in docs]},
                                              indent=2, default=str))
    elif args.format == "json":
        write_json(args.output, docs, summary)
    else:
        write_csv(args.output, docs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
