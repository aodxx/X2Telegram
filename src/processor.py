from hashlib import sha256
from pathlib import Path
import logging

from .config import Config
from .dedupe import DedupeStore
from .destinations import DestinationDispatcher, safe_filename
from .errors import DestinationError, SourceRetrievalError
from .downloader import MediaDownloader
from .metadata import MetadataProvider
from .models import PostResult, ResultStatus
from .telegram_api import TelegramClient
from .urls import XPost


def _media_fingerprint(path: str | Path, kind: str) -> str:
    return _media_hashes(path, kind)[0]


def _media_hashes(path: str | Path, kind: str) -> tuple[str, str]:
    fingerprint = sha256()
    content_hash = sha256()
    fingerprint.update(kind.encode("utf-8"))
    fingerprint.update(b"\0")
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            fingerprint.update(chunk)
            content_hash.update(chunk)
    return fingerprint.hexdigest(), content_hash.hexdigest()


MAX_VIDEO_VARIANT_ATTEMPTS = 3


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
        has_unknown = any(status == "outcome_unconfirmed" for status in statuses)
        if has_unknown:
            return "partial_success" if has_success else "outcome_unconfirmed"
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
        self._finalize_media_reconciliation(result)
        return result

    def _finalize_media_reconciliation(self, result: PostResult, status: str = "complete") -> None:
        for manifest_item in result.media_manifest:
            media_index = manifest_item["media_index"]
            for destination in self.config.destinations:
                destination_items = (result.destinations.get(destination) or {}).get("items") or []
                matching = [item for item in destination_items if item.get("media_index") == media_index]
                manifest_item["destinations"][destination] = matching[-1].get("status", "not_attempted") if matching else "not_attempted"

        destination_summary = {}
        for destination in self.config.destinations:
            statuses = [item["destinations"].get(destination, "not_attempted") for item in result.media_manifest]
            expected = len(result.media_manifest) if status == "complete" else None
            accounted = sum(value != "not_attempted" for value in statuses)
            destination_summary[destination] = {
                "expected_items": expected,
                "accounted_items": accounted,
                "delivered_items": sum(value in {"success", "ready"} for value in statuses),
                "duplicate_items": statuses.count("duplicate"),
                "failed_items": statuses.count("failed"),
                "unaccounted_items": max(0, len(result.media_manifest) - accounted) if status == "complete" else None,
            }
            if "outcome_unconfirmed" in statuses:
                destination_summary[destination]["unconfirmed_items"] = statuses.count("outcome_unconfirmed")

        result.media_reconciliation = {
            "status": status,
            "expected_items": len(result.media_manifest) if status == "complete" else None,
            "downloaded_items": sum(item.get("download_status") == "validated" for item in result.media_manifest),
            "download_failed_items": sum(item.get("download_status") == "failed" for item in result.media_manifest),
            "processing_failed_items": sum(item.get("download_status") == "processing_failed" for item in result.media_manifest),
            "destinations": destination_summary,
        }

    def _video_candidates(self, videos: list) -> list:
        """Rank direct variants and keep a bounded fallback when sizes are unknown."""
        if not videos:
            return []
        limit = self.downloader.max_bytes
        if "telegram" in self.config.destinations:
            local_api = (
                self.config.large_file_mode
                and self.config.telegram_api_base_url.rstrip("/") != "https://api.telegram.org"
            )
            limit = min(limit, (2000 if local_api else 50) * 1024 * 1024)

        def numeric(value, default=0.0):
            try:
                return float(value)
            except (TypeError, ValueError, OverflowError):
                return default

        def size_bytes(item):
            try:
                size = int(item.size_bytes)
            except (TypeError, ValueError, OverflowError):
                return None
            return size if size > 0 else None

        quality = lambda item: (
            numeric(item.bitrate, -1.0),
            numeric(item.width) * numeric(item.height),
            numeric(item.height, -1.0),
            numeric(item.width, -1.0),
        )
        sized = [(item, size_bytes(item)) for item in videos]
        safe = [item for item, size in sized if size is not None and size <= limit]
        unknown = [item for item, size in sized if size is None]
        oversized = [(item, size) for item, size in sized if size is not None and size > limit]
        if safe or unknown:
            # A missing filesize is not evidence that a variant is low quality.
            # Rank all variants that may fit by bitrate/resolution first, then
            # keep oversized variants as bounded fallbacks for a lower-quality retry.
            ranked = sorted(safe + unknown, key=quality, reverse=True)
            ranked.extend(item for item, _ in sorted(oversized, key=lambda pair: pair[1]))
            return ranked
        return [item for item, _ in sorted(oversized, key=lambda pair: pair[1])]

    def _select_video(self, videos: list) -> object | None:
        """Compatibility helper for callers needing only the preferred variant."""
        candidates = self._video_candidates(videos)
        return candidates[0] if candidates else None

    def _download_media(self, candidates: list, post: XPost, media_index: int) -> Path:
        attempts = candidates[:MAX_VIDEO_VARIANT_ATTEMPTS]
        last_error: SourceRetrievalError | None = None
        for variant_index, candidate in enumerate(attempts, start=1):
            try:
                path = self.downloader.download(candidate.url, candidate.kind)
            except SourceRetrievalError as exc:
                last_error = exc
                exc.variant_attempts = variant_index
                can_fallback = exc.code in {"media_too_large", "unsupported_media_format"}
                if not can_fallback or variant_index >= len(attempts):
                    raise
                self.logger.warning(
                    "media_variant_fallback",
                    extra={"event": "media_variant_fallback", "context": {
                        "post_id": post.post_id, "media_index": media_index,
                        "variant_index": variant_index, "error_code": exc.code,
                    }},
                )
                continue
            if variant_index > 1:
                self.logger.info(
                    "media_variant_fallback_succeeded",
                    extra={"event": "media_variant_fallback_succeeded", "context": {
                        "post_id": post.post_id, "media_index": media_index, "variant_index": variant_index,
                    }},
                )
            self.logger.info(
                "media_download_succeeded",
                extra={"event": "media_download_succeeded", "context": {
                    "post_id": post.post_id, "media_index": media_index,
                    "attempts": self.downloader.last_attempt_count,
                    "variant_attempts": variant_index,
                }},
            )
            return path
        if last_error:
            raise last_error
        raise SourceRetrievalError("source_download_failed", "Could not retrieve media from X.", "download")

    def _fail_all(self, result: PostResult, error_code: str, message: str, attempts: int | None = None) -> PostResult:
        result.error = message
        result.error_code = error_code
        for destination in self.config.destinations:
            entry = self._entry(result, destination)
            entry["status"] = "failed"
            entry["error_code"] = error_code
            entry["error"] = message
            entry["stage"] = result.stage
            if attempts is not None:
                entry["attempts"] = attempts
        result.status = ResultStatus.METADATA_ERROR if result.stage == "metadata" else ResultStatus.ERROR
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
            self._finalize_media_reconciliation(result, "not_enumerated")
            self.logger.info("post_skipped_duplicate", extra={"event": "post_skipped_duplicate", "context": {"post_id": post.post_id}})
            return result

        self.logger.info("post_started", extra={"event": "post_started", "context": {"post_id": post.post_id, "username": post.username}})
        try:
            metadata = self.metadata.get(post)
        except SourceRetrievalError as exc:
            self.logger.error("metadata_failed", extra={"event": "metadata_failed", "context": {
                "post_id": post.post_id, "stage": exc.stage, "error_code": exc.code,
                "attempts": exc.attempts,
            }})
            result.stage = exc.stage
            if exc.code == "no_supported_media":
                result.error_code = exc.code
                result.error = str(exc)
                return self._finish_no_media(result)
            failed = self._fail_all(result, exc.code, str(exc), exc.attempts)
            self._finalize_media_reconciliation(failed, "metadata_failed")
            return failed
        except Exception:
            self.logger.error("metadata_failed", extra={"event": "metadata_failed", "context": {"post_id": post.post_id}})
            result.stage = "metadata"
            failed = self._fail_all(result, "source_metadata_unavailable", "Could not retrieve public media metadata from X or its fallback providers.")
            self._finalize_media_reconciliation(failed, "metadata_failed")
            return failed

        if not metadata.media:
            result.error_code = "no_supported_media"
            result.error = "No supported public photo or direct MP4 video was found for this X post."
            return self._finish_no_media(result)

        selected = []
        video_groups: dict[int, list] = {}
        for item in metadata.media:
            if item.kind == "video":
                video_groups.setdefault(item.index, []).append(item)
        added_video_groups: set[int] = set()
        for item in metadata.media:
            if item.kind == "video":
                if item.index not in added_video_groups:
                    video_candidates = self._video_candidates(video_groups[item.index])
                    if video_candidates:
                        selected.append((video_candidates[0], video_candidates))
                    added_video_groups.add(item.index)
            else:
                selected.append((item, [item]))
        result.media_count = len(selected)
        result.media_manifest = [
            {
                "media_index": media_index,
                "source_index": item.index,
                "kind": item.kind,
                "bitrate": item.bitrate,
                "width": item.width,
                "height": item.height,
                "download_status": "pending",
                "size_bytes": None,
                "sha256": None,
                "destinations": {destination: "not_attempted" for destination in self.config.destinations},
            }
            for media_index, (item, _candidates) in enumerate(selected, start=1)
        ]
        caption = f"@{post.username}\n{post.normalized_url}"
        any_delivery = False
        any_failure = False
        any_unconfirmed = False
        legacy_ids = list((existing_post or {}).get("message_ids") or []) if legacy_complete else []

        for media_index, (item, candidates) in enumerate(selected, start=1):
            self.logger.info("media_download_started", extra={"event": "media_download_started", "context": {"post_id": post.post_id, "media_index": media_index}})
            path = None
            try:
                path = self._download_media(candidates, post, media_index)
                filename = safe_filename(post.username, post.post_id, media_index, Path(path).suffix)
                safe_path = Path(path).with_name(filename)
                if safe_path != Path(path):
                    Path(path).replace(safe_path)
                    path = safe_path
                fingerprint, content_sha256 = _media_hashes(path, item.kind)
                manifest_item = result.media_manifest[media_index - 1]
                manifest_item.update({
                    "download_status": "validated",
                    "size_bytes": Path(path).stat().st_size,
                    "sha256": content_sha256,
                })
                # MEGA must preserve older versions if the same X post later exposes
                # changed media. The full SHA-256 fingerprint makes each distinct payload a distinct remote
                # filename, avoiding overwrite/collision of older MEGA versions.
                filename_path = Path(filename)
                mega_filename = f"{filename_path.stem}_{fingerprint}{filename_path.suffix}"
            except SourceRetrievalError as exc:
                any_failure = True
                manifest_item = result.media_manifest[media_index - 1]
                manifest_item["download_status"] = "failed"
                manifest_item["error_code"] = exc.code
                message = str(exc)
                result.stage = result.stage or exc.stage
                for destination in self.config.destinations:
                    filename = safe_filename(post.username, post.post_id, media_index, ".mp4" if item.kind == "video" else ".jpg")
                    self._item(result, destination, filename, "failed", error_code=exc.code, error=message,
                               stage=exc.stage, media_index=media_index, attempts=exc.attempts,
                               variant_attempts=getattr(exc, "variant_attempts", None))
                result.error = result.error or message
                result.error_code = result.error_code or exc.code
                self.logger.error("media_download_failed", extra={"event": "media_download_failed", "context": {
                    "post_id": post.post_id, "media_index": media_index,
                    "stage": exc.stage, "error_code": exc.code, "attempts": exc.attempts,
                    "variant_attempts": getattr(exc, "variant_attempts", None),
                }})
                continue
            except Exception:
                any_failure = True
                code = "media_processing_error" if path else "source_download_failed"
                stage = "processing" if path else "download"
                manifest_item = result.media_manifest[media_index - 1]
                manifest_item["download_status"] = "processing_failed" if path else "failed"
                manifest_item["error_code"] = code
                message = "Downloaded media could not be prepared on the runner." if path else "The source media could not be retrieved after bounded attempts."
                if path:
                    Path(path).unlink(missing_ok=True)
                result.stage = result.stage or stage
                for destination in self.config.destinations:
                    filename = safe_filename(post.username, post.post_id, media_index, ".mp4" if item.kind == "video" else ".jpg")
                    self._item(result, destination, filename, "failed", error_code=code, error=message,
                               stage=stage, media_index=media_index)
                result.error = result.error or message
                result.error_code = result.error_code or code
                self.logger.error("media_download_failed", extra={"event": "media_download_failed", "context": {
                    "post_id": post.post_id, "media_index": media_index,
                    "stage": stage, "error_code": code,
                }})
                continue

            try:
                for destination in self.config.destinations:
                    destination_filename = mega_filename if destination in {"mega", "dropbox"} else filename
                    if destination == "telegram" and legacy_complete:
                        message_id = legacy_ids[media_index - 1] if media_index <= len(legacy_ids) else None
                        if message_id is not None:
                            result.message_ids.append(message_id)
                        self._item(result, destination, destination_filename, "duplicate", message_id=message_id, media_index=media_index)
                        any_delivery = True
                        continue

                    prior = self.dedupe.get_destination(dedupe_key, fingerprint, destination) if self.dedupe and destination in {"telegram", "mega", "dropbox"} else None
                    if prior:
                        if prior.get("status") == "outcome_unconfirmed":
                            any_unconfirmed = True
                            code = str(prior.get("error_code") or f"{destination}_outcome_unconfirmed")
                            message = str(prior.get("error") or f"{destination.capitalize()} outcome is unconfirmed; inspect the destination before retrying.")
                            self._item(result, destination, str(prior.get("filename") or destination_filename),
                                       "outcome_unconfirmed", error_code=code, error=message, media_index=media_index)
                            result.error = result.error or message
                            result.error_code = result.error_code or code
                            continue
                        prior_filename = str(prior.get("filename") or "")
                        # MEGA/Dropbox filenames are content-versioned. After upgrading the
                        # naming scheme, an old checkpoint must not suppress the migration
                        # upload: the remote still has the legacy filename. Once the new
                        # filename is checkpointed, ordinary retries remain deduplicated.
                        refresh_versioned_upload = (
                            destination in {"mega", "dropbox"}
                            and prior_filename != destination_filename
                        )
                        if not refresh_versioned_upload:
                            message_id = prior.get("message_id") if destination == "telegram" else None
                            if isinstance(message_id, int):
                                result.message_ids.append(message_id)
                            self._item(result, destination, prior_filename or destination_filename, "duplicate", message_id=message_id, media_index=media_index)
                            if destination_filename not in result.filenames:
                                result.filenames.append(destination_filename)
                            any_delivery = True
                            continue
                        self.logger.info(
                            "destination_version_filename_changed",
                            extra={"event": "destination_version_filename_changed",
                                   "context": {"post_id": post.post_id, "destination": destination}},
                        )

                    try:
                        details = self.dispatcher.deliver(destination, path, destination_filename, caption, item.kind)
                    except DestinationError as exc:
                        status = "outcome_unconfirmed" if exc.outcome_unknown else "failed"
                        any_unconfirmed = any_unconfirmed or exc.outcome_unknown
                        any_failure = any_failure or not exc.outcome_unknown
                        self._item(result, destination, destination_filename, status, error_code=exc.code, error=str(exc), media_index=media_index)
                        if exc.outcome_unknown and self.dedupe:
                            try:
                                self.dedupe.mark_destination_outcome_unconfirmed(
                                    dedupe_key, fingerprint, destination=destination,
                                    post_id=post.post_id, username=post.username, source_url=post.normalized_url,
                                    kind=item.kind, filename=destination_filename, error_code=exc.code, error=str(exc),
                                )
                            except Exception:
                                self._entry(result, destination)["items"][-1]["warning"] = "outcome_checkpoint_failed"
                                self.logger.error("outcome_checkpoint_failed", extra={"event": "outcome_checkpoint_failed", "context": {"post_id": post.post_id, "destination": destination}})
                        result.error = result.error or str(exc)
                        result.error_code = result.error_code or exc.code
                        event = "destination_outcome_unconfirmed" if exc.outcome_unknown else "destination_failed"
                        self.logger.warning(event, extra={"event": event, "context": {"post_id": post.post_id, "destination": destination, "error_code": exc.code, "media_index": media_index}})
                        continue
                    except Exception:
                        any_failure = True
                        code = f"{destination}_error"
                        message = f"{destination.capitalize()} delivery failed for this item."
                        self._item(result, destination, destination_filename, "failed", error_code=code, error=message, media_index=media_index)
                        result.error = result.error or message
                        result.error_code = result.error_code or code
                        self.logger.warning("destination_failed", extra={"event": "destination_failed", "context": {"post_id": post.post_id, "destination": destination, "error_code": code, "media_index": media_index}})
                        continue

                    state = "ready" if destination == "download" else "duplicate" if details.get("already_exists") else "success"
                    self._item(result, destination, destination_filename, state, media_index=media_index, **details)
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
        self._finalize_media_reconciliation(result)

        if not any_failure and not any_unconfirmed and self.dedupe and any(target in {"telegram", "mega", "dropbox"} for target in self.config.destinations):
            try:
                self.dedupe.mark_complete(dedupe_key)
            except Exception:
                self.logger.error("dedupe_finalize_failed", extra={"event": "dedupe_finalize_failed", "context": {"post_id": post.post_id}})

        if (any_failure or any_unconfirmed) and any_delivery:
            result.status = ResultStatus.PARTIAL_SUCCESS
            result.error_code = result.error_code or "partial_destination_failure"
            result.stage = result.stage or "completed"
        elif any_unconfirmed:
            result.status = ResultStatus.OUTCOME_UNCONFIRMED
            result.stage = result.stage or "completed_with_unconfirmed_outcome"
        elif any_failure:
            if self.config.destinations == ("telegram",):
                result.status = (
                    ResultStatus.METADATA_ERROR if result.stage == "metadata"
                    else ResultStatus.DOWNLOAD_ERROR if result.stage == "download"
                    else ResultStatus.TELEGRAM_ERROR if result.error_code and result.error_code.startswith("telegram")
                    else ResultStatus.ERROR
                )
            else:
                result.status = ResultStatus.FAILED
            result.stage = result.stage or "completed_with_errors"
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
