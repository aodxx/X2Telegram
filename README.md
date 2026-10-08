# X2Telegram

X media to Telegram automation running on GitHub Actions.

## Goal
Paste one or many public X post URLs into one GitHub Actions run. The system parses each URL, processes each post independently, and reports results.

## Project status

See [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) for the current implementation status, latest real-run evidence, production notes, and private Dashboard migration status.

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
2. Add the repository Actions secret `TELEGRAM_BOT_TOKEN`. The workflow is locked to chat `-1003906817580`.
3. Open **Actions → X2Telegram → Run workflow**, then paste one public X URL per line.
4. The workflow runs a Telegram preflight, extracts metadata, selects the highest-bitrate video (or photos), downloads to temporary storage, sends to Telegram, deletes the temporary file, and uploads a JSON report plus JSONL execution log as workflow artifacts.

The default workflow uses the standard Telegram Bot API and limits media to 50 MB. For larger media, enable the manual `large_file_mode` input. That mode requires repository secrets `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`, starts a Telegram Local Bot API Server for the job, and allows up to 2000 MB. The large-file path is intentionally opt-in.

If the optional `ALERT_WEBHOOK_URL` repository secret is configured with an HTTPS webhook, each run sends a redacted summary containing only run status, counts, and duration. The webhook never receives bot tokens, media URLs, captions, or per-post error text.

The workflow also enables duplicate prevention with `state/dedupe.json` v2. Each successfully delivered media item is checkpointed by content fingerprint and Telegram message ID, so a retry after partial failure can skip completed items even when temporary media URLs change. Existing v1 completed-post records remain readable. GitHub Actions concurrency serializes runs that share the state file. Exactly-once delivery is not guaranteed if Telegram accepts a send but the response is lost before the checkpoint is persisted.

Metadata fallback order is `yt-dlp` → X syndication → public FxTwitter API (`https://api.fxtwitter.com/2/status/{post_id}`). The fallback accepts only MP4 variants from the API and preserves required query parameters such as `?tag=12` on direct `video.twimg.com` URLs. Query parameters are stripped only from the source post URL used for lookup.

For local URL validation without sending anything:

```bash
printf '%s\n' 'https://x.com/user/status/123' | python -m src.cli --parse-only
```

For a complete local dry-run before GitHub Actions:

```bash
scripts/local_test.sh
scripts/local_test.sh --urls-file urls.txt
```

To verify the Telegram token, target group, bot membership, and permissions without sending a message or media, use:

```bash
TELEGRAM_BOT_TOKEN='set-locally-and-do-not-commit' scripts/local_test.sh --preflight
```

The local runner never calls `sendVideo`, `sendPhoto`, or `sendDocument`.

## Private Dashboard migration (in progress)

The GitHub Actions manual workflow above remains available and keeps its batch `urls` input. The new Dashboard path submits one post per job through a Cloudflare Control Worker; GitHub Actions remains the execution plane. The source implementation and offline tests are in `control-worker/`, with the API contract and setup steps in [`docs/CONTROL_PLANE_CONTRACT.md`](docs/CONTROL_PLANE_CONTRACT.md), [`docs/CLOUDFLARE_WORKER.md`](docs/CLOUDFLARE_WORKER.md), and [`docs/CLOUDFLARE_ACCESS.md`](docs/CLOUDFLARE_ACCESS.md).

**Normal-path E2E passed once, but migration is not production-ready.** The owner-approved X URL completed on the migration branch and delivered one MP4 to the locked Telegram group; see [`docs/E2E_TEST_REPORT.md`](docs/E2E_TEST_REPORT.md). The first `GH_TOKEN` value was exposed during setup and the owner declined rotation; rotate/revoke it before production. The Worker has been restored to `GH_REF=main`, but GitHub Pages `main` still uses the legacy dashboard and PR #2 is unmerged; do not rely on the new Dashboard path until the credential risk and remaining release gates are addressed. The manual Actions flow remains available. See [`docs/SECURITY_AUDIT.md`](docs/SECURITY_AUDIT.md).

Before downloading media, the worker verifies the token, target chat, bot membership, and send permission through the Telegram Bot API. The system processes posts independently: an unavailable or private post is reported without stopping other URLs.

Only use media you are authorized to download and redistribute, and comply with applicable platform terms. X availability and rate limits can change; unresolved public posts are reported as errors rather than retried indefinitely.
