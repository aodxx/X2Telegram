import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from .telegram_api import REQUIRED_CHAT_ID


STANDARD_MAX_FILE_SIZE_MB = 50
LARGE_MAX_FILE_SIZE_MB = 2000
DEFAULT_TELEGRAM_API_BASE_URL = "https://api.telegram.org"


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    timeout_seconds: int = 60
    max_retries: int = 3
    max_file_size_mb: int = STANDARD_MAX_FILE_SIZE_MB
    large_file_mode: bool = False
    telegram_api_base_url: str = DEFAULT_TELEGRAM_API_BASE_URL

    def __post_init__(self) -> None:
        if not self.telegram_bot_token.strip():
            raise ValueError("TELEGRAM_BOT_TOKEN is not configured")
        if self.telegram_chat_id.strip() != REQUIRED_CHAT_ID:
            raise ValueError(f"TELEGRAM_CHAT_ID must be {REQUIRED_CHAT_ID}")
        if self.timeout_seconds <= 0 or self.max_retries <= 0 or self.max_file_size_mb <= 0:
            raise ValueError("timeout, retries, and max file size must be greater than zero")
        if self.max_file_size_mb > LARGE_MAX_FILE_SIZE_MB:
            raise ValueError(f"MAX_FILE_SIZE_MB cannot exceed {LARGE_MAX_FILE_SIZE_MB}")
        if not self.large_file_mode and self.max_file_size_mb > STANDARD_MAX_FILE_SIZE_MB:
            raise ValueError(
                f"MAX_FILE_SIZE_MB cannot exceed {STANDARD_MAX_FILE_SIZE_MB} in standard mode"
            )
        parsed = urlsplit(self.telegram_api_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("TELEGRAM_API_BASE_URL must be an http(s) URL")
        if self.large_file_mode and self.telegram_api_base_url.rstrip("/") == DEFAULT_TELEGRAM_API_BASE_URL:
            raise ValueError(
                "LARGE_FILE_MODE requires a Telegram Local Bot API Server endpoint"
            )

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not configured")
        if not chat_id:
            raise ValueError("TELEGRAM_CHAT_ID is not configured")

        def positive_int(name: str, default: int) -> int:
            try:
                value = int(os.getenv(name, str(default)).strip())
            except ValueError as exc:
                raise ValueError(f"{name} must be an integer") from exc
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")
            return value

        def boolean(name: str, default: bool = False) -> bool:
            raw = os.getenv(name, "true" if default else "false").strip().lower()
            if raw not in {"true", "false", "1", "0", "yes", "no"}:
                raise ValueError(f"{name} must be true or false")
            return raw in {"true", "1", "yes"}

        large_file_mode = boolean("LARGE_FILE_MODE")
        default_size = LARGE_MAX_FILE_SIZE_MB if large_file_mode else STANDARD_MAX_FILE_SIZE_MB
        return cls(
            token,
            chat_id,
            positive_int("REQUEST_TIMEOUT_SECONDS", 60),
            positive_int("MAX_RETRIES", 3),
            positive_int("MAX_FILE_SIZE_MB", default_size),
            large_file_mode,
            os.getenv("TELEGRAM_API_BASE_URL", DEFAULT_TELEGRAM_API_BASE_URL).strip(),
        )
