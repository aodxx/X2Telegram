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
    """Extract public X media through yt-dlp and public metadata fallbacks."""

    def __init__(self, timeout_seconds: int = 60):
        self.timeout_seconds = timeout_seconds

    def get(self, post: XPost) -> Metadata:
        errors: list[str] = []
        try:
            metadata = self._from_ytdlp(post)
            if metadata.media:
                return metadata
        except Exception as exc:
            errors.append(f"yt-dlp: {exc}")

        for name, provider in (("syndication", self._from_syndication), ("fxtwitter", self._from_fxtwitter)):
            try:
                fallback = provider(post)
                if fallback.media:
                    return fallback
                # An empty public response is a valid no-media result; continue
                # to the next provider before declaring no media.
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        if errors and len(errors) == 3:
            raise RuntimeError("; ".join(errors))
        return Metadata(post, [])

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

    def _from_fxtwitter(self, post: XPost) -> Metadata:
        """Use FxTwitter's public status API when other metadata sources are empty."""
        endpoint = f"https://api.fxtwitter.com/2/status/{post.post_id}"
        response = requests.get(
            endpoint,
            timeout=self.timeout_seconds,
            headers={"User-Agent": "X2Telegram/1.0", "Accept": "application/json"},
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        if payload.get("code") not in (None, 200):
            raise RuntimeError(f"FxTwitter API returned code {payload.get('code')}")
        status = payload.get("status") or {}
        media = status.get("media") or {}
        items = media.get("all") or media.get("videos") or []
        results: list[MediaItem] = []
        seen: set[str] = set()
        for index, item in enumerate(items):
            kind = item.get("type")
            if kind == "video":
                variants = [
                    variant for variant in (item.get("formats") or [])
                    if variant.get("url") and variant.get("container") == "mp4"
                ]
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
