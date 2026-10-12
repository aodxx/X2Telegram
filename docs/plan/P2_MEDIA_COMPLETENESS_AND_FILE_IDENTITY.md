# Priority 2 — Media Completeness and File Identity

**Parent plan:** [MANUS_EXECUTION_PLAN.md](../MANUS_EXECUTION_PLAN.md)  
**Current status:** PARTIAL EVIDENCE / IN PROGRESS  
**Scope:** URL batches, media enumeration, filenames, dedupe identity, destination writes, and output accounting.

## Known context

The repository documents a successful MEGA version-retention integration using two synthetic payloads and full SHA-256-based filenames ([PROJECT_STATUS.md](../PROJECT_STATUS.md), [E2E_TEST_REPORT.md](../E2E_TEST_REPORT.md)). That proves the tested storage scenario only; it does not prove every real X multi-URL or multi-media scenario is complete. The combined live run [#38037210973](https://github.com/aodxx/X2Telegram/actions/runs/38037210973) had one media item fail at source download before reaching destinations.

## Required investigation

1. Read the parent plan and handoff/status/E2E docs.
2. Trace the pipeline from submitted URLs → post/media enumeration → stable identity and filename → dedupe/checkpoint → destination adapter → per-item report.
3. Inspect how distinct media items in one post are represented and whether the identity/fingerprint includes enough data to distinguish them.
4. Review the prior MEGA filename-retention fix and tests; do not revert it or discard existing dedupe checkpoints.
5. Identify the actual multi-line URL regression reported by the owner. If its original input is not recorded, reproduce with a controlled fixture containing at least two distinct URLs/media items.

## Implementation requirements

- Every submitted URL must be accounted for independently in the job report.
- Every supported photo/video/media item must be represented separately in processing results.
- Distinct content must not overwrite older content because of a colliding filename or incomplete identity.
- True duplicate work must remain idempotent.
- Keep destination-specific paths scoped to the destinations selected by the user.
- Ensure partial failures do not cause successful files to disappear from the report or output.
- Add focused tests for multiple URLs, multiple media items, same post with changed content, filename collisions, and dedupe behavior.
- Use byte size and SHA-256 comparisons when practical; file count alone is not sufficient proof of content integrity.

## Acceptance checklist

- [ ] A batch with at least two distinct URLs processes and reports each URL.
- [ ] A multi-media post accounts for every supported media item.
- [ ] Distinct media versions remain distinct at the destination; older files remain available.
- [ ] Duplicate submissions do not create unintended duplicate side effects.
- [ ] Report counts match actual outputs; file sizes/hashes are checked for the chosen integration scenario.
- [ ] Live evidence is clearly labeled by destination and by synthetic-vs-real source.
- [ ] Existing MEGA retention/dedupe behavior has not regressed.

## Safe validation

Use unit/integration fixtures first. For a live destination test, use a dedicated test folder/chat and safe media. Before and after the run, compare the remote listing, file sizes, and downloaded bytes where possible. Do not test by overwriting or deleting a user's existing files.

## Required handoff

State the exact input count, expected media count, observed count, destination(s), size/hash evidence, test run URL, and any remaining limitation. Do not report “all files complete” when the source extraction or destination output count was not verified.
