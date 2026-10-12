# Priority 3 — Retry and Job Recovery

**Parent plan:** [MANUS_EXECUTION_PLAN.md](../MANUS_EXECUTION_PLAN.md)  
**Current status:** PARTIAL — merged via PR [#24](https://github.com/aodxx/X2Telegram/pull/24) as main commit `9e9e9f8`; main CI [#38293276028](https://github.com/aodxx/X2Telegram/actions/runs/38293276028), Pages [#38293276008](https://github.com/aodxx/X2Telegram/actions/runs/38293276008), and Worker deploy [#38293345118](https://github.com/aodxx/X2Telegram/actions/runs/38293345118) passed. Production Worker version is `f2e1afaf-db8e-4356-be75-215f60eb53e5`. No live destination was invoked; residual idempotency/checkpoint limits below remain.
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

- [x] Per-target state is correct and understandable; `outcome_unconfirmed` is distinct from confirmed failure.
- [x] Retry submits only targets containing confirmed failed items; successful and outcome-unconfirmed targets are excluded by Dashboard selection.
- [x] Python checkpoint regression proves successful Telegram is not invoked again when retrying a failed MEGA target.
- [x] Reload/reopen uses lookup-only recovery, resumes polling when found, and does not dispatch when no run is visible.
- [x] Missing, expired, and temporarily unavailable reports have distinct Worker states and safe Dashboard messages.
- [x] Relevant local automated validation passed: Python 143 tests; Worker/Dashboard harness 40 tests.
- [x] No live check was run: this task has no explicitly approved test chat/folder for new destination retries; no external destination was invoked.

## Validation

Use deterministic unit/integration tests for idempotency and target retry. Use one focused browser test for reload/recovery when the dashboard can be accessed; avoid repeating identical manual checks after no relevant code change. Record the exact job ID/run URL and before/after target statuses when live testing is approved.

## Required handoff

Report job/target state before and after retry, whether any successful target was invoked again, browser recovery evidence, changed files/commit, tests actually run, and any blocked live scenario.

## Completeness audit outcomes — ambiguous outcomes and dispatch races

- `failed` is distinct from `outcome_unconfirmed`. Telegram send timeouts/non-JSON/5xx, Dropbox upload transport timeout/5xx, and MEGA upload/remote-verification uncertainty are checkpointed as unconfirmed and excluded from automatic retry. Regression coverage includes MEGA timeout during remote read-back after `mega-put` returned success.
- A failed MEGA target retry invokes MEGA once and leaves successful Telegram invocation count at 1 (before/after); the Python test asserts exact adapter call counts. Browser harness asserts retry payload contains only confirmed failed targets and excludes `success` and `outcome_unconfirmed` targets.
- The Worker now single-flights identical `request_id` submissions inside one isolate, rejects an in-flight conflicting payload with HTTP 409, and retains an accepted outcome for 30 seconds to cover GitHub run-list visibility delay. Deterministic concurrent tests assert one dispatch for identical payloads and one dispatch plus one 409 for conflicting payloads.
- **Remaining idempotency limit:** this reservation is isolate-local and ephemeral. It is not a global/durable lock across Cloudflare isolates, isolate restarts, or requests after its 30-second window. GitHub run lookup remains the durable practical dedupe signal once the run is visible. Exactly-once dispatch/delivery is not claimed; a narrow cross-isolate visibility race remains without a durable coordination service.
- Browser state remains in localStorage and contains job/request IDs and user-selected inputs only; credentials and signed artifact URLs are not stored. Reload/reopen uses `POST /jobs/recover` (lookup only); a not-found response stays locked for explicit user action and never auto-submits a new job. Missing/expired/unavailable report states remain distinguishable.
- Timeout boundaries are covered by deterministic mocks/fakes, including failed dispatch sanitization, in-flight request races, destination timeout classification, persisted unconfirmed checkpoints, and retry without resending success. No real destination was called because no new approved test target was provided.
- A failure-injection test simulates confirmed Telegram success followed by failed checkpoint persistence: the report carries `dedupe_checkpoint_failed`, but a later manually-created full-target job can resend because no durable success record exists. Dashboard's failed-only retry excludes that reported-success target, but no exactly-once guarantee is possible when checkpoint storage fails and the user creates a new full job.
- No database/queue was added. CI, Pages publish, and Worker deployment passed. This is production code, but no live destination retry was performed and the documented residual limits prevent an exactly-once claim.
