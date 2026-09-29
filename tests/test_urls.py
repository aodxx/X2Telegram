from src.urls import parse_batch, parse_x_url

def test_parse_query_string():
    post=parse_x_url("https://x.com/ninmopmn/status/2099828300118167587?s=20")
    assert post and post.username == "ninmopmn"
    assert post.post_id == "2099828300118167587"
    assert post.normalized_url == "https://x.com/ninmopmn/status/2099828300118167587"

def test_batch_deduplicates():
    raw="https://x.com/a/status/1?s=20\nhttps://x.com/a/status/2\nhttps://x.com/a/status/1"
    assert [p.post_id for p in parse_batch(raw)] == ["1","2"]
