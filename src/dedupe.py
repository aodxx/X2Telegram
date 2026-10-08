from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import os
import tempfile
from typing import Iterator


class DedupeStore:
    """Atomic per-post/media/destination checkpoints with v1/v2 read compatibility."""

    VERSION = 3

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
        version = payload.get("version") if isinstance(payload, dict) else None
        posts = payload.get("posts") if isinstance(payload, dict) else None
        if version not in {1, 2, self.VERSION} or not isinstance(posts, dict):
            raise RuntimeError("Dedupe state has an unsupported schema")
        if version == 1:
            migrated = {}
            for key, value in posts.items():
                if not isinstance(value, dict):
                    raise RuntimeError("Dedupe state has an invalid post record")
                record = dict(value)
                record.setdefault("media", {})
                if record.get("message_ids"):
                    record["legacy_complete"] = True
                migrated[key] = record
            return {"version": self.VERSION, "posts": migrated}
        if version == 2:
            return {"version": self.VERSION, "posts": posts}
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

    def _save(self, payload: dict) -> None:
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

    def get(self, key: str) -> dict | None:
        with self._locked():
            return self._load()["posts"].get(key)

    def get_media(self, key: str, fingerprint: str) -> dict | None:
        record = self.get(key)
        if not record:
            return None
        return (record.get("media") or {}).get(fingerprint)

    def get_destination(self, key: str, fingerprint: str, destination: str) -> dict | None:
        media = self.get_media(key, fingerprint)
        if not media:
            return None
        delivered = (media.get("destinations") or {}).get(destination)
        if isinstance(delivered, dict) and delivered.get("status") == "success":
            return delivered
        # State v2 stored Telegram fields directly on the media record.
        if destination == "telegram" and isinstance(media.get("message_id"), int):
            return {"status": "success", "message_id": media["message_id"], "filename": media.get("filename")}
        return None

    def mark_destination_sent(
        self,
        key: str,
        fingerprint: str,
        *,
        destination: str,
        post_id: str | None,
        username: str | None,
        source_url: str,
        kind: str,
        filename: str,
        details: dict | None = None,
    ) -> None:
        if destination not in {"telegram", "mega"}:
            raise ValueError("Only persistent destinations can be checkpointed")
        with self._locked():
            payload = self._load()
            record = payload["posts"].setdefault(key, {"media": {}})
            record.update({"post_id": post_id, "username": username, "source_url": source_url})
            media = record.setdefault("media", {}).setdefault(fingerprint, {"kind": kind, "filename": filename})
            delivered = {"status": "success", "filename": filename,
                         "delivered_at": datetime.now(timezone.utc).isoformat()}
            delivered.update(details or {})
            media.setdefault("destinations", {})[destination] = delivered
            # Retain the legacy v2 fields for Telegram report/backward compatibility.
            if destination == "telegram" and isinstance(delivered.get("message_id"), int):
                media.update({"message_id": delivered["message_id"], "filename": filename,
                              "sent_at": delivered["delivered_at"]})
            record["message_ids"] = [
                int(item["message_id"]) for item in record["media"].values()
                if isinstance(item, dict) and isinstance(item.get("message_id"), int)
            ]
            record["completed"] = False
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save(payload)

    def mark_media_sent(
        self,
        key: str,
        fingerprint: str,
        *,
        post_id: str | None,
        username: str | None,
        source_url: str,
        kind: str,
        message_id: int,
        filename: str,
    ) -> None:
        """Compatibility helper for existing callers/tests; records Telegram delivery."""
        self.mark_destination_sent(
            key, fingerprint, destination="telegram", post_id=post_id, username=username,
            source_url=source_url, kind=kind, filename=filename, details={"message_id": int(message_id)},
        )

    def mark_complete(self, key: str) -> None:
        with self._locked():
            payload = self._load()
            record = payload["posts"].get(key)
            if not record:
                return
            record["completed"] = True
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save(payload)

    def mark_sent(
        self,
        key: str,
        *,
        post_id: str | None,
        username: str | None,
        source_url: str,
        message_ids: list[int],
    ) -> None:
        """Compatibility helper: mark a previously delivered whole post as complete."""
        with self._locked():
            payload = self._load()
            payload["posts"][key] = {
                "post_id": post_id,
                "username": username,
                "source_url": source_url,
                "message_ids": [int(value) for value in message_ids],
                "media": {},
                "legacy_complete": True,
                "completed": True,
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save(payload)
