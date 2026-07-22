"""S3 upload — one file at a time, deleting each local file after its upload.

S3 itself is the dedupe state: a message whose main document key already
exists is skipped on later runs (unless --force), so no local database is
needed and local storage stays empty between messages.
"""

import logging
import mimetypes
import os

from .config import Settings

logger = logging.getLogger(__name__)


class S3Uploader:
    def __init__(self, settings: Settings):
        if not settings.s3_bucket:
            raise SystemExit(
                "S3_BUCKET_NAME is not set. Export it (or put it in .env.local for "
                "docker compose), or use --dry-run to skip uploading."
            )
        import boto3  # deferred so --dry-run works without boto3/credentials

        self._s3 = boto3.client("s3")
        self._bucket = settings.s3_bucket
        self._prefix = settings.s3_prefix

    def message_doc_key(self, message_id: str) -> str:
        return f"{self._prefix}{message_id}/csms-{message_id}.txt"

    def message_prefix(self, message_id: str) -> str:
        return f"{self._prefix}{message_id}/"

    def exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except self._s3.exceptions.ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            code = exc.response.get("Error", {}).get("Code")
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def upload_and_delete(self, local_path: str, key: str) -> None:
        content_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
        size = os.path.getsize(local_path)
        logger.info("Uploading s3://%s/%s (%d bytes, %s)", self._bucket, key, size, content_type)
        self._s3.upload_file(
            local_path, self._bucket, key, ExtraArgs={"ContentType": content_type}
        )
        os.remove(local_path)
        logger.info("Uploaded and removed local file %s", local_path)
