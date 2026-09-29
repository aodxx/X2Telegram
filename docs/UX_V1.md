# X2Telegram UX v1

## Goal
Design the real user flow before Milestone 2. The user should be able to paste many X post URLs in one batch, review what will be processed, start a run, watch per-post progress, and inspect the final result.

## Primary flow
1. Paste one or more X URLs, one URL per line.
2. The UI counts valid/duplicate/invalid URLs.
3. Review the batch before starting.
4. Start the GitHub Actions job.
5. Show each post independently as queued, checking, downloading, sent, or failed.
6. Show a final summary with success/no-media/unavailable/error counts.
7. Keep settings separate from the main workflow.

## Main screens
- Dashboard: batch input + recent run summary.
- Review: parsed posts and detected media type/count.
- Running: per-post progress.
- Complete: summary and expandable details.
- Settings: Telegram destination and optional advanced controls.

## UX rules
- Mobile-first.
- One primary action per screen.
- Never require editing YAML for normal use.
- One failed post must not stop other posts.
- Do not expose Telegram secrets in the browser.
- Query strings such as ?s=20 are accepted.
- Status names are human-readable but map to backend states:
  - Sent
  - No media
  - Unavailable
  - Metadata error
  - Download error
  - Telegram error
  - Skipped

## Milestone relationship
This UX is intentionally designed around the next metadata stage. The Review screen will eventually be populated by the metadata provider without downloading media first.

## Prototype
See `web/index.html`. It is a front-end prototype only; it does not yet trigger GitHub Actions or access Telegram.
