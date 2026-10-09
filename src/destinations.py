from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Callable

from .config import Config, DEFAULT_TELEGRAM_API_BASE_URL
from .errors import DestinationError
from .telegram_api import TelegramClient


DESTINATIONS = ("telegram", "mega", "dropbox", "download")


def safe_filename(username: str | None, post_id: str | None, index: int, suffix: str) -> str:
    user = re.sub(r"[^A-Za-z0-9_-]+", "_", username or "xpost").strip("._-") or "xpost"
    post = re.sub(r"[^0-9]+", "", post_id or "") or "media"
    extension = suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,8}", suffix or "") else ".bin"
    return f"{user}_{post}_{index:02d}{extension.lower()}"


def totp_code(secret: str, timestamp: float | None = None) -> str:
    """Generate the six-digit RFC 6238 TOTP used by MEGAcmd's --auth-code option."""
    normalized = re.sub(r"[\s-]", "", secret).upper()
    try:
        key = base64.b32decode(normalized + "=" * ((8 - len(normalized) % 8) % 8), casefold=True)
    except Exception as exc:
        raise DestinationError("mega_authentication_failed", "MEGA MFA secret is not valid base32.") from exc
    counter = int((timestamp if timestamp is not None else time.time()) // 30)
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


class MegaUploader:
    """Upload through MEGA's official MEGAcmd scriptable client."""

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        totp_secret: str | None = None,
        remote_folder: str | None = None,
        timeout_seconds: int = 3600,
        runner: Callable = subprocess.run,
        which: Callable = shutil.which,
    ):
        self.email = (email if email is not None else os.getenv("MEGA_EMAIL", "")).strip()
        self.password = password if password is not None else os.getenv("MEGA_PASSWORD", "")
        self.totp_secret = (totp_secret if totp_secret is not None else os.getenv("MEGA_TOTP_SECRET", "")).strip()
        self.remote_folder = remote_folder or os.getenv("MEGA_REMOTE_FOLDER", "X2Telegram")
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.runner = runner
        self.which = which
        self._logged_in = False
        self._login_error: DestinationError | None = None

    @staticmethod
    def _clean_remote_folder(value: str) -> str:
        parts = [part for part in str(value).strip("/").split("/") if part]
        if not parts or any(part in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9._ -]{1,80}", part) for part in parts):
            raise DestinationError("mega_configuration_error", "MEGA_REMOTE_FOLDER contains an unsupported path.")
        return "/".join(parts)

    def _run(self, args: list[str], timeout: int | None = None):
        try:
            return self.runner(
                args,
                check=False,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=timeout or self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise DestinationError("mega_client_unavailable", "MEGA upload client is unavailable on this runner.") from exc
        except subprocess.TimeoutExpired as exc:
            raise DestinationError("mega_timeout", "MEGA operation timed out; retry the job.") from exc
        except OSError as exc:
            raise DestinationError("mega_client_unavailable", "MEGA upload client could not be started.") from exc

    def _ensure_login(self) -> None:
        if self._logged_in:
            return
        if self._login_error:
            raise self._login_error
        if not self.email or not self.password:
            self._login_error = DestinationError(
                "mega_credentials_missing", "MEGA credentials are not configured in GitHub Actions Secrets."
            )
            raise self._login_error
        if not self.which("mega-login") or not self.which("mega-put"):
            self._login_error = DestinationError(
                "mega_client_unavailable", "MEGA upload client is unavailable on this runner."
            )
            raise self._login_error
        args = ["mega-login"]
        if self.totp_secret:
            args.append(f"--auth-code={totp_code(self.totp_secret)}")
        args.extend([self.email, self.password])
        result = self._run(args, timeout=90)
        if result.returncode != 0:
            # Never surface MEGAcmd output; it can contain account or session details.
            self._login_error = DestinationError(
                "mega_authentication_failed", "MEGA login failed. Check MEGA_EMAIL, MEGA_PASSWORD, and optional MEGA_TOTP_SECRET."
            )
            raise self._login_error
        self._logged_in = True

    def upload(self, path: str | Path, filename: str, *, timestamp: datetime | None = None) -> str:
        root_folder = self._clean_remote_folder(self.remote_folder)
        self._ensure_login()
        day = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%d")
        remote_folder = f"/{root_folder}/{day}"
        source = Path(path).resolve()
        requested_name = Path(filename).name
        if not requested_name or requested_name in {".", ".."} or requested_name != filename:
            raise DestinationError("mega_configuration_error", "MEGA filename must be a plain filename without path components.")

        # The processor normally names the downloaded file before delivery. Keep this
        # contract correct for other callers too: MEGAcmd uploads using the local
        # basename, not the separate filename argument.
        if source.name == requested_name:
            result = self._run(["mega-put", "-c", str(source), remote_folder])
        else:
            # Stage only mismatched names; do not rename or mutate the caller's file.
            with tempfile.TemporaryDirectory(prefix="x2telegram-mega-") as staging_dir:
                staged_path = Path(staging_dir) / requested_name
                shutil.copy2(source, staged_path)
                result = self._run(["mega-put", "-c", str(staged_path), remote_folder])

        if result.returncode != 0:
            raise DestinationError(
                "mega_upload_failed", "MEGA upload failed. Check available storage, account access, and network status."
            )
        return remote_folder

    def close(self) -> None:
        if not self._logged_in:
            return
        try:
            self._run(["mega-logout"], timeout=30)
        except DestinationError:
            pass
        finally:
            self._logged_in = False


class DownloadExporter:
    """Copy processed media to the directory uploaded as a private Actions artifact."""

    DEFAULT_MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024

    def __init__(self, directory: str | Path | None, max_total_bytes: int | None = None):
        self.directory = Path(directory) if directory else None
        self.max_total_bytes = max_total_bytes if max_total_bytes is not None else self.DEFAULT_MAX_TOTAL_BYTES
        self.total_bytes = 0

    def export(self, path: str | Path, filename: str) -> Path:
        if self.directory is None:
            raise DestinationError("download_storage_unavailable", "Browser download artifact is not configured.")
        destination: Path | None = None
        try:
            size = Path(path).stat().st_size
            if self.total_bytes + size > self.max_total_bytes:
                raise DestinationError("download_artifact_size_limit", "The browser download ZIP exceeds the 8 GiB job limit.")
            self.directory.mkdir(parents=True, exist_ok=True)
            destination = self.directory / Path(filename).name
            shutil.copy2(path, destination)
            self.total_bytes += size
            return destination
        except DestinationError:
            raise
        except OSError as exc:
            if destination is not None:
                try:
                    destination.unlink(missing_ok=True)
                except OSError:
                    pass
            raise DestinationError("download_export_failed", "Could not prepare the browser download artifact.") from exc


class DestinationDispatcher:
    """Dispatch the same downloaded file to each requested destination."""

    def __init__(
        self,
        config: Config,
        telegram: TelegramClient | None,
        mega: MegaUploader | None = None,
        download: DownloadExporter | None = None,
        dropbox=None,
    ):
        self.config = config
        self.telegram = telegram
        self.mega = mega or MegaUploader()
        self.download = download or DownloadExporter(os.getenv("DOWNLOAD_EXPORT_DIR", ""))
        self.dropbox = dropbox

    def deliver(self, destination: str, path: str | Path, filename: str, caption: str, kind: str) -> dict:
        if destination == "telegram":
            if self.telegram is None:
                raise DestinationError("telegram_configuration_error", "Telegram destination is not configured.")
            local_api_ready = (
                self.config.large_file_mode
                and self.config.telegram_api_base_url.rstrip("/") != DEFAULT_TELEGRAM_API_BASE_URL
            )
            limit_mb = 2000 if local_api_ready else 50
            size = Path(path).stat().st_size
            if size > limit_mb * 1024 * 1024:
                raise DestinationError(
                    "telegram_file_too_large",
                    ("File exceeds Telegram's 50 MB limit. Configure the Local Bot API and enable Large-file mode for larger Telegram files."
                     if not local_api_ready else "File exceeds Telegram's 2000 MB Local Bot API limit."),
                )
            if kind == "video":
                message_id = self.telegram.send_video(str(path), caption)
            elif kind == "photo":
                message_id = self.telegram.send_photo(str(path), caption)
            else:
                message_id = self.telegram.send_document(str(path), caption)
            return {"message_id": int(message_id)}
        if destination == "mega":
            remote_folder = self.mega.upload(path, filename)
            return {"remote_folder": remote_folder}
        if destination == "dropbox":
            if self.dropbox is None:
                raise DestinationError("dropbox_configuration_error", "Dropbox destination is not configured.")
            return {"dropbox_path": self.dropbox.upload(path, filename)}
        if destination == "download":
            self.download.export(path, filename)
            return {}
        raise DestinationError("unsupported_destination", "Destination is not supported.")

    def close(self) -> None:
        self.mega.close()
        if self.dropbox is not None:
            self.dropbox.close()
