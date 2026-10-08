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
from .logging_utils import configure_logging, log_event, redact
from .metadata import YtDlpMetadataProvider
from .models import ResultStatus
from .notifications import NotificationError, send_webhook, write_github_summary
from .processor import PostProcessor
from .telegram_api import TelegramClient
from .urls import parse_batch


def _write_report(payload: dict, path: str) -> str:
    # Reports are printed and uploaded as artifacts; redact defensively at the final boundary.
    output = json.dumps(redact(payload), ensure_ascii=False, indent=2, default=str)
    print(output)
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(output + "\n")
    return output


def build_summary(results: list[dict]) -> dict:
    """Aggregate per-post statuses for dashboards. Pure and additive."""
    failed = {"metadata_error", "download_error", "telegram_error", "error"}
    statuses = [item.get("status") for item in results]
    return {
        "total": len(results),
        "sent": statuses.count("sent"),
        "skipped_duplicate": statuses.count("skipped_duplicate"),
        "no_media": statuses.count("no_media"),
        "failed": sum(1 for status in statuses if status in failed),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Send public X post media to Telegram")
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
        "schema_version": 1,
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
        payload["results"] = [
            {"username": p.username, "post_id": p.post_id, "source_url": p.normalized_url, "status": "ready"}
            for p in posts
        ]
    else:
        try:
            config = Config.from_env()
            telegram = TelegramClient(
                config.telegram_bot_token,
                config.telegram_chat_id,
                config.timeout_seconds,
                config.max_retries,
                config.telegram_api_base_url,
            )
            preflight = telegram.preflight()
            payload["telegram_preflight"] = {
                "chat_id": preflight.chat_id,
                "chat_type": preflight.chat_type,
                "member_status": preflight.member_status,
                "can_send_messages": preflight.can_send_messages,
                "can_send_media": preflight.can_send_media,
            }
            dedupe = DedupeStore(args.dedupe_state) if args.dedupe_state else None
            worker = PostProcessor(config, YtDlpMetadataProvider(config.timeout_seconds), telegram, logger, dedupe)
            payload["results"] = [asdict(worker.process(post)) for post in posts]
            for item in payload["results"]:
                item["status"] = item["status"].value
            failed = {
                ResultStatus.METADATA_ERROR.value,
                ResultStatus.DOWNLOAD_ERROR.value,
                ResultStatus.TELEGRAM_ERROR.value,
                ResultStatus.ERROR.value,
            }
            if any(item["status"] in failed for item in payload["results"]):
                payload["status"] = "completed_with_errors"
                exit_code = 1
        except Exception as exc:
            payload["status"] = "configuration_error"
            payload["error_code"] = "configuration_error"
            payload["error"] = str(exc)[:500]
            log_event(logger, logging.ERROR, "run_failed", "run_failed", error=payload["error"])
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
