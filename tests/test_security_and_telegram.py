from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from src.config import Config
from src.downloader import MediaDownloader
from src.errors import SourceRetrievalError
from src.security import validate_download, validate_media_url
from src.telegram_api import TelegramApiError, TelegramClient


def telegram_response(payload, status=200):
    response = Mock()
    response.ok = status < 400
    response.status_code = status
    response.text = str(payload)
    response.json.return_value = payload
    return response


def media_response(status=200, headers=None, chunks=()):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)
    response.status_code = status
    response.headers = headers or {}
    response.iter_content.return_value = list(chunks)
    return response


def media_response(status=200, headers=None, chunks=()):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)
    response.status_code = status
    response.headers = headers or {}
    response.iter_content.return_value = list(chunks)
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


def test_telegram_transport_error_does_not_expose_tokenized_url():
    token = "123456789:SUPERSENSITIVE_BOT_TOKEN"
    client = TelegramClient(token, "-1003906817580")
    failure = requests.ConnectionError(f"connection failed for https://api.telegram.org/bot{token}/getMe")
    with patch("src.telegram_api.requests.post", side_effect=failure):
        with pytest.raises(TelegramApiError) as raised:
            client.preflight()
    assert token not in str(raised.value)
    assert "SUPERSENSITIVE_BOT_TOKEN" not in str(raised.value)
    assert "api.telegram.org" not in str(raised.value)


def test_telegram_error_response_does_not_expose_raw_description():
    token = "123456789:SUPERSENSITIVE_BOT_TOKEN"
    response = telegram_response(
        {"ok": False, "error_code": 401,
         "description": f"unauthorized at https://api.telegram.org/bot{token}/getMe"},
        status=401,
    )
    with patch("src.telegram_api.requests.post", return_value=response):
        with pytest.raises(TelegramApiError) as raised:
            TelegramClient(token, "-1003906817580").preflight()
    assert token not in str(raised.value)
    assert "SUPERSENSITIVE_BOT_TOKEN" not in str(raised.value)
    assert str(raised.value) == "Telegram getMe failed (HTTP 401)"


def test_telegram_send_timeout_is_unconfirmed_and_is_not_retried(tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"media")
    client = TelegramClient("token", "-1003906817580", max_retries=3)
    with patch("src.telegram_api.requests.post", side_effect=requests.Timeout("response lost")) as post:
        with pytest.raises(TelegramApiError) as raised:
            client.send_video(str(media), "caption")
    assert raised.value.outcome_unknown is True
    assert post.call_count == 1


def test_telegram_send_server_error_is_unconfirmed_and_is_not_retried(tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"media")
    response = telegram_response({"ok": False, "error_code": 500}, status=500)
    client = TelegramClient("token", "-1003906817580", max_retries=3)
    with patch("src.telegram_api.requests.post", return_value=response) as post:
        with pytest.raises(TelegramApiError) as raised:
            client.send_video(str(media), "caption")
    assert raised.value.outcome_unknown is True
    assert post.call_count == 1


def test_telegram_send_retries_confirmed_rate_limit_and_returns_message_id(tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"media")
    limited = telegram_response({"ok": False, "error_code": 429, "parameters": {"retry_after": 2}}, status=429)
    sent = telegram_response({"ok": True, "result": {"message_id": 42}})
    client = TelegramClient("token", "-1003906817580", max_retries=2)
    with patch("src.telegram_api.requests.post", side_effect=[limited, sent]) as post, patch("src.telegram_api.time.sleep") as sleep:
        assert client.send_video(str(media), "caption") == 42
    assert post.call_count == 2
    sleep.assert_called_once_with(2)


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
    response.status_code = 200
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


def test_downloader_rejects_redirect_to_unapproved_host():
    redirect = Mock(status_code=302, headers={"location": "https://attacker.invalid/steal"})
    redirect.__enter__ = Mock(return_value=redirect)
    redirect.__exit__ = Mock(return_value=None)
    downloader = MediaDownloader(max_retries=1)
    with patch("src.downloader.requests.get", return_value=redirect) as get:
        with pytest.raises(SourceRetrievalError, match="unapproved host") as raised:
            downloader.download("https://video.twimg.com/a.mp4", "video")
    assert raised.value.code == "unsupported_media_url"
    assert get.call_count == 1
    assert get.call_args.kwargs["allow_redirects"] is False


def test_downloader_follows_validated_media_redirect(tmp_path: Path):
    redirect = Mock(status_code=302, headers={"location": "https://pbs.twimg.com/a.mp4"})
    redirect.__enter__ = Mock(return_value=redirect)
    redirect.__exit__ = Mock(return_value=None)
    final = Mock(status_code=200, headers={"content-type": "video/mp4", "content-length": "12"})
    final.__enter__ = Mock(return_value=final)
    final.__exit__ = Mock(return_value=None)
    final.raise_for_status.return_value = None
    final.iter_content.return_value = [b"xxxxftypxxxx"]
    downloader = MediaDownloader(max_retries=1)
    with patch("src.downloader.requests.get", side_effect=[redirect, final]) as get:
        result = downloader.download("https://video.twimg.com/a.mp4", "video")
    assert get.call_count == 2
    assert all(call.kwargs["allow_redirects"] is False for call in get.call_args_list)
    assert get.call_args_list[1].args[0] == "https://pbs.twimg.com/a.mp4"
    assert result.read_bytes() == b"xxxxftypxxxx"
    result.unlink()


def test_downloader_honors_retry_after_for_http_429(tmp_path: Path):
    limited = media_response(429, {"Retry-After": "7"})
    recovered = media_response(200, {"content-type": "video/mp4", "content-length": "12"}, [b"xxxxftypxxxx"])
    downloader = MediaDownloader(max_file_size_mb=1, max_retries=2)
    with patch("src.downloader.requests.get", side_effect=[limited, recovered]) as get, \
         patch("src.downloader.time.sleep") as sleep:
        result = downloader.download("https://video.twimg.com/a.mp4", "video")
    assert get.call_count == 2
    sleep.assert_called_once_with(7.0)
    assert result.read_bytes() == b"xxxxftypxxxx"
    result.unlink()


def test_downloader_retries_timeout_with_bounded_backoff(tmp_path: Path):
    recovered = media_response(200, {"content-type": "video/mp4", "content-length": "12"}, [b"xxxxftypxxxx"])
    downloader = MediaDownloader(max_file_size_mb=1, max_retries=2)
    with patch("src.downloader.requests.get", side_effect=[requests.Timeout("timed out"), recovered]) as get, \
         patch("src.downloader.time.sleep") as sleep:
        result = downloader.download("https://video.twimg.com/a.mp4", "video")
    assert get.call_count == 2
    sleep.assert_called_once_with(1)
    assert result.read_bytes() == b"xxxxftypxxxx"
    result.unlink()


def test_downloader_does_not_retry_permanent_404_or_leak_source_url():
    response = media_response(404)
    downloader = MediaDownloader(max_retries=3)
    with patch("src.downloader.requests.get", return_value=response) as get:
        with pytest.raises(SourceRetrievalError) as raised:
            downloader.download("https://video.twimg.com/private.mp4?token=secret", "video")
    assert get.call_count == 1
    assert raised.value.code == "source_media_unavailable"
    assert "token=secret" not in str(raised.value)
    assert "video.twimg.com" not in str(raised.value)


def test_downloader_reports_rate_limit_after_retry_budget_is_exhausted():
    limited = media_response(429, {"Retry-After": "1"})
    downloader = MediaDownloader(max_retries=2)
    with patch("src.downloader.requests.get", return_value=limited) as get, \
         patch("src.downloader.time.sleep") as sleep:
        with pytest.raises(SourceRetrievalError) as raised:
            downloader.download("https://video.twimg.com/a.mp4", "video")
    assert raised.value.code == "source_rate_limited"
    assert raised.value.attempts == 2
    assert get.call_count == 2
    sleep.assert_called_once_with(1.0)


def test_downloader_rejects_hls_playlist_with_specific_error():
    playlist = media_response(200, {"content-type": "application/x-mpegurl"})
    downloader = MediaDownloader(max_retries=1)
    with patch("src.downloader.requests.get", return_value=playlist):
        with pytest.raises(SourceRetrievalError) as raised:
            downloader.download("https://video.twimg.com/playlist.m3u8", "video")
    assert raised.value.code == "unsupported_media_format"
    assert "HLS" in str(raised.value)


def test_downloader_rejects_declared_file_above_limit_before_streaming():
    oversized = media_response(200, {"content-type": "video/mp4", "content-length": str(1024 * 1024 + 1)})
    downloader = MediaDownloader(max_file_size_mb=1, max_retries=1)
    with patch("src.downloader.requests.get", return_value=oversized):
        with pytest.raises(SourceRetrievalError) as raised:
            downloader.download("https://video.twimg.com/a.mp4", "video")
    assert raised.value.code == "media_too_large"


def test_downloader_bounds_redirect_loops():
    loop = media_response(302, {"location": "https://video.twimg.com/a.mp4"})
    downloader = MediaDownloader(max_retries=1)
    with patch("src.downloader.requests.get", return_value=loop) as get:
        with pytest.raises(SourceRetrievalError) as raised:
            downloader.download("https://video.twimg.com/a.mp4", "video")
    assert raised.value.code == "source_redirect_error"
    assert get.call_count == 6
