from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import mimetypes
import os
import tempfile
import time
from urllib.parse import urljoin

import requests

from .errors import SourceRetrievalError
from .security import validate_download, validate_media_url


MAX_REDIRECTS = 5
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MAX_RETRY_DELAY_SECONDS = 60


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return min(max(0.0, seconds), float(_MAX_RETRY_DELAY_SECONDS))


def _http_error(status: int, retry_after: str | None = None) -> SourceRetrievalError:
    if status == 429:
        return SourceRetrievalError(
            "source_rate_limited",
            "X is rate limiting this media request (HTTP 429). The system will retry within its limit; try again later if it persists.",
            "download",
            retryable=True,
            retry_after=_retry_after_seconds(retry_after),
        )
    if status == 408:
        return SourceRetrievalError(
            "source_timeout", "The X media server timed out (HTTP 408). Please try again later.",
            "download", retryable=True,
        )
    if status in {401, 403}:
        return SourceRetrievalError(
            "source_access_denied",
            f"The X media server denied access (HTTP {status}). The post may be restricted or its media link may have expired.",
            "download",
        )
    if status in {404, 410}:
        return SourceRetrievalError(
            "source_media_unavailable",
            f"The X media file is unavailable (HTTP {status}); it may have been removed or its link may have expired.",
            "download",
        )
    if 500 <= status <= 599:
        return SourceRetrievalError(
            "source_server_error",
            f"The X media server returned HTTP {status}. Please try again later.",
            "download", retryable=True,
        )
    return SourceRetrievalError(
        "source_http_error", f"The X media server returned HTTP {status}.", "download",
    )


def _validate_source_url(url: str) -> None:
    try:
        validate_media_url(url)
    except ValueError as exc:
        if "invalid port" in str(exc).lower():
            code, message = "invalid_media_url", "The source returned a media URL with an invalid port."
        else:
            code, message = "unsupported_media_url", "The source returned a media URL on an unapproved host; it was blocked."
        raise SourceRetrievalError(code, message, "download") from exc


class MediaDownloader:
    def __init__(self, timeout_seconds: int = 60, max_file_size_mb: int = 50, max_retries: int = 2):
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_file_size_mb * 1024 * 1024
        self.max_retries = max(1, max_retries)
        self.last_attempt_count = 0

    def _too_large(self) -> SourceRetrievalError:
        limit_mb = self.max_bytes // (1024 * 1024)
        return SourceRetrievalError(
            "media_too_large",
            f"This media variant exceeds the configured {limit_mb} MB download limit. A lower-quality variant may fit.",
            "download",
        )

    @staticmethod
    def _remove_partial(path: Path | None) -> None:
        if path:
            path.unlink(missing_ok=True)

    def download(self, url: str, kind: str) -> Path:
        if kind not in {"video", "photo"}:
            raise SourceRetrievalError("unsupported_media_kind", "The source returned an unsupported media type.", "download")
        _validate_source_url(url)
        suffix = ".mp4" if kind == "video" else ".jpg"
        last_error: SourceRetrievalError | None = None

        for attempt in range(self.max_retries):
            self.last_attempt_count = attempt + 1
            part_path: Path | None = None
            try:
                current_url = url
                for redirect_count in range(MAX_REDIRECTS + 1):
                    _validate_source_url(current_url)
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
                                raise SourceRetrievalError(
                                    "source_redirect_error", "The X media server returned an incomplete redirect.", "download",
                                )
                            if redirect_count >= MAX_REDIRECTS:
                                raise SourceRetrievalError(
                                    "source_redirect_error", "The X media URL redirected too many times.", "download",
                                )
                            current_url = urljoin(current_url, location)
                            _validate_source_url(current_url)
                            continue

                        if not 200 <= response.status_code < 300:
                            raise _http_error(response.status_code, response.headers.get("Retry-After"))

                        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                        if content_type.startswith("text/") or content_type in {"application/json", "text/json"}:
                            raise SourceRetrievalError(
                                "source_response_not_media", "The X media server returned an error page instead of media.", "download",
                            )
                        if kind == "video" and content_type and content_type not in {"video/mp4", "application/octet-stream"}:
                            raise SourceRetrievalError(
                                "unsupported_media_format",
                                "The source returned a stream format other than a direct MP4 video (for example, an HLS playlist).",
                                "download",
                            )
                        if kind == "photo" and content_type and not content_type.startswith("image/") and content_type != "application/octet-stream":
                            raise SourceRetrievalError(
                                "unsupported_media_format", "The source returned a format other than a supported image.", "download",
                            )
                        if kind == "photo" and content_type.startswith("image/"):
                            guessed = mimetypes.guess_extension(content_type)
                            if guessed in {".png", ".webp", ".jpg", ".jpeg"}:
                                suffix = guessed
                        content_length = response.headers.get("content-length")
                        if content_length:
                            try:
                                declared_size = int(content_length)
                            except (TypeError, ValueError) as exc:
                                raise SourceRetrievalError(
                                    "invalid_media_response", "The X media server returned an invalid file size.", "download",
                                ) from exc
                            if declared_size < 0:
                                raise SourceRetrievalError(
                                    "invalid_media_response", "The X media server returned an invalid file size.", "download",
                                )
                            if declared_size > self.max_bytes:
                                raise self._too_large()

                        try:
                            with tempfile.NamedTemporaryFile(prefix="x2telegram-", suffix=".part", delete=False) as handle:
                                part_path = Path(handle.name)
                                total = 0
                                for chunk in response.iter_content(chunk_size=1024 * 256):
                                    if not chunk:
                                        continue
                                    total += len(chunk)
                                    if total > self.max_bytes:
                                        raise self._too_large()
                                    handle.write(chunk)
                        except SourceRetrievalError:
                            raise
                        except OSError as exc:
                            raise SourceRetrievalError(
                                "local_storage_error", "The downloaded media could not be saved on the runner.", "download",
                            ) from exc
                    break
                else:
                    raise SourceRetrievalError(
                        "source_redirect_error", "The X media URL redirected too many times.", "download",
                    )

                try:
                    validate_download(part_path, kind)
                except (OSError, ValueError) as exc:
                    raise SourceRetrievalError(
                        "invalid_media_response", "The downloaded response was empty or did not match the expected media type.", "download",
                    ) from exc
                final_path = part_path.with_suffix(suffix)
                try:
                    os.replace(part_path, final_path)
                except OSError as exc:
                    raise SourceRetrievalError(
                        "local_storage_error", "The downloaded media could not be finalized on the runner.", "download",
                    ) from exc
                return final_path
            except SourceRetrievalError as exc:
                exc.attempts = self.last_attempt_count
                last_error = exc
                self._remove_partial(part_path)
                if not exc.retryable or attempt + 1 >= self.max_retries:
                    raise
                delay = exc.retry_after if exc.retry_after is not None else min(2**attempt, _MAX_RETRY_DELAY_SECONDS)
                time.sleep(delay)
            except requests.Timeout as exc:
                last_error = SourceRetrievalError(
                    "source_timeout", "Timed out while retrieving media from X.", "download", retryable=True,
                    attempts=self.last_attempt_count,
                )
                self._remove_partial(part_path)
                if attempt + 1 >= self.max_retries:
                    raise last_error from exc
                time.sleep(min(2**attempt, _MAX_RETRY_DELAY_SECONDS))
            except requests.RequestException as exc:
                last_error = SourceRetrievalError(
                    "source_network_error", "A network error interrupted media retrieval from X.", "download", retryable=True,
                    attempts=self.last_attempt_count,
                )
                self._remove_partial(part_path)
                if attempt + 1 >= self.max_retries:
                    raise last_error from exc
                time.sleep(min(2**attempt, _MAX_RETRY_DELAY_SECONDS))
            except OSError as exc:
                self._remove_partial(part_path)
                raise SourceRetrievalError(
                    "local_storage_error", "The downloaded media could not be saved on the runner.", "download",
                ) from exc

        if last_error:
            raise last_error
        raise SourceRetrievalError("source_download_failed", "Could not retrieve media from X.", "download")
