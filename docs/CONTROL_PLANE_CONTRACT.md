# X2Telegram Control Plane Contract — Zone 1

สถานะ: **contract ปัจจุบัน** — Dashboard assets และ API อยู่บน Cloudflare Worker origin เดียวกัน; GitHub Pages redirect มายัง origin นี้

## เป้าหมายและหลัก

```text
GitHub Pages redirect → Cloudflare Access + Worker-hosted Dashboard/API → GitHub Actions → X2Telegram → Telegram
```

- Dashboard ส่ง X post URL ได้ 1–50 รายการต่อหนึ่ง job; แต่ละบรรทัดคือหนึ่งโพสต์และรายงานแยกผลต่อโพสต์
- GitHub Actions ยังคงเป็น execution plane; Python worker และ Telegram credentials ไม่ย้ายเข้า browser
- ไม่เพิ่ม database, Redis หรือ queue service
- `request_id` เป็น client-generated idempotency key ที่ Dashboard สร้างครั้งเดียวต่อ logical submit และ persist ไว้; `job_id` เป็น opaque deterministic ID ที่ Worker คำนวณจาก `request_id`, ordered normalized URL list และ `large_file_mode`
- หน้า Dashboard และ API ใช้ Worker origin เดียวกันเพื่อให้ Access cookie เป็น first-party; `/auth/check` ยืนยัน JWT ก่อนเปิดปุ่มส่ง
- Worker map URL เดี่ยวไปยัง workflow input `url`; batch ไปยัง `urls` (หนึ่ง URL/บรรทัด) โดยไม่เปลี่ยน Python input contract

## Resource และ API

Base URL เป็น Cloudflare Worker origin ที่ติดตั้ง Access เช่น `https://<configured-api-host>`.

### `POST /jobs`

ต้องยืนยันตัวตนผ่าน Cloudflare Access ก่อนรับคำขอ (ยกเว้น `OPTIONS` preflight และ `GET /health`). Worker ตรวจ Access JWT เพิ่มเอง; ห้ามเชื่อ header ที่ client ส่งมาโดยไม่มีลายเซ็นที่ผ่านการตรวจ

Request JSON:

```json
{
  "urls": [
    "https://x.com/account/status/1234567890",
    "https://x.com/account/status/1234567891"
  ],
  "large_file_mode": false,
  "request_id": "dashboard-<random-id>"
}
```

| Field | Required | Validation |
|---|---:|---|
| `url` | one of `url` / `urls` | URL เดี่ยวรูปแบบ HTTPS ของ X/Twitter post; ยอมรับเป็น backward-compatible input และ normalize เป็น `https://x.com/<user>/status/<id>` |
| `urls` | one of `url` / `urls` | JSON array จำนวน 1–50 URL; validate และ normalize ทุก URL; ปฏิเสธ post ID ซ้ำใน batch |
| `large_file_mode` | no | Boolean เท่านั้น; default `false` |
| `request_id` | yes | 1–128 ตัวอักษร `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`; client ต้อง reuse ค่านี้เมื่อ retry logical submit เดิม |

ขนาด body สูงสุด 16 KiB; JSON ต้องเป็น object และต้องส่ง `url` หรือ `urls` อย่างใดอย่างหนึ่งเท่านั้น; ไม่รับ arbitrary workflow input, chat ID, secret หรือ GitHub ref จาก client

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

### `GET /auth/check`

ต้องผ่าน Cloudflare Access JWT และ Worker email allowlist; ตอบ `{"status":"ok","authenticated":true}`. Dashboard ใช้ endpoint นี้แทน liveness check เพื่อไม่แสดงว่า login สำเร็จจากการตรวจ `/health` เพียงอย่างเดียว

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

Response API ใส่ `Content-Type: application/json`, `Cache-Control: no-store`; Worker อนุญาตเฉพาะ `DASHBOARD_ORIGIN` ที่ตั้งค่าไว้และไม่ใช้ wildcard. ปัจจุบัน Dashboard/API เป็น same-origin จึงไม่ต้องพึ่ง cross-origin preflight; `OPTIONS` ยังคงจำกัด origin เพื่อ compatibility และ request จริงต้องผ่าน Access/JWT validation. Static assets ต้องผ่าน Worker JWT verification ก่อน `env.ASSETS.fetch`.

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

Control Worker ส่ง GitHub Actions input `url` เมื่อมีโพสต์เดียว หรือ `urls` ที่คั่นด้วย newline เมื่อเป็น batch; ส่ง `large_file_mode`, `request_id`, `job_id` ตาม workflow contract ด้วย. `job_id` เป็น deterministic fingerprint และแยกจาก request ID. Manual workflow `urls` เดิมยังใช้งานได้, `url` ยังคง optional compatibility input, และ Python processing worker ยังคงอ่าน batch ผ่าน `INPUT_URLS` โดยไม่เปลี่ยน contract ภายใน
