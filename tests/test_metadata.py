from unittest.mock import Mock, patch

from src.metadata import YtDlpMetadataProvider
from src.urls import parse_x_url


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
    with patch("src.metadata.requests.get") as get:
        get.return_value.json.return_value = payload
        get.return_value.raise_for_status.return_value = None
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
                        {"container": "mp4", "bitrate": 2176000, "url": "https://video.twimg.com/high.mp4?tag=12"},
                    ],
                }]
            },
        },
    }
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    post = parse_x_url("https://x.com/user/status/123")
    with patch("src.metadata.requests.get", return_value=response):
        result = provider._from_fxtwitter(post)
    assert [item.bitrate for item in result.media] == [256000, 2176000]
    assert result.media[-1].url.endswith("?tag=12")


def test_get_uses_fxtwitter_after_empty_earlier_fallbacks():
    provider = YtDlpMetadataProvider(timeout_seconds=5)
    post = parse_x_url("https://x.com/user/status/123")
    with patch.object(provider, "_from_ytdlp", return_value=type("M", (), {"media": []})()), \
         patch.object(provider, "_from_syndication", return_value=type("M", (), {"media": []})()), \
         patch.object(provider, "_from_fxtwitter", return_value=type("M", (), {"media": ["video"]})()):
        result = provider.get(post)
    assert result.media == ["video"]
