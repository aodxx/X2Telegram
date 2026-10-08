# Cloudflare Control Worker — Zone 3

## สถานะปัจจุบัน (2026-10-09)

- Worker `x2telegram-control-plane` deploy แล้วที่ <https://x2telegram-control-plane.pantipa3826.workers.dev>
- Cloudflare Access ครอบ hostname นี้และบังคับ owner-only email OTP (ดู [`CLOUDFLARE_ACCESS.md`](CLOUDFLARE_ACCESS.md))
- Worker secret `ACCESS_ALLOWED_EMAIL` ถูกตั้งใน Cloudflare Secret Store; ไม่อยู่ใน source, Dashboard หรือ Git
- `GH_TOKEN` ถูกตั้งเป็น Worker secret ชนิด `secret_text`; authenticated `GET /health` และ read-only job lookup ผ่าน. Normal-path E2E run #37807253687 dispatch สำเร็จและ report ยืนยันส่งหนึ่ง MP4 (message ID 347); รายละเอียดใน [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md)
- Worker source รุ่น security hardening deploy แล้ว; cross-origin `GET /health` จาก Pages ได้ `200`, invalid URL ถูกปฏิเสธ `400 invalid_url`, และ oversized body 17 KiB ได้ `413 request_too_large` ก่อน live E2E run ที่บันทึกไว้ด้านบน
- Normal-path E2E ผ่านหนึ่งรายการบน migration branch; Worker ถูกคืน `GH_REF=main` แล้ว. รายงาน: [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md)
- PR #4 merged; Pages deploy run `37816537609` ผ่าน และ Worker version `9641c2a5-eda8-4eef-b7ba-6667461de2d3` deploy แล้ว. Dashboard เสิร์ฟ assets/API จาก Access-protected origin เดียวกัน, `/auth/check` ผ่าน browser session จริง และ batch submit รองรับสูงสุด 50 URL
- Live batch run `37816856323` สำเร็จสำหรับ 2 URLs; ทั้งคู่ถูกข้ามด้วย completed dedupe state (`sent=0`, `skipped_duplicate=2`, `failed=0`), จึงไม่มี Telegram send ซ้ำ. ยังไม่ใช่การทดสอบ fresh multi-post media delivery
- GitHub Actions manual flow เดิมบน `main` ยังเป็นทางเลือกใช้งานได้

## Architecture

```text
GitHub Pages redirect → Cloudflare Access + Worker-hosted Dashboard/API → GitHub Actions → Python worker → Telegram
```

Worker ให้บริการ Dashboard static assets จาก `../web` และ API บน origin เดียวกัน; `run_worker_first=true` ทำให้ Worker ตรวจ Access JWT ก่อนเรียก `env.ASSETS.fetch(request)`. Worker ไม่ดาวน์โหลด media ไม่ส่ง Telegram และไม่มี database/Redis/queue. `fflate` ใช้แตก ZIP ของ GitHub Actions report artifact เพื่อคืนเฉพาะ sanitized dashboard report

## Configuration

`wrangler.toml` มี non-secret variables:

- `GH_OWNER=aodxx`
- `GH_REPO=X2Telegram`
- `GH_WORKFLOW_ID=x2telegram.yml`
- `GH_REF=main`
- `DASHBOARD_ORIGIN=https://x2telegram-control-plane.pantipa3826.workers.dev`
- `ACCESS_TEAM_DOMAIN=https://falling-sky-a8ee.cloudflareaccess.com`
- `ACCESS_AUD` — audience ของ Access app ที่ตั้งไว้ใน config

Cloudflare Worker Secrets:

- `ACCESS_ALLOWED_EMAIL` — ตั้งไว้แล้ว; ใช้ตรวจ identity ซ้ำหลัง validate Access JWT
- `GH_TOKEN` — ตั้งเป็น `secret_text`; ใช้สำหรับ dispatch workflow และอ่าน workflow run/report ใน repository นี้

ห้ามใช้ GitHub CLI app user token (`ghu_…`) เป็น `GH_TOKEN`: token ของ integration เป็น credential สำหรับ session ชั่วคราว ไม่ใช่ secret ระยะยาวสำหรับ Worker. อย่าพิมพ์ token ลง chat หรือ commit ลง Git. เมื่อมี fine-grained PAT ให้เพิ่มผ่าน Cloudflare Worker secret prompt:

```bash
cd control-worker
npx wrangler secret put GH_TOKEN --name x2telegram-control-plane
```

หลังตั้ง secrets ให้รัน local tests และ deploy Worker ตามขั้นตอนของ Wrangler; ใช้ live E2E test matrix ใน [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md) เพื่อยืนยันฟังก์ชันที่เกี่ยวข้อง

## Endpoints

| Method/path | Authentication | Behavior |
|---|---|---|
| `GET /health` | Cloudflare Access ที่ edge | คืน service/status โดยไม่เปิดเผย credential หรือสถานะ upstream |
| `GET /auth/check` | Cloudflare Access JWT | ตรวจ session จริงก่อน Dashboard เปิดปุ่มส่ง |
| `POST /jobs` | Cloudflare Access JWT | รับ `url` เดี่ยวหรือ `urls` array 1–50; validate ทุก URL, duplicate, origin, schema, body size และ request ID; ตรวจ run เดิม; dispatch GitHub Actions |
| `GET /jobs/<job_id>` | Cloudflare Access JWT | ค้น run จาก workflow title, คืนสถานะและ sanitized artifact |
| `OPTIONS *` | CORS preflight | รับเฉพาะ Dashboard origin; Access application ตอบ preflight ด้วย CORS headers ที่กำหนด |

Worker ตรวจ Access JWT signature RS256 กับ Cloudflare Access JWKS, issuer, audience, `exp`/`nbf`, และ email allowlist. GitHub token อยู่ใน Worker secret เท่านั้น. GitHub errors ถูก sanitize; request body จำกัด 16 KiB โดยอ่าน stream แบบมี hard cap และตอบ `413` เมื่อเกิน; response ใช้ `Cache-Control: no-store`; CORS ไม่ใช้ wildcard

## Dispatch / idempotency / workflow interface

เมื่อได้รับ POST Worker normalize URL list, คำนวณ opaque `job_id` จาก `request_id + ordered normalized URL list + large_file_mode` และค้น run ที่ตรงกับ workflow title `X2Telegram <request_id> <job_id>`. run เดิมถูกคืนแทนการ dispatch ซ้ำ; payload ต่างที่ใช้ request ID ซ้ำแต่พบ run ที่ต่าง job fingerprint จะได้ `409 idempotency_conflict`.

Dashboard Worker ส่ง workflow input `url` เมื่อมีรายการเดียว หรือ `urls` newline-separated เมื่อเป็น batch; ไม่ส่งสองฟิลด์พร้อมกัน. Manual workflow ยังคงรองรับ `urls`. Worker tests ครอบ batch 1–50, duplicate URL rejection และ max-count enforcement; Python `state/dedupe.json` version 2 บันทึก SHA-256 content fingerprint และ Telegram message ID แยกราย media; อ่าน state version 1 ได้และยัง skip completed post เดิม. Downloader ตรวจทุก redirect hop กับ HTTPS/X-media allowlist ก่อนตามต่อ

เพราะไม่ใช้ durable store, สอง POST ที่มี request ID/payload เดียวกันพร้อมกันก่อน GitHub API แสดง run อาจ dispatch สอง workflow runs. Workflow concurrency และ per-media state ลดการส่งซ้ำ; ยังรับประกัน exactly-once ไม่ได้หาก Telegram รับ media แล้ว response หายก่อน checkpoint ถูก persist

## Local tests

```bash
npm ci --prefix control-worker
npm test --prefix control-worker
```

Unit tests mock GitHub/JWKS; ครอบคลุม unauthenticated, denied identity, invalid/malformed/oversized body, per-isolate rate cap, dispatch mapping, duplicate/conflict, GitHub failure, status/artifact, CORS. Tests ไม่เรียก GitHub จริง, ไม่ dispatch workflow และไม่ส่ง Telegram. Python tests ยังครอบ token redaction, validated redirects และ partial-media retry

## ผลตรวจสอบและขั้นตอนต่อไป

1. Deployment, owner Access session check, 1–50 URL UI และ live 2-URL dispatch/no-resend ผ่านแล้ว
2. ทำ scenarios ที่ยังเหลือตาม [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md): fresh multi-post delivery, multi-photo, partial-failure recovery, large-file, refresh และ mobile
3. พิจารณา Zone 6 (ลบ GAS) หลังทบทวน migration/E2E coverage; ปัจจุบัน `gas/` เป็น legacy/reference และ Dashboard ไม่เรียกใช้
