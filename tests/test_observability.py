import json
import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.logging_utils import configure_logging, redact
from src.notifications import NotificationError, build_summary, send_webhook, write_github_summary
from src.cli import _write_report


def test_redact_removes_bot_token_and_query_secrets():
    value = "https://api.telegram.org/bot12345:SECRET/getMe?token=hidden"
    safe = redact(value)
    assert "SECRET" not in safe
    assert "hidden" not in safe
    assert "bot12345:" not in safe
    assert "[REDACTED_BOT_TOKEN]" in safe


def test_raw_report_redacts_bot_token_from_stdout_and_file(tmp_path: Path, capsys):
    token = "123456789:REPORT_SUPERSECRET_TOKEN"
    report_path = tmp_path / "report.json"
    _write_report({
        "status": "completed_with_errors",
        "TELEGRAM_BOT_TOKEN": token,
        "results": [{
            "status": "telegram_error",
            "error": f"request failed https://api.telegram.org/bot{token}/sendPhoto",
        }],
    }, str(report_path))
    written = report_path.read_text(encoding="utf-8")
    printed = capsys.readouterr().out
    assert token not in written + printed
    assert "REPORT_SUPERSECRET_TOKEN" not in written + printed
    assert "TELEGRAM_BOT_TOKEN" not in written
    assert "[REDACTED_BOT_TOKEN]" in written


def test_build_summary_contains_counts_without_media_urls():
    report = {
        "status": "completed_with_errors",
        "run_id": "123",
        "duration_seconds": 1.2,
        "input_count": 2,
        "valid_unique_posts": 2,
        "results": [
            {"status": "sent", "media_url": "https://video.twimg.com/private"},
            {"status": "download_error"},
        ],
    }
    summary = build_summary(report)
    assert summary["counts"] == {"sent": 1, "download_error": 1}
    assert "media_url" not in json.dumps(summary)


def test_webhook_requires_https():
    with pytest.raises(NotificationError, match="HTTPS"):
        send_webhook({}, "http://example.invalid/hook")


def test_webhook_sends_summary_only():
    response = Mock(ok=True, status_code=200)
    with patch("src.notifications.requests.post", return_value=response) as post:
        assert send_webhook({"status": "sent", "results": [{"status": "sent", "url": "secret"}]}, "https://example.com/hook")
    payload = post.call_args.kwargs["json"]
    assert payload["source"] == "x2telegram"
    assert "url" not in json.dumps(payload)


def test_github_summary_is_written(tmp_path: Path):
    path = tmp_path / "summary.md"
    write_github_summary(
        {"status": "completed", "input_count": 1, "valid_unique_posts": 1, "duration_seconds": 0.5,
         "results": [{"status": "sent"}]},
        str(path),
    )
    text = path.read_text(encoding="utf-8")
    assert "X2Telegram run summary" in text
    assert "`sent`" in text


def test_json_logger_writes_one_json_line(tmp_path: Path):
    path = tmp_path / "run.jsonl"
    logger = configure_logging(str(path))
    logger.info("hello", extra={"event": "test", "context": {"token": "secret", "count": 1}})
    line = path.read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert parsed["event"] == "test"
    assert "secret" not in line
