# Priority 3 — Retry and Job Recovery

**Parent plan:** [MANUS_EXECUTION_PLAN.md](../MANUS_EXECUTION_PLAN.md)  
**Current status:** AUTOMATED MOCK EVIDENCE EXISTS / LIVE ACCEPTANCE NOT YET COMPLETE  
**Scope:** Job idempotency, target-level retry, reports, and Dashboard recovery after refresh/reopen.

## Existing evidence to preserve

The E2E report records automated mock coverage for retrying a failed MEGA target without re-sending successful Telegram work. Treat that as useful automated evidence, not proof of every production recovery path. Read the current implementation and tests before adding new state or changing APIs.

## Required investigation

1. Read the parent plan, `AGENTS.md`, `docs/AGENT_HANDOFF.md`, and current status/E2E reports.
2. Trace the job lifecycle through `POST /jobs`, idempotency key handling, GitHub Actions dispatch, target results, retry requests, report retrieval, and Dashboard browser persistence.
3. Determine how the dashboard distinguishes “resume/poll existing job” from “submit a new job”.
4. Inspect report artifact expiry/missing-artifact behavior and current target-success checkpoint semantics.

## Implementation requirements

- Retry only the targets/items whose prior result is confirmed failed or retryable.
- Never resend or re-upload a target already recorded as successful merely because another target failed.
- Keep server-side idempotency as the authority; client-side button disabling alone is insufficient.
- Refresh/reopen should restore the existing job ID and resume status/report polling where supported, without issuing a second dispatch.
- Missing/expired reports should produce a clear recovery message and must not silently submit a new job.
- Keep current privacy/security protections and existing dedupe checkpoints.
- Add focused tests for: one destination succeeds while another fails; retry selection; duplicate dispatch request; browser reload/reopen; missing/expired report.
- Avoid adding a database/queue unless a proven requirement cannot be met by the current architecture and is approved.

## Acceptance checklist

- [ ] Per-target state is correct and understandable.
- [ ] A partial-failure retry calls only the failed target(s).
- [ ] Successful targets produce no duplicate send/upload on retry.
- [ ] Reload/reopen resumes the existing job and does not dispatch another job.
- [ ] Expired or unavailable report handling is clear and safe.
- [ ] Relevant Worker/Python/dashboard tests pass.
- [ ] Any required live check is performed only with approved test destinations.

## Validation

Use deterministic unit/integration tests for idempotency and target retry. Use one focused browser test for reload/recovery when the dashboard can be accessed; avoid repeating identical manual checks after no relevant code change. Record the exact job ID/run URL and before/after target statuses when live testing is approved.

## Required handoff

Report job/target state before and after retry, whether any successful target was invoked again, browser recovery evidence, changed files/commit, tests actually run, and any blocked live scenario.

## Completeness audit additions — ambiguous outcomes and dispatch races

- Distinguish `failed` from `unknown/outcome-unconfirmed`. If a destination may have accepted an upload but the response or checkpoint was lost, reconcile remote state before retrying where the adapter supports it; do not blindly resend and do not claim exactly-once delivery.
- Verify concurrent duplicate `POST /jobs` requests with the same request ID/payload and conflicting payloads. Server-side behavior must be authoritative; document the actual guarantee and any remaining race rather than relying on disabled UI buttons.
- Define which state survives reload and where it lives. Do not store credentials or signed artifact URLs in browser storage; handle missing, stale, malformed, or unavailable local state without silently creating a new job.
- Test retry after timeout at three boundaries: before dispatch, after dispatch but before job ID is received, and after destination success but before success is persisted. Use mocks/fakes unless an approved test destination is available.
- Acceptance evidence must show the target invocation count before/after retry and identify any outcome that remains inherently ambiguous under the current architecture. Do not introduce a database/queue just to hide a documented limitation.
