from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
from secrets import randbelow
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests

from .errors import SourceRetrievalError
from .models import MediaItem
from .urls import XPost


_METADATA_MAX_RETRIES = 3
_MAX_RETRY_DELAY_SECONDS = 60
_MAX_METADATA_REDIRECTS = 5
_METADATA_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_METADATA_PROVIDER_HOSTS = {"cdn.syndication.twimg.com", "api.fxtwitter.com"}


def _metadata_url_host(url: str, *, expected_host: str | None = None) -> str:
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError as exc:
        raise SourceRetrievalError(
            "source_redirect_error", "A public X metadata provider returned an invalid redirect URL.", "metadata",
        ) from exc
    if (
        parts.scheme.lower() != "https"
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
        or host not in _METADATA_PROVIDER_HOSTS
        or (expected_host is not None and host != expected_host)
    ):
        raise SourceRetrievalError(
            "source_redirect_error", "A public X metadata provider redirected to an unapproved host or URL.", "metadata",
        )
    return host


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


def _metadata_http_error(status: int, retry_after: str | None = None) -> SourceRetrievalError:
    if status == 429:
        return SourceRetrievalError(
            "source_rate_limited",
            "A public X metadata provider is rate limiting requests (HTTP 429). The system will retry within its limit; try again later if it persists.",
            "metadata",
            retryable=True,
            retry_after=_retry_after_seconds(retry_after),
        )
    if status == 408:
        return SourceRetrievalError(
            "source_timeout", "A public X metadata provider timed out (HTTP 408). Please try again later.",
            "metadata", retryable=True,
        )
    if status in {401, 403}:
        return SourceRetrievalError(
            "source_access_denied",
            f"A public X metadata provider denied access (HTTP {status}). The post may be restricted or temporarily unavailable.",
            "metadata",
        )
    if status in {404, 410}:
        return SourceRetrievalError(
            "source_media_unavailable",
            f"A public X metadata provider reports the post as unavailable (HTTP {status}). It may have been removed or restricted.",
            "metadata",
        )
    if 500 <= status <= 599:
        return SourceRetrievalError(
            "source_server_error", f"A public X metadata provider returned HTTP {status}.",
            "metadata", retryable=True,
        )
    return SourceRetrievalError(
        "source_metadata_unavailable", f"A public X metadata provider returned HTTP {status}.", "metadata",
    )


def _classify_metadata_exception(exc: Exception) -> SourceRetrievalError:
    if isinstance(exc, SourceRetrievalError):
        return exc
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if not isinstance(status, int):
        match = re.search(r"HTTP(?: Error)?\s+(\d{3})", str(exc), re.IGNORECASE)
        status = int(match.group(1)) if match else None
    if isinstance(status, int):
        return _metadata_http_error(status, getattr(response, "headers", {}).get("Retry-After") if response else None)
    if isinstance(exc, requests.Timeout) or re.search(r"\b(timeout|timed out)\b", str(exc), re.IGNORECASE):
        return SourceRetrievalError(
            "source_timeout", "Timed out while reading public media metadata from X.", "metadata", retryable=True,
        )
    if isinstance(exc, requests.ConnectionError):
        return SourceRetrievalError(
            "source_network_error", "A network error interrupted public media metadata retrieval from X.", "metadata", retryable=True,
        )
    if re.search(r"no (?:video|media|photo).*found|does not contain.*media|not contain.*video", str(exc), re.IGNORECASE):
        return SourceRetrievalError(
            "no_supported_media", "The X post does not contain public photo or direct MP4 video media.", "metadata",
        )
    return SourceRetrievalError(
        "source_metadata_unavailable",
        "Could not retrieve public media metadata from X or its public fallback providers. Verify that the post is public and try again.",
        "metadata",
    )


@dataclass
class Metadata:
    post: XPost
    media: list[MediaItem]
    title: str = ""


class MetadataProvider:
    def get(self, post: XPost) -> Metadata:
        raise NotImplementedError


class YtDlpMetadataProvider(MetadataProvider):
    """Extract public X media through yt-dlp and public metadata fallbacks."""

    def __init__(self, timeout_seconds: int = 60, max_retries: int = _METADATA_MAX_RETRIES):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(1, min(max_retries, _METADATA_MAX_RETRIES))

    def get(self, post: XPost) -> Metadata:
        errors: list[SourceRetrievalError] = []
        providers = (self._from_ytdlp, self._from_syndication, self._from_fxtwitter)
        for provider in providers:
            try:
                result = provider(post)
            except Exception as exc:
                errors.append(_classify_metadata_exception(exc))
                continue
            if result.media:
                return result

        if errors:
            priority = {
                "source_rate_limited": 0,
                "source_access_denied": 1,
                "source_media_unavailable": 2,
                "no_supported_media": 3,
                "source_timeout": 3,
                "source_network_error": 4,
                "unsupported_media_format": 5,
                "source_server_error": 6,
                "source_redirect_error": 7,
                "source_metadata_invalid": 8,
                "source_metadata_unavailable": 9,
            }
            chosen = min(errors, key=lambda error: priority.get(error.code, 20))
            raise chosen
        return Metadata(post, [])

    def _get_json(self, endpoint: str, *, params: dict | None = None, headers: dict | None = None) -> dict[str, Any]:
        expected_host = _metadata_url_host(endpoint)
        last_error: SourceRetrievalError | None = None
        for attempt in range(self.max_retries):
            try:
                current_url = endpoint
                current_params = params
                for redirect_count in range(_MAX_METADATA_REDIRECTS + 1):
                    response = requests.get(
                        current_url, params=current_params, timeout=self.timeout_seconds,
                        headers=headers or {}, allow_redirects=False,
                    )
                    current_params = None
                    if response.status_code not in _METADATA_REDIRECT_STATUSES:
                        break
                    location = response.headers.get("Location") or response.headers.get("location")
                    if not location or redirect_count >= _MAX_METADATA_REDIRECTS:
                        raise SourceRetrievalError(
                            "source_redirect_error", "A public X metadata provider redirected too many times or omitted its redirect target.",
                            "metadata", attempts=attempt + 1,
                        )
                    current_url = urljoin(current_url, location)
                    try:
                        _metadata_url_host(current_url, expected_host=expected_host)
                    except SourceRetrievalError as exc:
                        exc.attempts = attempt + 1
                        raise
                else:
                    raise SourceRetrievalError(
                        "source_redirect_error", "A public X metadata provider redirected too many times.",
                        "metadata", attempts=attempt + 1,
                    )
            except requests.Timeout as exc:
                last_error = SourceRetrievalError(
                    "source_timeout", "Timed out while reading public media metadata from X.", "metadata", retryable=True,
                    attempts=attempt + 1,
                )
                if attempt + 1 >= self.max_retries:
                    raise last_error from exc
                time.sleep(min(2**attempt, _MAX_RETRY_DELAY_SECONDS))
                continue
            except requests.RequestException as exc:
                last_error = SourceRetrievalError(
                    "source_network_error", "A network error interrupted public media metadata retrieval from X.", "metadata", retryable=True,
                    attempts=attempt + 1,
                )
                if attempt + 1 >= self.max_retries:
                    raise last_error from exc
                time.sleep(min(2**attempt, _MAX_RETRY_DELAY_SECONDS))
                continue

            if not 200 <= response.status_code < 300:
                last_error = _metadata_http_error(response.status_code, response.headers.get("Retry-After"))
                last_error.attempts = attempt + 1
                if not last_error.retryable or attempt + 1 >= self.max_retries:
                    raise last_error
                delay = last_error.retry_after if last_error.retry_after is not None else min(2**attempt, _MAX_RETRY_DELAY_SECONDS)
                time.sleep(delay)
                continue
            try:
                payload = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError) as exc:
                raise SourceRetrievalError(
                    "source_metadata_invalid", "A public X metadata provider returned malformed JSON.", "metadata",
                    attempts=attempt + 1,
                ) from exc
            if not isinstance(payload, dict):
                raise SourceRetrievalError(
                    "source_metadata_invalid", "A public X metadata provider returned an unexpected response.", "metadata",
                    attempts=attempt + 1,
                )
            return payload

        raise last_error or SourceRetrievalError(
            "source_metadata_unavailable", "Could not retrieve public media metadata from X.", "metadata",
        )

    def _from_ytdlp(self, post: XPost) -> Metadata:
        from yt_dlp import YoutubeDL

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": self.timeout_seconds,
            "retries": max(0, self.max_retries - 1),
            "extractor_retries": max(0, self.max_retries - 1),
        }
        with YoutubeDL(options) as ydl:
            info: dict[str, Any] = ydl.extract_info(post.normalized_url, download=False)
        entries = [entry for entry in (info.get("entries") or []) if entry]
        media_entries = entries or [info]
        media: list[MediaItem] = []
        seen: set[str] = set()
        found_video_formats = False
        unsupported_video_entry = False
        # Formats within one entry are variants of that media item; separate
        # entries represent distinct items in a multi-media post.
        for media_index, media_info in enumerate(media_entries):
            formats = media_info.get("formats") or []
            video_formats = [item for item in formats if item.get("url") and item.get("vcodec") not in (None, "none")]
            found_video_formats = found_video_formats or bool(video_formats)
            supported_for_entry = 0
            for item in video_formats:
                url = item["url"]
                protocol = str(item.get("protocol") or "").lower()
                extension = str(item.get("ext") or "").lower()
                try:
                    path = urlsplit(url).path.lower()
                except ValueError:
                    path = ""
                hls_or_dash = (
                    protocol.startswith("m3u8")
                    or protocol in {"http_dash_segments", "dash", "f4m"}
                    or path.endswith((".m3u8", ".mpd", ".f4m"))
                    or extension in {"m3u8", "mpd", "f4m"}
                )
                if hls_or_dash or extension != "mp4":
                    continue
                if url in seen:
                    continue
                seen.add(url)
                supported_for_entry += 1
                media.append(MediaItem(
                    "video", url, media_index,
                    int(item["tbr"] * 1000) if item.get("tbr") else None,
                    item.get("width"), item.get("height"), extension,
                    item.get("filesize") or item.get("filesize_approx"),
                ))
            if video_formats and not supported_for_entry:
                unsupported_video_entry = True
        if found_video_formats and (unsupported_video_entry or not media):
            raise SourceRetrievalError(
                "unsupported_media_format",
                "X exposed one or more media entries without a supported direct MP4 variant; a public fallback may provide supported media.",
                "metadata",
            )
        return Metadata(post, media, info.get("title") or "")

    def _from_syndication(self, post: XPost) -> Metadata:
        # This public embed endpoint is unofficial and may change; keep it as a fallback.
        endpoint = "https://cdn.syndication.twimg.com/tweet-result"
        params = {"id": post.post_id, "lang": "en", "token": str(randbelow(900_000_000) + 100_000_000)}
        payload = self._get_json(
            endpoint,
            params=params,
            headers={"User-Agent": "X2Telegram/1.0", "Accept": "application/json"},
        )
        media: list[MediaItem] = []
        seen: set[str] = set()
        for index, item in enumerate(payload.get("mediaDetails") or []):
            kind = item.get("type")
            if kind == "photo":
                url = item.get("media_url_https")
                info = item.get("original_info") or {}
                if url and url not in seen:
                    seen.add(url)
                    media.append(MediaItem("photo", f"{url}?name=orig", index,
                                           width=info.get("width"), height=info.get("height"), mime_type="jpg"))
            elif kind == "video":
                variants = [variant for variant in (item.get("video_info") or {}).get("variants", [])
                            if variant.get("url") and variant.get("content_type") == "video/mp4"]
                for variant in variants:
                    url = variant["url"]
                    if url in seen:
                        continue
                    seen.add(url)
                    width, height = (item.get("video_info") or {}).get("aspect_ratio") or (None, None)
                    media.append(MediaItem("video", url, index, bitrate=variant.get("bitrate"),
                                           width=width, height=height, mime_type="mp4",
                                           size_bytes=variant.get("filesize") or variant.get("size")))
        return Metadata(post, media, payload.get("text") or "")

    def _from_fxtwitter(self, post: XPost) -> Metadata:
        """Use FxTwitter's public status API when other metadata sources are empty."""
        endpoint = f"https://api.fxtwitter.com/2/status/{post.post_id}"
        payload = self._get_json(
            endpoint,
            headers={"User-Agent": "X2Telegram/1.0", "Accept": "application/json"},
        )
        if payload.get("code") not in (None, 200):
            raise SourceRetrievalError(
                "source_metadata_unavailable", "The public metadata provider could not read this X post.", "metadata",
            )
        status = payload.get("status") or {}
        media = status.get("media") or {}
        items = media.get("all") or media.get("videos") or []
        results: list[MediaItem] = []
        seen: set[str] = set()
        for index, item in enumerate(items):
            kind = item.get("type")
            if kind == "video":
                variants = [variant for variant in (item.get("formats") or [])
                            if variant.get("url") and variant.get("container") == "mp4"]
                for variant in variants:
                    url = variant["url"]
                    if url in seen:
                        continue
                    seen.add(url)
                    results.append(MediaItem(
                        "video", url, index,
                        bitrate=variant.get("bitrate"),
                        width=variant.get("width") or item.get("width"),
                        height=variant.get("height") or item.get("height"),
                        mime_type="mp4",
                        size_bytes=variant.get("filesize") or variant.get("size"),
                    ))
            elif kind == "photo" and item.get("url"):
                url = item["url"]
                if url not in seen:
                    seen.add(url)
                    results.append(MediaItem(
                        "photo", url, index,
                        width=item.get("width"), height=item.get("height"), mime_type="jpg",
                    ))
        return Metadata(post, results, status.get("text") or "")
