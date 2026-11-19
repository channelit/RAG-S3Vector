"""Environment-driven settings (12-factor style, container friendly)."""

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    s3_bucket: str = field(default_factory=lambda: os.environ.get("S3_BUCKET_NAME", ""))
    s3_prefix: str = field(default_factory=lambda: os.environ.get("S3_PREFIX", "csms/"))
    # Bedrock Knowledge Base + its S3 data source that index the messages (IDs,
    # not names). When set, the scraper syncs the data source after a run that
    # uploaded messages; `reindex` mode / `--reindex` need them.
    knowledge_base_id: str = field(default_factory=lambda: os.environ.get("KNOWLEDGE_BASE_ID", ""))
    kb_data_source_id: str = field(default_factory=lambda: os.environ.get("KB_DATA_SOURCE_ID", ""))
    # Collection summary (statistics documents, see summary.py). Its prefix must
    # sit outside S3_PREFIX; unset = no summary is written. The summary Knowledge
    # Base + data source IDs are optional: when set, the scraper syncs that data
    # source after writing the documents.
    summary_prefix: str = field(default_factory=lambda: os.environ.get("SUMMARY_PREFIX", ""))
    summary_knowledge_base_id: str = field(
        default_factory=lambda: os.environ.get("SUMMARY_KNOWLEDGE_BASE_ID", "")
    )
    summary_kb_data_source_id: str = field(
        default_factory=lambda: os.environ.get("SUMMARY_KB_DATA_SOURCE_ID", "")
    )
    request_delay: float = field(
        default_factory=lambda: float(os.environ.get("REQUEST_DELAY_SECONDS", "0.7"))
    )
    request_timeout: float = field(
        default_factory=lambda: float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "30"))
    )
    max_retries: int = field(default_factory=lambda: int(os.environ.get("MAX_RETRIES", "3")))
    user_agent: str = field(
        default_factory=lambda: os.environ.get(
            "USER_AGENT",
            # cbp.gov rejects generic client UAs with 403; a browser-style UA is required
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 CSMS-Scraper/1.0",
        )
    )

    def __post_init__(self):
        if self.s3_prefix and not self.s3_prefix.endswith("/"):
            self.s3_prefix += "/"
        if self.summary_prefix and not self.summary_prefix.endswith("/"):
            self.summary_prefix += "/"
