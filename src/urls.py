import re
from dataclasses import dataclass
from urllib.parse import urlsplit

@dataclass(frozen=True)
class XPost:
    original_url: str
    normalized_url: str
    username: str
    post_id: str

_STATUS_RE = re.compile(r"^/([^/]+)/status/(\d+)$")

def parse_x_url(value: str) -> XPost | None:
    value = value.strip()
    if not value:
        return None
    candidate = value if "://" in value else f"https://{value}"
    parts = urlsplit(candidate)
    if parts.scheme not in {"http", "https"}:
        return None
    host = parts.netloc.lower().split(":")[0]
    if host not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        return None
    match = _STATUS_RE.match(parts.path.rstrip("/"))
    if not match:
        return None
    username, post_id = match.groups()
    return XPost(value, f"https://x.com/{username}/status/{post_id}", username, post_id)

def parse_batch(text: str) -> list[XPost]:
    seen=set(); posts=[]
    for line in text.splitlines():
        post=parse_x_url(line)
        if post and post.normalized_url not in seen:
            posts.append(post); seen.add(post.normalized_url)
    return posts
