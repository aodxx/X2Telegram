from pathlib import Path

def looks_like_html(data: bytes) -> bool:
    head=data[:512].lstrip().lower()
    return head.startswith((b"<!doctype html", b"<html", b"<?xml"))

def validate_download(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Downloaded file is empty or missing")
    with path.open("rb") as fh: head=fh.read(512)
    if looks_like_html(head): raise ValueError("Downloaded response appears to be HTML/error content")
