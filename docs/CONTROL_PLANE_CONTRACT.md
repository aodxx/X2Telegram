# X2Telegram Control Plane Contract

สถานะ: contract ปัจจุบันของ Dashboard ที่เสิร์ฟจาก Cloudflare Worker origin เดียวกับ API

## เป้าหมายและ flow

```text
GitHub Pages redirect → Cloudflare Access + Worker-hosted Dashboard/API
  → GitHub Actions → Python processor → selected destination(s)
```

- Dashboard ส่ง X post URL ได้ 1–50 รายการต่อหนึ่ง job
- เลือก destination ได้หนึ่งหรือหลายรายการจาก `telegram`, `mega`, `download`; เมื่อ field ไม่มีให้ใช้ Telegram เพื่อ backward compatibility
- Actions ยังคงเป็น execution plane; Python worker download/validate media ครั้งเดียวก่อน dispatch ไปยัง targets
- ไม่เพิ่ม database, Redis, queue หรือ Google Drive integration
- `request_id` คือ client-generated idempotency key; `job_id` fingerprint ครอบ request ID, ordered normalized URLs, `large_file_mode` และ normalized destinations
- Dashboard และ API ใช้ Worker origin เดียวกัน; `/auth/check` ยืนยัน Access JWT ก่อนเปิดปุ่มส่ง

## API

Base URL คือ Worker origin ที่ติดตั้ง Access เช่น `https://<configured-api-host>`.

### `POST /jobs`

ทุก POST ต้องผ่าน Cloudflare Access JWT และ worker ตรวจ signature/issuer/audience/expiry/email allowlist ซ้ำ

Request JSON:

```json
{
  "urls": ["https://x.com/account/status/1234567890"],
  "destinations": ["telegram", "download"],
  "large_file_mode": false,
  "request_id": "dashboard-<random-id>"
}
```

| Field | Required | Validation |
|---|---:|---|
| `url` | เลือก `url` หรือ `urls` อย่างใดอย่างหนึ่ง | URL เดี่ยว HTTPS ของ X/Twitter post; backward-compatible |
| `urls` | เลือก `url` หรือ `urls` อย่างใดอย่างหนึ่ง | JSON array 1–50 URLs; validate/normalize ทุก URL; reject post ID ซ้ำใน batch |
| `destinations` | no | array 1–3 รายการจาก `telegram`, `mega`, `download`; empty, unknown หรือ duplicate target ถูกปฏิเสธ; เมื่อไม่ส่งให้ default `telegram` |
| `large_file_mode` | no | Boolean; default `false` |
| `request_id` | yes | `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`; retry logical request เดิมต้องใช้ค่าเดิม |

Request body จำกัด 16 KiB; ไม่รับ arbitrary workflow input, chat ID, secret หรือ GitHub ref จาก client

### POST response

```json
{
  "job_id": "job-<payload-fingerprint>",
  "request_id": "dashboard-<random-id>",
  "state": "accepted",
  "progress": {"phase": "queued", "percent": 0},
  "destinations": ["telegram", "download"],
  "result": null,
  "download": null,
  "error": null
}
```

Dispatch ใหม่คืน HTTP `202`; job ที่ match กับ request เดิมคืน HTTP `200` และ `duplicate: true` พร้อม state เดิม. Retry หลัง dispatch timeout ต้องใช้ `request_id` เดิม

### `GET /jobs/<job_id>`

ต้องผ่าน Access; อ่าน run title และ private sanitized report artifact แล้วคืน state, summary และผลราย post/destination/media. หากมีทั้ง success และ failure งานยังเป็น `completed` และ result แสดง `partial_success` ราย target/post; หากทุก target ล้มเหลว state เป็น `failed`. Media ZIP readiness มี object `download` เช่น `available`, `status`, `file_count`, `expires_at`; artifact ที่หาย/หมดอายุจะถูกปรับ result target ให้ failed แทน false-ready

Response ไม่คืน raw logs, signed GitHub artifact URL, media CDN URL, credential, Authorization header หรือ traceback

### `GET /jobs/<job_id>/download`

ต้องผ่าน Access และ workflow ต้องเสร็จสิ้น. Worker ยืนยัน job/report/artifact ให้ตรงกับ run นั้น แล้ว stream private ZIP จาก GitHub Actions โดยตรงไปยัง browser; ไม่ buffer ZIP ทั้งก้อนใน Worker และไม่เปิดเผย signed artifact URL ให้ frontend. Response ใช้ `Content-Type: application/zip`, `Content-Disposition: attachment`, `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`. Artifact มี retention 7 วัน

### `GET /auth/check` และ `/health`

- `/auth/check` ต้องผ่าน Access JWT และ email allowlist; ตอบ authenticated session สำหรับ Dashboard
- `/health` เป็น liveness endpoint ไม่มี GitHub lookup และไม่ยืนยัน upstream readiness
- Static assets ถูก serve หลัง Access/JWT check; `OPTIONS` ยอมรับเฉพาะ configured Dashboard origin

## Destination statuses และ error behavior

Report แยก `destinations[telegram|mega|download]` และผล `items[]`. สถานะสำคัญ ได้แก่ `success`, `failed`, `partial_success`, `duplicate`, `ready`, `processing`. Failure ของ target หนึ่งไม่หยุด dispatcher; job-level success ยังมีได้เมื่อมี target อื่นสำเร็จ. Download ZIP lookup/expiry failure จะสะท้อนใน result และ Dashboard status

`mega_credentials_missing`, `mega_authentication_failed`, `mega_client_unavailable`, `mega_upload_failed`, `download_artifact_size_limit`, `download_artifact_missing`, `download_expired` เป็น safe error codes; report ไม่รวม MEGA command output/password/TOTP seed หรือ media signed URL

## Authentication/security boundary

1. Cloudflare Access จำกัดผู้ใช้ตาม owner email policy
2. Worker ตรวจ `Cf-Access-Jwt-Assertion` ด้วย Cloudflare Access JWKS, issuer, audience, `exp`/`nbf` และ email allowlist
3. GitHub credential อยู่ใน Worker secret; Telegram และ MEGA credentials อยู่ใน GitHub Actions Secrets เท่านั้น
4. Browser ไม่ส่ง credential, chat ID หรือ raw workflow configuration
5. Worker จำกัด request body 16 KiB, exact Dashboard origin และ response cache `no-store`
6. Download route คืนไฟล์เฉพาะ artifact name/run ID ที่ตรงกับ job และยังไม่หมดอายุ

## Idempotency และ retry

Worker คำนวณ `job_id` จาก payload ที่ normalize แล้ว (รวม destinations) และค้น run เดิมก่อน dispatch. Request ID เดิมแต่ payload เปลี่ยน—including destination choice—ได้ `409 idempotency_conflict`. ไม่มี durable reservation/database จึงอาจมี concurrent dispatch ก่อน GitHub แสดง run; Actions concurrency, Python per-media/destination dedupe state v3 และ retry ด้วย ID เดิมลดความเสี่ยงส่งซ้ำ. ระบบไม่รับประกัน exactly-once หาก target รับไฟล์แต่ response/checkpoint หาย

Python state v3 จดผลสำเร็จแยก Telegram/MEGA ตาม media fingerprint; retry จะข้าม target/item ที่สำเร็จแล้วและลองเฉพาะส่วนที่ยังไม่สำเร็จ. Download artifact เป็นผลลัพธ์เฉพาะ workflow run จึงสร้างใหม่ด้วย job ใหม่ได้

## Compatibility

`url` เดี่ยว, `urls` batch และ Telegram default ยังคงรองรับ; Dashboard ส่ง `destinations` เมื่อมีการเลือก target และ Worker ส่งต่อเป็น workflow input JSON. Workflow หลักเดียวรับ inputs `url`, `urls`, `destinations`, `large_file_mode`, `request_id`, `job_id`; Python CLI อ่าน `INPUT_URL`/`INPUT_URLS` และ `DESTINATIONS_JSON`. Manual GitHub Actions เดิมใช้ได้โดยไม่ส่ง `destinations` ซึ่ง default เป็น Telegram
