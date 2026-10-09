"""Create the private, API-safe report consumed by the Control Worker.

The full workflow report stays in the GitHub Actions artifact. The dashboard
projection is allow-listed and must never expose credentials, MEGA session data,
or media URLs.
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
_SAFE_DESTINATIONS = {"telegram", "mega", "dropbox", "download"}
_SAFE_DESTINATION_STATUSES = {"success", "failed", "partial_success", "duplicate", "ready", "no_media", "processing"}
_SAFE_ITEM_STATUSES = {"success", "failed", "duplicate", "ready"}
_SAFE_CODE_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,80}$")

_TOP_KEYS = (
    "schema_version", "run_id", "request_id", "job_id", "status", "started_at", "finished_at",
    "duration_seconds", "large_file_mode", "input_count", "valid_unique_posts",
    "dedupe_enabled", "summary", "error_code",
)
_RESULT_KEYS = (
    "post_id", "username", "source_url", "status", "stage", "error_code",
    "media_count", "message_ids", "filenames", "destinations",
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


def _safe_code(value: Any) -> str | None:
    candidate = str(value or "")
    return candidate if _SAFE_CODE_RE.fullmatch(candidate) else None


def _safe_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _safe_summary(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    keys = ("total", "sent", "skipped_duplicate", "no_media", "failed")
    summary: dict[str, Any] = {key: _safe_count(source.get(key, 0)) for key in keys}
    raw_destinations = source.get("destinations") if isinstance(source.get("destinations"), dict) else {}
    destinations = {}
    for name in _SAFE_DESTINATIONS:
        raw_counts = raw_destinations.get(name)
        if not isinstance(raw_counts, dict):
            continue
        destinations[name] = {
            status: _safe_count(raw_counts.get(status, 0))
            for status in _SAFE_DESTINATION_STATUSES
            if status in raw_counts
        }
    if destinations:
        summary["destinations"] = destinations
    return summary


def _safe_destination_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"status": "failed", "error_code": "invalid_result"}
    clean: dict[str, Any] = {}
    status = str(item.get("status", ""))
    clean["status"] = status if status in _SAFE_ITEM_STATUSES else "failed"
    if item.get("filename") is not None:
        filename = str(item["filename"]).replace("\\", "/").split("/")[-1]
        clean["filename"] = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:160]
    if isinstance(item.get("message_id"), int):
        clean["message_id"] = item["message_id"]
    code = _safe_code(item.get("error_code"))
    if code:
        clean["error_code"] = code
    if item.get("error"):
        clean["error"] = redact(item["error"])
    warning = _safe_code(item.get("warning"))
    if warning:
        clean["warning"] = warning
    return clean


def _safe_destinations(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    clean = {}
    for name, details in value.items():
        if name not in _SAFE_DESTINATIONS or not isinstance(details, dict):
            continue
        status = str(details.get("status", ""))
        target: dict[str, Any] = {"status": status if status in _SAFE_DESTINATION_STATUSES else "failed"}
        code = _safe_code(details.get("error_code"))
        if code:
            target["error_code"] = code
        if details.get("error"):
            target["error"] = redact(details["error"])
        if isinstance(details.get("items"), list):
            target["items"] = [_safe_destination_item(item) for item in details["items"][:100]]
        clean[name] = target
    return clean


def _safe_selected_destinations(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [name for name in ("telegram", "mega", "dropbox", "download") if name in value and value.count(name) == 1]


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
            clean[key] = _safe_count(value)
        elif key == "message_ids":
            clean[key] = [int(message_id) for message_id in (value or []) if isinstance(message_id, int)][:100]
        elif key == "filenames":
            clean[key] = [_bounded_text(filename, 160) for filename in (value or [])][:100]
        elif key == "destinations":
            clean[key] = _safe_destinations(value)
    if item.get("error"):
        clean["error"] = redact(item["error"])
    return clean


def sanitize_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Return only allow-listed fields needed by the private Dashboard API."""
    out: dict[str, Any] = {key: payload[key] for key in _TOP_KEYS if key in payload}
    out["request_id"] = _safe_request_id(payload.get("request_id"))
    out["job_id"] = _safe_request_id(payload.get("job_id"))
    out["summary"] = _safe_summary(payload.get("summary"))
    selected_destinations = _safe_selected_destinations(payload.get("selected_destinations"))
    if selected_destinations:
        out["selected_destinations"] = selected_destinations
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
