from src.urls import parse_batch, parse_batch_inputs, parse_x_url


def test_parse_query_string():
    post = parse_x_url("https://x.com/ninmopmn/status/2099828300118167587?s=20")
    assert post and post.username == "ninmopmn"
    assert post.post_id == "2099828300118167587"
    assert post.normalized_url == "https://x.com/ninmopmn/status/2099828300118167587"


def test_batch_deduplicates():
    raw = "https://x.com/a/status/1?s=20\nhttps://x.com/a/status/2\nhttps://x.com/a/status/1"
    assert [post.post_id for post in parse_batch(raw)] == ["1", "2"]


def test_batch_accepts_space_separated_urls():
    raw = "https://x.com/a/status/1 https://x.com/a/status/2 https://x.com/a/status/1"
    assert [post.post_id for post in parse_batch(raw)] == ["1", "2"]


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


def test_batch_outcomes_normalize_crlf_ignore_blank_lines_and_reject_invalid_tokens():
    raw = "  https://x.com/a/status/1?s=20  \r\n\r\nnot-an-x-url\r\nhttps://x.com/a/status/2\r\n"
    outcomes, blank_lines = parse_batch_inputs(raw)
    assert blank_lines == 1
    assert [item.disposition for item in outcomes] == ["accepted", "rejected", "accepted"]
    assert [item.line_number for item in outcomes] == [1, 3, 4]
    assert outcomes[1].error_code == "invalid_x_url"
    assert [post.post_id for post in parse_batch(raw)] == ["1", "2"]


def test_batch_reports_exact_and_normalized_duplicates_without_sending_twice():
    raw = (
        "https://x.com/a/status/1?s=20\n"
        "https://x.com/a/status/1?s=20\n"
        "https://mobile.twitter.com/a/status/1?utm_source=test\n"
    )
    outcomes, blank_lines = parse_batch_inputs(raw)
    assert blank_lines == 0
    assert [item.disposition for item in outcomes] == ["accepted", "duplicate", "normalized_duplicate"]
    assert [item.duplicate_of for item in outcomes] == [None, 1, 1]
    assert len(parse_batch(raw)) == 1


def test_batch_accepts_mixed_line_endings_without_counting_terminal_newline_as_blank():
    raw = "https://x.com/a/status/1\r\n\r\nhttps://x.com/a/status/2\nhttps://x.com/a/status/3\r\n"
    outcomes, blank_lines = parse_batch_inputs(raw)
    assert blank_lines == 1
    assert [item.disposition for item in outcomes] == ["accepted", "accepted", "accepted"]
    assert [item.line_number for item in outcomes] == [1, 3, 4]


def test_batch_rejects_untrusted_hosts_ports_and_url_credentials():
    assert parse_x_url("https://x.com:8443/user/status/1") is None
    assert parse_x_url("https://user:pass@x.com/user/status/1") is None
    assert parse_x_url("https://x.com.attacker.invalid/user/status/1") is None


def test_malformed_url_authority_is_rejected_without_raising():
    assert parse_x_url("https://[::1") is None
