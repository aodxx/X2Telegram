import json
from pathlib import Path
from unittest.mock import patch

from src.config import Config
from src.metadata import Metadata
from src.models import MediaItem, ResultStatus
from src.processor import PostProcessor
from src.security import validate_download
from src.urls import parse_x_url


class FakeMetadata:
    def get(self, post):
        return Metadata(post, [MediaItem("video", "https://media.invalid/a.mp4", 0, bitrate=100)])


class FakeTelegram:
    def send_video(self, path, caption):
        assert Path(path).exists()
        return 42


def test_worker_sends_and_cleans_download(tmp_path):
    config = Config("token", "chat", max_file_size_mb=1)
    processor = PostProcessor(config, FakeMetadata(), FakeTelegram())
    fake = tmp_path / "video.mp4"
    fake.write_bytes(b"not-html-media")
    with patch.object(processor.downloader, "download", return_value=fake):
        result = processor.process(parse_x_url("https://x.com/user/status/123"))
    assert result.status == ResultStatus.SENT
    assert result.message_ids == [42]
    assert not fake.exists()


def test_validate_rejects_html(tmp_path):
    path = tmp_path / "bad"
    path.write_bytes(b"<!doctype html><body>error</body>")
    try:
        validate_download(path)
    except ValueError as exc:
        assert "HTML" in str(exc)
    else:
        raise AssertionError("HTML response must be rejected")
