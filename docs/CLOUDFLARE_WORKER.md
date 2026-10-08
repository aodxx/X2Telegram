# Cloudflare Control Worker — Zone 3

## สถานะ

Implementation + offline tests เสร็จแล้ว; **ยังไม่ได้ deploy** ตามข้อกำหนด Zone 3. Worker source: `control-worker/src/index.js`; config: `control-worker/wrangler.toml`.

## Architecture

```text
GitHub Pages → Cloudflare Access → x2telegram-control-plane Worker → GitHub Actions → Python worker → Telegram
```

Worker เป็น API/control layer เท่านั้น ไม่ download media, ไม่ส่ง Telegram, ไม่มี database/Redis/queue และไม่มี backend framework. `fflate` ใช้แตก ZIP ของ GitHub Actions report artifact ใน Worker เพื่อคืนเฉพาะ sanitized dashboard report

## Configuration

`wrangler.toml` กำหนดชื่อ `x2telegram-control-plane`, main module, compatibility date, GitHub repository/workflow/ref และ exact Dashboard CORS origin. `workers.dev` host ตาม account subdomain ที่ตรวจแบบ read-only คือ:

```text
https://x2telegram-control-plane.pantipa3826.workers.dev
```

`web/config.js` ใช้ public API origin นี้; ไม่ใช่ credential. ชื่อ Worker ยังว่างในรายการ script ปัจจุบัน ณ วันที่ audit; ไม่มีการสร้าง resource ใน Cloudflare

ตั้งค่า secret ด้วย Wrangler หลังมี fine-grained GitHub token ที่จำกัด repository `aodxx/X2Telegram`:

```bash
cd control-worker
npx wrangler secret put GH_TOKEN
```

ห้ามพิมพ์หรือ commit token. สิทธิ์ที่ตั้งใจใช้: Actions read/write เพื่อ dispatch/read workflow runs/artifacts และ Metadata read; ต้องตรวจว่า token จริงให้สิทธิ์เท่านี้ก่อน deployment

ตั้ง Worker vars ที่เหลือใน `wrangler.toml`/dashboard:

- `GH_OWNER=aodxx`
- `GH_REPO=X2Telegram`
- `GH_WORKFLOW_ID=x2telegram.yml`
- `GH_REF=main`
- `DASHBOARD_ORIGIN=https://aodxx.github.io`
- `ACCESS_TEAM_DOMAIN=https://<team>.cloudflareaccess.com`
- `ACCESS_AUD=<Access application AUD>`
- `ACCESS_ALLOWED_EMAIL=<owner email>`

ค่า Access สามรายการสุดท้ายยังว่าง เพราะไม่มี Access application/AUD ที่อ่านได้ในบัญชีขณะตรวจ และ worker ยังไม่ deploy

## Endpoints

| Method/path | Authentication | Behavior |
|---|---|---|
| `GET /health` | liveness only | คืน service/status โดยไม่เปิดเผย credential หรือสถานะ upstream |
| `POST /jobs` | Cloudflare Access JWT | รับ JSON URL เดี่ยว; ตรวจ origin/schema/body size/URL/mode/request ID; ตรวจ run เดิม; dispatch GitHub Actions |
| `GET /jobs/<job_id>` | Cloudflare Access JWT | ค้น run จาก workflow title, คืนสถานะและ sanitized artifact |
| `OPTIONS *` | preflight | ตอบ CORS เฉพาะ Dashboard origin ที่ระบุไว้; Access app ต้องตั้งค่า OPTIONS preflight เพิ่มเติม |

Worker ตรวจ Access JWT signature RS256 กับ Cloudflare Access JWKS, issuer, audience, `exp`/`nbf`, และ email allowlist. GitHub token อยู่ใน Worker secret เท่านั้น. Error จาก GitHub ถูก sanitize ไม่คืน response body/token. API response ใช้ `Cache-Control: no-store` และ CORS ไม่ใช้ wildcard

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

## Deployment checklist (ยังไม่ดำเนินการ)

1. สร้าง fine-grained GitHub credential ที่จำกัด repo/permissions ตามต้องการและเก็บเป็น `GH_TOKEN` Worker Secret
2. สร้าง Access app/policy เฉพาะ Worker, ตั้ง owner identity allowlist, เปิด production Access
3. ตั้ง Access team domain, AUD, email allowlist และ CORS จาก Dashboard origin
4. ตรวจ exact host/origin และ Access login flow; ตั้งค่า `OPTIONS` preflight ใน Access ให้ตรงกับ Worker CORS (อย่า bypass โดยไม่มี origin check)
5. ตั้ง secrets/vars และ deploy ด้วย `npx wrangler deploy`
6. ทดสอบ `GET /health`, unauthenticated denial, authorized submit, duplicate, status/report ก่อนเปิด dashboard ใช้งาน

Cloudflare docs: [Protect a Worker with Access](https://developers.cloudflare.com/workers/configuration/cloudflare-access/), [workers.dev URLs](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/), [Access CORS](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/cors/), [Validate Access JWT](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/).
