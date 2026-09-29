from pathlib import Path
import tempfile

from .config import Config
from .downloader import MediaDownloader
from .metadata import MetadataProvider
from .models import PostResult, ResultStatus
from .telegram_api import TelegramClient
from .urls import XPost


class PostProcessor:
    def __init__(self, config: Config, metadata: MetadataProvider, telegram: TelegramClient | None = None):
        self.metadata = metadata
        self.downloader = MediaDownloader(config.timeout_seconds, config.max_file_size_mb)
        self.telegram = telegram or TelegramClient(config.telegram_bot_token, config.telegram_chat_id,
                                                   config.timeout_seconds, config.max_retries)

    def process(self, post: XPost) -> PostResult:
        result = PostResult(post.normalized_url, post.post_id, post.username, ResultStatus.ERROR)
        try:
            metadata = self.metadata.get(post)
            result.media_count = len(metadata.media)
            if not metadata.media:
                result.status = ResultStatus.NO_MEDIA
                return result
            # One post produces one Telegram message: the highest quality video, or photos.
            selected = [max(metadata.media, key=lambda item: (item.bitrate or -1, (item.width or 0) * (item.height or 0)))] if any(i.kind == "video" for i in metadata.media) else metadata.media
            caption = f"@{post.username}\n{post.normalized_url}"
            with tempfile.TemporaryDirectory(prefix="x2telegram-") as temp_dir:
                for item in selected:
                    path = self.downloader.download(item.url, item.kind)
                    try:
                        if item.kind == "video":
                            message_id = self.telegram.send_video(str(path), caption)
                        elif item.kind == "photo":
                            message_id = self.telegram.send_photo(str(path), caption)
                        else:
                            message_id = self.telegram.send_document(str(path), caption)
                        result.message_ids.append(message_id)
                    finally:
                        Path(path).unlink(missing_ok=True)
            result.status = ResultStatus.SENT
        except Exception as exc:
            result.error = str(exc)[:500]
            if result.media_count == 0:
                result.status = ResultStatus.METADATA_ERROR
            else:
                result.status = ResultStatus.DOWNLOAD_ERROR
        return result
