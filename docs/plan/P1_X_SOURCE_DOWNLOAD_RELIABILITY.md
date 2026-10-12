# Priority 1 — X Source Download Reliability

**Parent plan:** [MANUS_EXECUTION_PLAN.md](../MANUS_EXECUTION_PLAN.md)  
**Current status:** COMPLETE for source reliability and per-URL reporting — the deployed P1 fix passes a post-fix source-only live fetch of the historical failing URL; no destination was called during that verification.
**Scope:** Source retrieval, media parsing, per-URL outcomes, and actionable download errors. Do not redesign destinations or the control plane unless evidence shows they are the root cause.

## Why this is first

The current project status records real runs where one URL succeeds but another fails with `download_error` before any destination is reached (see [PROJECT_STATUS.md](../PROJECT_STATUS.md) and [E2E_TEST_REPORT.md](../E2E_TEST_REPORT.md)). The root cause must be confirmed from the current code and available run logs; the label alone is not a diagnosis.

## Required starting investigation

1. Read `AGENTS.md`, `docs/AGENT_HANDOFF.md`, `docs/PROJECT_STATUS.md`, and `docs/E2E_TEST_REPORT.md`.
2. Inspect the current downloader, X metadata/media extraction path, report/error serialization, and tests. Check `git status --short --branch` and recent commits before editing.
3. Trace the most relevant recorded failures, starting with Actions run [#38102121635](https://github.com/aodxx/X2Telegram/actions/runs/38102121635) and the failed URL in combined run [#38037210973](https://github.com/aodxx/X2Telegram/actions/runs/38037210973). If logs are no longer available, state that limitation and reproduce with a safe fixture before inferring a cause.
4. Record the exact failing stage and exception/category. Redact credentials, cookies, bearer tokens, and signed/private URLs from any saved logs.

## Implementation requirements

- Fix only confirmed causes; do not make broad speculative changes to X parsing.
- Preserve batch isolation: one URL failing must not erase or hide successful results from other URLs.
- Reports must identify the failed URL/item and stage with a useful, safe error category.
- Distinguish unsupported, unavailable/deleted/private source, timeout/network, parse/metadata, and media-download errors where the code can reliably know the difference.
- Keep secrets and sensitive request headers out of UI messages, artifacts, and logs.
- Add regression tests for the observed failure and a small set of directly related cases (for example redirect chain, timeout, malformed metadata, source HTTP failure). Use mocked/fixture tests when live source access is unnecessary.
- Avoid retry loops. If retrying transient failures, bound attempts and avoid repeating permanent failures.

## Acceptance checklist

- [x] Root cause or reproducible source-level limitation is documented with evidence.
- [x] The relevant URL now succeeds in a reproducible case, or gives a precise failure reason if the source is genuinely unavailable/unsupported.
- [x] Multi-URL jobs preserve successful items when another URL fails.
- [x] Reports are safe and actionable; no credentials or signed URL leakage.
- [x] Targeted regression tests pass; relevant existing CI evidence is reused when code has not changed.
- [x] `docs/PROJECT_STATUS.md` and `docs/E2E_TEST_REPORT.md` reflect only verified new evidence.

## Validation and live-test boundary

Run targeted tests first, then the relevant Python suite before finalizing a behavior change. Do not run a live destination upload just to diagnose source retrieval. If a live X URL is needed, use an owner-approved URL and avoid sending it to real destinations unless explicitly authorized.

## Required handoff

Report: confirmed cause; code/tests changed; commands actually run; CI/run URL; live evidence or why unavailable; remaining source limitations; next action. Do not claim all X URLs are supported because one URL passed.

## Completeness audit additions — input normalization and bounded recovery

- Normalize line endings (LF/CRLF), trim surrounding whitespace, and ignore blank lines without merging distinct URLs. Preserve the original submitted URL for user-facing identification while never exposing cookies, authorization headers, or signed query values in logs.
- Record an outcome for every submitted line: accepted, duplicate/normalized duplicate, rejected input, source metadata failure, media download failure, or success. Totals must reconcile to the submitted input count; explain explicitly how blank lines and duplicate URLs are counted.
- Classify errors as transient, permanent, or unknown only when evidence supports the classification. For transient network/HTTP failures, use bounded attempts with backoff and respect source rate limits; do not repeatedly retry private, deleted, unsupported, or malformed content.
- Add fixtures for CRLF/mixed newlines, blank lines, duplicate URLs, redirect loops/limits, timeout, rate-limit response (including Retry-After when present), malformed metadata, and one failing URL surrounded by successful URLs.
- Acceptance evidence must include input count, per-input outcome count, retry attempt count, and a sanitized error example. Do not include full private/signed URLs in saved reports.

## Verification record (2026-10-12; pre-release)

| Scenario | Expected / input | Observed | Destinations | Evidence | Remaining limitation |
|---|---:|---|---|---|---|
| Historical source failure, run [#38102121635](https://github.com/aodxx/X2Telegram/actions/runs/38102121635) | 1 URL, one video | Three direct MP4 variants had unknown sizes; chosen 2,176,000-bitrate candidate and the 950,000 candidate exceeded the 50 MB cap; the 632,000 candidate fetched and validated at 29,799,397 bytes | None; source-only | Sanitized fetch-only reproduction summarized above; no destination adapter called | The post-fix code has not been exercised against X again |
| Historical HLS failure, run [#38037210973](https://github.com/aodxx/X2Telegram/actions/runs/38037210973) | 2 URLs, 2 post results | First post reached all four destinations; second provider returned HLS playlists marked as MP4 and the direct downloader rejected the playlist; public fallbacks exposed direct MP4 variants | Historical live run: Telegram/MEGA/Dropbox/ZIP for first post; none for failed post | Sanitized report/log artifacts and source-only probe | Historical run predates this fix; no new destination upload was made |
| Bounded video-variant fallback | 1 URL, 3 candidates | Highest and middle candidates fail at the size cap; the lower candidate succeeds; exactly one Telegram send | Telegram mock | `tests/test_destinations.py::test_telegram_falls_back_to_lower_video_variant_when_size_is_unknown` | Synthetic downloader results; no live send |
| Batch isolation and input reconciliation | 5 nonblank URL tokens, 1 blank line | 3 accepted unique posts, 1 normalized duplicate, 1 rejected; 3 post results in original order (2 success, 1 source failure); partial-success retained; injected failure carries 2 reported HTTP attempts and 1 video variant attempt | Download-only mock | `tests/test_cli_inputs.py::test_cli_keeps_successes_around_failed_url_and_reconciles_inputs` | No live workflow dispatch; retry count is injected in this batch fixture and separately asserted with two mocked HTTP calls in downloader retry tests |
| HTTP/source/input edge cases | 429, timeout, 404, malformed JSON/authority, HLS, redirect loop, oversized response | Retries are bounded; numeric `Retry-After` is honored; 404 is not retried; malformed source data, IPv6 authority and media/redirect failures are safely classified/rejected; redirect loops stop after 6 requests; one empty provider cannot hide another provider's transient error; metadata redirects are same-host only; CLI passes `MAX_RETRIES` through | None; unit mocks | `tests/test_security_and_telegram.py`, `tests/test_metadata.py`, `tests/test_urls.py`, `tests/test_cli_inputs.py` | These specific error-edge cases remain mock-only; the direct-MP4 fallback behavior has the separate live row below |

| Post-fix live check of the historical failing URL | 1 owner-approved URL; one video identity, 3 direct MP4 variants | The previous highest/middle candidates exceed the standard 50 MB cap; bounded fallback fetched and validated the lower candidate at 29,799,397 bytes; SHA-256 `58e9b145e35229b9e02dff432bc680e357d065aaa438c55737c648f88166e589` | Source-only; no destination adapter invoked | Local fetch-only test on 2026-10-13; historical source context [#38102121635](https://github.com/aodxx/X2Telegram/actions/runs/38102121635), post ID `2108928241461551160` | One public post only; this does not imply every X post is supported |

**Release validation (deployed commit `8fb44274738d0c0090958f4b880189b0b93d17c7`):** local `pytest -q` — 129 passed; CI run [#38254729760](https://github.com/aodxx/X2Telegram/actions/runs/38254729760) — Python 129 and Worker 27 passed; synthetic MEGA integration [#38254729778](https://github.com/aodxx/X2Telegram/actions/runs/38254729778) and Pages [#38254729838](https://github.com/aodxx/X2Telegram/actions/runs/38254729838) passed; Worker deploy [#38263528272](https://github.com/aodxx/X2Telegram/actions/runs/38263528272) succeeded as version `e6bff44f-12e9-4a55-bfdb-c7b7cfb6587f`. Python compile, Node/inline dashboard JS syntax, workflow YAML parse, and `git diff --check` passed. Sanitized error example is `source_rate_limited` / HTTP 429; reports retain stage and attempt count but remove source URLs and query tokens. Subsequent P2 release is merged as commit `a5711e1`; main CI [#38288698022](https://github.com/aodxx/X2Telegram/actions/runs/38288698022) passed Python 134 and Worker 27, and isolated MEGA integration [#38288698061](https://github.com/aodxx/X2Telegram/actions/runs/38288698061) passed. **Remaining limitation:** only the documented source-only test was live-verified for P1; no destination send was made during P1 validation; do not infer support for all X URLs.
