from pathlib import Path
import mimetypes
import tempfile

import requests

from .security import validate_download


class MediaDownloader:
    def __init__(self, timeout_seconds: int = 60, max_file_size_mb: int = 50):
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_file_size_mb * 1024 * 1024

    def download(self, url: str, kind: str) -> Path:
        suffix = ".mp4" if kind == "video" else ".jpg"
        response = requests.get(url, stream=True, timeout=self.timeout_seconds, headers={"User-Agent": "X2Telegram/1.0"})
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type.startswith("text/") or content_type == "application/json":
            raise ValueError(f"Unexpected media content type: {content_type}")
        if content_type:
            guessed = mimetypes.guess_extension(content_type)
            if guessed and kind == "photo" and guessed in {".png", ".webp", ".jpg", ".jpeg"}:
                suffix = guessed
        total = 0
        with tempfile.NamedTemporaryFile(prefix="x2telegram-", suffix=suffix, delete=False) as handle:
            path = Path(handle.name)
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                total += len(chunk)
                if total > self.max_bytes:
                    path.unlink(missing_ok=True)
                    raise ValueError(f"Downloaded file exceeds {self.max_bytes // (1024 * 1024)} MB limit")
                handle.write(chunk)
        validate_download(path)
        return path
