from pathlib import Path
import mimetypes
import os
import tempfile
import time
from urllib.parse import urljoin

import requests

from .security import validate_download, validate_media_url


MAX_REDIRECTS = 5
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class MediaDownloader:
    def __init__(self, timeout_seconds: int = 60, max_file_size_mb: int = 50, max_retries: int = 2):
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_file_size_mb * 1024 * 1024
        self.max_retries = max(1, max_retries)

    def download(self, url: str, kind: str) -> Path:
        if kind not in {"video", "photo"}:
            raise ValueError(f"Unsupported media kind: {kind}")
        validate_media_url(url)
        suffix = ".mp4" if kind == "video" else ".jpg"
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            part_path: Path | None = None
            try:
                current_url = url
                for redirect_count in range(MAX_REDIRECTS + 1):
                    validate_media_url(current_url)
                    with requests.get(
                        current_url,
                        stream=True,
                        timeout=self.timeout_seconds,
                        allow_redirects=False,
                        headers={"User-Agent": "X2Telegram/1.0", "Accept": "video/mp4,image/*"},
                    ) as response:
                        if response.status_code in _REDIRECT_STATUSES:
                            location = response.headers.get("location")
                            if not location:
                                raise ValueError("Media redirect is missing a Location header")
                            if redirect_count >= MAX_REDIRECTS:
                                raise ValueError("Media URL has too many redirects")
                            current_url = urljoin(current_url, location)
                            validate_media_url(current_url)
                            continue

                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                        if content_type.startswith("text/") or content_type in {"application/json", "text/json"}:
                            raise ValueError(f"Unexpected media content type: {content_type}")
                        if kind == "video" and content_type and content_type not in {
                            "video/mp4", "application/octet-stream"
                        }:
                            raise ValueError(f"Unexpected video content type: {content_type}")
                        if kind == "photo" and content_type.startswith("image/"):
                            guessed = mimetypes.guess_extension(content_type)
                            if guessed in {".png", ".webp", ".jpg", ".jpeg"}:
                                suffix = guessed
                        content_length = response.headers.get("content-length")
                        if content_length and int(content_length) > self.max_bytes:
                            raise ValueError(f"Downloaded file exceeds {self.max_bytes // (1024 * 1024)} MB limit")

                        with tempfile.NamedTemporaryFile(prefix="x2telegram-", suffix=".part", delete=False) as handle:
                            part_path = Path(handle.name)
                            total = 0
                            for chunk in response.iter_content(chunk_size=1024 * 256):
                                if not chunk:
                                    continue
                                total += len(chunk)
                                if total > self.max_bytes:
                                    raise ValueError(
                                        f"Downloaded file exceeds {self.max_bytes // (1024 * 1024)} MB limit"
                                    )
                                handle.write(chunk)
                    break
                else:
                    raise ValueError("Media URL has too many redirects")

                validate_download(part_path, kind)
                final_path = part_path.with_suffix(suffix)
                os.replace(part_path, final_path)
                return final_path
            except (requests.RequestException, OSError, ValueError) as exc:
                last_error = exc
                if part_path:
                    part_path.unlink(missing_ok=True)
                if isinstance(exc, ValueError) and "exceeds" in str(exc):
                    raise
                if attempt + 1 < self.max_retries:
                    time.sleep(2**attempt)

        raise ValueError(f"Media download failed after {self.max_retries} attempts: {last_error}")
