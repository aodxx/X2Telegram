"""Build a public-safe report for the dashboard from the full run report.

Whitelist only: anything not listed here never leaves the workflow.
URLs inside error text are redacted so direct media links are not published.
"""
import json
import re
import sys

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_TOP_KEYS = (
    "schema_version", "run_id", "request_id", "status", "started_at", "finished_at",
    "duration_seconds", "large_file_mode", "input_count", "valid_unique_posts", "summary", "error_code",
)
_RESULT_KEYS = (
    "post_id", "username", "source_url", "status", "stage", "error_code", "media_count", "message_ids", "filenames",
)


def redact(text):
    if not text:
        return text
    return _URL_RE.sub("[url]", str(text))[:300]


def sanitize_report(payload: dict) -> dict:
    out = {key: payload.get(key) for key in _TOP_KEYS if key in payload}
    if payload.get("error"):
        out["error"] = redact(payload["error"])
    out["results"] = []
    for item in payload.get("results", []):
        clean = {key: item.get(key) for key in _RESULT_KEYS if key in item}
        if item.get("error"):
            clean["error"] = redact(item["error"])
        out["results"].append(clean)
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python -m src.dashboard_report INPUT OUTPUT", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as handle:
        payload = json.load(handle)
    with open(argv[2], "w", encoding="utf-8") as handle:
        json.dump(sanitize_report(payload), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
