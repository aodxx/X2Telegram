# X2Telegram Control Plane Contract — Zone 1

สถานะ: **contract สำหรับ implementation** (ยังไม่ใช่ production deployment)

## เป้าหมายและหลัก

```text
GitHub Pages Dashboard → Cloudflare Access → Control Worker → GitHub Actions → X2Telegram → Telegram
```

- Dashboard ส่ง X post URL หนึ่งรายการต่อหนึ่ง job ตาม scope ใน Master Plan
- GitHub Actions ยังคงเป็น execution plane; Python worker และ Telegram credentials ไม่ย้ายเข้า browser
- ไม่เพิ่ม database, Redis หรือ queue service
- `request_id` เป็น client-generated idempotency key ที่ Dashboard สร้างครั้งเดียวต่อ logical submit และ persist ไว้; `job_id` เป็น opaque deterministic ID ที่ Worker คำนวณจาก `request_id`, normalized URL และ `large_file_mode`
- Worker map `url` จาก public API ไปยัง workflow input เดิม `urls` (หนึ่ง URL/บรรทัด) เพื่อรักษา workflow/manual compatibility

## Resource และ API

Base URL เป็น Cloudflare Worker origin ที่ติดตั้ง Access เช่น `https://<configured-api-host>`.

### `POST /jobs`

ต้องยืนยันตัวตนผ่าน Cloudflare Access ก่อนรับคำขอ (ยกเว้น `OPTIONS` preflight และ `GET /health`). Worker ตรวจ Access JWT เพิ่มเอง; ห้ามเชื่อ header ที่ client ส่งมาโดยไม่มีลายเซ็นที่ผ่านการตรวจ

Request JSON:

```json
{
  "url": "https://x.com/account/status/1234567890",
  "large_file_mode": false,
  "request_id": "dashboard-<random-id>"
}
```

| Field | Required | Validation |
|---|---:|---|
| `url` | yes | HTTPS URL ของ `x.com`, `www.x.com`, `mobile.x.com`, `twitter.com`, `www.twitter.com` หรือ `mobile.twitter.com`; path ต้องมี `/status/<digits>`; normalize เป็น `https://x.com/<user>/status/<id>` |
| `large_file_mode` | no | Boolean เท่านั้น; default `false` |
| `request_id` | yes | 1–128 ตัวอักษร `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`; client ต้อง reuse ค่านี้เมื่อ retry logical submit เดิม |

ขนาด body สูงสุด 16 KiB; JSON ต้องเป็น object; ไม่รับ arbitrary workflow input, chat ID, secret, GitHub ref หรือ URL list จาก client

### POST response

ทุก response เป็น JSON:

```json
{
  "job_id": "job-<payload-fingerprint>",
  "request_id": "dashboard-<random-id>",
  "state": "accepted",
  "created_at": "2026-10-08T00:00:00.000Z",
  "updated_at": "2026-10-08T00:00:00.000Z",
  "progress": {"phase": "queued", "percent": 0},
  "result": null,
  "error": null,
  "telegram": null
}
```

- ใหม่และ dispatch สำเร็จ: HTTP `202`, `state=accepted`.
- มี workflow run ที่ตรงกับ `request_id` อยู่แล้ว: HTTP `200`, คืน `job_id` เดิมและสถานะปัจจุบัน (ไม่ dispatch ซ้ำ) พร้อม `duplicate: true`.
- response มาจาก retry หลัง dispatch แต่ก่อน GitHub สร้าง run ให้ค้นพบได้: Worker อาจตอบ `202 accepted`; client คงใช้ `request_id` เดิมและ query status เดิม ห้ามสร้าง request ID ใหม่เพื่อ retry.

### `GET /jobs/<job_id>`

ต้องผ่าน Access และรูปแบบ job ID เดียวกับ request ID. Worker ค้นหา workflow run ที่ title/name ตรงกับ `X2Telegram <job_id>` แล้วคำนวณ response schema เดิม

- queued / requested / waiting: `state=processing`, progress phase `queued`
- in progress: `state=processing`, phase `running`
- completed + conclusion success: `state=completed`, progress 100; อ่าน sanitized report artifact หากมี
- completed + non-success conclusion: `state=failed`, ใช้ข้อความ sanitized; อ่าน artifact ได้หากมี
- run ยังไม่ปรากฏใน GitHub: HTTP `404`, `error.code=job_not_found` (client retry ด้วย job_id เดิม)

`created_at`/`updated_at` ใช้เวลา GitHub run เท่าที่มี; `result` มีเฉพาะ sanitized report; `telegram` มีเฉพาะ message IDs/count ที่ allow-listed ใน report. ห้ามคืน media URL, raw logs, token, Authorization header หรือ error traceback

### `GET /health`

ไม่มีข้อมูล config/account และไม่เรียก GitHub API; ตอบ HTTP `200` `{"status":"ok","service":"x2telegram-control"}`. เป็น liveness endpoint เท่านั้น ไม่ยืนยันว่า GitHub, Telegram หรือ Actions พร้อมทำงาน

## State และ error schema

สถานะภายนอก: `accepted`, `processing`, `completed`, `failed`, `duplicate`, `invalid_request`.

Error object:

```json
{"error":{"code":"invalid_url","message":"URL must be a public X post URL"},"request_id":"dashboard-..."}
```

| HTTP | Code / use |
|---:|---|
| 400 | `invalid_request`, `invalid_json`, `invalid_url`, `invalid_large_file_mode`, `request_too_large` |
| 401 | `unauthorized` — Access JWT missing/invalid/expired |
| 403 | `forbidden` — Access identity ไม่อยู่ใน allowlist หรือ JWT audience ไม่ตรง |
| 404 | `job_not_found` |
| 409 | `duplicate` ใช้เฉพาะ conflict ที่คืน job เดิมไม่ได้; ปกติ duplicate ตอบสถานะเดิมด้วย HTTP 200 |
| 429 | `rate_limited` |
| 502 | `github_dispatch_failed`, `github_read_failed`, `report_unavailable` เมื่อ dependency ภายนอกล้มเหลว |
| 500 | `internal_error` พร้อมข้อความกลางที่ไม่เปิดเผยข้อมูลลับ |

Response ทุกกรณีใส่ `Content-Type: application/json`, `Cache-Control: no-store`; CORS อนุญาตเฉพาะ origin ของ Dashboard ที่ตั้งค่าไว้ ไม่ใช้ wildcard และรองรับ `OPTIONS` สำหรับ preflight. Access CORS configuration ต้องเปิดทางให้ OPTIONS preflight ตามเอกสาร Cloudflare; request จริงยังต้องผ่าน policy/JWT validation.

## Authentication / security boundary

1. Cloudflare Access application อนุญาตเฉพาะ identity ของเจ้าของระบบ (email allowlist ที่กำหนดตอนตั้งค่า)
2. Worker ตรวจ `Cf-Access-Jwt-Assertion` ด้วย JWKS จาก `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`, issuer ที่ตรงกับ team domain, audience ที่ตรงกับ app AUD และ `exp`/`nbf`; ตรวจ email allowlist เพิ่ม
3. GitHub fine-grained credential อยู่เฉพาะ Worker Secret `GH_TOKEN`; minimum intended scope คือ Actions: read/write สำหรับ dispatch/read runs/artifacts และ Metadata: read เฉพาะ repository `aodxx/X2Telegram`
4. Telegram credentials อยู่เฉพาะ GitHub Actions Secrets; ไม่ส่งผ่าน dispatch inputs
5. ไม่บันทึก request body/URL, JWT, cookies, Authorization, GitHub response body หรือ secret ใน logs
6. CORS ไม่ใช่ authentication; ทุก resource ยกเว้น liveness/preflight ต้องผ่าน Access/JWT

## Idempotency และ duplicate policy

- `request_id` เป็น idempotency key; Dashboard สร้างครั้งเดียวและ persist ก่อน network request. Worker คำนวณ `job_id = job-<sha256-prefix>` จาก request ID + payload ที่ normalize แล้ว จึงได้ ID เดิมเมื่อ retry payload เดิม
- Worker ค้น workflow run ที่ match กับ request ID ก่อน dispatch; เมื่อพบแล้วคืน job เดิมเป็น duplicate/current status
- API ไม่อ้างว่ามี transactional reservation เพราะตามข้อห้ามไม่มี durable database/queue: request ซ้ำที่เข้ามาพร้อมกันก่อน GitHub แสดง run อาจสร้าง workflow runs ซ้ำได้
- การป้องกันไม่ให้ส่ง Telegram ซ้ำชั้นสุดท้ายอาศัย workflow `concurrency` ที่มีอยู่, persisted post-level `state/dedupe.json` และการ serialize workflow; retry job เดิมไม่เปลี่ยน request ID
- ชื่อ workflow run ผูกทั้ง request ID และ job ID; เมื่อพบ request ID เดิมแต่ fingerprint/job ID ต่างกัน ให้ตอบ HTTP `409 idempotency_conflict`; ไม่ dispatch อีก run
- ID ใหม่ถือเป็น intent ใหม่ แต่ dedupe post-level ของ worker ยังคงป้องกัน post ที่สำเร็จไปแล้ว
- ข้อจำกัด no-database/race ต้องแสดงในเอกสารและต้องทดสอบ concurrent submit ก่อนอ้าง exactly-once; เป้าหมายคือ at-most-once Telegram delivery สำหรับ post ที่ persist dedupe state สำเร็จ ไม่ใช่ guarantee exactly-once ของ GitHub run

## Retry model

- Client retry network/502/429 ใช้ `request_id` เดิม; เคารพ `Retry-After` เมื่อมี และใช้ exponential backoff พร้อม jitter แบบมีเพดาน
- 400/401/403/409 ไม่ retry อัตโนมัติจนกว่าจะแก้ input/auth/conflict
- `GET /jobs/<job_id>` เป็น safe-to-retry; 404 ระหว่างช่วง dispatch visibility ให้ retry แบบ backoff ช่วงสั้นด้วย ID เดิม
- GitHub dispatch timeout ที่ไม่ทราบผล: Worker ตรวจ runs ด้วย request_id ก่อนตัดสินใจ dispatch ซ้ำ
- Workflow failed: ไม่ auto-dispatch ใหม่; ผู้ใช้เริ่ม retry เป็น logical action ใหม่หลังตรวจผล (หรือส่ง request_id ใหม่เมื่อมีนโยบาย explicit retry) โดย worker dedupe เดิมปกป้องโพสต์ที่ส่งแล้ว

## Compatibility

Control Worker ส่ง GitHub Actions inputs `url`, `urls`, `large_file_mode`, `request_id`, `job_id` ตามที่ workflow รองรับหลัง Zone 2. `job_id` เป็น deterministic fingerprint และแยกจาก request ID. สำหรับ manual workflow dispatch เดิม `urls` ยังใช้งานได้; `url`/`job_id` เป็น optional compatibility additions. Python processing worker ยังคงรับ URL batch ผ่าน `INPUT_URLS` และไม่เปลี่ยน contract ภายใน
