import re
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class XPost:
    original_url: str
    normalized_url: str
    username: str
    post_id: str


@dataclass(frozen=True)
class BatchInput:
    index: int
    line_number: int
    disposition: str
    post: XPost | None = None
    error_code: str | None = None
    duplicate_of: int | None = None


_STATUS_RE = re.compile(r"^/(.+)/status/(\d+)$")


def parse_x_url(value: str) -> XPost | None:
    value = value.strip().strip("<>\"'`.,;)]}").replace("\u200b", "")
    if not value:
        return None
    candidate = value if "://" in value else f"https://{value}"
    try:
        parts = urlsplit(candidate)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"} or parts.username is not None or parts.password is not None:
        return None
    if host not in {"x.com", "www.x.com", "mobile.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}:
        return None
    if port not in (None, 443):
        return None
    match = _STATUS_RE.match(parts.path.rstrip("/"))
    if not match:
        return None
    path_prefix, post_id = match.groups()
    username = path_prefix.split("/")[-1] or "unknown"
    return XPost(value, f"https://x.com/{username}/status/{post_id}", username, post_id)


def parse_batch_inputs(text: str) -> tuple[list[BatchInput], int]:
    """Normalize line endings and return an outcome for every nonblank URL token.

    Blank physical lines are ignored by the processor and returned separately so
    the final report can account for them without treating them as URL inputs.
    """
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines() if normalized else []
    outcomes: list[BatchInput] = []
    seen: dict[str, tuple[int, str]] = {}
    blank_line_count = 0

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            blank_line_count += 1
            continue
        for token in stripped.split():
            index = len(outcomes) + 1
            post = parse_x_url(token)
            if post is None:
                outcomes.append(BatchInput(index, line_number, "rejected", error_code="invalid_x_url"))
                continue
            prior = seen.get(post.normalized_url)
            if prior:
                prior_index, prior_original = prior
                disposition = "duplicate" if post.original_url == prior_original else "normalized_duplicate"
                outcomes.append(BatchInput(index, line_number, disposition, post, duplicate_of=prior_index))
                continue
            seen[post.normalized_url] = (index, post.original_url)
            outcomes.append(BatchInput(index, line_number, "accepted", post))

    return outcomes, blank_line_count


def parse_batch(text: str) -> list[XPost]:
    """Return unique valid posts, preserving the historical public API."""
    outcomes, _ = parse_batch_inputs(text)
    return [item.post for item in outcomes if item.disposition == "accepted" and item.post is not None]
