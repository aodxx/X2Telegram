from hashlib import sha256
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


def _media_fingerprint(path: str | Path, kind: str) -> str:
    digest = sha256()
    digest.update(kind.encode("utf-8"))
    digest.update(b"\0")
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        existing_post = self.dedupe.get(dedupe_key) if self.dedupe else None
        if existing_post and existing_post.get("legacy_complete"):
            result.status = ResultStatus.SKIPPED_DUPLICATE
            result.stage = "dedupe"
            result.error_code = "already_sent"
            result.message_ids = list(existing_post.get("message_ids") or [])
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
            sent_this_run = 0
            with tempfile.TemporaryDirectory(prefix="x2telegram-"):
                for item in selected:
                    stage = "download"
                    result.stage = stage
                    path = self.downloader.download(item.url, item.kind)
                    try:
                        fingerprint = _media_fingerprint(path, item.kind)
                        already_sent = self.dedupe.get_media(dedupe_key, fingerprint) if self.dedupe else None
                        fallback_name = f"{post.username}_{post.post_id}_{len(result.filenames) + 1:02d}{Path(path).suffix}"
                        if already_sent:
                            saved_id = already_sent.get("message_id")
                            if isinstance(saved_id, int):
                                result.message_ids.append(saved_id)
                            result.filenames.append(str(already_sent.get("filename") or fallback_name))
                            continue

                        stage = "telegram"
                        result.stage = stage
                        if item.kind == "video":
                            message_id = self.telegram.send_video(str(path), caption)
                        elif item.kind == "photo":
                            message_id = self.telegram.send_photo(str(path), caption)
                        else:
                            message_id = self.telegram.send_document(str(path), caption)
                        filename = f"{post.username}_{post.post_id}_{len(result.filenames) + 1:02d}{Path(path).suffix}"
                        result.message_ids.append(message_id)
                        result.filenames.append(filename)
                        sent_this_run += 1
                        if self.dedupe:
                            stage = "dedupe"
                            result.stage = stage
                            self.dedupe.mark_media_sent(
                                dedupe_key,
                                fingerprint,
                                post_id=post.post_id,
                                username=post.username,
                                source_url=post.normalized_url,
                                kind=item.kind,
                                message_id=message_id,
                                filename=filename,
                            )
                    finally:
                        Path(path).unlink(missing_ok=True)

            if self.dedupe:
                stage = "dedupe"
                result.stage = stage
                self.dedupe.mark_complete(dedupe_key)
            if sent_this_run:
                result.status = ResultStatus.SENT
                result.stage = "completed"
                self.logger.info(
                    "post_sent",
                    extra={
                        "event": "post_sent",
                        "context": {"post_id": post.post_id, "message_ids": result.message_ids},
                    },
                )
            else:
                result.status = ResultStatus.SKIPPED_DUPLICATE
                result.stage = "dedupe"
                result.error_code = "already_sent"
                self.logger.info(
                    "post_skipped_duplicate",
                    extra={"event": "post_skipped_duplicate", "context": {"post_id": post.post_id}},
                )
        except Exception as exc:
            result.error = str(exc)[:500]
            result.error_code = f"{stage}_error"
            if stage == "metadata":
                result.status = ResultStatus.METADATA_ERROR
            elif stage == "download":
                result.status = ResultStatus.DOWNLOAD_ERROR
            elif stage == "telegram":
                result.status = ResultStatus.TELEGRAM_ERROR
            else:
                result.status = ResultStatus.ERROR
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
