import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
import os
import sys
import time

from .config import Config
from .dedupe import DedupeStore
from .destinations import DownloadExporter, MegaUploader
from .dropbox import DropboxUploader
from .errors import DestinationError
from .logging_utils import configure_logging, log_event, redact
from .metadata import YtDlpMetadataProvider
from .models import ResultStatus
from .notifications import NotificationError, send_webhook, write_github_summary
from .processor import PostProcessor
from .telegram_api import REQUIRED_CHAT_ID, TelegramClient
from .urls import parse_batch_inputs


class _UnavailableTelegram:
    def __init__(self, code: str, message: str):
        self.error = DestinationError(code, message)

    def _raise(self):
        raise self.error

    def send_video(self, path, caption):
        self._raise()

    def send_photo(self, path, caption):
        self._raise()

    def send_document(self, path, caption):
        self._raise()


def _write_report(payload: dict, path: str) -> str:
    # Reports are printed and uploaded as artifacts; redact defensively at the final boundary.
    output = json.dumps(redact(payload), ensure_ascii=False, indent=2, default=str)
    print(output)
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(output + "\n")
    return output


def _has_destination_failure(results: list[dict]) -> bool:
    """Return true when any selected destination failed, including partial delivery."""
    return any(
        value.get("status") in {"failed", "partial_success", "outcome_unconfirmed"}
        for item in results
        for value in (item.get("destinations") or {}).values()
    )


def build_summary(results: list[dict]) -> dict:
    """Aggregate post-level and per-destination statuses for dashboards."""
    failed_statuses = {"metadata_error", "download_error", "telegram_error", "error", "failed", "partial_success"}
    statuses = [item.get("status") for item in results]
    per_destination: dict[str, dict[str, int]] = {}
    for item in results:
        for destination, details in (item.get("destinations") or {}).items():
            if not isinstance(details, dict):
                continue
            target_counts = per_destination.setdefault(destination, {})
            status = str(details.get("status", "unknown"))
            target_counts[status] = target_counts.get(status, 0) + 1
    summary = {
        "total": len(results),
        "sent": sum(1 for status in statuses if status in {"sent", "success", "partial_success"}),
        "skipped_duplicate": statuses.count("skipped_duplicate"),
        "no_media": statuses.count("no_media"),
        "failed": sum(1 for status in statuses if status in failed_statuses),
    }
    unconfirmed = sum(
        1 for item in results
        if item.get("status") == "outcome_unconfirmed"
        or any(value.get("status") == "outcome_unconfirmed" for value in (item.get("destinations") or {}).values() if isinstance(value, dict))
    )
    if unconfirmed:
        summary["outcome_unconfirmed"] = unconfirmed
    if per_destination:
        summary["destinations"] = per_destination
    return summary


def build_input_outcomes(inputs: list, results: list[dict]) -> list[dict]:
    result_by_post = {str(item.get("post_id")): item for item in results if item.get("post_id") is not None}
    outcomes = []
    for entry in inputs:
        item = {
            "index": entry.index,
            "line_number": entry.line_number,
            "disposition": entry.disposition,
        }
        if entry.post:
            item.update({"username": entry.post.username, "post_id": entry.post.post_id,
                         "source_url": entry.post.normalized_url})
        if entry.duplicate_of is not None:
            item["duplicate_of"] = entry.duplicate_of
        if entry.disposition == "accepted":
            processed = result_by_post.get(entry.post.post_id) if entry.post else None
            item["status"] = processed.get("status", "accepted") if processed else "accepted"
            if processed:
                for key in ("stage", "error_code", "error", "attempts", "variant_attempts"):
                    if processed.get(key) is not None:
                        item[key] = processed[key]
                for details in (processed.get("destinations") or {}).values():
                    if not isinstance(details, dict):
                        continue
                    for key in ("attempts", "variant_attempts"):
                        if details.get(key) is not None and key not in item:
                            item[key] = details[key]
                    for media in details.get("items") or []:
                        if media.get("status") != "failed":
                            continue
                        for key in ("attempts", "variant_attempts"):
                            if media.get(key) is not None and key not in item:
                                item[key] = media[key]
        else:
            item["status"] = entry.disposition
            if entry.error_code:
                item["error_code"] = entry.error_code
            if entry.disposition == "rejected":
                item["error"] = "This entry is not a valid X post URL."
        outcomes.append(item)
    return outcomes


def build_input_summary(outcomes: list[dict], blank_line_count: int) -> dict:
    counts = {name: 0 for name in ("accepted", "duplicate", "normalized_duplicate", "rejected")}
    for item in outcomes:
        disposition = item.get("disposition")
        if disposition in counts:
            counts[disposition] += 1
    return {
        "submitted": len(outcomes),
        **counts,
        "blank_lines_ignored": max(0, int(blank_line_count)),
    }


def _create_telegram(config: Config, payload: dict):
    if "telegram" not in config.destinations:
        return None
    if not config.telegram_bot_token:
        return _UnavailableTelegram("telegram_credentials_missing", "Telegram bot credentials are not configured in GitHub Actions Secrets.")
    if config.telegram_chat_id != REQUIRED_CHAT_ID:
        return _UnavailableTelegram("telegram_configuration_error", "Telegram target chat is not configured correctly.")
    client = TelegramClient(
        config.telegram_bot_token,
        config.telegram_chat_id,
        config.timeout_seconds,
        config.max_retries,
        config.telegram_api_base_url,
    )
    try:
        preflight = client.preflight()
        payload["telegram_preflight"] = {
            "status": "success",
            "chat_id": preflight.chat_id,
            "chat_type": preflight.chat_type,
            "member_status": preflight.member_status,
            "can_send_messages": preflight.can_send_messages,
            "can_send_media": preflight.can_send_media,
        }
        return client
    except Exception:
        payload["telegram_preflight"] = {"status": "failed", "error_code": "telegram_preflight_failed"}
        return _UnavailableTelegram(
            "telegram_preflight_failed",
            "Telegram preflight failed. Verify the bot, target group, and send permissions.",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Process public X post media to selected destinations")
    parser.add_argument("--parse-only", action="store_true")
    parser.add_argument("--report", default="")
    parser.add_argument("--log", default=os.getenv("LOG_PATH", ""))
    parser.add_argument("--alert-webhook", default=os.getenv("ALERT_WEBHOOK_URL", ""))
    parser.add_argument("--dedupe-state", default=os.getenv("DEDUPE_STATE_PATH", ""))
    args = parser.parse_args()
    logger = configure_logging(args.log)
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    raw = sys.stdin.read()
    batch_inputs, blank_line_count = parse_batch_inputs(raw)
    posts = [entry.post for entry in batch_inputs if entry.disposition == "accepted" and entry.post is not None]
    payload = {
        "schema_version": 2,
        "run_id": os.getenv("GITHUB_RUN_ID"),
        "request_id": os.getenv("REQUEST_ID") or None,
        "job_id": os.getenv("JOB_ID") or os.getenv("REQUEST_ID") or None,
        "large_file_mode": os.getenv("LARGE_FILE_MODE", "").lower() == "true",
        "started_at": started_at,
        "status": "completed",
        "input_count": len(batch_inputs),
        "blank_line_count": blank_line_count,
        "valid_unique_posts": len(posts),
        "dedupe_enabled": bool(args.dedupe_state),
        "results": [],
        "input_outcomes": [],
    }
    exit_code = 0
    log_event(logger, logging.INFO, "run_started", "run_started", input_count=payload["input_count"],
              blank_line_count=blank_line_count, valid_unique_posts=len(posts))
    if args.parse_only:
        payload["selected_destinations"] = ["telegram"]
        payload["results"] = [
            {"username": post.username, "post_id": post.post_id, "source_url": post.normalized_url, "status": "ready"}
            for post in posts
        ]
        if not posts:
            payload["status"] = "completed_with_errors"
            payload["error_code"] = "invalid_x_url" if batch_inputs else "no_input_urls"
            payload["error"] = "No valid X post URL was provided. Check the input and try again."
            exit_code = 1
    elif not posts:
        payload["status"] = "completed_with_errors"
        payload["error_code"] = "invalid_x_url" if batch_inputs else "no_input_urls"
        payload["error"] = "No valid X post URL was provided. Check the input and try again."
        exit_code = 1
    else:
        worker = None
        try:
            config = Config.from_env()
            payload["selected_destinations"] = list(config.destinations)
            telegram = _create_telegram(config, payload)
            dedupe = DedupeStore(args.dedupe_state) if args.dedupe_state else None
            worker = PostProcessor(
                config,
                YtDlpMetadataProvider(config.timeout_seconds, max_retries=config.max_retries),
                telegram,
                logger,
                dedupe,
                MegaUploader(),
                DownloadExporter(os.getenv("DOWNLOAD_EXPORT_DIR", "")),
                dropbox_uploader=(
                    DropboxUploader(timeout_seconds=config.timeout_seconds, max_retries=config.max_retries)
                    if "dropbox" in config.destinations else None
                ),
            )
            payload["results"] = [asdict(worker.process(post)) for post in posts]
            for item in payload["results"]:
                item["status"] = item["status"].value
            any_failure = _has_destination_failure(payload["results"])
            any_unconfirmed = any(
                item.get("status") == "outcome_unconfirmed"
                or any(value.get("status") == "outcome_unconfirmed" for value in (item.get("destinations") or {}).values() if isinstance(value, dict))
                for item in payload["results"]
            )
            any_delivery = any(
                value.get("status") in {"success", "ready", "duplicate", "partial_success"}
                for item in payload["results"]
                for value in (item.get("destinations") or {}).values()
            )
            if any_unconfirmed and not any_delivery:
                payload["status"] = "outcome_unconfirmed"
                exit_code = 1
            elif any_failure and any_delivery:
                payload["status"] = "partial_success"
                exit_code = 1
            elif any_failure:
                payload["status"] = "completed_with_errors"
                exit_code = 1
        except Exception as exc:
            payload["status"] = "configuration_error"
            payload["error_code"] = "configuration_error"
            payload["error"] = str(exc)[:500]
            log_event(logger, logging.ERROR, "run_failed", "run_failed", error=payload["error"])
            exit_code = 1
        finally:
            if worker:
                worker.close()

    payload["input_outcomes"] = build_input_outcomes(batch_inputs, payload["results"])
    payload["input_summary"] = build_input_summary(payload["input_outcomes"], blank_line_count)
    has_rejected_input = any(item.disposition == "rejected" for item in batch_inputs)
    if has_rejected_input and posts and payload["status"] != "configuration_error":
        any_delivery = any(
            value.get("status") in {"success", "ready", "duplicate", "partial_success"}
            for item in payload["results"]
            for value in (item.get("destinations") or {}).values()
        )
        payload["status"] = "partial_success" if any_delivery else "completed_with_errors"
        exit_code = 1

    payload["summary"] = build_summary(payload["results"])
    payload["duration_seconds"] = round(time.monotonic() - started, 3)
    payload["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_report(payload, args.report)
    try:
        write_github_summary(payload)
        if args.alert_webhook:
            send_webhook(payload, args.alert_webhook)
            log_event(logger, logging.INFO, "alert_sent", "alert_sent")
    except NotificationError as exc:
        payload["alert_error"] = str(exc)[:300]
        log_event(logger, logging.ERROR, "alert_failed", "alert_failed", error=payload["alert_error"])
        if args.report:
            _write_report(payload, args.report)
        exit_code = 1
    log_event(logger, logging.INFO, "run_finished", "run_finished", status=payload["status"], duration_seconds=payload["duration_seconds"])
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
