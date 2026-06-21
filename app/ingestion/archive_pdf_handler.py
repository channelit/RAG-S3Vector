"""
ArchivePdfHandler
=================
Handles PDF files stored under the 'archive/' prefix in the document bucket.

Workflow:
  1. Download the PDF from S3
  2. Extract all hyperlinks from PDF annotation objects
  3. For each link, fetch the HTML page and extract visible text
  4. Chunk, embed, and index the text into S3 Vectors

The metadata stored per vector:
  source           — URL of the HTML page (used for retrieval / attribution)
  pdf_source       — S3 key of the originating PDF
  link_index       — position of the URL in the PDF (0-based)
  chunk_id         — chunk index within that page's text
  document_date    — ISO timestamp from the PDF's S3 LastModified
  document_timestamp — Unix int of same (used for numeric pre-filtering)
  text             — the text chunk (non-filterable)
"""

import io
import json
import logging
import urllib.error
import urllib.request
from html.parser import HTMLParser

logger = logging.getLogger()


class _TextExtractor(HTMLParser):
    """Strips tags and returns visible page text, skipping nav/script/style."""

    _SKIP = {"script", "style", "nav", "header", "footer", "aside", "noscript", "menu"}

    def __init__(self):
        super().__init__()
        self._depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._SKIP:
            self._depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP:
            self._depth = max(0, self._depth - 1)

    def handle_data(self, data):
        if self._depth == 0:
            text = data.strip()
            if text:
                self._parts.append(text)

    @property
    def text(self) -> str:
        return "\n".join(self._parts)


class ArchivePdfHandler:
    """Indexes CSMS HTML pages linked from archive PDF files."""

    ARCHIVE_PREFIX = "archive/"
    FETCH_TIMEOUT = 20       # seconds per HTTP request
    MAX_LINKS = 200          # safety cap on links per PDF
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200
    BATCH_SIZE = 500
    EMBEDDING_DIMENSION = 1024

    @staticmethod
    def should_handle(key: str) -> bool:
        k = key.lower()
        return k.startswith(ArchivePdfHandler.ARCHIVE_PREFIX) and k.endswith(".pdf")

    def __init__(
        self,
        s3_client,
        bedrock_client,
        s3vectors_client,
        vector_bucket_name: str,
        vector_index_name: str,
        embedding_model_id: str,
    ):
        self._s3 = s3_client
        self._bedrock = bedrock_client
        self._s3v = s3vectors_client
        self._vector_bucket = vector_bucket_name
        self._vector_index = vector_index_name
        self._embedding_model = embedding_model_id

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def handle(
        self,
        bucket: str,
        key: str,
        document_date: str,
        document_timestamp: int,
    ) -> int:
        """Download PDF, follow each link, index HTML content. Returns vectors written."""
        logger.info("[ArchivePdf] START s3://%s/%s", bucket, key)

        pdf_bytes = self._download_pdf(bucket, key)
        links = self._extract_links(pdf_bytes, key)

        if not links:
            logger.warning("[ArchivePdf] No hyperlinks found in PDF — nothing to index")
            return 0

        total_vectors = 0
        for idx, url in enumerate(links):
            logger.info("[ArchivePdf] Link %d/%d: %s", idx + 1, len(links), url)

            try:
                page_text = self._fetch_text(url)
            except Exception as exc:
                logger.error("[ArchivePdf] Fetch failed for %s: %s", url, exc)
                continue

            if not page_text.strip():
                logger.warning("[ArchivePdf] No text extracted from %s — skipping", url)
                continue

            logger.info("[ArchivePdf] Extracted %d chars from %s", len(page_text), url)

            chunks = self._chunk_text(page_text)
            logger.info("[ArchivePdf] Chunked into %d piece(s)", len(chunks))

            vectors = []
            for chunk_idx, chunk in enumerate(chunks):
                logger.info(
                    "[ArchivePdf] Embedding link=%d chunk=%d/%d", idx, chunk_idx + 1, len(chunks)
                )
                embedding = self._embed(chunk)
                vectors.append(
                    {
                        "key": f"{key}#{idx}#chunk-{chunk_idx}",
                        "data": {"float32": embedding},
                        "metadata": {
                            "source": url,
                            "pdf_source": key,
                            "link_index": idx,
                            "chunk_id": str(chunk_idx),
                            "document_date": document_date,
                            "document_timestamp": document_timestamp,
                            "text": chunk,
                        },
                    }
                )

            written = self._put_vectors(vectors, url)
            total_vectors += written
            logger.info(
                "[ArchivePdf] Indexed %d chunk(s) from %s (running total=%d)",
                written, url, total_vectors,
            )

        logger.info(
            "[ArchivePdf] END s3://%s/%s — %d total vectors from %d link(s)",
            bucket, key, total_vectors, len(links),
        )
        return total_vectors

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _download_pdf(self, bucket: str, key: str) -> bytes:
        logger.info("[ArchivePdf] Downloading PDF from s3://%s/%s", bucket, key)
        data = self._s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        logger.info("[ArchivePdf] PDF downloaded: %d bytes", len(data))
        return data

    def _extract_links(self, pdf_bytes: bytes, source_key: str) -> list[str]:
        """Return deduplicated HTTP/HTTPS URLs from PDF annotation objects."""
        from pypdf import PdfReader  # imported here so Lambda cold-start is unaffected for non-archive paths

        reader = PdfReader(io.BytesIO(pdf_bytes))
        logger.info("[ArchivePdf] PDF has %d page(s)", len(reader.pages))

        seen: set[str] = set()
        links: list[str] = []

        for page_num, page in enumerate(reader.pages):
            if "/Annots" not in page:
                continue
            for annot in page["/Annots"]:
                try:
                    obj = annot.get_object()
                    if obj.get("/Subtype") != "/Link":
                        continue
                    action = obj.get("/A")
                    if not action:
                        continue
                    uri = action.get("/URI", "")
                    if isinstance(uri, bytes):
                        uri = uri.decode("utf-8", errors="ignore")
                    uri = uri.strip()
                    if not uri.startswith("http"):
                        continue
                    if uri in seen:
                        continue
                    seen.add(uri)
                    links.append(uri)
                    logger.info("[ArchivePdf] Found link on page %d: %s", page_num + 1, uri)
                    if len(links) >= self.MAX_LINKS:
                        logger.warning(
                            "[ArchivePdf] MAX_LINKS=%d reached — stopping extraction", self.MAX_LINKS
                        )
                        return links
                except Exception as exc:
                    logger.warning("[ArchivePdf] Skipping annotation on page %d: %s", page_num + 1, exc)

        return links

    def _fetch_text(self, url: str) -> str:
        """Fetch HTML from URL and return extracted visible text."""
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; CBP-RAG-Indexer/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=self.FETCH_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "")
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].strip().split(";")[0] or "utf-8"
            raw_html = resp.read().decode(charset, errors="ignore")

        logger.info("[ArchivePdf] Fetched %d raw HTML chars from %s", len(raw_html), url)
        extractor = _TextExtractor()
        extractor.feed(raw_html)
        return extractor.text

    def _chunk_text(self, text: str) -> list[str]:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + self.CHUNK_SIZE, len(text))
            if end < len(text):
                boundary = text.rfind(". ", start, end)
                if boundary > start:
                    end = boundary + 1
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            next_start = end - self.CHUNK_OVERLAP
            start = next_start if next_start > start else end
        return chunks

    def _embed(self, text: str) -> list[float]:
        request_body = {
            "taskType": "SINGLE_EMBEDDING",
            "singleEmbeddingParams": {
                "embeddingPurpose": "GENERIC_INDEX",
                "embeddingDimension": self.EMBEDDING_DIMENSION,
                "text": {"truncationMode": "END", "value": text},
            },
        }
        response = self._bedrock.invoke_model(
            modelId=self._embedding_model,
            body=json.dumps(request_body),
        )
        return json.loads(response["body"].read())["embeddings"][0]["embedding"]

    def _put_vectors(self, vectors: list[dict], url: str) -> int:
        written = 0
        for offset in range(0, len(vectors), self.BATCH_SIZE):
            batch = vectors[offset: offset + self.BATCH_SIZE]
            logger.info(
                "[ArchivePdf] PutVectors: bucket=%s index=%s batch=%d offset=%d url=%s",
                self._vector_bucket, self._vector_index, len(batch), offset, url,
            )
            self._s3v.put_vectors(
                vectorBucketName=self._vector_bucket,
                indexName=self._vector_index,
                vectors=batch,
            )
            written += len(batch)
            logger.info("[ArchivePdf] PutVectors ok: %d written", len(batch))
        return written
