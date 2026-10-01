import os
from urllib.parse import urlsplit

import requests


class NotificationError(RuntimeError):
    pass


def build_summary(report: dict) -> dict:
    results = report.get("results", [])
    counts: dict[str, int] = {}
    for item in results:
        status = str(item.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return {
        "status": report.get("status", "unknown"),
        "run_id": report.get("run_id"),
        "duration_seconds": report.get("duration_seconds"),
        "input_count": report.get("input_count", 0),
        "valid_unique_posts": report.get("valid_unique_posts", 0),
        "counts": counts,
    }


def send_webhook(report: dict, webhook_url: str | None = None, timeout: int = 10) -> bool:
    """Send an opt-in generic JSON webhook; never sends secrets or media URLs."""
    url = (webhook_url or os.getenv("ALERT_WEBHOOK_URL", "")).strip()
    if not url:
        return False
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise NotificationError("ALERT_WEBHOOK_URL must be an HTTPS URL")
    payload = {"source": "x2telegram", "summary": build_summary(report)}
    response = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json", "User-Agent": "X2Telegram/1.0"},
        timeout=timeout,
    )
    if not response.ok:
        raise NotificationError(f"Alert webhook failed with HTTP {response.status_code}")
    return True


def write_github_summary(report: dict, path: str | None = None) -> None:
    target = path or os.getenv("GITHUB_STEP_SUMMARY", "")
    if not target:
        return
    summary = build_summary(report)
    lines = [
        "## X2Telegram run summary",
        "",
        f"- Status: `{summary['status']}`",
        f"- Input URLs: `{summary['input_count']}`",
        f"- Unique posts: `{summary['valid_unique_posts']}`",
        f"- Duration: `{summary['duration_seconds']}s`",
        "",
        "| Result | Count |",
        "|---|---:|",
    ]
    lines.extend(f"| `{key}` | {value} |" for key, value in sorted(summary["counts"].items()))
    with open(target, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
