# Priority 5 — Mobile Dashboard UX and Operational Clarity

**Parent plan:** [MANUS_EXECUTION_PLAN.md](../MANUS_EXECUTION_PLAN.md)  
**Current status:** PARTIAL / VERIFY CURRENT DEPLOYED UI  
**Scope:** Mobile user flow, progress, per-URL results, safe retry, and Browser ZIP availability. Preserve Cloudflare Access and server-side idempotency.

## Required investigation

1. Read the parent plan, `AGENTS.md`, current handoff/status docs, and current dashboard implementation.
2. Inspect the deployed UI and current API/report shape before proposing a new component or endpoint.
3. Map which information is already available in job status/report responses and reuse it rather than duplicating state.
4. Confirm the existing responsive layout and current deployed commit before editing.

## User-facing requirements

- Show total URLs/items and clear success/failure/in-progress counts.
- Show a separate status for each submitted URL and media item when the API/report supports it.
- Display actionable error details without exposing credentials, signed URLs, raw headers, or internal secrets.
- Make retry available only for failed/retryable work and keep it consistent with Priority 3.
- Make submission state visible and prevent accidental double taps; retain server-side idempotency as the actual duplicate protection.
- Clearly indicate Browser ZIP states such as preparing, ready, unavailable, or expired, according to the actual backend capability.
- Preserve access/login protections. Never make the dashboard or download artifact public just to simplify use.
- Keep the interface usable at mobile viewport widths without requiring horizontal scrolling for the main flow.

## Implementation guidance

- Prefer the smallest changes to existing HTML/CSS/JS and current Worker APIs.
- Add UI tests or lightweight browser checks for the changed interaction; do not introduce a new frontend framework without a demonstrated need.
- Verify loading, success, partial failure, full failure, retry, report expiry, and reload/reopen states with fixtures or mocked API responses.
- Perform one focused real-mobile-browser smoke test for Access login, submit, polling, results, and ZIP download when the environment is available. If real-device access is unavailable, mark that part BLOCKED while completing safe automated checks.

## Acceptance checklist

- [ ] Mobile layout shows job progress and results clearly.
- [ ] Counts and per-URL/per-item statuses match the API report.
- [ ] Error messages are actionable and secret-safe.
- [ ] Retry does not include successful targets/items.
- [ ] Double submit/reload does not create a duplicate job.
- [ ] ZIP ready/expired/unavailable state is clear and truthful.
- [ ] Cloudflare Access and private artifact protections remain intact.
- [ ] A focused mobile browser flow is documented, or the real-device portion is explicitly BLOCKED.

## Validation

Use existing test tooling and targeted browser checks. Run relevant regression checks after modifying shared APIs or dispatch behavior. Do not repeat the same manual mobile smoke test unless the relevant UI or auth flow changed.

## Required handoff

Report viewport/device or browser, tested flow, screenshots/logs if available without sensitive data, tests actually run, commit/deployment details if deployed, and any real-device limitation.
