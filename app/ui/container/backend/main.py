import json
import logging
import os
from pathlib import Path

import boto3
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger("uvicorn")

QUERY_LAMBDA_NAME = os.environ["QUERY_LAMBDA_NAME"]
lambda_client = boto3.client("lambda")

app = FastAPI(title="RAG Query API")

STATIC_DIR = Path(__file__).parent / "static"


class QueryRequest(BaseModel):
    query: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/query")
def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    response = lambda_client.invoke(
        FunctionName=QUERY_LAMBDA_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps({"query": req.query}),
    )
    payload = json.loads(response["Payload"].read())
    if "FunctionError" in response:
        raise HTTPException(status_code=502, detail="Lambda invocation error")

    body = payload.get("body")
    if isinstance(body, str):
        return json.loads(body)
    return body


# SPA static files — registered last so API routes take precedence
if STATIC_DIR.exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        return FileResponse(str(STATIC_DIR / "index.html"))
