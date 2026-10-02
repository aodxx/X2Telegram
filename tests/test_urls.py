from src.urls import parse_batch, parse_x_url

def test_parse_query_string():
    post=parse_x_url("https://x.com/ninmopmn/status/2099828300118167587?s=20")
    assert post and post.username == "ninmopmn"
    assert post.post_id == "2099828300118167587"
    assert post.normalized_url == "https://x.com/ninmopmn/status/2099828300118167587"

def test_batch_deduplicates():
    raw="https://x.com/a/status/1?s=20\nhttps://x.com/a/status/2\nhttps://x.com/a/status/1"
    assert [p.post_id for p in parse_batch(raw)] == ["1","2"]

def test_batch_accepts_space_separated_urls():
    raw="https://x.com/a/status/1 https://x.com/a/status/2 https://x.com/a/status/1"
    assert [p.post_id for p in parse_batch(raw)] == ["1", "2"]

def test_batch_normalizes_query_parameters():
    posts = parse_batch("https://x.com/a/status/1?s=20&utm_source=test")
    assert posts[0].normalized_url == "https://x.com/a/status/1"

def test_accepts_bare_mobile_and_special_status_paths():
    cases = [
        "x.com/user/status/1234567890",
        "https://mobile.twitter.com/user/status/1234567891/",
        "https://x.com/i/web/status/1234567892",
        "<https://x.com/user/status/1234567893>",
    ]
    assert [parse_x_url(value).post_id for value in cases] == [
        "1234567890", "1234567891", "1234567892", "1234567893"
    ]
