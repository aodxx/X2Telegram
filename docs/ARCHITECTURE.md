# Architecture

## Milestone 1 — foundation

Implemented:
- Batch URL input.
- X/Twitter host validation.
- Query-string removal.
- Username and post ID extraction.
- Duplicate removal.
- Result models.
- Metadata and Telegram provider boundaries.
- Temporary-file validation helper.
- Manual GitHub Actions entry point.

## Milestone 2 — metadata
1. Implement a compatible metadata provider.
2. Return ordered media without downloading it.
3. Classify no-media and unavailable posts.
4. Add timeout/retry handling.

## Milestone 3 — media transfer
1. Download selected media to temporary storage.
2. Validate content type and file signatures.
3. Select highest available video bitrate.
4. Send media to Telegram.
5. Return message IDs per item.

## Milestone 4 — large-file path
Evaluate Local Bot API Server only where needed. Scope its lifecycle to one workflow job: start → health check → upload → stop → verify stopped.

## Milestone 5 — reporting
Produce Markdown/JSON summaries with per-post status, media count, message IDs, and error reason.

## Security
- Never commit Telegram credentials.
- Use GitHub Actions Secrets.
- Never persist downloaded media in the repository.
- Keep workflow permissions minimal.
