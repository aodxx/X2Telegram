from __future__ import annotations

import base64
from pathlib import Path
import json
import os
import time
from typing import Callable

import requests

from .errors import DestinationError


class DropboxUploader:
    """Dropbox API v2 uploader using short-lived access tokens and OAuth refresh tokens."""

    API_BASE = "https://api.dropboxapi.com/2"
    CONTENT_BASE = "https://content.dropboxapi.com/2"
    TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
    CHUNK_SIZE = 8 * 1024 * 1024
    SMALL_FILE_LIMIT = 150 * 1024 * 1024
    RETRY_STATUSES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        access_token: str | None = None,
        refresh_token: str | None = None,
        app_key: str | None = None,
        app_secret: str | None = None,
        remote_folder: str | None = None,
        timeout_seconds: int = 120,
        max_retries: int = 3,
        request: Callable = requests.request,
        sleep: Callable = time.sleep,
    ):
        self.access_token = (access_token if access_token is not None else os.getenv("DROPBOX_ACCESS_TOKEN", "")).strip()
        self.refresh_token = (refresh_token if refresh_token is not None else os.getenv("DROPBOX_REFRESH_TOKEN", "")).strip()
        self.app_key = (app_key if app_key is not None else os.getenv("DROPBOX_APP_KEY", "")).strip()
        self.app_secret = (app_secret if app_secret is not None else os.getenv("DROPBOX_APP_SECRET", "")).strip()
        self.remote_folder = self._clean_folder(remote_folder or os.getenv("DROPBOX_REMOTE_FOLDER", "X2Telegram"))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_retries = max(1, int(max_retries))
        self.request = request
        self.sleep = sleep
        self._refresh_attempted = False

    @staticmethod
    def _clean_folder(value: str) -> str:
        parts = [part for part in str(value).strip("/").split("/") if part]
        if not parts or any(part in {".", ".."} or "/" in part or "\\" in part for part in parts):
            raise DestinationError("dropbox_configuration_error", "DROPBOX_REMOTE_FOLDER contains an unsupported path.")
        return "/" + "/".join(parts)

    def _path(self, filename: str) -> str:
        plain = Path(filename).name
        if not plain or plain != filename:
            raise DestinationError("dropbox_configuration_error", "Dropbox filename must be a plain filename.")
        return f"{self.remote_folder}/{plain}"

    def _auth_headers(self) -> dict[str, str]:
        if not self.access_token:
            raise DestinationError("dropbox_credentials_missing", "Dropbox access token or refresh token is not configured in GitHub Actions Secrets.")
        return {"Authorization": f"Bearer {self.access_token}"}

    def _refresh_access_token(self) -> None:
        if not self.refresh_token or not self.app_key or not self.app_secret:
            raise DestinationError("dropbox_credentials_missing", "Dropbox OAuth refresh credentials are not configured in GitHub Actions Secrets.")
        credentials = base64.b64encode(f"{self.app_key}:{self.app_secret}".encode()).decode()
        try:
            response = self.request(
                "POST", self.TOKEN_URL,
                headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise DestinationError("dropbox_authentication_failed", "Dropbox OAuth token refresh failed.") from exc
        if response.status_code >= 400:
            raise DestinationError("dropbox_authentication_failed", "Dropbox OAuth token refresh failed; check the App Key, App Secret, and Refresh Token.")
        try:
            token = response.json().get("access_token")
        except (ValueError, AttributeError) as exc:
            raise DestinationError("dropbox_authentication_failed", "Dropbox OAuth token response was invalid.") from exc
        if not token:
            raise DestinationError("dropbox_authentication_failed", "Dropbox OAuth token response did not include an access token.")
        self.access_token = str(token)

    @staticmethod
    def _retry_after(response) -> float:
        try:
            return max(0.0, min(float(response.headers.get("Retry-After", "1")), 60.0))
        except (AttributeError, TypeError, ValueError):
            return 1.0

    def _call(self, method: str, url: str, *, headers: dict[str, str] | None = None, data=None, json_body: dict | None = None):
        refreshed = False
        for attempt in range(self.max_retries + 1):
            request_headers = dict(headers or {})
            request_headers.update(self._auth_headers())
            if json_body is not None:
                request_headers["Content-Type"] = "application/json"
                body = json.dumps(json_body)
            else:
                body = data
            try:
                response = self.request(method, url, headers=request_headers, data=body, timeout=self.timeout_seconds)
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise DestinationError("dropbox_network_error", "Dropbox request failed after retries.") from exc
                self.sleep(min(2 ** attempt, 30))
                continue
            if response.status_code == 401 and not refreshed and self.refresh_token:
                self._refresh_access_token()
                refreshed = True
                continue
            if response.status_code in self.RETRY_STATUSES and attempt < self.max_retries:
                self.sleep(self._retry_after(response) if response.status_code == 429 else min(2 ** attempt, 30))
                continue
            return response
        raise DestinationError("dropbox_network_error", "Dropbox request failed after retries.")

    def _ensure_success(self, response, operation: str) -> dict:
        if response.status_code >= 400:
            if response.status_code == 401:
                code = "dropbox_authentication_failed"
            elif response.status_code == 429:
                code = "dropbox_rate_limited"
            elif response.status_code == 409:
                code = "dropbox_conflict"
            else:
                code = "dropbox_api_error"
            raise DestinationError(code, f"Dropbox {operation} failed (HTTP {response.status_code}).")
        try:
            return response.json() if response.content else {}
        except (ValueError, AttributeError) as exc:
            raise DestinationError("dropbox_api_error", f"Dropbox {operation} returned invalid JSON.") from exc

    def _content_call(self, endpoint: str, argument: dict, data) -> dict:
        response = self._call(
            "POST", f"{self.CONTENT_BASE}{endpoint}",
            headers={"Dropbox-API-Arg": json.dumps(argument, separators=(",", ":")), "Content-Type": "application/octet-stream"},
            data=data,
        )
        return self._ensure_success(response, endpoint.rsplit("/", 1)[-1])

    def _upload_small(self, path: Path, target: str) -> dict:
        with path.open("rb") as handle:
            return self._content_call("/files/upload", {"path": target, "mode": {".tag": "add"}, "autorename": False, "mute": True, "strict_conflict": True}, handle)

    def _upload_session(self, path: Path, target: str) -> dict:
        total = path.stat().st_size
        with path.open("rb") as handle:
            first = handle.read(self.CHUNK_SIZE)
            started = self._content_call("/files/upload_session/start", {"close": False}, first)
            session_id = started.get("session_id")
            if not session_id:
                raise DestinationError("dropbox_api_error", "Dropbox upload session did not return a session ID.")
            offset = len(first)
            while total - offset > self.CHUNK_SIZE:
                chunk = handle.read(self.CHUNK_SIZE)
                self._content_call("/files/upload_session/append_v2", {"cursor": {"session_id": session_id, "offset": offset}, "close": False}, chunk)
                offset += len(chunk)
            final = handle.read()
            return self._content_call("/files/upload_session/finish", {"cursor": {"session_id": session_id, "offset": offset}, "commit": {"path": target, "mode": {".tag": "add"}, "autorename": False, "mute": True, "strict_conflict": True}}, final)

    def upload(self, path: str | Path, filename: str) -> str:
        if not self.access_token and not self.refresh_token:
            raise DestinationError("dropbox_credentials_missing", "Dropbox OAuth credentials are not configured in GitHub Actions Secrets.")
        source = Path(path)
        if not source.is_file():
            raise DestinationError("dropbox_upload_failed", "Dropbox source file is unavailable.")
        target = self._path(filename)
        try:
            if source.stat().st_size <= self.SMALL_FILE_LIMIT:
                self._upload_small(source, target)
            else:
                self._upload_session(source, target)
        except OSError as exc:
            raise DestinationError("dropbox_upload_failed", "Dropbox source file could not be read.") from exc
        return target

    def close(self) -> None:
        return None
