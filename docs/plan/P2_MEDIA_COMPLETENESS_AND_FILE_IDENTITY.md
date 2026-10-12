# Priority 2 — Media Completeness and File Identity

**Parent plan:** [MANUS_EXECUTION_PLAN.md](../MANUS_EXECUTION_PLAN.md)  
**Current status:** PARTIAL EVIDENCE / IN PROGRESS  
**Scope:** URL batches, media enumeration, filenames, dedupe identity, destination writes, and output accounting.

## Local implementation evidence (2026-10-12)

| Scenario | Expected / input | Observed | Destination | Evidence | Remaining limitation |
|---|---|---|---|---|---|
| Two video media items in one post, each with two bitrate variants | 1 synthetic post, 2 media identities, 4 variants → 2 files | Best variant selected independently per media identity; report items carry `media_index` 1 and 2; exported bytes match the selected fixture URLs | Download-only mock | `tests/test_destinations.py::test_post_with_two_video_media_items_downloads_best_variant_for_each` | No live X multi-video source or remote destination verification |
| Metadata identity normalization | 2 videos × 2 variants; yt-dlp single-video formats | Syndication keeps one index per media item; yt-dlp formats share the single item's index | Metadata unit tests | `tests/test_metadata.py::test_syndication_assigns_one_media_index_to_each_video_and_its_variants`, `test_ytdlp_assigns_same_media_index_to_all_video_formats` | Provider payloads are fixtures, not live X responses |

Python validation on the working tree: targeted media/metadata tests **43 passed**; full suite **132 passed**. This is automated evidence only and does not complete the P2 live-source/destination acceptance criteria.

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

## Completeness audit additions — expected-versus-observed manifest

- Build an explicit per-job manifest from the submitted URLs and enumerated supported media items before destination delivery. Track each item through extraction, local validation, and each selected destination; make skipped/unsupported items explicit rather than silently omitting them.
- Keep separate concepts separate: source/post identity, media-item identity, and content SHA-256. Use content hash to verify bytes and avoid collisions, but do not use a post-level identifier alone as the identity for every photo/video in a post.
- Reconcile expected item count against downloaded/validated count and each destination's verified count. A destination success flag alone is insufficient if the remote object cannot be found or its size does not match.
- Define and test duplicate policy explicitly: same submitted URL, same source item/content, and different content under a reused filename are different cases. Distinct content must remain available; true duplicates may be skipped idempotently.
- Test interrupted/failed uploads and name collisions without deleting old content. Where supported, verify remote size and SHA-256 by downloading back; otherwise state exactly which weaker evidence was used.
- Acceptance report must include a reconciliation table or equivalent: submitted URLs → discovered items → validated local files → expected destination writes → verified destination objects, with explanations for every difference.
