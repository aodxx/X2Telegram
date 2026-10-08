from src.cli import build_summary
from src.cli import main
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


def test_build_summary_counts_destination_outcomes_separately():
    summary = build_summary([
        {"status": "partial_success", "destinations": {"telegram": {"status": "success"}, "mega": {"status": "failed"}}},
        {"status": "success", "destinations": {"telegram": {"status": "duplicate"}, "mega": {"status": "success"}, "download": {"status": "ready"}}},
    ])
    assert summary["destinations"] == {
        "telegram": {"success": 1, "duplicate": 1},
        "mega": {"failed": 1, "success": 1},
        "download": {"ready": 1},
    }


def test_sanitize_is_allow_listed_for_apps_script():
    payload = {
        "run_id": "1", "request_id": "gas-request-01", "job_id": "dashboard-job-01", "status": "completed",
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
    assert clean["job_id"] == "dashboard-job-01"
    item = clean["results"][0]
    assert "media_url" not in item
    assert "twimg" not in item["error"]
    assert "[url]" in item["error"]
    assert "[secret]" in item["error"]
    assert item["source_url"] == "https://x.com/u/status/9"


def test_invalid_request_id_is_not_forwarded():
    clean = sanitize_report({"request_id": "../../secret", "job_id": "../secret", "results": []})
    assert clean["request_id"] is None
    assert clean["job_id"] is None


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


def test_sanitizer_keeps_destination_statuses_but_drops_remote_paths_and_secrets():
    clean = sanitize_report({
        "selected_destinations": ["telegram", "mega", "download", "unknown"],
        "summary": {"total": 1, "destinations": {"telegram": {"success": 1}, "mega": {"failed": 1}, "unknown": {"success": 1}}},
        "results": [{"status": "partial_success", "destinations": {
            "telegram": {"status": "success", "items": [{"status": "success", "filename": "u_1_01.mp4", "message_id": 42}]},
            "mega": {"status": "failed", "error": "login password=not-a-secret", "items": [{"status": "failed", "filename": "u_1_01.mp4", "error_code": "mega_authentication_failed", "error": "failed https://mega.nz/private"}], "remote_folder": "/private/account"},
            "unknown": {"status": "success"},
        }}],
    })
    assert clean["selected_destinations"] == ["telegram", "mega", "download"]
    item = clean["results"][0]
    assert item["destinations"]["telegram"]["status"] == "success"
    assert item["destinations"]["telegram"]["items"][0]["message_id"] == 42
    assert item["destinations"]["mega"]["status"] == "failed"
    assert "[secret]" in item["destinations"]["mega"]["error"]
    assert "[url]" in item["destinations"]["mega"]["items"][0]["error"]
    assert "remote_folder" not in item["destinations"]["mega"]
    assert "unknown" not in item["destinations"]


def test_cli_report_includes_job_id(tmp_path, monkeypatch):
    import io
    import json
    import sys

    report_path = tmp_path / "report.json"
    monkeypatch.setenv("REQUEST_ID", "request-123")
    monkeypatch.setenv("JOB_ID", "job-0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    monkeypatch.setattr(sys, "stdin", io.StringIO("https://x.com/user/status/123\n"))
    monkeypatch.setattr(sys, "argv", ["src.cli", "--parse-only", "--report", str(report_path)])
    assert main() == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["request_id"] == "request-123"
    assert report["job_id"] == "job-0123456789abcdef0123456789abcdef"
