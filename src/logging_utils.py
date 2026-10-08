import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any


_SECRET_PATTERNS = (
    re.compile(r"bot\d{5,}:[A-Za-z0-9_-]+", re.IGNORECASE),
    re.compile(r"([?&](?:token|api_key|apikey|auth|key)=)[^&\s]+", re.IGNORECASE),
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        sensitive_terms = ("token", "secret", "api_key", "api_hash", "authorization", "password")
        return {
            str(k): redact(v)
            for k, v in value.items()
            if not any(term in str(k).lower() for term in sensitive_terms)
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        result = value
        for pattern in _SECRET_PATTERNS:
            result = pattern.sub("[REDACTED_BOT_TOKEN]", result)
        return result[:1000]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": getattr(record, "event", record.getMessage()),
            "message": record.getMessage(),
        }
        context = getattr(record, "context", {})
        if context:
            payload["context"] = redact(context)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(log_path: str = "") -> logging.Logger:
    logger = logging.getLogger("x2telegram")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = JsonFormatter()
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    if log_path:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, level: int, event: str, message: str, **context: Any) -> None:
    logger.log(level, message, extra={"event": event, "context": redact(context)})
