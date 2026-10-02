from pathlib import Path
import logging
import tempfile

from .config import Config
from .dedupe import DedupeStore
from .downloader import MediaDownloader
from .metadata import MetadataProvider
from .models import PostResult, ResultStatus
from .telegram_api import TelegramClient
from .urls import XPost


class PostProcessor:
    def __init__(
        self,
        config: Config,
        metadata: MetadataProvider,
        telegram: TelegramClient | None = None,
        logger: logging.Logger | None = None,
        dedupe: DedupeStore | None = None,
    ):
        self.metadata = metadata
        self.downloader = MediaDownloader(config.timeout_seconds, config.max_file_size_mb, config.max_retries)
        self.telegram = telegram or TelegramClient(
            config.telegram_bot_token,
            config.telegram_chat_id,
            config.timeout_seconds,
            config.max_retries,
            config.telegram_api_base_url,
        )
        self.logger = logger or logging.getLogger("x2telegram")
        self.dedupe = dedupe

    def process(self, post: XPost) -> PostResult:
        result = PostResult(post.normalized_url, post.post_id, post.username, ResultStatus.ERROR)
        stage = "metadata"
        result.stage = stage
        dedupe_key = post.post_id or post.normalized_url
        if self.dedupe and self.dedupe.get(dedupe_key):
            result.status = ResultStatus.SKIPPED_DUPLICATE
            result.stage = "dedupe"
            result.error_code = "already_sent"
            self.logger.info(
                "post_skipped_duplicate",
                extra={"event": "post_skipped_duplicate", "context": {"post_id": post.post_id}},
            )
            return result
        self.logger.info(
            "post_started",
            extra={"event": "post_started", "context": {"post_id": post.post_id, "username": post.username}},
        )
        try:
            metadata = self.metadata.get(post)
            result.media_count = len(metadata.media)
            if not metadata.media:
                result.status = ResultStatus.NO_MEDIA
                result.stage = "metadata"
                self.logger.info(
                    "post_no_media",
                    extra={"event": "post_no_media", "context": {"post_id": post.post_id}},
                )
                return result

            selected = (
                [max(metadata.media, key=lambda item: (item.bitrate or -1, (item.width or 0) * (item.height or 0)))]
                if any(item.kind == "video" for item in metadata.media)
                else metadata.media
            )
            caption = f"@{post.username}\n{post.normalized_url}"
            with tempfile.TemporaryDirectory(prefix="x2telegram-"):
                for item in selected:
                    stage = "download"
                    result.stage = stage
                    path = self.downloader.download(item.url, item.kind)
                    try:
                        stage = "telegram"
                        result.stage = stage
                        if item.kind == "video":
                            message_id = self.telegram.send_video(str(path), caption)
                        elif item.kind == "photo":
                            message_id = self.telegram.send_photo(str(path), caption)
                        else:
                            message_id = self.telegram.send_document(str(path), caption)
                        result.message_ids.append(message_id)
                        result.filenames.append(f"{post.username}_{post.post_id}_{len(result.filenames) + 1:02d}{Path(path).suffix}")
                    finally:
                        Path(path).unlink(missing_ok=True)
            result.status = ResultStatus.SENT
            result.stage = "completed"
            if self.dedupe:
                self.dedupe.mark_sent(
                    dedupe_key,
                    post_id=post.post_id,
                    username=post.username,
                    source_url=post.normalized_url,
                    message_ids=result.message_ids,
                )
            self.logger.info(
                "post_sent",
                extra={
                    "event": "post_sent",
                    "context": {"post_id": post.post_id, "message_ids": result.message_ids},
                },
            )
        except Exception as exc:
            result.error = str(exc)[:500]
            result.error_code = f"{stage}_error"
            if stage == "metadata":
                result.status = ResultStatus.METADATA_ERROR
            elif stage == "download":
                result.status = ResultStatus.DOWNLOAD_ERROR
            else:
                result.status = ResultStatus.TELEGRAM_ERROR
            self.logger.error(
                "post_failed",
                extra={
                    "event": "post_failed",
                    "context": {
                        "post_id": post.post_id,
                        "stage": stage,
                        "status": result.status.value,
                        "error": result.error,
                    },
                },
            )
        return result
