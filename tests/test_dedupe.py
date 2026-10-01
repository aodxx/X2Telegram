from pathlib import Path
from unittest.mock import patch

from src.config import Config
from src.dedupe import DedupeStore
from src.metadata import Metadata
from src.models import MediaItem, ResultStatus
from src.processor import PostProcessor
from src.urls import parse_x_url


class FakeMetadata:
    def __init__(self):
        self.calls = 0

    def get(self, post):
        self.calls += 1
        return Metadata(post, [MediaItem("video", "https://media.invalid/a.mp4", 0, bitrate=100)])


class FakeTelegram:
    def __init__(self):
        self.calls = 0

    def send_video(self, path, caption):
        self.calls += 1
        return 42


class FailingTelegram(FakeTelegram):
    def send_video(self, path, caption):
        self.calls += 1
        raise RuntimeError("send failed")


def test_dedupe_store_is_atomic_and_reloadable(tmp_path: Path):
    store = DedupeStore(tmp_path / "state" / "dedupe.json")
    assert store.get("123") is None
    store.mark_sent("123", post_id="123", username="user", source_url="https://x.com/user/status/123", message_ids=[42])
    assert store.get("123")["message_ids"] == [42]
    assert not list((tmp_path / "state").glob(".dedupe-*.tmp"))


def test_processor_skips_duplicate_before_metadata_or_download(tmp_path: Path):
    store = DedupeStore(tmp_path / "dedupe.json")
    store.mark_sent("123", post_id="123", username="user", source_url="https://x.com/user/status/123", message_ids=[42])
    metadata = FakeMetadata()
    telegram = FakeTelegram()
    config = Config("token", "-1003906817580", max_file_size_mb=1)
    processor = PostProcessor(config, metadata, telegram, dedupe=store)
    result = processor.process(parse_x_url("https://x.com/user/status/123"))
    assert result.status == ResultStatus.SKIPPED_DUPLICATE
    assert result.error_code == "already_sent"
    assert metadata.calls == 0
    assert telegram.calls == 0


def test_processor_marks_only_successful_send(tmp_path: Path):
    store = DedupeStore(tmp_path / "dedupe.json")
    metadata = FakeMetadata()
    telegram = FakeTelegram()
    config = Config("token", "-1003906817580", max_file_size_mb=1)
    processor = PostProcessor(config, metadata, telegram, dedupe=store)
    fake = tmp_path / "video.mp4"
    fake.write_bytes(b"media")
    with patch.object(processor.downloader, "download", return_value=fake):
        result = processor.process(parse_x_url("https://x.com/user/status/123"))
    assert result.status == ResultStatus.SENT
    assert store.get("123")["message_ids"] == [42]


def test_processor_does_not_mark_failed_send(tmp_path: Path):
    store = DedupeStore(tmp_path / "dedupe.json")
    config = Config("token", "-1003906817580", max_file_size_mb=1)
    processor = PostProcessor(config, FakeMetadata(), FailingTelegram(), dedupe=store)
    fake = tmp_path / "video.mp4"
    fake.write_bytes(b"media")
    with patch.object(processor.downloader, "download", return_value=fake):
        result = processor.process(parse_x_url("https://x.com/user/status/123"))
    assert result.status == ResultStatus.TELEGRAM_ERROR
    assert store.get("123") is None
