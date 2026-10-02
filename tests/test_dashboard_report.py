from src.cli import build_summary
from src.dashboard_report import sanitize_report


def test_build_summary_counts_statuses():
    results = [
        {"status": "sent"}, {"status": "sent"}, {"status": "skipped_duplicate"},
        {"status": "no_media"}, {"status": "telegram_error"}, {"status": "metadata_error"},
    ]
    assert build_summary(results) == {
        "total": 6, "sent": 2, "skipped_duplicate": 1, "no_media": 1, "failed": 2,
    }


def test_build_summary_empty():
    assert build_summary([])["total"] == 0


def test_sanitize_is_allow_listed_for_apps_script():
    payload = {
        "run_id": "1", "request_id": "gas-request-01", "status": "completed",
        "summary": {"total": 1},
        "telegram_preflight": {"chat_id": "-100", "member_status": "administrator"},
        "TELEGRAM_BOT_TOKEN": "secret",
        "results": [{
            "post_id": "9", "username": "u", "source_url": "https://x.com/u/status/9",
            "status": "download_error", "stage": "download", "error_code": "download_error",
            "error": "failed https://video.twimg.com/a.mp4?tag=12 token=abc123",
            "media_url": "https://video.twimg.com/a.mp4",
        }],
    }
    clean = sanitize_report(payload)
    assert "telegram_preflight" not in clean
    assert "TELEGRAM_BOT_TOKEN" not in clean
    assert clean["request_id"] == "gas-request-01"
    item = clean["results"][0]
    assert "media_url" not in item
    assert "twimg" not in item["error"]
    assert "[url]" in item["error"]
    assert "[secret]" in item["error"]
    assert item["source_url"] == "https://x.com/u/status/9"


def test_invalid_request_id_is_not_forwarded():
    clean = sanitize_report({"request_id": "../../secret", "results": []})
    assert clean["request_id"] is None


def test_summary_and_result_values_are_normalized():
    clean = sanitize_report({
        "summary": {"total": -2, "sent": "2"},
        "results": [{"media_count": "3", "message_ids": [4], "filenames": ["a.mp4"]}],
    })
    assert clean["summary"] == {
        "total": 0, "sent": 2, "skipped_duplicate": 0, "no_media": 0, "failed": 0,
    }
    assert clean["results"][0]["media_count"] == 3
    assert clean["results"][0]["message_ids"] == [4]
