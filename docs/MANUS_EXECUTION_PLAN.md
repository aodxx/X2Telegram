# X2Telegram — Manus Execution Plan (5 Priorities)

**Owner:** Repository owner  
**Implementation agent:** AI Manus  
**Oversight and acceptance:** ChatGPT  
**Repository:** `aodxx/X2Telegram`  
**Branch:** `main`  
**Status:** Active plan — execute in order; do not treat this document as evidence that a priority is already complete.

**Progress snapshot (2026-10-13):** Priority 1 and Priority 2 acceptance are complete. P1 source reliability is deployed and its historical failure URL passed source-only live verification; P2 was merged as main commit `a5711e1` (PR #23), with main CI [#38288698022](https://github.com/aodxx/X2Telegram/actions/runs/38288698022) and synthetic MEGA multi-item integration [#38288698061](https://github.com/aodxx/X2Telegram/actions/runs/38288698061) passing. The Cloudflare Worker remains on deployment commit `8fb4427` because P2 did not change Worker code. Continue with Priority 3; consult the detailed guides for scope and remaining evidence.

This is the overview and acceptance contract for the five agreed development priorities. Detailed implementation guides are stored in `docs/plan/`; Manus must read the matching guide before working on a priority. This lets work continue from repository documents without asking the user to paste long prompts.

## Detailed implementation guides (read these before coding)

1. [Priority 1 — X Source Download Reliability](plan/P1_X_SOURCE_DOWNLOAD_RELIABILITY.md)
2. [Priority 2 — Media Completeness and File Identity](plan/P2_MEDIA_COMPLETENESS_AND_FILE_IDENTITY.md)
3. [Priority 3 — Retry and Job Recovery](plan/P3_RETRY_AND_JOB_RECOVERY.md)
4. [Priority 4 — Large-File Telegram and Dropbox](plan/P4_LARGE_FILE_TELEGRAM_AND_DROPBOX.md)
5. [Priority 5 — Mobile Dashboard UX](plan/P5_MOBILE_DASHBOARD_UX.md)

`AGENTS.md` now points agents to these files as required reading. The existence of these plans is not evidence that implementation or acceptance testing is complete.

## Mission and working rules

Improve the existing X2Telegram system in place. The intended flow remains:

```text
Dashboard → Cloudflare Access → Cloudflare Worker → GitHub Actions → downloader → Telegram / MEGA / Dropbox / Browser ZIP
```

1. **Implement, do not stop at a plan.** Inspect the current code and evidence, make the smallest useful change, validate it, and update the status documents. If blocked, finish independent work that does not require the missing dependency.
2. **Work in priority order.** Start with Priority 1. Move to the next priority after the current one meets its acceptance criteria, or document a specific external blocker and continue with work that can safely proceed.
3. **Avoid unnecessary repeated testing.** Read existing test reports and recent successful CI runs first. Reuse evidence when the relevant code has not changed. After a change, run the smallest targeted tests that prove it, plus relevant regression checks. Run the full suite before a commit/release when changes could affect shared behavior; do not rerun an unchanged full suite merely to repeat a result.
4. **Keep scope tight.** Do not redesign the architecture, introduce a database/queue, recreate Google Apps Script, rotate secrets, alter production chat IDs, weaken Cloudflare Access, or add infrastructure unless the identified root cause genuinely requires it and the reason is documented.
5. **Protect real destinations.** Never run an uncontrolled live test that could spam a production Telegram chat, overwrite/delete user files, or create costly/large uploads. Use a confirmed test destination and synthetic fixtures for live tests. Do not guess credentials or test chat IDs.
6. **Never confuse tests with proof of a live outcome.** Clearly distinguish unit/mock coverage, CI results, and real integration evidence. Do not claim production readiness or 100% completion without evidence for the relevant scenario.
7. **Preserve user data and deduplication.** Do not discard existing dedupe fingerprints/checkpoints or replace distinct media with a shared filename. Retries must not duplicate targets that already succeeded.
8. **Keep the user informed concisely.** Report what changed, what evidence was checked, what remains blocked, and the next concrete action. Do not give repeated progress narration without new evidence.
9. **Review before changing.** Start by checking `git status --short --branch`, `git log -3 --oneline`, `AGENTS.md` (if present), this plan, `docs/AGENT_HANDOFF.md`, `docs/PROJECT_STATUS.md`, and `docs/E2E_TEST_REPORT.md`. Confirm the current branch/head before editing. Do not overwrite unrelated user changes.
10. **Keep documentation truthful.** Update `docs/AGENT_HANDOFF.md`, `docs/PROJECT_STATUS.md`, and `docs/E2E_TEST_REPORT.md` only where new evidence changes them. Add run URLs/commit SHAs and test scope, but never put tokens, secrets, or private credentials in logs/docs.

## Priority 1 — Correct X/source downloading and useful per-URL errors

### Goal
A submitted URL should either download the expected media or fail with an actionable, URL-specific explanation. One bad URL must not silently hide the results of other URLs in the same batch.

### Work
- Inspect recent `download_error` examples, the downloader path, existing logs/reports, and the relevant code before changing anything.
- Identify the actual failure causes (for example redirects, source response changes, timeouts, unsupported/private/deleted content, or parsing failures); do not guess from the error label alone.
- Fix the smallest confirmed root cause(s). Preserve current supported sources and avoid broad rewrites.
- Make errors identify the failed URL/item and stage, without leaking cookies, tokens, signed URLs, or other secrets.
- Ensure batch processing reports each URL independently and continues safely when one URL fails.
- Add or adjust targeted regression tests for the observed cause and important nearby cases. Use mocks/fixtures for source failures where live access is not necessary.

### Acceptance criteria
- The root cause of the targeted failure is recorded with evidence.
- The affected URL succeeds in a reproducible test when the source is expected to work, or produces a clear and accurate failure reason when the source itself is unavailable/unsupported.
- A failing URL does not erase successful results for other URLs.
- Reports identify success/failure per URL without exposing secrets.
- Relevant tests pass; no known regression is introduced.

**Live validation:** Use a live source only when safe and necessary. Do not claim all X URLs are supported based on one URL or mocked tests.

## Priority 2 — File completeness, identity, and no unintended overwrites

### Goal
Multiple submitted URLs and posts with multiple media items must produce all expected distinct files. A new download must not overwrite or make an older distinct file disappear.

### Work
- Trace the full path from URL/post parsing through media enumeration, filenames, deduplication, and each destination adapter.
- Treat different media items or different versions as distinct unless there is evidence they are truly duplicates.
- Check MEGA filename/version-retention behavior and the reported multi-line URL case in particular; do not assume an earlier synthetic test proves every real scenario.
- Check Dropbox, Telegram, and Browser ZIP only where the shared code or changed behavior makes that relevant.
- Add focused tests for multiple URLs, multiple photos/media items, filename collisions, and distinct content with similar metadata. Verify file count, byte size, and hashes where practical.
- For live destination verification, use a test folder/chat and synthetic or explicitly approved test media. Confirm remote file count and contents rather than relying only on a “success” status.

### Acceptance criteria
- A batch of multiple URLs processes each URL, not just the first.
- Every expected media item is accounted for in the report and output.
- Distinct files do not overwrite one another or disappear because of naming/dedupe collisions.
- True duplicate handling remains idempotent.
- Evidence states exactly which destinations and scenarios were tested; synthetic evidence is labeled as synthetic.

## Priority 3 — Partial-failure retry and recovery without duplicate delivery

### Goal
When one destination fails after another succeeds, the user can recover the job without repeating successful deliveries. Refreshing or reopening the dashboard must not accidentally dispatch a duplicate job.

### Work
- Review current job idempotency, target-level result state, retry API/worker path, report artifacts, and dashboard recovery logic before adding new state.
- Test the case where one target succeeds and another fails. Retry only the failed target(s).
- Verify that an already-successful Telegram/MEGA/Dropbox target is not sent/uploaded again during retry.
- Verify dashboard reload/reopen restores the recent job from the existing persistence mechanism, continues polling, and retrieves the status/report where available.
- Handle expired/missing reports with a clear message and safe recovery behavior. Do not create a duplicate job merely because the browser reloaded.
- Add focused regression coverage for partial success, retry selection, idempotency, and reload/recovery.

### Acceptance criteria
- Target-level success/failure is visible and accurate.
- Retry executes only failed targets/items, with no duplicate success-side effects.
- Reload/reopen recovers the existing job where supported and does not dispatch another job.
- The behavior is demonstrated by relevant tests and, when safe test destinations are available, a live run.

## Priority 4 — Large-file delivery and token-refresh integration

### Goal
Prove the supported large-file paths work in real conditions, not only in unit tests.

### Track A: Telegram Local Bot API (>50 MB)
- Confirm a dedicated Telegram test chat and explicit authorization before sending anything.
- Use a synthetic file larger than 50 MB and no larger than the supported 2,000 MB limit.
- Verify the Local Bot API server is ready, the workflow selects large-file mode, the upload succeeds through the intended API path, and the report shows correct status and size.
- Confirm retries do not duplicate the send.
- If there is no confirmed test chat or suitable environment, mark this live check **blocked** and proceed with other work. Do not use or change the production chat as a workaround.

### Track B: Dropbox refresh and large-file upload session
- Use the existing Dropbox test folder/account and avoid changing secrets unless a confirmed configuration problem requires it.
- Verify refresh-token-only operation when an access token is absent/expired, and verify the upload-session path for a large file.
- Confirm the remote file exists and its byte size/content is correct; record the relevant run URL and clean up test artifacts according to the agreed policy.
- Distinguish prior evidence (such as one successful normal media upload) from proof of refresh-token and large-file behavior.

### Acceptance criteria
- Each track is marked **passed**, **failed**, or **blocked** with a reason and evidence.
- Do not mark either track passed based solely on automated tests.
- Do not block unrelated priorities just because a live credential or test destination is unavailable.

## Priority 5 — Mobile dashboard clarity and safe operation

### Goal
On a real mobile browser, the user can submit work and understand progress, errors, retries, and ZIP availability without accidental duplicate jobs.

### Work
- Inspect the existing dashboard and reuse current APIs/state wherever practical.
- Make progress and outcomes clear: total URLs/items, success/failure counts, per-URL or per-item status, and actionable error details.
- Provide a clear retry path for failed work only, consistent with Priority 3.
- Show Browser ZIP status/availability/expiry or a useful explanation when the artifact is unavailable.
- Ensure submit controls show the job state and prevent accidental double-submit while preserving server-side idempotency.
- Verify the dashboard remains usable on a real mobile browser at the supported viewport, including Access login, submit, polling, report viewing, and ZIP download. Use automated/browser checks for iteration; perform one focused real-device smoke test when available instead of repeatedly repeating the same manual steps.

### Acceptance criteria
- The main mobile workflow completes from login through status/result review for the supported scenario.
- Progress, failures, retry availability, and ZIP state are understandable without reading developer logs.
- Reload/reopen does not submit a duplicate job.
- No security boundary is weakened to simplify the UI.

## Shared definition of done

A priority may be marked **DONE** only when:
- The stated goal and acceptance criteria are met for the declared scope.
- Relevant code/diff has been reviewed.
- Appropriate validation passed and its exact scope is recorded.
- Required live evidence exists for any criterion that specifically requires a real integration.
- No known blocker or contradictory failure is hidden.
- Status and handoff documentation reflect the evidence.

Use these statuses:
- **DONE** — acceptance criteria met with evidence.
- **PARTIAL** — some criteria met; remaining work is explicit.
- **BLOCKED** — progress requires a specific external prerequisite; unrelated work should continue.
- **FAILED** — the attempted implementation/validation did not meet the criteria and needs a targeted correction.

## Efficient validation policy

Before running tests, inspect recent CI results and the current reports. Choose tests based on changed files and risk:
- Python downloader/processor changes: targeted pytest cases first; run the full Python suite before finalizing a meaningful change.
- Worker/dashboard/API changes: targeted Worker tests and relevant dashboard checks; run the Worker suite before finalizing shared-path changes.
- Workflow/security changes: validate the changed workflow and permissions/immutable refs, plus affected tests.
- Before a release/commit with broad impact, use the repository's documented checks as applicable:
  ```bash
  python3 -m pytest -q
  npm test --prefix control-worker
  python3 -m compileall -q src tests
  node --check control-worker/src/index.js
  git diff --check
  ```
Do not claim a command passed unless it was actually run and its result was observed. If a test is unchanged and recent CI already proves the same commit/code path, cite that run rather than rerunning it without cause.

## Required handoff after each work session

Keep this concise and evidence-based:

- **Current priority/status:**
- **Root cause or change:**
- **Files/commit:**
- **Validation actually run:** (commands, counts, CI run URL)
- **Live evidence:** (destination/scenario/result, or why blocked)
- **Known limitations/blockers:**
- **Next concrete action:**

Always continue from the latest repository state. Do not make the user paste this plan into a chat. If Manus cannot read repository files automatically, tell the user the specific access issue instead of asking them to copy the entire document.

## First action for Manus

1. Read this plan and the current `docs/AGENT_HANDOFF.md`, `docs/PROJECT_STATUS.md`, and `docs/E2E_TEST_REPORT.md`.
2. Inspect the current branch/head, recent commits, working tree, and latest relevant GitHub Actions results.
3. Map the existing evidence/code to Priority 1 acceptance criteria; state the confirmed root cause and then implement the smallest justified fix.
4. Continue in priority order. Do not return only a plan or a test checklist.

## Cross-priority acceptance additions from completeness audit

Before declaring any priority complete, record a compact evidence matrix with: scenario, input/expected count, observed result, destinations involved, test type (unit/mock/CI/live), evidence URL or artifact, and remaining limitation. Do not use a percentage-complete estimate as a substitute for acceptance evidence.

- Reconcile expected and observed counts at every boundary relevant to the priority; explain every missing, skipped, duplicate, or unverified item.
- Distinguish confirmed failure from unknown outcome. Where a remote side effect may have happened but cannot be confirmed, reconcile before retrying when possible and state the remaining exactly-once limitation.
- Keep one current source of truth for production commit/version/run. If status documents disagree, verify the actual latest successful deployment run and update the conflicting document(s) rather than copying old values forward.
- Map each change to its regression test and only rerun the relevant tests after changes; reuse prior CI evidence only when the tested code and configuration are unchanged.
- The priority numbers in `docs/AGENT_HANDOFF.md` describe an operational backlog and may group live-validation blockers differently. The five-step implementation order in this plan is authoritative for Manus unless a concrete blocker is recorded with evidence.
