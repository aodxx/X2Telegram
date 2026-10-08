from dataclasses import dataclass
from pathlib import Path
import time

import requests


REQUIRED_CHAT_ID = "-1003906817580"


class TelegramApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class TelegramPreflight:
    bot_id: int
    bot_username: str | None
    chat_id: str
    chat_type: str | None
    member_status: str
    can_send_messages: bool
    can_send_media: bool


class TelegramClient:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        timeout_seconds: int = 60,
        max_retries: int = 3,
        api_base_url: str = "https://api.telegram.org",
    ):
        if not bot_token or not bot_token.strip():
            raise ValueError("Telegram bot token is required")
        if str(chat_id).strip() != REQUIRED_CHAT_ID:
            raise ValueError(f"Telegram destination is fixed to {REQUIRED_CHAT_ID}")
        self.chat_id = str(chat_id).strip()
        self.timeout = timeout_seconds
        self.max_retries = max(1, max_retries)
        self.base_url = f"{api_base_url.rstrip('/')}/bot{bot_token.strip()}"

    def _request_json(self, method: str, params: dict[str, str | int] | None = None) -> dict:
        try:
            response = requests.post(
                f"{self.base_url}/{method}",
                data=params or {},
                timeout=self.timeout,
            )
            payload = response.json()
        except (requests.RequestException, ValueError):
            # requests exceptions can include the full API URL, which contains the bot token.
            raise TelegramApiError(f"Telegram {method} request failed") from None
        if not response.ok or not payload.get("ok"):
            error_code = payload.get("error_code")
            if not isinstance(error_code, int) or not 100 <= error_code <= 599:
                error_code = response.status_code
            # Never persist Telegram's raw response description/body in reports or logs.
            raise TelegramApiError(f"Telegram {method} failed (HTTP {error_code})")
        return payload

    def preflight(self) -> TelegramPreflight:
        """Verify token, destination chat, bot membership, and send permissions."""
        me = self._request_json("getMe")["result"]
        chat = self._request_json("getChat", {"chat_id": self.chat_id})["result"]
        member = self._request_json(
            "getChatMember",
            {"chat_id": self.chat_id, "user_id": int(me["id"])},
        )["result"]

        status = member.get("status", "unknown")
        if status in {"left", "kicked"}:
            raise TelegramApiError(f"Bot is not a member of Telegram chat {self.chat_id}")
        if status == "restricted" and not member.get("can_send_messages", False):
            raise TelegramApiError(f"Bot cannot send messages to Telegram chat {self.chat_id}")
        if status not in {"creator", "administrator", "member", "restricted"}:
            raise TelegramApiError(f"Unsupported bot membership status: {status}")

        return TelegramPreflight(
            bot_id=int(me["id"]),
            bot_username=me.get("username"),
            chat_id=self.chat_id,
            chat_type=chat.get("type"),
            member_status=status,
            can_send_messages=True,
            # Telegram exposes media rights through the same send permission for groups.
            can_send_media=True,
        )

    def _send(self, method: str, field: str, path: str, caption: str) -> int:
        for attempt in range(self.max_retries):
            try:
                with Path(path).open("rb") as handle:
                    response = requests.post(
                        f"{self.base_url}/{method}",
                        data={"chat_id": self.chat_id, "caption": caption[:1024]},
                        files={field: handle},
                        timeout=self.timeout,
                    )
                try:
                    payload = response.json()
                except ValueError:
                    raise TelegramApiError(f"Telegram {method} returned invalid JSON") from None
                if response.ok and payload.get("ok"):
                    return int(payload["result"]["message_id"])
                error_code = payload.get("error_code")
                if not isinstance(error_code, int) or not 100 <= error_code <= 599:
                    error_code = response.status_code
                retry_after = (payload.get("parameters") or {}).get("retry_after")
                retryable = error_code == 429 or error_code >= 500
                if not retryable or attempt + 1 >= self.max_retries:
                    raise TelegramApiError(f"Telegram {method} failed (HTTP {error_code})")
                try:
                    delay = min(int(retry_after or (2**attempt)), 60)
                except (TypeError, ValueError, OverflowError):
                    delay = min(2**attempt, 60)
                time.sleep(delay)
            except (requests.RequestException, OSError):
                if attempt + 1 >= self.max_retries:
                    # Do not include exception text: it may contain the tokenized request URL.
                    raise TelegramApiError(f"Telegram {method} request failed") from None
                time.sleep(min(2**attempt, 60))
        raise TelegramApiError(f"Telegram {method} failed")

    def send_video(self, path: str, caption: str) -> int:
        return self._send("sendVideo", "video", path, caption)

    def send_photo(self, path: str, caption: str) -> int:
        return self._send("sendPhoto", "photo", path, caption)

    def send_document(self, path: str, caption: str) -> int:
        return self._send("sendDocument", "document", path, caption)
