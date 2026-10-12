# Priority 2 — Media Completeness and File Identity

**Parent plan:** [MANUS_EXECUTION_PLAN.md](../MANUS_EXECUTION_PLAN.md)  
**Current status:** COMPLETE — merged via PR #23 as main commit `a5711e1`; main CI and isolated live MEGA multi-item verification passed. This release changes Python processing/reporting, not the Cloudflare Worker, so no Worker deployment was required.
**Scope:** URL batches, media enumeration, filenames, dedupe identity, destination writes, and output accounting.

## Implementation and verification evidence (2026-10-13)

| Scenario | Expected / input | Observed | Destination | Evidence | Remaining limitation |
|---|---:|---|---|---|---|
| Two video media items in one post, each with two bitrate variants | 1 synthetic post, 2 media identities, 4 variants → 2 files | Best variant selected independently; two local files match expected bytes, sizes, and SHA-256; manifest/reconciliation report 2 expected, 2 validated, 2 ready, 0 unaccounted | Download-only mock | `tests/test_destinations.py::test_post_with_two_video_media_items_downloads_best_variant_for_each` | Fixture source; remote confirmation is separate |
| yt-dlp playlist entries | 2 entries × 2 variants → 2 identities | Parser no longer discards all but the first entry; each entry's formats share one identity | Metadata unit test | `tests/test_metadata.py::test_ytdlp_preserves_distinct_media_entries_and_groups_each_entries_variants` | Fixture payload; live test below covers a mixed photo/video post |
| Real public multi-media source | 1 owner-used URL; 4 metadata entries (1 photo + 3 video variants) → 2 distinct media items | Download-only process exported exactly 2 files: 79,517 bytes / SHA-256 `e309f9c18a4b55322afd56312b7ac6a66f5c5769cd3d3de476105f835422a84a` and 2,797,748 bytes / SHA-256 `551ceed75acef2aadccf7f7c2f98d62eece4e304e8c0fa1f55f81adeeba3b8f5`; report expected 2, validated 2, ready 2 | Live X source → local temporary Download-only; temp files removed | Source-only run 2026-10-13 against owner-used post ID `2108081184366604583`; prior workflow report run [#38160545553](https://github.com/aodxx/X2Telegram/actions/runs/38160545553) enumerated 2 Dropbox items | The live probe did not write to any remote destination; historical run conclusion was failure, so it is not treated as successful remote proof |
| Remote output integrity and idempotency | 2 synthetic video identities × 2 variants; change content for item 1 and repeat item 2 | **3 remote files verified** by listing and download-back bytes/SHA-256: 48 bytes / `28bb4d1ed69295fe0420a9dceeddbde67dd3a1e6c8c20ae934f3875cfc480e5`; 55 bytes / `bf01bc3d3c7955fb6ecce615318203455cb195056d2a342cf59fe86af15987fd`; changed item 64 bytes / `2f6737d7eceba40bc742996a8b049e4ab883652be42decaf1971f2d6406a68bf`. Pass asserted initial 2 uploads, changed content new filename, unchanged item duplicate, 0 unaccounted. Run-folder cleanup confirmed by workflow success. | MEGA synthetic integration; no X-sourced file uploaded | PR runs [#38288011489](https://github.com/aodxx/X2Telegram/actions/runs/38288011489) and [#38288024709](https://github.com/aodxx/X2Telegram/actions/runs/38288024709); main run [#38288698061](https://github.com/aodxx/X2Telegram/actions/runs/38288698061), main commit `a5711e1` | Synthetic payloads validate the integration path; only one real X mixed-media source was source-tested |

Python validation: targeted destination/metadata/report tests **54 passed**; full suite **134 passed**; Worker **27 passed**; Python compile, workflow YAML and embedded bash/Python syntax, internal links, and `git diff --check` passed. PR Automated Tests [#38287966939](https://github.com/aodxx/X2Telegram/actions/runs/38287966939) and main CI [#38288698022](https://github.com/aodxx/X2Telegram/actions/runs/38288698022) passed. The media manifest tracks each enumerated item, local size/SHA-256, and per-selected-destination outcome; metadata failures and legacy pre-enumeration duplicates are explicitly marked as not enumerated rather than claiming zero expected items. The API sanitizer allowlists the new fields and drops URLs/paths. P2 is complete on main commit `a5711e1`.

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

- [x] A batch with at least two distinct URLs processes and reports each URL.
- [x] A multi-media post accounts for every supported media item.
- [x] Distinct media versions remain distinct at the destination; older files remain available.
- [x] Duplicate submissions do not create unintended duplicate side effects.
- [x] Report counts match actual outputs; file sizes/hashes are checked for the chosen integration scenario.
- [x] Live evidence is clearly labeled by destination and by synthetic-vs-real source.
- [x] Existing MEGA retention/dedupe behavior has not regressed.

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
