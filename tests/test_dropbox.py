import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config import Config
from src.dedupe import DedupeStore
from src.dropbox import DropboxUploader
from src.errors import DestinationError
from src.metadata import Metadata
from src.models import MediaItem
from src.processor import PostProcessor
from src.urls import parse_x_url


class Response:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._payload = payload or {}
        self.content = json.dumps(self._payload).encode()

    def json(self):
        return self._payload


class OneMedia:
    def get(self, post):
        return Metadata(post, [MediaItem("video", "https://media.invalid/a.mp4", 0)])


class FakeDropbox:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail
        self.names = []

    def upload(self, path, filename):
        self.calls += 1
        self.names.append(filename)
        if self.fail:
            raise DestinationError("dropbox_api_error", "Dropbox upload failed.")
        return "/X2Telegram/" + filename

    def close(self):
        pass


class FakeMega:
    def close(self):
        pass

    def upload(self, path, filename):
        return "/X2Telegram/2026-10-09"


def test_small_upload_uses_add_without_overwrite(tmp_path):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Response(payload={"path_display": "/X2Telegram/video_abc.mp4"})

    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    uploader = DropboxUploader(access_token="access", remote_folder="X2Telegram", request=request)
    assert uploader.upload(source, "video_abc.mp4") == "/X2Telegram/video_abc.mp4"
    assert calls[0][1].endswith("/files/upload")
    argument = json.loads(calls[0][2]["headers"]["Dropbox-API-Arg"])
    assert argument["mode"] == {".tag": "add"}
    assert argument["autorename"] is False
    assert calls[0][2]["headers"]["Authorization"] == "Bearer access"


def test_expired_access_token_refreshes_once_without_exposing_secret():
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/oauth2/token"):
            return Response(payload={"access_token": "refreshed"})
        if len([item for item in calls if item[1].endswith("/files/upload")]) == 1:
            return Response(401, payload={"error": "expired"})
        return Response(payload={"path_display": "/X2Telegram/a.mp4"})

    source = tmp_path = Path("/tmp") / "dropbox-refresh-test.mp4"
    source.write_bytes(b"x")
    try:
        uploader = DropboxUploader(access_token="expired", refresh_token="refresh", app_key="key", app_secret="secret", request=request)
        uploader.upload(source, "a.mp4")
        assert calls[1][0] == "POST" and calls[1][1].endswith("/oauth2/token")
        assert calls[-1][2]["headers"]["Authorization"] == "Bearer refreshed"
    finally:
        source.unlink(missing_ok=True)


def test_rate_limit_honors_retry_after():
    waits = []
    attempts = []

    def request(method, url, **kwargs):
        attempts.append(url)
        if len(attempts) == 1:
            return Response(429, payload={"error": "too_many_requests"}, headers={"Retry-After": "3"})
        return Response(payload={"path_display": "/X2Telegram/a.mp4"})

    source = Path("/tmp/dropbox-rate-test.mp4")
    source.write_bytes(b"x")
    try:
        DropboxUploader(access_token="token", request=request, sleep=waits.append).upload(source, "a.mp4")
        assert waits == [3.0]
    finally:
        source.unlink(missing_ok=True)


def test_large_upload_uses_session_start_append_finish(tmp_path):
    calls = []

    def request(method, url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/upload_session/start"):
            return Response(payload={"session_id": "session-1"})
        if url.endswith("/upload_session/append_v2"):
            return Response(payload={})
        return Response(payload={"path_display": "/X2Telegram/large.mp4"})

    source = tmp_path / "large.mp4"
    source.write_bytes(b"0123456789")
    uploader = DropboxUploader(access_token="token", request=request)
    uploader.SMALL_FILE_LIMIT = 4
    uploader.CHUNK_SIZE = 3
    assert uploader.upload(source, "large.mp4") == "/X2Telegram/large.mp4"
    assert [url.rsplit("/", 1)[-1] for url, _ in calls] == ["start", "append_v2", "append_v2", "finish"]


def test_missing_oauth_credentials_is_reported_without_api_call(tmp_path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"x")
    with pytest.raises(DestinationError) as raised:
        DropboxUploader(access_token="", refresh_token="").upload(source, "video.mp4")
    assert raised.value.code == "dropbox_credentials_missing"


def test_mega_and_dropbox_are_called_and_checkpointed_separately(tmp_path):
    store = DedupeStore(tmp_path / "dedupe.json")
    dropbox = FakeDropbox()
    config = Config(max_file_size_mb=2000, destinations=("mega", "dropbox"))
    processor = PostProcessor(config, OneMedia(), mega_uploader=FakeMega(), dropbox_uploader=dropbox, dedupe=store)
    source = tmp_path / "source.mp4"
    def download_again(url, kind):
        source.write_bytes(b"same-content")
        return source

    processor.downloader.download = download_again
    first = processor.process(parse_x_url("https://x.com/user/status/100"))
    assert first.destinations["mega"]["status"] == "success"
    assert first.destinations["dropbox"]["status"] == "success"
    assert dropbox.calls == 1
    second = processor.process(parse_x_url("https://x.com/user/status/100"))
    assert second.destinations["mega"]["status"] == "duplicate"
    assert second.destinations["dropbox"]["status"] == "duplicate"
    assert dropbox.calls == 1
