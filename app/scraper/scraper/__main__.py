"""CLI entry point.

    python -m scraper all      [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--limit N]
    python -m scraper current  [--limit N]
    python -m scraper archive  [SOURCE ...] [--discover] [--list] [--limit N]
    python -m scraper message  ID_OR_URL [ID_OR_URL ...]
    python -m scraper serve    [--host 0.0.0.0] [--port 8080]

`all` is the one-command mode: it unions the live feed with every archive PDF
currently posted on the CBP landing page (falling back to the built-in
presets if discovery fails) and processes everything in the requested date
range. SOURCE is a preset name (2011-2015, 2016-2020, 2021-2025,
latest-month), an archive-PDF URL, or a local PDF path. Common flags:
--dry-run, --output-dir, --force, --since/--until YYYY-MM-DD, --bucket,
--prefix.
"""

import argparse
import logging
import sys
from datetime import datetime

from .archive_pdf import (
    KNOWN_ARCHIVES,
    archive_filename_years,
    discover_archive_pdfs,
    refs_from_archive_pdf,
)
from .config import Settings
from .csms import MessageRef, bulletin_url_for_id, canonical_bulletin_url
from .feed import list_feed_messages
from .pipeline import Pipeline
from .web import WebClient

logger = logging.getLogger("scraper")


def _parse_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scraper",
        description="Download CBP CSMS messages and upload them to S3 with "
                    "Bedrock Knowledge Base metadata sidecars.",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    def common(p: argparse.ArgumentParser):
        p.add_argument("--limit", type=int, default=None,
                       help="stop after this many NEW messages are uploaded/written")
        p.add_argument("--since", type=_parse_date, default=None, metavar="YYYY-MM-DD",
                       help="only messages sent on/after this date")
        p.add_argument("--until", type=_parse_date, default=None, metavar="YYYY-MM-DD",
                       help="only messages sent on/before this date")
        p.add_argument("--force", action="store_true",
                       help="re-process messages already present in S3")
        p.add_argument("--dry-run", action="store_true",
                       help="no AWS: write files to --output-dir and keep them")
        p.add_argument("--output-dir", "-o", default="out",
                       help="local output directory for --dry-run (default: out)")
        p.add_argument("--bucket", default=None, help="override S3_BUCKET_NAME")
        p.add_argument("--prefix", default=None, help="override S3_PREFIX (default csms/)")
        p.add_argument("--delay", type=float, default=None,
                       help="override REQUEST_DELAY_SECONDS between HTTP requests")

    p_all = sub.add_parser(
        "all",
        help="live feed + every posted archive PDF in one run (pair with --since/--until)",
    )
    p_all.add_argument("--no-discover", action="store_true",
                       help="use the built-in archive presets instead of scraping the landing page")
    p_all.add_argument("--list", action="store_true", dest="list_only",
                       help="list discovered message refs without processing")
    common(p_all)

    p_current = sub.add_parser("current", help="scrape the live feed (last ~100 messages)")
    common(p_current)

    p_archive = sub.add_parser("archive", help="scrape archive PDF(s)")
    p_archive.add_argument("sources", nargs="*",
                           help=f"preset ({', '.join(KNOWN_ARCHIVES)}), PDF URL, or local path")
    p_archive.add_argument("--discover", action="store_true",
                           help="scrape cbp.gov archive landing page for current PDFs")
    p_archive.add_argument("--list", action="store_true", dest="list_only",
                           help="list discovered message refs without processing")
    common(p_archive)

    p_message = sub.add_parser("message", help="process specific message(s)")
    p_message.add_argument("targets", nargs="+", help="numeric CSMS ID or bulletin URL")
    common(p_message)

    p_serve = sub.add_parser("serve", help="run as an HTTP service (POST /scrape, GET /health)")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8080)

    return parser


def _all_archive_sources(args, client: WebClient) -> list[str]:
    """Archive PDFs for `all` mode: landing-page discovery with preset fallback."""
    if args.no_discover:
        return list(KNOWN_ARCHIVES.values())
    try:
        sources = discover_archive_pdfs(client)
    except Exception as exc:
        logger.warning("Archive discovery failed (%s) — falling back to built-in presets", exc)
        sources = []
    return sources or list(KNOWN_ARCHIVES.values())


def collect_refs(args, client: WebClient) -> list[MessageRef]:
    if args.mode == "all":
        # Live feed first (newest messages, precise pub_date hints), then every
        # archive PDF whose filename years could intersect the requested range.
        refs = list_feed_messages(client)
        for source in _all_archive_sources(args, client):
            years = archive_filename_years(source)
            if years and (
                (args.since and max(years) < args.since.year)
                or (args.until and min(years) > args.until.year)
            ):
                logger.info(
                    "Skipping archive %s — filename years %s outside %s..%s",
                    source, sorted(years), args.since or "*", args.until or "*",
                )
                continue
            refs.extend(refs_from_archive_pdf(client, source))

        # Feed and the rolling monthly archive overlap by design; keep first sighting.
        seen: set[str] = set()
        unique: list[MessageRef] = []
        for ref in refs:
            key = ref.message_id or ref.url or ref.lnks_url
            if key in seen:
                continue
            seen.add(key)
            unique.append(ref)
        return unique

    if args.mode == "current":
        return list_feed_messages(client)

    if args.mode == "archive":
        sources = list(args.sources)
        if args.discover:
            sources += discover_archive_pdfs(client)
        if not sources:
            print("No archive source given. Presets:")
            for name, url in KNOWN_ARCHIVES.items():
                print(f"  {name:14s} {url}")
            print("Or pass a PDF URL / local path, or use --discover.")
            raise SystemExit(2)
        refs: list[MessageRef] = []
        for source in sources:
            resolved = KNOWN_ARCHIVES.get(source, source)
            refs.extend(refs_from_archive_pdf(client, resolved))
        return refs

    # mode == "message"
    refs = []
    for target in args.targets:
        if target.startswith("http"):
            url = canonical_bulletin_url(target)
            if not url:
                raise SystemExit(f"Not a recognizable GovDelivery bulletin URL: {target}")
            refs.append(MessageRef(url=url))
        else:
            url = bulletin_url_for_id(target)
            if not url:
                raise SystemExit(
                    f"{target!r} is not a numeric CSMS ID. Legacy IDs (YY-NNNNNN) have no "
                    "computable URL — pass the bulletin URL or use archive mode."
                )
            refs.append(MessageRef(message_id=target.strip(), url=url))
    return refs


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        stream=sys.stdout,
    )
    args = build_parser().parse_args(argv)

    if args.mode == "serve":
        from .server import serve
        serve(args.host, args.port)
        return 0

    settings = Settings()
    if args.bucket:
        settings.s3_bucket = args.bucket
    if args.prefix is not None:
        settings.s3_prefix = args.prefix if args.prefix.endswith("/") or not args.prefix else args.prefix + "/"
    if args.delay is not None:
        settings.request_delay = args.delay

    if args.mode == "all" and not args.since and args.limit is None:
        logger.warning(
            "all mode without --since or --limit will backfill the entire archive "
            "(30k+ messages since 2011)"
        )

    client = WebClient(settings)
    refs = collect_refs(args, client)
    logger.info("Discovered %d message ref(s)", len(refs))

    if getattr(args, "list_only", False):
        for ref in refs:
            print(ref.describe())
        return 0

    uploader = None
    if not args.dry_run:
        from .uploader import S3Uploader
        uploader = S3Uploader(settings)

    pipeline = Pipeline(
        settings=settings,
        client=client,
        uploader=uploader,
        output_dir=args.output_dir,
        force=args.force,
        since=args.since,
        until=args.until,
    )
    stats = pipeline.run(refs, limit=args.limit)
    print(f"\nDone: {stats.summary()}")
    return 1 if (stats.failed and not stats.uploaded) else 0


if __name__ == "__main__":
    raise SystemExit(main())
