from dataclasses import dataclass, field
from enum import Enum

class ResultStatus(str, Enum):
    SENT = "sent"
    NO_MEDIA = "no_media"
    METADATA_ERROR = "metadata_error"
    DOWNLOAD_ERROR = "download_error"
    TELEGRAM_ERROR = "telegram_error"
    SKIPPED = "skipped"
    ERROR = "error"

@dataclass
class MediaItem:
    kind: str
    url: str
    index: int
    bitrate: int | None = None
    width: int | None = None
    height: int | None = None
    mime_type: str | None = None

@dataclass
class PostResult:
    source_url: str
    post_id: str | None
    username: str | None
    status: ResultStatus
    media_count: int = 0
    message_ids: list[int] = field(default_factory=list)
    error: str | None = None
