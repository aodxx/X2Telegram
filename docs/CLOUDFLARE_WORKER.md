# Cloudflare Control Worker — Zone 3

## สถานะปัจจุบัน (2026-10-08)

- Worker `x2telegram-control-plane` deploy แล้วที่ <https://x2telegram-control-plane.pantipa3826.workers.dev>
- Cloudflare Access ครอบ hostname นี้และบังคับ owner-only email OTP (ดู [`CLOUDFLARE_ACCESS.md`](CLOUDFLARE_ACCESS.md))
- Worker secret `ACCESS_ALLOWED_EMAIL` ถูกตั้งใน Cloudflare Secret Store; ไม่อยู่ใน source, Dashboard หรือ Git
- `GH_TOKEN` ถูกตั้งเป็น Worker secret ชนิด `secret_text` แล้ว แต่ยังไม่ได้ยืนยัน authenticated GitHub API access ผ่าน Worker
- **ก่อนใช้งานจริงให้ rotate GH_TOKEN เป็นค่าใหม่**; ค่าแรกถูกส่งผ่านแชตระหว่าง setup และไม่ควรใช้ต่อใน production
- ห้าม merge PR #2 หรือเปลี่ยน Dashboard production ให้เรียก Worker จนกว่าจะ rotate credential และผ่าน authenticated verification
- GitHub Actions manual flow เดิมบน `main` ยังเป็นทางเลือกใช้งานได้

## Architecture

```text
GitHub Pages → Cloudflare Access → x2telegram-control-plane Worker → GitHub Actions → Python worker → Telegram
```

Worker เป็น API/control layer เท่านั้น ไม่ดาวน์โหลด media ไม่ส่ง Telegram ไม่มี database/Redis/queue/backend framework. `fflate` ใช้แตก ZIP ของ GitHub Actions report artifact ใน Worker เพื่อคืนเฉพาะ sanitized dashboard report

## Configuration

`wrangler.toml` มี non-secret variables:

- `GH_OWNER=aodxx`
- `GH_REPO=X2Telegram`
- `GH_WORKFLOW_ID=x2telegram.yml`
- `GH_REF=main`
- `DASHBOARD_ORIGIN=https://aodxx.github.io`
- `ACCESS_TEAM_DOMAIN=https://falling-sky-a8ee.cloudflareaccess.com`
- `ACCESS_AUD` — audience ของ Access app ที่ตั้งไว้ใน config

Cloudflare Worker Secrets:

- `ACCESS_ALLOWED_EMAIL` — ตั้งไว้แล้ว; ใช้ตรวจ identity ซ้ำหลัง validate Access JWT
- `GH_TOKEN` — ตั้งแล้วเป็น `secret_text`; ควร rotate ก่อน production เป็น fine-grained credential จำกัดเฉพาะ repository `aodxx/X2Telegram` ด้วยสิทธิ์ `Actions: Read and write` และ `Metadata: Read-only`

ห้ามใช้ GitHub CLI app user token (`ghu_…`) เป็น `GH_TOKEN`: token ของ integration เป็น credential สำหรับ session ชั่วคราว ไม่ใช่ secret ระยะยาวสำหรับ Worker. อย่าพิมพ์ token ลง chat หรือ commit ลง Git. เมื่อมี fine-grained PAT ให้เพิ่มผ่าน Cloudflare Worker secret prompt:

```bash
cd control-worker
npx wrangler secret put GH_TOKEN --name x2telegram-control-plane
```

หลังตั้ง secret ให้ทดสอบ; ห้ามเริ่ม run ทดสอบด้วย URL จริงหรือส่ง Telegram โดยไม่มีการอนุมัติทดสอบแยกต่างหาก

## Endpoints

| Method/path | Authentication | Behavior |
|---|---|---|
| `GET /health` | Cloudflare Access ที่ edge | คืน service/status โดยไม่เปิดเผย credential หรือสถานะ upstream |
| `POST /jobs` | Cloudflare Access JWT | รับ JSON URL เดี่ยว; ตรวจ origin/schema/body size/URL/mode/request ID; ตรวจ run เดิม; dispatch GitHub Actions |
| `GET /jobs/<job_id>` | Cloudflare Access JWT | ค้น run จาก workflow title, คืนสถานะและ sanitized artifact |
| `OPTIONS *` | CORS preflight | รับเฉพาะ Dashboard origin; Access application ตอบ preflight ด้วย CORS headers ที่กำหนด |

Worker ตรวจ Access JWT signature RS256 กับ Cloudflare Access JWKS, issuer, audience, `exp`/`nbf`, และ email allowlist. GitHub token อยู่ใน Worker secret เท่านั้น. GitHub errors ถูก sanitize; response ใช้ `Cache-Control: no-store`; CORS ไม่ใช้ wildcard

## Dispatch / idempotency / workflow interface

เมื่อได้รับ POST Worker normalize X URL, คำนวณ opaque `job_id` จาก `request_id + normalized URL + large_file_mode` และค้น run ที่ตรงกับ workflow title `X2Telegram <request_id> <job_id>`. run เดิมถูกคืนแทนการ dispatch ซ้ำ; payload ต่างที่ใช้ request ID ซ้ำแต่พบ run ที่ต่าง job fingerprint จะได้ `409 idempotency_conflict`.

Workflow dispatch inputs มี `url`, `urls` (compatibility; หนึ่ง URL), `large_file_mode`, `request_id`, `job_id`. Workflow concurrency และ Python `state/dedupe.json` ยังคงเป็นตัวป้องกัน Telegram delivery ซ้ำชั้นสุดท้าย โดยไม่เพิ่ม state service

เพราะไม่ใช้ durable store, สอง POST ที่มี request ID/payload เดียวกันพร้อมกันก่อน GitHub API แสดง run อาจ dispatch สอง workflow runs. Workflow concurrency และ post dedupe ป้องกันการส่ง Telegram ซ้ำเมื่อ state ถูก persist สำเร็จ แต่ API ไม่อ้าง exactly-once ของ workflow dispatch

## Local tests

```bash
npm ci --prefix control-worker
npm test --prefix control-worker
```

Unit tests mock GitHub/JWKS; ครอบคลุม unauthenticated, denied identity, invalid/malformed request, dispatch mapping, duplicate/conflict, GitHub failure, status/artifact, CORS. Tests ไม่เรียก GitHub จริง, ไม่ dispatch workflow และไม่ส่ง Telegram

## ขั้นตอนที่ค้างก่อนเปิดใช้งาน

1. Rotate `GH_TOKEN` เป็นค่าใหม่โดยไม่ส่ง token ผ่านแชต และเก็บผ่าน Cloudflare Worker Secret เท่านั้น
2. เจ้าของ sign in ที่ Worker ผ่าน email OTP; ตรวจว่าเข้าถึง `/health` ได้
3. ทำ authenticated read-only verification กับ GitHub API ผ่าน Worker; ห้าม dispatch URL จริงหรือส่ง Telegram ในขั้นตรวจนี้
4. เมื่อ verification ผ่านแล้วจึงพิจารณา merge PR #2 และเปลี่ยน Dashboard production
