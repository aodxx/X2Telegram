from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.config import Config
from src.dedupe import DedupeStore
from src.destinations import DestinationError, DestinationDispatcher, DownloadExporter, MegaUploader, safe_filename, totp_code
from src.metadata import Metadata
from src.models import MediaItem, ResultStatus
from src.processor import PostProcessor
from src.urls import parse_x_url


class OneMediaMetadata:
    def get(self, post):
        return Metadata(post, [MediaItem("video", "https://media.invalid/a.mp4", 0, bitrate=100)])


class MixedMediaMetadata:
    def get(self, post):
        return Metadata(post, [
            MediaItem("photo", "https://media.invalid/photo.jpg", 0),
            MediaItem("video", "https://media.invalid/low.mp4", 1, bitrate=100),
            MediaItem("video", "https://media.invalid/high.mp4", 2, bitrate=200),
        ])


class FakeTelegram:
    def __init__(self):
        self.calls = 0
        self.uploaded_names = []

    def send_video(self, path, caption):
        self.calls += 1
        self.uploaded_names.append(Path(path).name)
        return 700 + self.calls

    def send_photo(self, path, caption):
        self.calls += 1
        self.uploaded_names.append(Path(path).name)
        return 700 + self.calls

    def send_document(self, path, caption):
        self.calls += 1
        self.uploaded_names.append(Path(path).name)
        return 700 + self.calls


class FakeMega:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail
        self.uploaded_names = []
        self.requested_filenames = []

    def upload(self, path, filename):
        self.calls += 1
        self.uploaded_names.append(Path(path).name)
        self.requested_filenames.append(filename)
        if self.fail:
            raise DestinationError("mega_upload_failed", "MEGA upload failed.")
        return "/X2Telegram/2026-10-09"

    def close(self):
        pass


def make_processor(tmp_path, destinations, *, telegram=None, mega=None, dedupe=None, download=None, config=None):
    config = config or Config(
        "bot-token" if "telegram" in destinations else "",
        "-1003906817580" if "telegram" in destinations else "",
        max_file_size_mb=2000 if any(target != "telegram" for target in destinations) else 50,
        destinations=tuple(destinations),
    )
    processor = PostProcessor(
        config, OneMediaMetadata(), telegram, dedupe=dedupe, mega_uploader=mega,
        download_exporter=download,
    )
    path = tmp_path / "source.mp4"
    path.write_bytes(b"valid-enough-test-fixture")
    return processor, path


def test_all_three_destinations_use_one_download_and_report_each_status(tmp_path):
    telegram = FakeTelegram()
    mega = FakeMega()
    exporter = DownloadExporter(tmp_path / "exports")
    processor, media_path = make_processor(
        tmp_path, ["telegram", "mega", "download"], telegram=telegram, mega=mega, download=exporter,
    )
    with patch.object(processor.downloader, "download", return_value=media_path) as download:
        result = processor.process(parse_x_url("https://x.com/user/status/123"))
    assert download.call_count == 1
    assert telegram.calls == 1 and mega.calls == 1
    assert telegram.uploaded_names == ["user_123_01.mp4"]
    assert mega.uploaded_names == ["user_123_01.mp4"]
    assert len(mega.requested_filenames) == 1
    assert __import__("re").fullmatch(r"user_123_01_[0-9a-f]{64}\.mp4", mega.requested_filenames[0])
    assert result.destinations["mega"]["items"][0]["filename"] == mega.requested_filenames[0]
    assert result.status == ResultStatus.SUCCESS
    assert result.destinations["telegram"]["status"] == "success"
    assert result.destinations["mega"]["status"] == "success"
    assert result.destinations["download"]["status"] == "ready"
    exported = tmp_path / "exports" / "user_123_01.mp4"
    assert exported.read_bytes() == b"valid-enough-test-fixture"


def test_mixed_photo_video_post_keeps_photo_and_downloads_best_video_once(tmp_path):
    telegram = FakeTelegram()
    mega = FakeMega()
    exporter = DownloadExporter(tmp_path / "exports")
    config = Config("bot-token", "-1003906817580", max_file_size_mb=2000, destinations=("telegram", "mega", "download"))
    processor = PostProcessor(config, MixedMediaMetadata(), telegram, mega_uploader=mega, download_exporter=exporter)
    downloaded = []

    def fake_download(url, kind):
        path = tmp_path / ("photo.jpg" if kind == "photo" else "video.mp4")
        path.write_bytes(url.encode())
        downloaded.append(url)
        return path

    with patch.object(processor.downloader, "download", side_effect=fake_download) as download:
        result = processor.process(parse_x_url("https://x.com/user/status/126"))

    assert download.call_count == 2
    assert downloaded == ["https://media.invalid/photo.jpg", "https://media.invalid/high.mp4"]
    assert telegram.calls == 2 and mega.calls == 2
    assert result.media_count == 2
    assert sorted(item.name for item in (tmp_path / "exports").iterdir()) == ["user_126_01.jpg", "user_126_02.mp4"]


@pytest.mark.parametrize("destinations", [("mega",), ("download",), ("telegram", "download")])
def test_important_single_and_pair_destination_paths_succeed(tmp_path, destinations):
    telegram = FakeTelegram() if "telegram" in destinations else None
    mega = FakeMega() if "mega" in destinations else None
    exporter = DownloadExporter(tmp_path / "exports") if "download" in destinations else None
    processor, media_path = make_processor(
        tmp_path, destinations, telegram=telegram, mega=mega, download=exporter,
    )
    with patch.object(processor.downloader, "download", return_value=media_path) as download:
        result = processor.process(parse_x_url("https://x.com/user/status/124"))
    assert result.status == ResultStatus.SUCCESS
    assert download.call_count == 1
    for destination in destinations:
        expected = "ready" if destination == "download" else "success"
        assert result.destinations[destination]["status"] == expected


def test_download_only_does_not_persist_delivery_dedupe(tmp_path):
    store = DedupeStore(tmp_path / "dedupe.json")
    exporter = DownloadExporter(tmp_path / "exports")
    processor, media_path = make_processor(tmp_path, ["download"], download=exporter, dedupe=store)
    with patch.object(processor.downloader, "download", return_value=media_path):
        result = processor.process(parse_x_url("https://x.com/user/status/125"))
    assert result.destinations["download"]["status"] == "ready"
    assert store.get("125") is None


def test_failed_mega_does_not_resend_telegram_on_retry(tmp_path):
    store = DedupeStore(tmp_path / "dedupe.json")
    telegram = FakeTelegram()
    post = parse_x_url("https://x.com/user/status/456")
    first_mega = FakeMega(fail=True)
    first, media_path = make_processor(tmp_path, ["telegram", "mega"], telegram=telegram, mega=first_mega, dedupe=store)
    with patch.object(first.downloader, "download", return_value=media_path):
        initial = first.process(post)
    assert initial.status == ResultStatus.PARTIAL_SUCCESS
    assert initial.destinations["telegram"]["status"] == "success"
    assert initial.destinations["mega"]["status"] == "failed"
    assert telegram.calls == 1

    retry_mega = FakeMega()
    retry, retry_path = make_processor(tmp_path, ["telegram", "mega"], telegram=telegram, mega=retry_mega, dedupe=store)
    with patch.object(retry.downloader, "download", return_value=retry_path):
        retried = retry.process(post)
    assert retried.status == ResultStatus.SUCCESS
    assert retried.destinations["telegram"]["status"] == "duplicate"
    assert retried.destinations["mega"]["status"] == "success"
    assert telegram.calls == 1
    assert retry_mega.calls == 1


def test_mega_only_without_credentials_fails_only_mega_target(tmp_path):
    processor, media_path = make_processor(tmp_path, ["mega"], mega=MegaUploader(email="", password=""))
    with patch.object(processor.downloader, "download", return_value=media_path):
        result = processor.process(parse_x_url("https://x.com/user/status/789"))
    assert result.status == ResultStatus.FAILED
    assert result.destinations["mega"]["status"] == "failed"
    assert result.destinations["mega"]["items"][0]["error_code"] == "mega_credentials_missing"


def test_invalid_mega_folder_does_not_block_other_destinations(tmp_path):
    telegram = FakeTelegram()
    exporter = DownloadExporter(tmp_path / "exports")
    invalid_mega = MegaUploader(remote_folder="../invalid")
    processor, media_path = make_processor(
        tmp_path, ["telegram", "mega", "download"], telegram=telegram, mega=invalid_mega, download=exporter,
    )
    with patch.object(processor.downloader, "download", return_value=media_path):
        result = processor.process(parse_x_url("https://x.com/user/status/790"))
    assert result.status == ResultStatus.PARTIAL_SUCCESS
    assert result.destinations["telegram"]["status"] == "success"
    assert result.destinations["mega"]["status"] == "failed"
    assert result.destinations["mega"]["items"][0]["error_code"] == "mega_configuration_error"
    assert result.destinations["download"]["status"] == "ready"
    assert telegram.calls == 1


def test_mega_auth_and_upload_commands_use_date_folder_without_leaking_output(tmp_path):
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        output = "safe_name.mp4" if args[0] == "mega-ls" else "session details"
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    media_path = tmp_path / "safe_name.mp4"
    media_path.write_bytes(b"video")
    uploader = MegaUploader(
        email="owner@example.com", password="sensitive-password", remote_folder="X2Telegram",
        runner=runner, which=lambda _name: True,
    )
    remote = uploader.upload(media_path, "safe_name.mp4", timestamp=datetime(2026, 10, 9, tzinfo=timezone.utc))
    assert remote == "/X2Telegram/2026-10-09"
    assert calls[0][0] == "mega-login"
    assert calls[1] == ["mega-put", "-c", str(media_path.resolve()), "/X2Telegram/2026-10-09"]
    assert calls[2] == ["mega-ls", "/X2Telegram/2026-10-09/safe_name.mp4"]
    uploader.close()
    assert calls[-1] == ["mega-logout"]


def test_mega_upload_uses_requested_filename_without_mutating_source(tmp_path):
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        if args[0] == "mega-login":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[0] == "mega-put":
            staged = Path(args[2])
            assert staged.name == "safe_name.mp4"
            assert staged.read_bytes() == b"video"
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[0] == "mega-ls":
            return SimpleNamespace(returncode=0, stdout="/X2Telegram/2026-10-09/safe_name.mp4", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    source = tmp_path / "temporary-download.mp4"
    source.write_bytes(b"video")
    uploader = MegaUploader(
        email="owner@example.com", password="p", remote_folder="X2Telegram",
        runner=runner, which=lambda _name: True,
    )
    remote = uploader.upload(source, "safe_name.mp4", timestamp=datetime(2026, 10, 9, tzinfo=timezone.utc))
    assert remote == "/X2Telegram/2026-10-09"
    assert source.exists()
    assert source.read_bytes() == b"video"
    assert not Path(calls[1][2]).exists()  # staged copy is cleaned up after the command
    uploader.close()


def test_mega_upload_fails_if_remote_file_cannot_be_verified(tmp_path):
    media_path = tmp_path / "safe_name.mp4"
    media_path.write_bytes(b"video")

    def runner(args, **kwargs):
        if args[0] == "mega-ls":
            return SimpleNamespace(returncode=0, stdout="/X2Telegram/2026-10-09/other_file.mp4", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    uploader = MegaUploader(
        email="owner@example.com", password="p", runner=runner, which=lambda _name: True,
    )
    with pytest.raises(DestinationError) as raised:
        uploader.upload(media_path, "safe_name.mp4", timestamp=datetime(2026, 10, 9, tzinfo=timezone.utc))
    assert raised.value.code == "mega_upload_verification_failed"
    uploader.close()


def test_mega_upload_rejects_filename_path_components(tmp_path):
    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"video")
    uploader = MegaUploader(email="owner@example.com", password="p", runner=lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""), which=lambda _name: True)
    with pytest.raises(DestinationError) as raised:
        uploader.upload(media_path, "../unsafe.mp4")
    assert raised.value.code == "mega_configuration_error"


def test_mega_login_failure_discards_client_output(tmp_path):
    def runner(args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="password=private", stderr="session=private")

    uploader = MegaUploader(email="owner@example.com", password="p", runner=runner, which=lambda _name: True)
    with pytest.raises(DestinationError) as raised:
        uploader.upload(tmp_path / "missing.mp4", "safe.mp4")
    assert raised.value.code == "mega_authentication_failed"
    assert "private" not in str(raised.value)


def test_totp_uses_rfc6238_six_digit_vector():
    # RFC 6238 test secret; the six-digit truncation of the 8-digit reference is 287082 at t=59.
    assert totp_code("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", timestamp=59) == "287082"


def test_safe_filename_prevents_path_injection():
    assert safe_filename("../evil user", "123/../../", 2, ".MP4") == "evil_user_123_02.mp4"


def test_download_export_enforces_total_archive_size_before_copy(tmp_path):
    exporter = DownloadExporter(tmp_path / "exports", max_total_bytes=4)
    source = tmp_path / "five-bytes.mp4"
    source.write_bytes(b"12345")
    with pytest.raises(DestinationError) as raised:
        exporter.export(source, "safe.mp4")
    assert raised.value.code == "download_artifact_size_limit"
    assert not (tmp_path / "exports" / "safe.mp4").exists()


def test_telegram_standard_size_limit_is_per_destination(tmp_path):
    telegram = FakeTelegram()
    mega = FakeMega()
    config = Config("bot-token", "-1003906817580", max_file_size_mb=2000, destinations=("telegram", "mega"))
    dispatcher = DestinationDispatcher(config, telegram, mega)
    sparse = tmp_path / "large.mp4"
    with sparse.open("wb") as handle:
        handle.truncate(51 * 1024 * 1024)
    with pytest.raises(DestinationError, match="50 MB"):
        dispatcher.deliver("telegram", sparse, "large.mp4", "caption", "video")
    assert dispatcher.deliver("mega", sparse, "large.mp4", "caption", "video")["remote_folder"] == "/X2Telegram/2026-10-09"


def test_non_telegram_destinations_can_run_without_telegram_secrets(monkeypatch):
    monkeypatch.setenv("DESTINATIONS_JSON", '["download", "mega"]')
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    config = Config.from_env()
    assert config.destinations == ("mega", "download")
    assert config.max_file_size_mb == 2000
    assert not config.telegram_bot_token


def test_destination_parser_rejects_unknown_and_duplicate_names():
    from src.config import parse_destinations

    with pytest.raises(ValueError, match="unsupported"):
        parse_destinations('["telegram", "gdrive"]')
    with pytest.raises(ValueError, match="unique"):
        parse_destinations('["mega", "mega"]')
