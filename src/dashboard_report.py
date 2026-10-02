"""Create the private, API-safe report consumed by Google Apps Script.

The full workflow report stays in the GitHub Actions artifact. This module
creates an allow-listed projection for the backend; it must never be
published to a public Git branch or served directly from GitHub Pages.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SECRET_RE = re.compile(
    r"(?i)(?:bearer\s+|(?:token|api[_ -]?key|secret|password|authorization)\s*[:=]\s*)[^\s,;]+"
)
_SAFE_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

_TOP_KEYS = (
    "schema_version", "run_id", "request_id", "status", "started_at", "finished_at",
    "duration_seconds", "large_file_mode", "input_count", "valid_unique_posts",
    "dedupe_enabled", "summary", "error_code",
)
_RESULT_KEYS = (
    "post_id", "username", "source_url", "status", "stage", "error_code",
    "media_count", "message_ids", "filenames",
)
_MAX_TEXT = 300


def _bounded_text(value: Any, limit: int = _MAX_TEXT) -> str | None:
    if value is None:
        return None
    return str(value)[:limit]


def redact(value: Any) -> str | None:
    """Remove URLs and credential-like values from errors before API output."""
    if value is None:
        return None
    text = _URL_RE.sub("[url]", str(value))
    text = _SECRET_RE.sub("[secret]", text)
    return text[:_MAX_TEXT]


def _safe_request_id(value: Any) -> str | None:
    if value is None or value == "":
        return None
    candidate = str(value)
    return candidate if _SAFE_REQUEST_ID_RE.fullmatch(candidate) else None


def _safe_summary(value: Any) -> dict[str, int]:
    source = value if isinstance(value, dict) else {}
    keys = ("total", "sent", "skipped_duplicate", "no_media", "failed")
    return {key: max(0, int(source.get(key, 0) or 0)) for key in keys}


def _safe_result(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"status": "error", "error_code": "invalid_result"}
    clean: dict[str, Any] = {}
    for key in _RESULT_KEYS:
        if key not in item:
            continue
        value = item[key]
        if key in {"source_url", "username", "post_id", "status", "stage", "error_code"}:
            clean[key] = _bounded_text(value)
        elif key == "media_count":
            clean[key] = max(0, int(value or 0))
        elif key == "message_ids":
            clean[key] = [int(message_id) for message_id in (value or [])]
        elif key == "filenames":
            clean[key] = [_bounded_text(filename, 160) for filename in (value or [])]
    if item.get("error"):
        clean["error"] = redact(item["error"])
    return clean


def sanitize_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Return only the fields Google Apps Script needs from a workflow report."""
    out: dict[str, Any] = {key: payload[key] for key in _TOP_KEYS if key in payload}
    out["request_id"] = _safe_request_id(payload.get("request_id"))
    out["summary"] = _safe_summary(payload.get("summary"))
    if payload.get("error"):
        out["error"] = redact(payload["error"])
    out["results"] = [_safe_result(item) for item in (payload.get("results") or [])]
    return out


def write_sanitized_report(input_path: str | Path, output_path: str | Path) -> None:
    with Path(input_path).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("workflow report must be a JSON object")
    with Path(output_path).open("w", encoding="utf-8") as handle:
        json.dump(sanitize_report(payload), handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python -m src.dashboard_report INPUT OUTPUT", file=sys.stderr)
        return 2
    write_sanitized_report(argv[1], argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
