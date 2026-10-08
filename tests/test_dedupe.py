from pathlib import Path
import json
from unittest.mock import patch
import pytest

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


class MultiPhotoMetadata:
    def __init__(self, urls):
        self.urls = urls
        self.calls = 0

    def get(self, post):
        self.calls += 1
        return Metadata(post, [MediaItem("photo", url, index) for index, url in enumerate(self.urls)])


class SequencedPhotoTelegram:
    def __init__(self, fail_on=None, start_id=200):
        self.calls = 0
        self.fail_on = fail_on
        self.start_id = start_id

    def send_photo(self, path, caption):
        self.calls += 1
        if self.calls == self.fail_on:
            raise RuntimeError("send failed")
        return self.start_id + self.calls


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


def test_v1_completed_state_remains_a_whole_post_duplicate(tmp_path: Path):
    state_path = tmp_path / "dedupe.json"
    state_path.write_text(json.dumps({
        "version": 1,
        "posts": {
            "123": {
                "post_id": "123", "username": "user", "source_url": "https://x.com/user/status/123",
                "message_ids": [42], "sent_at": "2026-01-01T00:00:00+00:00",
            }
        },
    }), encoding="utf-8")
    store = DedupeStore(state_path)
    metadata = FakeMetadata()
    telegram = FakeTelegram()
    result = PostProcessor(Config("token", "-1003906817580"), metadata, telegram, dedupe=store).process(
        parse_x_url("https://x.com/user/status/123")
    )
    assert result.status == ResultStatus.SKIPPED_DUPLICATE
    assert result.message_ids == [42]
    assert metadata.calls == 0
    assert telegram.calls == 0


@pytest.mark.parametrize("fail_on", [1, 2, 3], ids=["first-media", "middle-media", "last-media"])
def test_retry_skips_sent_media_by_content_when_temporary_urls_change(tmp_path: Path, fail_on: int):
    store = DedupeStore(tmp_path / "dedupe.json")
    post = parse_x_url("https://x.com/user/status/456")
    first_urls = [
        "https://pbs.twimg.com/old-a.jpg?token=temporary-a",
        "https://pbs.twimg.com/old-b.jpg?token=temporary-b",
        "https://pbs.twimg.com/old-c.jpg?token=temporary-c",
    ]
    retry_urls = [
        "https://pbs.twimg.com/new-a.jpg?token=rotated-a",
        "https://pbs.twimg.com/new-b.jpg?token=rotated-b",
        "https://pbs.twimg.com/new-c.jpg?token=rotated-c",
    ]
    contents = {
        "old-a.jpg": b"photo-a-bytes", "new-a.jpg": b"photo-a-bytes",
        "old-b.jpg": b"photo-b-bytes", "new-b.jpg": b"photo-b-bytes",
        "old-c.jpg": b"photo-c-bytes", "new-c.jpg": b"photo-c-bytes",
    }

    def make_downloader():
        def download(url, kind):
            filename = url.split("/", 3)[-1].split("?", 1)[0].split("/")[-1]
            path = tmp_path / filename
            path.write_bytes(contents[filename])
            return path
        return download

    first_metadata = MultiPhotoMetadata(first_urls)
    first_telegram = SequencedPhotoTelegram(fail_on=fail_on)
    first_processor = PostProcessor(
        Config("token", "-1003906817580"), first_metadata, first_telegram, dedupe=store
    )
    with patch.object(first_processor.downloader, "download", side_effect=make_downloader()):
        first_result = first_processor.process(post)
    assert first_result.status == ResultStatus.TELEGRAM_ERROR
    record = store.get("456")
    assert len(first_result.message_ids) == fail_on - 1
    assert (record is None and fail_on == 1) or (
        record is not None and record["completed"] is False and len(record["media"]) == fail_on - 1
    )

    retry_metadata = MultiPhotoMetadata(retry_urls)
    retry_telegram = SequencedPhotoTelegram(start_id=300)
    retry_processor = PostProcessor(
        Config("token", "-1003906817580"), retry_metadata, retry_telegram, dedupe=store
    )
    with patch.object(retry_processor.downloader, "download", side_effect=make_downloader()):
        retry_result = retry_processor.process(post)
    assert retry_result.status == ResultStatus.SENT
    assert len(retry_result.message_ids) == 3
    assert retry_telegram.calls == 4 - fail_on
    assert retry_metadata.calls == 1
    assert store.get("456")["completed"] is True
    assert len(store.get("456")["media"]) == 3

    duplicate_metadata = MultiPhotoMetadata(retry_urls)
    duplicate_telegram = SequencedPhotoTelegram()
    duplicate_processor = PostProcessor(
        Config("token", "-1003906817580"), duplicate_metadata, duplicate_telegram, dedupe=store
    )
    with patch.object(duplicate_processor.downloader, "download", side_effect=make_downloader()):
        duplicate_result = duplicate_processor.process(post)
    assert duplicate_result.status == ResultStatus.SKIPPED_DUPLICATE
    assert len(duplicate_result.message_ids) == 3
    assert duplicate_metadata.calls == 1
    assert duplicate_telegram.calls == 0


def test_completed_post_sends_new_media_without_resending_existing_media(tmp_path: Path):
    store = DedupeStore(tmp_path / "dedupe.json")
    post = parse_x_url("https://x.com/user/status/789")
    contents = {"old-a.jpg": b"photo-a", "new-a.jpg": b"photo-a", "new-b.jpg": b"photo-b"}

    def download(url, kind):
        filename = url.split("/", 3)[-1].split("?", 1)[0].split("/")[-1]
        path = tmp_path / filename
        path.write_bytes(contents[filename])
        return path

    initial_metadata = MultiPhotoMetadata(["https://pbs.twimg.com/old-a.jpg?token=old"])
    initial_telegram = SequencedPhotoTelegram(start_id=200)
    initial_processor = PostProcessor(
        Config("token", "-1003906817580"), initial_metadata, initial_telegram, dedupe=store
    )
    with patch.object(initial_processor.downloader, "download", side_effect=download):
        initial_result = initial_processor.process(post)
    assert initial_result.status == ResultStatus.SENT
    assert store.get("789")["completed"] is True

    updated_metadata = MultiPhotoMetadata([
        "https://pbs.twimg.com/new-a.jpg?token=rotated",
        "https://pbs.twimg.com/new-b.jpg?token=rotated",
    ])
    updated_telegram = SequencedPhotoTelegram(start_id=300)
    updated_processor = PostProcessor(
        Config("token", "-1003906817580"), updated_metadata, updated_telegram, dedupe=store
    )
    with patch.object(updated_processor.downloader, "download", side_effect=download):
        updated_result = updated_processor.process(post)
    assert updated_result.status == ResultStatus.SENT
    assert updated_result.message_ids == [201, 301]
    assert updated_telegram.calls == 1
    assert len(store.get("789")["media"]) == 2
