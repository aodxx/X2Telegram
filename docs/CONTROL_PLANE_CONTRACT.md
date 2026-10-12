# X2Telegram Control Plane Contract

สถานะ: contract ปัจจุบันของ Dashboard ที่เสิร์ฟจาก Cloudflare Worker origin เดียวกับ API

## เป้าหมายและ flow

```text
GitHub Pages redirect → Cloudflare Access + Worker-hosted Dashboard/API
  → GitHub Actions → Python processor → selected destination(s)
```

- Dashboard ส่ง X post URL ได้ 1–50 รายการต่อหนึ่ง job
- เลือก destination ได้หนึ่งหรือหลายรายการจาก `telegram`, `mega`, `dropbox`, `download`; เมื่อ field ไม่มีให้ใช้ Telegram เพื่อ backward compatibility
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
| `destinations` | no | array 1–4 รายการจาก `telegram`, `mega`, `dropbox`, `download`; empty, unknown หรือ duplicate target ถูกปฏิเสธ; เมื่อไม่ส่งให้ default `telegram` |
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

### `POST /jobs/recover`

ใช้ request fields และ normalization เดียวกับ `POST /jobs` แต่เป็น **lookup-only**: ค้น run เดิมด้วย `request_id` และ payload fingerprint, คืน HTTP `200` เมื่อพบ run/คำขอที่กำลัง dispatch ใน isolate เดียวกัน, `409 idempotency_conflict` เมื่อ payload ขัดแย้งกับ run/reservation ที่พบ, หรือ `404 job_not_found` เมื่อยังไม่พบ. Endpoint นี้ไม่เรียก GitHub Actions dispatch และไม่ใช้ dispatch rate-limit quota. การ `404` แปลว่าไม่พบในข้อมูลที่มองเห็น ณ เวลาตรวจ ไม่ใช่หลักฐานว่าไม่มี request ที่กำลังเดินทางหรือ run ที่ยังไม่ปรากฏ; Dashboard จึงไม่ส่งงานใหม่ให้อัตโนมัติ.

### `GET /jobs/<job_id>`

ต้องผ่าน Access; อ่าน run title และ private sanitized report artifact แล้วคืน state, summary และผลราย post/destination/media. หากมีทั้ง success และ failure งานยังเป็น `completed` และ result แสดง `partial_success` ราย target/post; หากทุก target ล้มเหลว state เป็น `failed`; หากไม่มี target ที่ยืนยันสำเร็จแต่มีผลกำกวม state เป็น `outcome_unconfirmed`. `report_availability.status` แยก `pending`, `ready`, `missing`, `expired`, และ `unavailable`; expiry metadata/error code ถูกส่งแบบ sanitized. Media ZIP readiness มี object `download` เช่น `available`, `status`, `file_count`, `expires_at`; artifact ที่หาย/หมดอายุจะไม่ถูกแสดงว่า ready.

Response ไม่คืน raw logs, signed GitHub artifact URL, media CDN URL, credential, Authorization header หรือ traceback

### `GET /jobs/<job_id>/download`

ต้องผ่าน Access และ workflow ต้องเสร็จสิ้น. Worker ยืนยัน job/report/artifact ให้ตรงกับ run นั้น แล้ว stream private ZIP จาก GitHub Actions โดยตรงไปยัง browser; ไม่ buffer ZIP ทั้งก้อนใน Worker และไม่เปิดเผย signed artifact URL ให้ frontend. Response ใช้ `Content-Type: application/zip`, `Content-Disposition: attachment`, `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`. Artifact มี retention 7 วัน

### `GET /auth/check` และ `/health`

- `/auth/check` ต้องผ่าน Access JWT และ email allowlist; ตอบ authenticated session สำหรับ Dashboard
- `/health` เป็น liveness endpoint ไม่มี GitHub lookup และไม่ยืนยัน upstream readiness
- Static assets ถูก serve หลัง Access/JWT check; `OPTIONS` ยอมรับเฉพาะ configured Dashboard origin

## Destination statuses และ error behavior

Report แยก `destinations[telegram|mega|dropbox|download]` และผล `items[]`. สถานะสำคัญ ได้แก่ `success`, `failed`, `partial_success`, `duplicate`, `ready`, `processing`, และ `outcome_unconfirmed`. Failure ของ target หนึ่งไม่หยุด dispatcher; job-level success ยังมีได้เมื่อมี target อื่นสำเร็จ. Target ที่มีผลกำกวมไม่ถูกเสนอเป็น retry เป้าหมายอัตโนมัติ; ผู้ใช้ควรตรวจปลายทางก่อนตัดสินใจ. Download ZIP lookup/expiry failure และ report availability จะสะท้อนใน result และ Dashboard status.

แต่ละ post อาจมี `media_manifest[]` และ `media_reconciliation`. Manifest บันทึก `media_index` ภายใน post, `source_index`, `kind`, สถานะดาวน์โหลด/validation, `size_bytes`, content `sha256` (hash ของ bytes ไม่รวม post identity) และสถานะต่อ destination ที่เลือก. Reconciliation สรุปจำนวน expected, validated, accounted, delivered, duplicate, failed และ unaccounted items ต่อ destination; หาก metadata ล้มเหลวหรือ legacy duplicate ถูกข้ามก่อน enumerate จะรายงาน expected เป็น `null` และสถานะ `metadata_failed`/`not_enumerated` แทนการอ้างว่า expected เป็นศูนย์. Fields เหล่านี้เป็น optional เพื่อคง compatibility กับ report เก่า

Destination status ใน manifest หมายถึง adapter outcome (`success`, `ready`, `duplicate`, `failed`, `not_attempted`) ไม่ใช่หลักฐาน remote read-back โดยตัวมันเอง. การอ้าง remote integrity ต้องมี integration evidence เช่น remote listing และ download-back bytes/hash แยกต่างหาก. Dashboard sanitizer allowlists เฉพาะ fields ข้างต้นและไม่ส่ง media URL, signed query, local path หรือ remote folder.

`mega_credentials_missing`, `mega_authentication_failed`, `mega_client_unavailable`, `mega_upload_failed`, `download_artifact_size_limit`, `download_artifact_missing`, `download_expired` เป็น safe error codes; report ไม่รวม MEGA command output/password/TOTP seed หรือ media signed URL

## Authentication/security boundary

1. Cloudflare Access จำกัดผู้ใช้ตาม owner email policy
2. Worker ตรวจ `Cf-Access-Jwt-Assertion` ด้วย Cloudflare Access JWKS, issuer, audience, `exp`/`nbf` และ email allowlist
3. GitHub credential อยู่ใน Worker secret; Telegram, MEGA และ Dropbox credentials อยู่ใน GitHub Actions Secrets เท่านั้น
4. Browser ไม่ส่ง credential, chat ID หรือ raw workflow configuration
5. Worker จำกัด request body 16 KiB, exact Dashboard origin และ response cache `no-store`
6. Download route คืนไฟล์เฉพาะ artifact name/run ID ที่ตรงกับ job และยังไม่หมดอายุ

## Idempotency และ retry

Worker คำนวณ `job_id` จาก payload ที่ normalize แล้ว (รวม destinations) และค้น run เดิมก่อน dispatch. Request ID เดิมแต่ payload เปลี่ยน—including destination choice—ได้ `409 idempotency_conflict`. ภายใน Worker isolate เดียว มี in-memory single-flight reservation keyed by Access identity + `request_id`; identical concurrent submissions share one dispatch, conflicting in-flight payload gets 409, and an accepted outcome remains cached for 30 seconds to cover run-list visibility delay. Reservation นี้ไม่ durable/global และไม่ coordinate ข้าม isolate หรือ isolate restart; จึงยังมี narrow concurrent dispatch race ก่อน GitHub แสดง run. GitHub run lookup กับ Python per-media/destination checkpoint ช่วยลดความเสี่ยงหลัง run ปรากฏ แต่ระบบไม่รับประกัน exactly-once dispatch/delivery หาก request/response/checkpoint สูญหาย.

Python dedupe state v4 จดผลสำเร็จและ outcome-unconfirmed แยก Telegram/MEGA/Dropbox ตาม media fingerprint; retry จะข้าม target/item ที่สำเร็จแล้ว, ลองเฉพาะ confirmed failures และไม่ replay ผลกำกวมโดยอัตโนมัติ. หากปลายทางยืนยัน success แต่การเขียน success checkpoint ล้มเหลว report จะติด `dedupe_checkpoint_failed`; Dashboard failed-only retry จะไม่เลือก target ที่รายงาน success แต่ job เต็มรายการที่ผู้ใช้สร้างใหม่ภายหลังอาจส่งซ้ำได้เพราะไม่มี durable record. Download artifact เป็นผลลัพธ์เฉพาะ workflow run จึงสร้างใหม่ด้วย job ใหม่ได้. Dashboard reload/reopen ใช้ lookup-only recovery แล้ว resume status/report polling; มันไม่สร้าง request ID ใหม่หรือ dispatch อัตโนมัติ.

## Compatibility

`url` เดี่ยว, `urls` batch และ Telegram default ยังคงรองรับ; Dashboard ส่ง `destinations` เมื่อมีการเลือก target และ Worker ส่งต่อเป็น workflow input JSON. Workflow หลักเดียวรับ inputs `url`, `urls`, `destinations`, `large_file_mode`, `request_id`, `job_id`; Python CLI อ่าน `INPUT_URL`/`INPUT_URLS` และ `DESTINATIONS_JSON`. Manual GitHub Actions เดิมใช้ได้โดยไม่ส่ง `destinations` ซึ่ง default เป็น Telegram
