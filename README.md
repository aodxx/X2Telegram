# X2Telegram

X media to Telegram automation running on GitHub Actions.

## Goal

Paste one or many public X post URLs into one GitHub Actions run. The system parses each URL, processes each post independently, and reports results.

## Principles
- Simple setup: configure secrets once.
- Batch input: one URL or many URLs, one per line.
- Independent processing: one bad URL must not stop the rest.
- Temporary files only: media is not committed to Git.
- Secrets stay in GitHub Actions Secrets.
- Clear per-post result states.

## Planned flow
X URLs -> parse -> metadata -> validation -> media selection -> temporary download -> Telegram -> result -> cleanup.

## Repository layout
.github/workflows/x2telegram.yml
src/
tests/
docs/

## Setup and real usage
1. Create a Telegram bot with `@BotFather`, add it to the target chat, and obtain the bot token.
2. Add repository Actions secrets named `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
3. Open **Actions → X2Telegram → Run workflow**, then paste one public X URL per line.
4. The workflow extracts metadata, selects the highest-bitrate video (or photos), downloads to temporary storage, sends to Telegram, deletes the temporary file, and uploads a JSON report as a workflow artifact.

For local URL validation without sending anything:

```bash
printf '%s\n' 'https://x.com/user/status/123' | python -m src.cli --parse-only
```

The system processes posts independently: an unavailable or private post is reported without stopping other URLs.

Only use media you are authorized to download and redistribute, and comply with applicable platform terms. X availability and rate limits can change; unresolved public posts are reported as errors rather than retried indefinitely.
