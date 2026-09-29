from pathlib import Path
import time
import requests


class TelegramApiError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, bot_token: str, chat_id: str, timeout_seconds: int = 60, max_retries: int = 3):
        self.chat_id = chat_id
        self.timeout = timeout_seconds
        self.max_retries = max_retries
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def _send(self, method: str, field: str, path: str, caption: str) -> int:
        for attempt in range(self.max_retries):
            try:
                with Path(path).open("rb") as handle:
                    response = requests.post(f"{self.base_url}/{method}",
                                             data={"chat_id": self.chat_id, "caption": caption[:1024]},
                                             files={field: handle}, timeout=self.timeout)
                payload = response.json()
                if response.ok and payload.get("ok"):
                    return int(payload["result"]["message_id"])
                description = payload.get("description", response.text[:300])
                raise TelegramApiError(f"Telegram {method} failed: {description}")
            except (requests.RequestException, ValueError) as exc:
                if attempt + 1 >= self.max_retries:
                    raise TelegramApiError(f"Telegram {method} request failed: {exc}") from exc
                time.sleep(2 ** attempt)
        raise TelegramApiError(f"Telegram {method} failed")

    def send_video(self, path: str, caption: str) -> int:
        return self._send("sendVideo", "video", path, caption)

    def send_photo(self, path: str, caption: str) -> int:
        return self._send("sendPhoto", "photo", path, caption)

    def send_document(self, path: str, caption: str) -> int:
        return self._send("sendDocument", "document", path, caption)
