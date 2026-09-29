from dataclasses import dataclass
from typing import Any
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
    """Extract public X media URLs without downloading the post itself."""

    def __init__(self, timeout_seconds: int = 60):
        self.timeout_seconds = timeout_seconds

    def get(self, post: XPost) -> Metadata:
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

        if not media:
            for index, item in enumerate(info.get("thumbnails") or []):
                url = item.get("url")
                ext = (item.get("ext") or "").lower()
                if url and url not in seen and (ext in {"jpg", "jpeg", "png", "webp"} or ".jpg" in url or ".png" in url):
                    seen.add(url)
                    media.append(MediaItem("photo", url, index, mime_type=ext or "jpg"))
        return Metadata(post, media, info.get("title") or "")
