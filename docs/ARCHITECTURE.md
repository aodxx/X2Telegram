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

## Private Dashboard control plane (migration implementation)

Target flow:

```text
GitHub Pages → Cloudflare Access → Cloudflare Control Worker → GitHub Actions → X2Telegram Python worker → Telegram
```

GitHub Actions remains the execution plane and retains the Telegram bot credential, fixed Telegram destination, media processing, concurrency and persisted duplicate state. Dedupe state version 2 stores a content fingerprint and Telegram message ID per successfully delivered media item; version 1 completed-post entries remain readable as whole-post duplicates. The downloader validates every HTTPS redirect hop against the X media-host allowlist. The Cloudflare Worker validates Access JWTs and exact Dashboard origin, maps one X post request to `workflow_dispatch`, finds the run by deterministic job fingerprint, and returns only the sanitized private dashboard artifact. It stores no jobs/database/queue and receives no Telegram secret.

The Dashboard implementation, API contract, workflow input compatibility and offline tests are in this repository (`control-worker/`, `docs/CONTROL_PLANE_CONTRACT.md`, `docs/CLOUDFLARE_WORKER.md`, `docs/CLOUDFLARE_ACCESS.md`). The Control Worker and owner-only Cloudflare Access are deployed; authenticated health and read-only GitHub workflow lookup have passed. **The migration is not production-ready:** the exposed `GH_TOKEN` still must be revoked/rotated, the new request has not been dispatched, and no Telegram E2E has run. PR #2 remains unmerged, so GitHub Pages `main` and the manual GitHub Actions batch path remain unchanged. The `gas/` implementation is legacy/reference pending the successful E2E gate, not the new Dashboard API path.
