import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    timeout_seconds: int = 60
    max_retries: int = 3
    max_file_size_mb: int = 50

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

        return cls(token, chat_id, positive_int("REQUEST_TIMEOUT_SECONDS", 60),
                   positive_int("MAX_RETRIES", 3), positive_int("MAX_FILE_SIZE_MB", 50))
