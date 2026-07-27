"""HTTP trigger mode: expose the scraper as a URL endpoint.

    python -m scraper serve [--host 0.0.0.0] [--port 8080]

Endpoints:
    GET  /health   liveness/readiness probe (always 200 while the process is up)
    GET  /status   state of the current/last run
    POST /scrape   trigger a run; body mirrors the CLI, e.g.
                   {"mode": "current", "limit": 5}
                   {"mode": "archive", "sources": ["2021-2025"], "limit": 200}
                   {"mode": "message", "targets": ["69302472"], "dry_run": true}

Runs execute in a background thread; /scrape answers 202 immediately and 409
while a run is already in progress (one run at a time — the pipeline is
sequential by design for politeness).
"""

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("scraper")

app = FastAPI(title="csms-scraper")

_lock = threading.Lock()
_state: dict[str, Any] = {"status": "idle"}


class ScrapeRequest(BaseModel):
    mode: str
    sources: list[str] = []          # archive mode: presets, PDF URLs, local paths
    discover: bool = False           # archive mode
    targets: list[str] = []          # message mode: CSMS IDs or bulletin URLs
    limit: Optional[int] = None
    since: Optional[str] = None      # YYYY-MM-DD
    until: Optional[str] = None      # YYYY-MM-DD
    force: bool = False
    dry_run: bool = False
    output_dir: Optional[str] = None
    bucket: Optional[str] = None
    prefix: Optional[str] = None
    delay: Optional[float] = None

    def to_argv(self) -> list[str]:
        if self.mode not in ("current", "archive", "message"):
            raise ValueError("mode must be one of: current, archive, message")
        argv = [self.mode]
        if self.mode == "archive":
            if not self.sources and not self.discover:
                raise ValueError("archive mode requires sources and/or discover=true")
            argv += self.sources
            if self.discover:
                argv.append("--discover")
        elif self.mode == "message":
            if not self.targets:
                raise ValueError("message mode requires targets")
            argv += self.targets
        if self.limit is not None:
            argv += ["--limit", str(self.limit)]
        if self.since:
            argv += ["--since", self.since]
        if self.until:
            argv += ["--until", self.until]
        if self.force:
            argv.append("--force")
        if self.dry_run:
            argv.append("--dry-run")
        if self.output_dir:
            argv += ["--output-dir", self.output_dir]
        if self.bucket:
            argv += ["--bucket", self.bucket]
        if self.prefix is not None:
            argv += ["--prefix", self.prefix]
        if self.delay is not None:
            argv += ["--delay", str(self.delay)]
        return argv


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run(run_id: str, argv: list[str]) -> None:
    from .__main__ import main
    error: Optional[str] = None
    try:
        exit_code = main(argv)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 2
        error = str(exc.code) if not isinstance(exc.code, int) else None
    except Exception as exc:
        logger.exception("Run %s crashed", run_id)
        exit_code = 1
        error = f"{type(exc).__name__}: {exc}"
    with _lock:
        _state.update(
            status="succeeded" if exit_code == 0 else "failed",
            exit_code=exit_code,
            error=error,
            finished_at=_utcnow(),
        )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status")
def status():
    with _lock:
        return dict(_state)


@app.post("/scrape", status_code=202)
def scrape(req: ScrapeRequest):
    try:
        argv = req.to_argv()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Validate flag values (dates, numbers) up front so bad requests get a 400
    # instead of a run that immediately dies in the background thread.
    from .__main__ import build_parser
    try:
        build_parser().parse_args(argv)
    except SystemExit:
        raise HTTPException(status_code=400, detail=f"invalid arguments: {argv}")

    run_id = uuid.uuid4().hex[:12]
    with _lock:
        if _state.get("status") == "running":
            raise HTTPException(
                status_code=409,
                detail={"message": "a run is already in progress", **_state},
            )
        _state.clear()
        _state.update(
            status="running",
            run_id=run_id,
            argv=argv,
            started_at=_utcnow(),
        )
    threading.Thread(target=_run, args=(run_id, argv), daemon=True).start()
    return {"run_id": run_id, "argv": argv, "status": "running"}


def serve(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")
