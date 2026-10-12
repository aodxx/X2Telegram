# Priority 1 — X Source Download Reliability

**Parent plan:** [MANUS_EXECUTION_PLAN.md](../MANUS_EXECUTION_PLAN.md)  
**Current status:** NOT VERIFIED / IN PROGRESS  
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

- [ ] Root cause or reproducible source-level limitation is documented with evidence.
- [ ] The relevant URL now succeeds in a reproducible case, or gives a precise failure reason if the source is genuinely unavailable/unsupported.
- [ ] Multi-URL jobs preserve successful items when another URL fails.
- [ ] Reports are safe and actionable; no credentials or signed URL leakage.
- [ ] Targeted regression tests pass; relevant existing CI evidence is reused when code has not changed.
- [ ] `docs/PROJECT_STATUS.md` and `docs/E2E_TEST_REPORT.md` reflect only verified new evidence.

## Validation and live-test boundary

Run targeted tests first, then the relevant Python suite before finalizing a behavior change. Do not run a live destination upload just to diagnose source retrieval. If a live X URL is needed, use an owner-approved URL and avoid sending it to real destinations unless explicitly authorized.

## Required handoff

Report: confirmed cause; code/tests changed; commands actually run; CI/run URL; live evidence or why unavailable; remaining source limitations; next action. Do not claim all X URLs are supported because one URL passed.
