"""Environment-driven settings (12-factor style, container friendly)."""

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    s3_bucket: str = field(default_factory=lambda: os.environ.get("S3_BUCKET_NAME", ""))
    s3_prefix: str = field(default_factory=lambda: os.environ.get("S3_PREFIX", "csms/"))
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
