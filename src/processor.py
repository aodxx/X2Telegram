from hashlib import sha256
from pathlib import Path
import logging

from .config import Config
from .dedupe import DedupeStore
from .destinations import DestinationDispatcher, safe_filename
from .errors import DestinationError
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
    """Fetch each media item once, then independently deliver it to chosen targets."""

    def __init__(
        self,
        config: Config,
        metadata: MetadataProvider,
        telegram: TelegramClient | None = None,
        logger: logging.Logger | None = None,
        dedupe: DedupeStore | None = None,
        mega_uploader=None,
        download_exporter=None,
        dropbox_uploader=None,
    ):
        self.config = config
        self.metadata = metadata
        self.downloader = MediaDownloader(config.timeout_seconds, config.max_file_size_mb, config.max_retries)
        self.telegram = telegram
        if self.telegram is None and "telegram" in config.destinations and config.telegram_bot_token and config.telegram_chat_id:
            self.telegram = TelegramClient(
                config.telegram_bot_token,
                config.telegram_chat_id,
                config.timeout_seconds,
                config.max_retries,
                config.telegram_api_base_url,
            )
        self.logger = logger or logging.getLogger("x2telegram")
        self.dedupe = dedupe
        self.dispatcher = DestinationDispatcher(config, self.telegram, mega_uploader, download_exporter, dropbox_uploader)

    def close(self) -> None:
        self.dispatcher.close()

    def _entry(self, result: PostResult, destination: str) -> dict:
        return result.destinations.setdefault(destination, {"status": "processing", "items": []})

    def _item(self, result: PostResult, destination: str, filename: str, status: str, **details) -> None:
        item = {"filename": filename, "status": status}
        item.update({key: value for key, value in details.items() if value is not None})
        self._entry(result, destination)["items"].append(item)

    @staticmethod
    def _destination_status(items: list[dict]) -> str:
        statuses = [item.get("status") for item in items]
        successes = {"success", "ready", "duplicate"}
        has_success = any(status in successes for status in statuses)
        has_failure = any(status == "failed" for status in statuses)
        if has_failure and has_success:
            return "partial_success"
        if has_failure:
            return "failed"
        if statuses and all(status == "duplicate" for status in statuses):
            return "duplicate"
        if statuses and all(status == "ready" for status in statuses):
            return "ready"
        return "success"

    def _finish_no_media(self, result: PostResult) -> PostResult:
        result.status = ResultStatus.NO_MEDIA
        result.stage = "metadata"
        for destination in self.config.destinations:
            result.destinations[destination] = {"status": "no_media", "items": []}
        return result

    def _fail_all(self, result: PostResult, error_code: str, message: str) -> PostResult:
        result.error = message
        result.error_code = error_code
        for destination in self.config.destinations:
            self._entry(result, destination)["status"] = "failed"
            self._entry(result, destination)["error_code"] = error_code
            self._entry(result, destination)["error"] = message
        result.status = ResultStatus.METADATA_ERROR if error_code == "metadata_error" else ResultStatus.ERROR
        return result

    def process(self, post: XPost) -> PostResult:
        result = PostResult(
            post.normalized_url,
            post.post_id,
            post.username,
            ResultStatus.ERROR,
            destinations={target: {"status": "processing", "items": []} for target in self.config.destinations},
        )
        dedupe_key = post.post_id or post.normalized_url
        existing_post = self.dedupe.get(dedupe_key) if self.dedupe else None
        legacy_complete = bool(existing_post and existing_post.get("legacy_complete"))
        if legacy_complete and self.config.destinations == ("telegram",):
            result.status = ResultStatus.SKIPPED_DUPLICATE
            result.stage = "dedupe"
            result.error_code = "already_sent"
            result.message_ids = list(existing_post.get("message_ids") or [])
            result.destinations["telegram"] = {
                "status": "duplicate",
                "items": [{"status": "duplicate", "message_id": value} for value in result.message_ids],
            }
            self.logger.info("post_skipped_duplicate", extra={"event": "post_skipped_duplicate", "context": {"post_id": post.post_id}})
            return result

        self.logger.info("post_started", extra={"event": "post_started", "context": {"post_id": post.post_id, "username": post.username}})
        try:
            metadata = self.metadata.get(post)
        except Exception:
            self.logger.error("metadata_failed", extra={"event": "metadata_failed", "context": {"post_id": post.post_id}})
            result.stage = "metadata"
            return self._fail_all(result, "metadata_error", "Could not read public media metadata for this post.")

        if not metadata.media:
            return self._finish_no_media(result)

        videos = [item for item in metadata.media if item.kind == "video"]
        selected = []
        best_video = max(videos, key=lambda item: (item.bitrate or -1, (item.width or 0) * (item.height or 0))) if videos else None
        video_added = False
        for item in metadata.media:
            if item.kind == "video":
                if not video_added:
                    selected.append(best_video)
                    video_added = True
            else:
                selected.append(item)
        result.media_count = len(selected)
        caption = f"@{post.username}\n{post.normalized_url}"
        any_delivery = False
        any_failure = False
        legacy_ids = list((existing_post or {}).get("message_ids") or []) if legacy_complete else []

        for media_index, item in enumerate(selected, start=1):
            self.logger.info("media_download_started", extra={"event": "media_download_started", "context": {"post_id": post.post_id, "media_index": media_index}})
            try:
                path = self.downloader.download(item.url, item.kind)
                filename = safe_filename(post.username, post.post_id, media_index, Path(path).suffix)
                safe_path = Path(path).with_name(filename)
                if safe_path != Path(path):
                    Path(path).replace(safe_path)
                    path = safe_path
                fingerprint = _media_fingerprint(path, item.kind)
                # MEGA must preserve older versions if the same X post later exposes
                # changed media. The full SHA-256 fingerprint makes each distinct payload a distinct remote
                # filename, avoiding overwrite/collision of older MEGA versions.
                filename_path = Path(filename)
                mega_filename = f"{filename_path.stem}_{fingerprint}{filename_path.suffix}"
            except Exception:
                any_failure = True
                message = "Media download failed for this item."
                for destination in self.config.destinations:
                    filename = safe_filename(post.username, post.post_id, media_index, ".mp4" if item.kind == "video" else ".jpg")
                    self._item(result, destination, filename, "failed", error_code="download_error", error=message)
                result.error = result.error or message
                result.error_code = result.error_code or "download_error"
                self.logger.error("media_download_failed", extra={"event": "media_download_failed", "context": {"post_id": post.post_id, "media_index": media_index}})
                continue

            try:
                for destination in self.config.destinations:
                    destination_filename = mega_filename if destination in {"mega", "dropbox"} else filename
                    if destination == "telegram" and legacy_complete:
                        message_id = legacy_ids[media_index - 1] if media_index <= len(legacy_ids) else None
                        if message_id is not None:
                            result.message_ids.append(message_id)
                        self._item(result, destination, destination_filename, "duplicate", message_id=message_id)
                        any_delivery = True
                        continue

                    prior = self.dedupe.get_destination(dedupe_key, fingerprint, destination) if self.dedupe and destination in {"telegram", "mega", "dropbox"} else None
                    if prior:
                        message_id = prior.get("message_id") if destination == "telegram" else None
                        if isinstance(message_id, int):
                            result.message_ids.append(message_id)
                        self._item(result, destination, str(prior.get("filename") or destination_filename), "duplicate", message_id=message_id)
                        if destination_filename not in result.filenames:
                            result.filenames.append(destination_filename)
                        any_delivery = True
                        continue

                    try:
                        details = self.dispatcher.deliver(destination, path, destination_filename, caption, item.kind)
                    except DestinationError as exc:
                        any_failure = True
                        self._item(result, destination, destination_filename, "failed", error_code=exc.code, error=str(exc))
                        result.error = result.error or str(exc)
                        result.error_code = result.error_code or exc.code
                        self.logger.warning("destination_failed", extra={"event": "destination_failed", "context": {"post_id": post.post_id, "destination": destination, "error_code": exc.code, "media_index": media_index}})
                        continue
                    except Exception:
                        any_failure = True
                        code = f"{destination}_error"
                        message = f"{destination.capitalize()} delivery failed for this item."
                        self._item(result, destination, destination_filename, "failed", error_code=code, error=message)
                        result.error = result.error or message
                        result.error_code = result.error_code or code
                        self.logger.warning("destination_failed", extra={"event": "destination_failed", "context": {"post_id": post.post_id, "destination": destination, "error_code": code, "media_index": media_index}})
                        continue

                    state = "ready" if destination == "download" else "success"
                    self._item(result, destination, destination_filename, state, **details)
                    if destination_filename not in result.filenames:
                        result.filenames.append(destination_filename)
                    if destination == "telegram" and isinstance(details.get("message_id"), int):
                        result.message_ids.append(details["message_id"])
                    any_delivery = True
                    if self.dedupe and destination in {"telegram", "mega", "dropbox"}:
                        try:
                            self.dedupe.mark_destination_sent(
                                dedupe_key,
                                fingerprint,
                                destination=destination,
                                post_id=post.post_id,
                                username=post.username,
                                source_url=post.normalized_url,
                                kind=item.kind,
                                filename=destination_filename,
                                details=details,
                            )
                        except Exception:
                            # Delivery already succeeded; keep its status truthful but make the checkpoint risk visible.
                            self._entry(result, destination)["items"][-1]["warning"] = "dedupe_checkpoint_failed"
                            self.logger.error("dedupe_checkpoint_failed", extra={"event": "dedupe_checkpoint_failed", "context": {"post_id": post.post_id, "destination": destination}})
            finally:
                Path(path).unlink(missing_ok=True)

        for destination in self.config.destinations:
            entry = self._entry(result, destination)
            entry["status"] = self._destination_status(entry["items"])

        if not any_failure and self.dedupe and any(target in {"telegram", "mega", "dropbox"} for target in self.config.destinations):
            try:
                self.dedupe.mark_complete(dedupe_key)
            except Exception:
                self.logger.error("dedupe_finalize_failed", extra={"event": "dedupe_finalize_failed", "context": {"post_id": post.post_id}})

        if any_failure and any_delivery:
            result.status = ResultStatus.PARTIAL_SUCCESS
            result.error_code = result.error_code or "partial_destination_failure"
            result.stage = "completed"
        elif any_failure:
            if self.config.destinations == ("telegram",):
                result.status = ResultStatus.TELEGRAM_ERROR if result.error_code and result.error_code.startswith("telegram") else ResultStatus.DOWNLOAD_ERROR if result.error_code == "download_error" else ResultStatus.ERROR
            else:
                result.status = ResultStatus.FAILED
            result.stage = "completed_with_errors"
        elif self.config.destinations == ("telegram",):
            result.status = ResultStatus.SKIPPED_DUPLICATE if result.destinations["telegram"]["status"] == "duplicate" else ResultStatus.SENT
            result.stage = "completed"
        elif all(result.destinations[target]["status"] == "duplicate" for target in self.config.destinations):
            result.status = ResultStatus.SKIPPED_DUPLICATE
            result.stage = "dedupe"
        else:
            result.status = ResultStatus.SUCCESS
            result.stage = "completed"

        self.logger.info(
            "post_processed",
            extra={"event": "post_processed", "context": {"post_id": post.post_id, "status": result.status.value,
                   "destination_statuses": {key: value["status"] for key, value in result.destinations.items()}}},
        )
        return result
