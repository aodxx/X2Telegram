from unittest.mock import patch

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
