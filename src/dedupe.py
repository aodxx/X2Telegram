from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import os
import tempfile
from typing import Iterator


class DedupeStore:
    """Small local state store for successful X post deliveries.

    State is keyed by post ID (or normalized URL when an ID is unavailable).
    Writes use a lock and atomic replace so a killed runner cannot leave a
    partially-written JSON file.
    """

    VERSION = 1

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    @property
    def enabled(self) -> bool:
        return bool(str(self.path))

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": self.VERSION, "posts": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Dedupe state is unreadable: {exc}") from exc
        if payload.get("version") != self.VERSION or not isinstance(payload.get("posts"), dict):
            raise RuntimeError("Dedupe state has an unsupported schema")
        return payload

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            try:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            except ImportError:
                pass
            try:
                yield
            finally:
                try:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                except ImportError:
                    pass

    def get(self, key: str) -> dict | None:
        with self._locked():
            return self._load()["posts"].get(key)

    def mark_sent(self, key: str, *, post_id: str | None, username: str | None,
                  source_url: str, message_ids: list[int]) -> None:
        with self._locked():
            payload = self._load()
            payload["posts"][key] = {
                "post_id": post_id,
                "username": username,
                "source_url": source_url,
                "message_ids": message_ids,
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=".dedupe-", suffix=".tmp", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self.path)
            finally:
                Path(temp_name).unlink(missing_ok=True)
