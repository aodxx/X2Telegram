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

## Setup
1. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID as GitHub Actions secrets.
2. Open Actions and run X2Telegram.
3. Paste URLs, one per line.
4. Review the generated summary.

Only use media you are authorized to download and redistribute, and comply with applicable platform terms.
