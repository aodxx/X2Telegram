from dataclasses import dataclass
from secrets import randbelow
from typing import Any

import requests

from .models import MediaItem
from .urls import XPost


@dataclass
class Metadata:
    post: XPost
    media: list[MediaItem]
    title: str = ""


class MetadataProvider:
    def get(self, post: XPost) -> Metadata:
        raise NotImplementedError


class YtDlpMetadataProvider(MetadataProvider):
    """Extract public X media, with a syndication fallback for photo posts."""

    def __init__(self, timeout_seconds: int = 60):
        self.timeout_seconds = timeout_seconds

    def get(self, post: XPost) -> Metadata:
        ytdlp_error: Exception | None = None
        try:
            metadata = self._from_ytdlp(post)
            if metadata.media:
                return metadata
        except Exception as exc:
            ytdlp_error = exc

        try:
            fallback = self._from_syndication(post)
            if fallback.media or not ytdlp_error:
                return fallback
            # A tombstone/empty public response is a valid no-media result.
            return fallback
        except Exception as fallback_error:
            if ytdlp_error:
                raise RuntimeError(f"yt-dlp: {ytdlp_error}; syndication: {fallback_error}") from fallback_error
            raise

    def _from_ytdlp(self, post: XPost) -> Metadata:
        from yt_dlp import YoutubeDL

        options = {"quiet": True, "no_warnings": True, "skip_download": True,
                   "noplaylist": True, "socket_timeout": self.timeout_seconds, "retries": 2}
        with YoutubeDL(options) as ydl:
            info: dict[str, Any] = ydl.extract_info(post.normalized_url, download=False)
        entries = info.get("entries") or []
        if entries:
            info = next((entry for entry in entries if entry), info)
        media: list[MediaItem] = []
        seen: set[str] = set()
        videos = [item for item in (info.get("formats") or [])
                  if item.get("url") and item.get("vcodec") not in (None, "none")]
        for index, item in enumerate(videos):
            url = item["url"]
            if url in seen:
                continue
            seen.add(url)
            media.append(MediaItem("video", url, index,
                                   int(item["tbr"] * 1000) if item.get("tbr") else None,
                                   item.get("width"), item.get("height"), item.get("ext")))
        return Metadata(post, media, info.get("title") or "")

    def _from_syndication(self, post: XPost) -> Metadata:
        # This public embed endpoint is unofficial and may change; keep it as a fallback.
        endpoint = "https://cdn.syndication.twimg.com/tweet-result"
        params = {"id": post.post_id, "lang": "en", "token": str(randbelow(900_000_000) + 100_000_000)}
        response = requests.get(endpoint, params=params, timeout=self.timeout_seconds,
                                headers={"User-Agent": "X2Telegram/1.0", "Accept": "application/json"})
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
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
                variants = [v for v in (item.get("video_info") or {}).get("variants", [])
                            if v.get("url") and v.get("content_type") == "video/mp4"]
                for variant in variants:
                    url = variant["url"]
                    if url in seen:
                        continue
                    seen.add(url)
                    width, height = (item.get("video_info") or {}).get("aspect_ratio") or (None, None)
                    media.append(MediaItem("video", url, index, bitrate=variant.get("bitrate"),
                                           width=width, height=height, mime_type="mp4"))
        return Metadata(post, media, payload.get("text") or "")
