import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    timeout_seconds: int = 60
    max_retries: int = 3

    @classmethod
    def from_env(cls):
        token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
        chat_id=os.getenv("TELEGRAM_CHAT_ID","").strip()
        if not token: raise ValueError("TELEGRAM_BOT_TOKEN is not configured")
        if not chat_id: raise ValueError("TELEGRAM_CHAT_ID is not configured")
        return cls(token, chat_id, int(os.getenv("REQUEST_TIMEOUT_SECONDS","60")), int(os.getenv("MAX_RETRIES","3")))
