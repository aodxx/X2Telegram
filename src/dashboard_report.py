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
_SAFE_DESTINATION_STATUSES = {"success", "failed", "partial_success", "duplicate", "ready", "no_media", "processing", "outcome_unconfirmed"}
_SAFE_ITEM_STATUSES = {"success", "failed", "duplicate", "ready", "outcome_unconfirmed"}
_SAFE_MEDIA_DOWNLOAD_STATUSES = {"pending", "validated", "failed", "processing_failed"}
_SAFE_MEDIA_DESTINATION_STATUSES = _SAFE_ITEM_STATUSES | {"not_attempted"}
_SAFE_RECONCILIATION_STATUSES = {"complete", "metadata_failed", "not_enumerated"}
_SAFE_CODE_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,80}$")
_SAFE_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_SAFE_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,50}$")
_SAFE_POST_ID_RE = re.compile(r"^\d{1,32}$")
_SAFE_X_URL_RE = re.compile(r"^https://x\.com/[A-Za-z0-9_]{1,50}/status/\d{1,32}$")
_SAFE_INPUT_DISPOSITIONS = {"accepted", "duplicate", "normalized_duplicate", "rejected"}

_TOP_KEYS = (
    "schema_version", "run_id", "request_id", "job_id", "status", "started_at", "finished_at",
    "duration_seconds", "large_file_mode", "input_count", "blank_line_count", "valid_unique_posts",
    "dedupe_enabled", "summary", "input_summary", "error_code",
)
_RESULT_KEYS = (
    "post_id", "username", "source_url", "status", "stage", "error_code",
    "media_count", "message_ids", "filenames", "destinations", "media_manifest", "media_reconciliation",
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
    if "outcome_unconfirmed" in source:
        summary["outcome_unconfirmed"] = _safe_count(source.get("outcome_unconfirmed"))
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
    stage = _safe_code(item.get("stage"))
    if stage:
        clean["stage"] = stage
    if item.get("media_index") is not None:
        clean["media_index"] = max(1, _safe_count(item.get("media_index")))
    for key in ("attempts", "variant_attempts"):
        if item.get(key) is not None:
            clean[key] = max(1, _safe_count(item.get(key)))
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
        stage = _safe_code(details.get("stage"))
        if stage:
            target["stage"] = stage
        if details.get("attempts") is not None:
            target["attempts"] = max(1, _safe_count(details.get("attempts")))
        if isinstance(details.get("items"), list):
            target["items"] = [_safe_destination_item(item) for item in details["items"][:100]]
        clean[name] = target
    return clean


def _safe_media_manifest(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    clean = []
    for item in value[:100]:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if not isinstance(kind, str) or kind not in {"photo", "video"}:
            continue
        download_status = str(item.get("download_status", ""))
        entry: dict[str, Any] = {
            "media_index": max(1, _safe_count(item.get("media_index"))),
            "source_index": _safe_count(item.get("source_index")),
            "kind": kind,
            "download_status": download_status if download_status in _SAFE_MEDIA_DOWNLOAD_STATUSES else "failed",
        }
        for key in ("bitrate", "width", "height"):
            if item.get(key) is not None:
                entry[key] = _safe_count(item.get(key))
        if item.get("size_bytes") is not None:
            entry["size_bytes"] = _safe_count(item.get("size_bytes"))
        digest = str(item.get("sha256") or "")
        if _SAFE_SHA256_RE.fullmatch(digest):
            entry["sha256"] = digest.lower()
        code = _safe_code(item.get("error_code"))
        if code:
            entry["error_code"] = code
        destinations = item.get("destinations") if isinstance(item.get("destinations"), dict) else {}
        entry["destinations"] = {}
        for name in ("telegram", "mega", "dropbox", "download"):
            destination_status = destinations.get(name)
            if isinstance(destination_status, str) and destination_status in _SAFE_MEDIA_DESTINATION_STATUSES:
                entry["destinations"][name] = destination_status
        clean.append(entry)
    return clean


def _safe_media_reconciliation(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    status = str(source.get("status", ""))
    clean: dict[str, Any] = {"status": status if status in _SAFE_RECONCILIATION_STATUSES else "metadata_failed"}
    for key in ("expected_items", "downloaded_items", "download_failed_items", "processing_failed_items"):
        raw = source.get(key)
        clean[key] = None if raw is None else _safe_count(raw)
    raw_destinations = source.get("destinations") if isinstance(source.get("destinations"), dict) else {}
    clean_destinations = {}
    count_keys = ("expected_items", "accounted_items", "delivered_items", "duplicate_items", "failed_items", "unaccounted_items")
    for name in ("telegram", "mega", "dropbox", "download"):
        raw = raw_destinations.get(name)
        if not isinstance(raw, dict):
            continue
        clean_destinations[name] = {
            key: None if raw.get(key) is None else _safe_count(raw.get(key))
            for key in count_keys
        }
        if "unconfirmed_items" in raw:
            clean_destinations[name]["unconfirmed_items"] = _safe_count(raw.get("unconfirmed_items"))
    clean["destinations"] = clean_destinations
    return clean


def _safe_selected_destinations(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [name for name in ("telegram", "mega", "dropbox", "download") if name in value and value.count(name) == 1]


def _safe_input_summary(value: Any, outcome_count: int) -> dict[str, int]:
    source = value if isinstance(value, dict) else {}
    counts = {
        key: _safe_count(source.get(key, 0))
        for key in ("accepted", "duplicate", "normalized_duplicate", "rejected")
    }
    submitted = sum(counts.values())
    if submitted != outcome_count:
        submitted = outcome_count
        counts["rejected"] = max(0, submitted - counts["accepted"] - counts["duplicate"] - counts["normalized_duplicate"])
    return {
        "submitted": submitted,
        **counts,
        "blank_lines_ignored": _safe_count(source.get("blank_lines_ignored", 0)),
    }


def _safe_input_outcome(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"disposition": "rejected", "status": "rejected", "error_code": "invalid_result"}
    disposition = str(item.get("disposition", ""))
    if disposition not in _SAFE_INPUT_DISPOSITIONS:
        disposition = "rejected"
    clean: dict[str, Any] = {
        "index": max(1, _safe_count(item.get("index"))),
        "line_number": max(1, _safe_count(item.get("line_number"))),
        "disposition": disposition,
        "status": _safe_code(item.get("status")) or disposition,
    }
    post_id = str(item.get("post_id") or "")
    if _SAFE_POST_ID_RE.fullmatch(post_id):
        clean["post_id"] = post_id
    username = str(item.get("username") or "")
    if _SAFE_USERNAME_RE.fullmatch(username):
        clean["username"] = username
    source_url = str(item.get("source_url") or "")
    if _SAFE_X_URL_RE.fullmatch(source_url):
        clean["source_url"] = source_url
    duplicate_of = _safe_count(item.get("duplicate_of"))
    if duplicate_of:
        clean["duplicate_of"] = duplicate_of
    stage = _safe_code(item.get("stage"))
    if stage:
        clean["stage"] = stage
    code = _safe_code(item.get("error_code"))
    if code:
        clean["error_code"] = code
    for key in ("attempts", "variant_attempts"):
        if item.get(key) is not None:
            clean[key] = max(1, _safe_count(item.get(key)))
    if item.get("error"):
        clean["error"] = redact(item["error"])
    return clean


def _safe_result(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"status": "error", "error_code": "invalid_result"}
    clean: dict[str, Any] = {}
    for key in _RESULT_KEYS:
        if key not in item:
            continue
        value = item[key]
        if key == "source_url":
            source_url = str(value or "")
            if _SAFE_X_URL_RE.fullmatch(source_url):
                clean[key] = source_url
        elif key == "username":
            username = str(value or "")
            clean[key] = username if _SAFE_USERNAME_RE.fullmatch(username) else "unknown"
        elif key == "post_id":
            post_id = str(value or "")
            if _SAFE_POST_ID_RE.fullmatch(post_id):
                clean[key] = post_id
        elif key in {"status", "stage", "error_code"}:
            clean[key] = _safe_code(value) or "error"
        elif key == "media_count":
            clean[key] = _safe_count(value)
        elif key == "message_ids":
            clean[key] = [int(message_id) for message_id in (value or []) if isinstance(message_id, int)][:100]
        elif key == "filenames":
            clean[key] = [_bounded_text(filename, 160) for filename in (value or [])][:100]
        elif key == "destinations":
            clean[key] = _safe_destinations(value)
        elif key == "media_manifest":
            clean[key] = _safe_media_manifest(value)
        elif key == "media_reconciliation":
            clean[key] = _safe_media_reconciliation(value)
    if item.get("error"):
        clean["error"] = redact(item["error"])
    return clean


def sanitize_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Return only allow-listed fields needed by the private Dashboard API."""
    out: dict[str, Any] = {key: payload[key] for key in _TOP_KEYS if key in payload}
    out["request_id"] = _safe_request_id(payload.get("request_id"))
    out["job_id"] = _safe_request_id(payload.get("job_id"))
    out["summary"] = _safe_summary(payload.get("summary"))
    raw_outcomes = payload.get("input_outcomes") if isinstance(payload.get("input_outcomes"), list) else []
    out["input_outcomes"] = [_safe_input_outcome(item) for item in raw_outcomes]
    out["input_summary"] = _safe_input_summary(payload.get("input_summary"), len(out["input_outcomes"]))
    out["blank_line_count"] = _safe_count(payload.get("blank_line_count", out["input_summary"]["blank_lines_ignored"]))
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
