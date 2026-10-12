import io
import json
import sys
from pathlib import Path

from src.config import Config
from src.errors import SourceRetrievalError
from src.metadata import Metadata
from src.models import MediaItem
from src import cli


class FakeMetadataProvider:
    def __init__(self, _timeout_seconds, max_retries=None):
        self.max_retries = max_retries

    def get(self, post):
        return Metadata(post, [MediaItem("photo", f"https://pbs.twimg.com/{post.post_id}.jpg", 0)])


def test_cli_keeps_successes_around_failed_url_and_reconciles_inputs(tmp_path, monkeypatch, capsys):
    raw = (
        " https://x.com/user/status/1?s=20 \r\n"
        "\r\n"
        "not-an-x-url\r\n"
        "https://x.com/user/status/2\r\n"
        "https://mobile.twitter.com/user/status/1?utm_source=test\r\n"
        "https://x.com/user/status/3\r\n"
    )
    report_path = tmp_path / "report.json"
    export_dir = tmp_path / "exports"
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    monkeypatch.setattr(sys, "argv", ["src.cli", "--report", str(report_path)])
    monkeypatch.setattr(cli.Config, "from_env", lambda: Config(destinations=("download",), max_file_size_mb=50, max_retries=2))
    providers = []
    class TrackingMetadataProvider(FakeMetadataProvider):
        def __init__(self, timeout_seconds, max_retries=None):
            super().__init__(timeout_seconds, max_retries)
            providers.append(self)
    monkeypatch.setattr(cli, "YtDlpMetadataProvider", TrackingMetadataProvider)
    monkeypatch.setenv("DOWNLOAD_EXPORT_DIR", str(export_dir))

    def download(_downloader, url, _kind):
        if url.endswith("/2.jpg"):
            raise SourceRetrievalError(
                "source_rate_limited", "X is rate limiting this media request (HTTP 429).", "download", attempts=2,
            )
        path = tmp_path / f"source-{url.rsplit('/', 1)[-1]}"
        path.write_bytes(b"local-test-image")
        return path

    monkeypatch.setattr("src.downloader.MediaDownloader.download", download)
    assert cli.main() == 1
    capsys.readouterr()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["status"] == "partial_success"
    assert report["input_count"] == 5
    assert report["blank_line_count"] == 1
    assert report["valid_unique_posts"] == 3
    assert [item["post_id"] for item in report["results"]] == ["1", "2", "3"]
    assert [item["status"] for item in report["results"]] == ["success", "failed", "success"]
    assert report["results"][1]["stage"] == "download"
    assert report["results"][1]["error_code"] == "source_rate_limited"
    assert report["input_outcomes"][2]["error_code"] == "source_rate_limited"
    assert report["input_outcomes"][2]["attempts"] == 2
    assert report["input_outcomes"][2]["variant_attempts"] == 1
    assert len(providers) == 1 and providers[0].max_retries == 2
    assert report["input_summary"] == {
        "submitted": 5,
        "accepted": 3,
        "duplicate": 0,
        "normalized_duplicate": 1,
        "rejected": 1,
        "blank_lines_ignored": 1,
    }
    assert [item["disposition"] for item in report["input_outcomes"]] == [
        "accepted", "rejected", "accepted", "normalized_duplicate", "accepted",
    ]
    assert "utm_source" not in json.dumps(report)
    assert "not-an-x-url" not in json.dumps(report)
    assert len(list(export_dir.glob("*.zip"))) <= 1
