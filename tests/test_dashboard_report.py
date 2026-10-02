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


def test_sanitize_whitelists_and_redacts_urls():
    payload = {
        "run_id": "1", "status": "completed", "summary": {"total": 1},
        "telegram_preflight": {"chat_id": "-100", "member_status": "administrator"},
        "TELEGRAM_BOT_TOKEN": "secret",
        "results": [{
            "post_id": "9", "username": "u", "source_url": "https://x.com/u/status/9",
            "status": "download_error", "stage": "download", "error_code": "download_error",
            "error": "failed https://video.twimg.com/a.mp4?tag=12 timeout",
            "media_url": "https://video.twimg.com/a.mp4",
        }],
    }
    clean = sanitize_report(payload)
    assert "telegram_preflight" not in clean and "TELEGRAM_BOT_TOKEN" not in clean
    item = clean["results"][0]
    assert "media_url" not in item
    assert "twimg" not in item["error"] and "[url]" in item["error"]
    assert item["source_url"] == "https://x.com/u/status/9"
