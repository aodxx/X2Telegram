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
GitHub Pages redirect → Cloudflare Access + Worker-hosted Dashboard/API → GitHub Actions → X2Telegram Python worker → Telegram
```

GitHub Actions remains the execution plane and retains the Telegram credential, fixed destination, media processing, concurrency and persisted duplicate state. Dedupe state version 2 stores a content fingerprint and Telegram message ID per successfully delivered media item; version 1 completed-post entries remain readable as whole-post duplicates. The downloader validates every HTTPS redirect hop against the X media-host allowlist. The Cloudflare Worker validates Access JWTs and exact Dashboard origin, serves protected Dashboard assets from the same origin as the API, accepts up to 50 post URLs per job, finds the workflow run by deterministic batch fingerprint, and returns only the sanitized report artifact. It stores no jobs/database/queue and receives no Telegram secret.

The Dashboard implementation, API contract, workflow input compatibility and tests are in this repository (`control-worker/`, `docs/CONTROL_PLANE_CONTRACT.md`, `docs/CLOUDFLARE_WORKER.md`, `docs/CLOUDFLARE_ACCESS.md`). The Worker serves the Dashboard under Access; the GitHub Pages URL redirects to it so the browser does not rely on third-party Access cookies. `/auth/check` reports an authenticated session only after JWT verification. Dashboard submits batches of 1–50 URLs as one Actions run, while manual Actions dispatch remains compatible. The earlier one-URL live E2E passed; the new multi-URL batch path is covered by offline tests, with live batch delivery still unverified. The `gas/` implementation is legacy/reference, not the current Dashboard API path.
