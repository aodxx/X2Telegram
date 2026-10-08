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
from .destinations import DestinationError, DownloadExporter, MegaUploader
from .logging_utils import configure_logging, log_event, redact
from .metadata import YtDlpMetadataProvider
from .models import ResultStatus
from .notifications import NotificationError, send_webhook, write_github_summary
from .processor import PostProcessor
from .telegram_api import REQUIRED_CHAT_ID, TelegramClient
from .urls import parse_batch


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
    if per_destination:
        summary["destinations"] = per_destination
    return summary


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
    posts = parse_batch(raw)
    payload = {
        "schema_version": 2,
        "run_id": os.getenv("GITHUB_RUN_ID"),
        "request_id": os.getenv("REQUEST_ID") or None,
        "job_id": os.getenv("JOB_ID") or os.getenv("REQUEST_ID") or None,
        "large_file_mode": os.getenv("LARGE_FILE_MODE", "").lower() == "true",
        "started_at": started_at,
        "status": "completed",
        "input_count": len(raw.splitlines()),
        "valid_unique_posts": len(posts),
        "dedupe_enabled": bool(args.dedupe_state),
        "results": [],
    }
    exit_code = 0
    log_event(logger, logging.INFO, "run_started", "run_started", input_count=payload["input_count"], valid_unique_posts=len(posts))
    if args.parse_only:
        payload["selected_destinations"] = ["telegram"]
        payload["results"] = [
            {"username": post.username, "post_id": post.post_id, "source_url": post.normalized_url, "status": "ready"}
            for post in posts
        ]
    else:
        worker = None
        try:
            config = Config.from_env()
            payload["selected_destinations"] = list(config.destinations)
            telegram = _create_telegram(config, payload)
            dedupe = DedupeStore(args.dedupe_state) if args.dedupe_state else None
            worker = PostProcessor(
                config,
                YtDlpMetadataProvider(config.timeout_seconds),
                telegram,
                logger,
                dedupe,
                MegaUploader(),
                DownloadExporter(os.getenv("DOWNLOAD_EXPORT_DIR", "")),
            )
            payload["results"] = [asdict(worker.process(post)) for post in posts]
            for item in payload["results"]:
                item["status"] = item["status"].value
            any_failure = any(
                value.get("status") in {"failed", "partial_success"}
                for item in payload["results"]
                for value in (item.get("destinations") or {}).values()
            )
            any_delivery = any(
                value.get("status") in {"success", "ready", "duplicate", "partial_success"}
                for item in payload["results"]
                for value in (item.get("destinations") or {}).values()
            )
            if any_failure and any_delivery:
                payload["status"] = "partial_success"
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
