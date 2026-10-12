from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys

import pytest
import requests

from src.errors import SourceRetrievalError
from src.metadata import Metadata, YtDlpMetadataProvider
from src.models import MediaItem
from src.urls import parse_x_url


def json_response(payload, status=200, headers=None):
    response = Mock()
    response.status_code = status
    response.headers = headers or {}
    response.json.return_value = payload
    return response


def test_syndication_extracts_photo_and_strips_source_query():
    provider = YtDlpMetadataProvider(timeout_seconds=5)
    payload = {
        "text": "photo",
        "mediaDetails": [{
            "type": "photo",
            "media_url_https": "https://pbs.twimg.com/media/example.jpg",
            "original_info": {"width": 1200, "height": 800},
        }],
    }
    post = parse_x_url("https://x.com/user/status/123?s=20")
    with patch("src.metadata.requests.get", return_value=json_response(payload)) as get:
        result = provider._from_syndication(post)
    assert result.media[0].kind == "photo"
    assert result.media[0].width == 1200
    assert "s=20" not in post.normalized_url
    get.assert_called_once()


def test_fxtwitter_extracts_high_quality_mp4_variants():
    provider = YtDlpMetadataProvider(timeout_seconds=5)
    payload = {
        "code": 200,
        "status": {
            "text": "video",
            "media": {
                "all": [{
                    "type": "video",
                    "width": 1280,
                    "height": 720,
                    "formats": [
                        {"container": "m3u8", "url": "https://video.twimg.com/stream.m3u8"},
                        {"container": "mp4", "bitrate": 256000, "url": "https://video.twimg.com/low.mp4?tag=12"},
                        {"container": "mp4", "bitrate": 2176000, "filesize": 80_000_000, "url": "https://video.twimg.com/high.mp4?tag=12"},
                    ],
                }]
            },
        },
    }
    post = parse_x_url("https://x.com/user/status/123")
    with patch("src.metadata.requests.get", return_value=json_response(payload)):
        result = provider._from_fxtwitter(post)
    assert [item.bitrate for item in result.media] == [256000, 2176000]
    assert [item.index for item in result.media] == [0, 0]
    assert result.media[-1].size_bytes == 80_000_000
    assert result.media[-1].url.endswith("?tag=12")


def test_syndication_assigns_one_media_index_to_each_video_and_its_variants():
    provider = YtDlpMetadataProvider(timeout_seconds=5)
    post = parse_x_url("https://x.com/user/status/123")
    payload = {"mediaDetails": [
        {"type": "video", "video_info": {"variants": [
            {"content_type": "video/mp4", "bitrate": 100, "url": "https://video.twimg.com/first-low.mp4"},
            {"content_type": "video/mp4", "bitrate": 200, "url": "https://video.twimg.com/first-high.mp4"},
        ]}},
        {"type": "video", "video_info": {"variants": [
            {"content_type": "video/mp4", "bitrate": 150, "url": "https://video.twimg.com/second-low.mp4"},
            {"content_type": "video/mp4", "bitrate": 300, "url": "https://video.twimg.com/second-high.mp4"},
        ]}},
    ]}
    with patch("src.metadata.requests.get", return_value=json_response(payload)):
        result = provider._from_syndication(post)
    assert [item.index for item in result.media] == [0, 0, 1, 1]


def test_ytdlp_filters_hls_and_keeps_progressive_mp4():
    provider = YtDlpMetadataProvider(timeout_seconds=5)
    post = parse_x_url("https://x.com/user/status/123")

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def extract_info(self, _url, download=False):
            assert download is False
            return {"formats": [
                {"url": "https://video.twimg.com/playlist.m3u8?sig=secret", "vcodec": "h264", "protocol": "m3u8_native", "ext": "mp4", "tbr": 2200},
                {"url": "https://video.twimg.com/direct.mp4?sig=secret", "vcodec": "h264", "protocol": "https", "ext": "mp4", "tbr": 900},
            ]}

    with patch.dict(sys.modules, {"yt_dlp": SimpleNamespace(YoutubeDL=FakeYoutubeDL)}):
        result = provider._from_ytdlp(post)
    assert len(result.media) == 1
    assert result.media[0].bitrate == 900_000
    assert result.media[0].url.endswith("direct.mp4?sig=secret")


def test_ytdlp_assigns_same_media_index_to_all_video_formats():
    provider = YtDlpMetadataProvider(timeout_seconds=5)
    post = parse_x_url("https://x.com/user/status/123")

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def extract_info(self, _url, download=False):
            return {"formats": [
                {"url": "https://video.twimg.com/low.mp4", "vcodec": "h264", "protocol": "https", "ext": "mp4", "tbr": 100},
                {"url": "https://video.twimg.com/high.mp4", "vcodec": "h264", "protocol": "https", "ext": "mp4", "tbr": 200},
            ]}

    with patch.dict(sys.modules, {"yt_dlp": SimpleNamespace(YoutubeDL=FakeYoutubeDL)}):
        result = provider._from_ytdlp(post)
    assert len(result.media) == 2
    assert [item.index for item in result.media] == [0, 0]


def test_ytdlp_metadata_uses_configured_bounded_retry_budget():
    provider = YtDlpMetadataProvider(timeout_seconds=5, max_retries=1)
    post = parse_x_url("https://x.com/user/status/123")
    captured = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured.update(options)
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def extract_info(self, _url, download=False):
            return {"formats": []}

    with patch.dict(sys.modules, {"yt_dlp": SimpleNamespace(YoutubeDL=FakeYoutubeDL)}):
        provider._from_ytdlp(post)
    assert captured["retries"] == 0
    assert captured["extractor_retries"] == 0


def test_ytdlp_reports_unsupported_when_only_hls_exists():
    provider = YtDlpMetadataProvider(timeout_seconds=5)
    post = parse_x_url("https://x.com/user/status/123")

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def extract_info(self, _url, download=False):
            return {"formats": [{
                "url": "https://video.twimg.com/playlist.m3u8?sig=secret",
                "vcodec": "h264", "protocol": "m3u8_native", "ext": "mp4",
            }]}

    with patch.dict(sys.modules, {"yt_dlp": SimpleNamespace(YoutubeDL=FakeYoutubeDL)}):
        with pytest.raises(SourceRetrievalError) as raised:
            provider._from_ytdlp(post)
    assert raised.value.code == "unsupported_media_format"
    assert "secret" not in str(raised.value)


def test_get_uses_public_mp4_fallback_after_unsupported_hls():
    provider = YtDlpMetadataProvider(timeout_seconds=5)
    post = parse_x_url("https://x.com/user/status/123")
    fallback = Metadata(post, [MediaItem("video", "https://video.twimg.com/direct.mp4", 0, bitrate=100)])
    with patch.object(provider, "_from_ytdlp", side_effect=SourceRetrievalError(
        "unsupported_media_format", "Only HLS streams were returned.", "metadata")), \
         patch.object(provider, "_from_syndication", return_value=fallback):
        result = provider.get(post)
    assert result.media == fallback.media


def test_get_does_not_hide_transient_provider_failure_as_no_media():
    provider = YtDlpMetadataProvider(timeout_seconds=5)
    post = parse_x_url("https://x.com/user/status/123")
    empty = Metadata(post, [])
    timeout = SourceRetrievalError("source_timeout", "Timed out safely.", "metadata", retryable=True, attempts=2)
    with patch.object(provider, "_from_ytdlp", return_value=empty), \
         patch.object(provider, "_from_syndication", side_effect=timeout), \
         patch.object(provider, "_from_fxtwitter", return_value=empty):
        with pytest.raises(SourceRetrievalError) as raised:
            provider.get(post)
    assert raised.value.code == "source_timeout"
    assert raised.value.attempts == 2


def test_get_reports_no_media_only_when_all_providers_return_empty_successfully():
    provider = YtDlpMetadataProvider(timeout_seconds=5)
    post = parse_x_url("https://x.com/user/status/123")
    empty = Metadata(post, [])
    with patch.object(provider, "_from_ytdlp", return_value=empty), \
         patch.object(provider, "_from_syndication", return_value=empty), \
         patch.object(provider, "_from_fxtwitter", return_value=empty):
        assert provider.get(post).media == []


def test_metadata_provider_honors_retry_after_for_http_429():
    provider = YtDlpMetadataProvider(timeout_seconds=5, max_retries=3)
    post = parse_x_url("https://x.com/user/status/123")
    limited = json_response({}, status=429, headers={"Retry-After": "7"})
    recovered = json_response({"mediaDetails": []})
    with patch("src.metadata.requests.get", side_effect=[limited, recovered]) as get, \
         patch("src.metadata.time.sleep") as sleep:
        result = provider._from_syndication(post)
    assert result.media == []
    assert get.call_count == 2
    sleep.assert_called_once_with(7.0)


def test_metadata_provider_respects_one_attempt_budget():
    provider = YtDlpMetadataProvider(timeout_seconds=5, max_retries=1)
    limited = json_response({}, status=429, headers={"Retry-After": "7"})
    with patch("src.metadata.requests.get", return_value=limited) as get, \
         patch("src.metadata.time.sleep") as sleep:
        with pytest.raises(SourceRetrievalError) as raised:
            provider._get_json("https://cdn.syndication.twimg.com/tweet-result")
    assert raised.value.code == "source_rate_limited"
    assert raised.value.attempts == 1
    get.assert_called_once()
    sleep.assert_not_called()


def test_metadata_redirects_stay_on_the_same_approved_https_host():
    provider = YtDlpMetadataProvider(timeout_seconds=5, max_retries=1)
    redirect = json_response({}, status=302, headers={"Location": "/tweet-result-v2"})
    final = json_response({"mediaDetails": []})
    with patch("src.metadata.requests.get", side_effect=[redirect, final]) as get:
        payload = provider._get_json(
            "https://cdn.syndication.twimg.com/tweet-result", params={"id": "123", "token": "synthetic"},
        )
    assert payload == {"mediaDetails": []}
    assert get.call_count == 2
    assert all(call.kwargs["allow_redirects"] is False for call in get.call_args_list)
    assert get.call_args_list[1].args[0] == "https://cdn.syndication.twimg.com/tweet-result-v2"
    assert get.call_args_list[1].kwargs["params"] is None


def test_metadata_provider_rejects_cross_host_redirect_without_following_it():
    provider = YtDlpMetadataProvider(timeout_seconds=5, max_retries=1)
    redirect = json_response({}, status=302, headers={"Location": "https://attacker.invalid/collect?token=synthetic"})
    with patch("src.metadata.requests.get", return_value=redirect) as get:
        with pytest.raises(SourceRetrievalError) as raised:
            provider._get_json("https://cdn.syndication.twimg.com/tweet-result", params={"token": "synthetic"})
    assert raised.value.code == "source_redirect_error"
    assert "attacker.invalid" not in str(raised.value)
    assert "synthetic" not in str(raised.value)
    get.assert_called_once()
    assert get.call_args.kwargs["allow_redirects"] is False


def test_metadata_provider_bounds_same_host_redirect_loop():
    provider = YtDlpMetadataProvider(timeout_seconds=5, max_retries=1)
    loop = json_response({}, status=302, headers={"Location": "/again"})
    with patch("src.metadata.requests.get", return_value=loop) as get:
        with pytest.raises(SourceRetrievalError) as raised:
            provider._get_json("https://api.fxtwitter.com/2/status/123")
    assert raised.value.code == "source_redirect_error"
    assert get.call_count == 6


def test_metadata_provider_classifies_malformed_json_without_leaking_response():
    provider = YtDlpMetadataProvider(timeout_seconds=5, max_retries=3)
    post = parse_x_url("https://x.com/user/status/123")
    malformed = json_response({})
    malformed.json.side_effect = ValueError("invalid JSON at https://private.invalid/?token=secret")
    with patch("src.metadata.requests.get", return_value=malformed):
        with pytest.raises(SourceRetrievalError) as raised:
            provider._from_syndication(post)
    assert raised.value.code == "source_metadata_invalid"
    assert raised.value.attempts == 1
    assert "private.invalid" not in str(raised.value)
    assert "secret" not in str(raised.value)


def test_metadata_provider_does_not_leak_provider_urls_in_errors():
    provider = YtDlpMetadataProvider(timeout_seconds=5)
    post = parse_x_url("https://x.com/user/status/123")
    failure = requests.HTTPError("HTTP Error 404 for https://api.example.invalid/item?token=secret")
    with patch.object(provider, "_from_ytdlp", side_effect=failure), \
         patch.object(provider, "_from_syndication", side_effect=failure), \
         patch.object(provider, "_from_fxtwitter", side_effect=failure):
        with pytest.raises(SourceRetrievalError) as raised:
            provider.get(post)
    assert raised.value.code == "source_media_unavailable"
    assert "api.example.invalid" not in str(raised.value)
    assert "secret" not in str(raised.value)
