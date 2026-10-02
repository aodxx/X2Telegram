#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_PREFLIGHT=0
SKIP_TESTS=0
URL_FILE=""

usage() {
  cat <<'EOF'
Usage: scripts/local_test.sh [options]

Safe local verification for X2Telegram. It never sends a message or media.

Options:
  --preflight           Call Telegram getMe/getChat/getChatMember only.
                        Requires TELEGRAM_BOT_TOKEN; never calls sendVideo.
  --urls-file PATH      Parse URLs from PATH instead of the built-in sample.
  --skip-tests          Skip pytest (not recommended).
  -h, --help            Show this help.

Examples:
  scripts/local_test.sh
  scripts/local_test.sh --urls-file urls.txt
  TELEGRAM_BOT_TOKEN='do-not-print-this' scripts/local_test.sh --preflight
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --preflight) RUN_PREFLIGHT=1; shift ;;
    --skip-tests) SKIP_TESTS=1; shift ;;
    --urls-file)
      [[ $# -ge 2 ]] || { echo "--urls-file requires a path" >&2; exit 2; }
      URL_FILE="$2"
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

if [[ "$SKIP_TESTS" -eq 0 ]]; then
  echo "[1/4] Running automated tests..."
  python3 -m pytest -q
else
  echo "[1/4] Skipping automated tests by request"
fi

echo "[2/4] Checking Python syntax..."
python3 -m compileall -q src tests

echo "[3/4] Parsing URLs without Telegram or media delivery..."
TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT
if [[ -n "$URL_FILE" ]]; then
  [[ -f "$URL_FILE" ]] || { echo "URL file not found: $URL_FILE" >&2; exit 1; }
  INPUT_CMD=(cat "$URL_FILE")
else
  INPUT_CMD=(printf '%s\n' 'https://x.com/example/status/1234567890123456789?s=20')
fi
"${INPUT_CMD[@]}" | python3 -m src.cli --parse-only \
  --report "$TMP_DIR/report.json" \
  --log "$TMP_DIR/run.jsonl" >/dev/null
python3 - "$TMP_DIR/report.json" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if report.get("status") != "completed":
    raise SystemExit(f"parse-only check failed: {report.get('status')}")
print(f"Parsed {report['valid_unique_posts']} unique public X URL(s)")
PY

if [[ "$RUN_PREFLIGHT" -eq 1 ]]; then
  echo "[4/4] Running Telegram preflight only (no send operation)..."
  [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] || {
    echo "TELEGRAM_BOT_TOKEN is required for --preflight; value is never printed" >&2
    exit 1
  }
  export TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:--1003906817580}"
  python3 - <<'PY'
from src.config import Config
from src.telegram_api import TelegramClient

config = Config.from_env()
client = TelegramClient(
    config.telegram_bot_token,
    config.telegram_chat_id,
    config.timeout_seconds,
    config.max_retries,
    config.telegram_api_base_url,
)
result = client.preflight()
print({
    "chat_id": result.chat_id,
    "chat_type": result.chat_type,
    "member_status": result.member_status,
    "can_send_messages": result.can_send_messages,
    "can_send_media": result.can_send_media,
})
PY
else
  echo "[4/4] Telegram preflight skipped (use --preflight to opt in)"
fi

echo "Local checks passed. No Telegram message or media was sent."
