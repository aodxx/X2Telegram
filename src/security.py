from pathlib import Path
from urllib.parse import urlsplit


ALLOWED_MEDIA_HOSTS = {"video.twimg.com", "pbs.twimg.com", "ton.twimg.com"}


def validate_media_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_MEDIA_HOSTS:
        raise ValueError("Media URL host is not an approved X media host")


def looks_like_html(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return head.startswith((b"<!doctype html", b"<html", b"<?xml"))


def validate_download(path: Path, kind: str = "unknown") -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Downloaded file is empty or missing")
    with path.open("rb") as fh:
        head = fh.read(512)
    if looks_like_html(head) or head.lstrip().startswith((b"{", b"[")):
        raise ValueError("Downloaded response appears to be HTML/JSON error content")
    if kind == "video" and b"ftyp" not in head[:128]:
        raise ValueError("Downloaded response is not a recognized MP4 file")
    if kind == "photo" and not (
        head.startswith(b"\xff\xd8\xff")
        or head.startswith(b"\x89PNG\r\n\x1a\n")
        or head.startswith(b"RIFF")
    ):
        raise ValueError("Downloaded response is not a recognized image file")
