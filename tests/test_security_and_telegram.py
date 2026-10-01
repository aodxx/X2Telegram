from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.config import Config
from src.downloader import MediaDownloader
from src.security import validate_download, validate_media_url
from src.telegram_api import TelegramClient


def telegram_response(payload, status=200):
    response = Mock()
    response.ok = status < 400
    response.status_code = status
    response.text = str(payload)
    response.json.return_value = payload
    return response


def test_config_rejects_non_project_chat():
    with pytest.raises(ValueError, match="-1003906817580"):
        Config("token", "-100123")


def test_standard_mode_rejects_size_above_50_mb():
    with pytest.raises(ValueError, match="standard mode"):
        Config("token", "-1003906817580", max_file_size_mb=51)


def test_large_mode_requires_local_api_endpoint():
    with pytest.raises(ValueError, match="Local Bot API"):
        Config("token", "-1003906817580", max_file_size_mb=2000, large_file_mode=True)


def test_large_mode_accepts_custom_endpoint():
    config = Config(
        "token",
        "-1003906817580",
        max_file_size_mb=2000,
        large_file_mode=True,
        telegram_api_base_url="http://127.0.0.1:8081",
    )
    assert config.telegram_api_base_url == "http://127.0.0.1:8081"


def test_telegram_preflight_checks_bot_and_membership():
    responses = [
        telegram_response({"ok": True, "result": {"id": 123, "is_bot": True, "username": "xbot"}}),
        telegram_response({"ok": True, "result": {"id": -1003906817580, "type": "supergroup"}}),
        telegram_response({"ok": True, "result": {"status": "administrator"}}),
    ]
    with patch("src.telegram_api.requests.post", side_effect=responses) as post:
        result = TelegramClient("token", "-1003906817580").preflight()
    assert result.member_status == "administrator"
    assert post.call_count == 3


def test_telegram_client_uses_custom_endpoint():
    client = TelegramClient(
        "token", "-1003906817580", api_base_url="http://127.0.0.1:8081"
    )
    assert client.base_url == "http://127.0.0.1:8081/bottoken"


def test_media_url_must_be_https_x_media_host():
    validate_media_url("https://video.twimg.com/ext_tw_video/1/vid/1280x720/video.mp4")
    with pytest.raises(ValueError):
        validate_media_url("https://example.invalid/video.mp4")


def test_validate_download_requires_mp4_signature(tmp_path: Path):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"not-an-mp4")
    with pytest.raises(ValueError, match="recognized MP4"):
        validate_download(path, "video")


def test_downloader_writes_atomic_mp4(tmp_path: Path):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)
    response.headers = {"content-type": "video/mp4", "content-length": "12"}
    response.iter_content.return_value = [b"xxxxftypxxxx"]
    response.raise_for_status.return_value = None
    with patch("src.downloader.requests.get", return_value=response):
        result = MediaDownloader(max_file_size_mb=1).download(
            "https://video.twimg.com/ext_tw_video/1/vid/1280x720/video.mp4", "video"
        )
    assert result.suffix == ".mp4"
    assert result.read_bytes() == b"xxxxftypxxxx"
    assert not result.with_suffix(".part").exists()
    result.unlink()
