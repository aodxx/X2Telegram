# Priority 4 — Large-File Telegram and Dropbox Validation

**Parent plan:** [MANUS_EXECUTION_PLAN.md](../MANUS_EXECUTION_PLAN.md)  
**Current status:** PARTIAL — automated edge-case coverage was strengthened on the current working branch; both large-file live tracks remain blocked pending explicitly authorized test destinations
**Scope:** Telegram Local Bot API for files over 50 MB and Dropbox token refresh/large-file upload sessions.

## Current implementation and validation update (2026-10-13)

The Dashboard and regression-test changes were merged via PR [#27](https://github.com/aodxx/X2Telegram/pull/27) as main commit `763bd9a`; Pages deployment [#38300619373](https://github.com/aodxx/X2Telegram/actions/runs/38300619373) succeeded. This remains **automated evidence only** for the P4 destination paths: no live Telegram/Dropbox write was performed, and no Worker deployment was needed.

| Track | Status in this session | Evidence / blocker |
|---|---|---|
| Telegram Local Bot API | **BLOCKED (live)** | Added mocked size-boundary coverage at 50 MB and 50 MB + 1 byte. Confirmed a missing/unready Local Bot API does not send an oversized file through the standard Bot API, while an independent destination can still proceed. No dedicated test-chat authorization is recorded; the production chat is not used. |
| Dropbox OAuth/session | **BLOCKED (live)** | Added assertions for exact session chunk bytes/offsets, refresh failure sanitization, and an ambiguous final response that is not replayed. No explicitly authorized test account/folder and cleanup policy are recorded for a live upload. |

Regression suite on main commit `763bd9a`: CI [#38300530120](https://github.com/aodxx/X2Telegram/actions/runs/38300530120) passed; Python **147 passed**, Worker/Dashboard **45 passed**. Python compile, inline Dashboard JavaScript syntax, workflow YAML parsing, and `git diff --check` also passed locally. These mocked tests do **not** satisfy the live acceptance checkboxes below.

**ภาษาไทย:** เพิ่ม automated tests สำหรับขอบเขต 50 MB, การปฏิเสธเมื่อ Local Bot API ไม่พร้อม, Dropbox chunk/offset, refresh failure และ final timeout โดยไม่ส่งไฟล์จริง; สถานะ live ของทั้งสอง track ยัง **BLOCKED** เพราะยังไม่มีปลายทางทดสอบและขอบเขตอนุญาตที่ยืนยันไว้

## Track A — Telegram Local Bot API

### Existing evidence and limits

The current status documents successful normal Telegram sends, but the standard Bot API path has a 50 MB limit and the Local Bot API large-file path has no recorded live proof. Automated tests do not satisfy this live acceptance criterion.

### Procedure

1. Confirm a dedicated test chat and explicit owner authorization. If absent, mark the track BLOCKED and proceed with independent work; do not guess the chat ID or use the production group as a workaround.
2. Use a synthetic file larger than 50 MB and within the currently supported 2,000 MB maximum.
3. Verify the workflow enables large-file mode, the Local Bot API server is ready before upload, and the request uses the intended local API endpoint.
4. Verify Telegram accepted the upload, the report records success and the correct byte size, and retry does not send a duplicate.
5. Save the Actions run URL and non-sensitive result evidence. Never save bot tokens or private chat credentials.

### Acceptance

- [ ] Test destination authorization recorded.
- [ ] File >50 MB uploaded through Local Bot API, not standard Bot API.
- [ ] Server readiness and selected mode are visible in safe logs/report.
- [ ] Report size/status matches the test file.
- [ ] Retry/idempotency does not duplicate the message.
- [ ] Run URL recorded without secrets.

## Track B — Dropbox token refresh and large-file session

### Existing evidence and limits

The repository records one successful normal Dropbox upload in combined run [#38037210973](https://github.com/aodxx/X2Telegram/actions/runs/38037210973). Refresh-token-only/expired-access-token behavior and the large-file upload-session path are currently supported by automated tests only.

### Procedure

1. Inspect the Dropbox adapter and existing refresh/session tests before changing code.
2. Use the configured Dropbox test account/folder. Do not ask for secrets in chat and do not rotate credentials without evidence of a real configuration problem.
3. Verify refresh-token operation when the access token is absent or expired, including safe handling of refresh errors.
4. Exercise upload-session behavior with a file large enough to enter that path; use the implementation's supported limits and avoid needless huge files.
5. Confirm the remote file's existence, size, and content hash if download-back verification is supported.
6. Record the run URL and clean up only the test artifact created for this run, if safe and consistent with account policy.

### Acceptance

- [ ] Refresh-token-only/expired-access-token path passes an actual integration check.
- [ ] Large-file upload session passes an actual integration check.
- [ ] Remote file and bytes/size are verified.
- [ ] Retry behavior is safe and does not create unintended duplicates.
- [ ] Evidence and any limitation are documented.

## General safety and status rules

Each track is independently marked PASS, FAIL, or BLOCKED. Do not mark a track PASS based on unit tests alone. A missing test destination/credential is a specific blocker, not permission to use production. Continue other priorities when a track is blocked.

## Required handoff

For each track report test environment (without secrets), file size, selected upload path, destination verification, run URL, retry result, and PASS/FAIL/BLOCKED status.

## Completeness audit additions — boundary, interruption, and integrity checks

- Test size boundaries around Telegram's standard 50 MB threshold and verify mode selection, including the case where Telegram is not selected. Use small boundary fixtures for routing logic and only one approved synthetic file above 50 MB for live validation.
- For Dropbox, exercise upload-session chunk boundaries, interruption/resume or restart behavior supported by the adapter, access-token expiry/refresh failure, and a retry after an ambiguous final response. Confirm incomplete sessions do not appear as successful final files.
- Verify the configured Local Bot API endpoint is the intended local service, readiness checks fail safely, and tokens/API credentials never appear in diagnostics. Do not expose a Local Bot API endpoint publicly as a workaround.
- Record exact byte size, expected checksum, remote size/checksum where available, chosen upload mode, and whether verification is mock or live. A successful HTTP response alone is not sufficient evidence of file integrity.
- Make cleanup narrowly scoped to artifacts created by the test run. If the environment cannot safely verify a scenario, mark only that scenario BLOCKED and continue independent work.
