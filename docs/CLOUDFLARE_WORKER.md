# Cloudflare Control Worker

## สถานะ live (2026-10-09)

- Worker `x2telegram-control-plane` ใช้งานที่ <https://x2telegram-control-plane.pantipa3826.workers.dev>
- Version ID ปัจจุบัน: `0a099878-485a-43ef-9097-cf4f44e24373`
- Source: `main`, commit `389621bab764d15aa7ded722b74a944314693274` (PR #6)
- Cloudflare Access จำกัด hostname นี้ตาม email owner policy; Dashboard static assets และ API อยู่ origin เดียวกัน
- Worker-hosted Dashboard แสดง Access session ผ่าน browser จริงและมี destination selectors
- Live Download-only run #37843359593 ประมวลผล 2 URLs และ browser ดาวน์โหลด ZIP จริงผ่าน protected endpoint; report มี Download 2 files พร้อม ZIP CRC check ผ่าน
- Live Telegram normal-path run #37807253687 และ Dashboard batch/no-resend run #37816856323 ยังคงเป็นหลักฐาน Telegram/batch ก่อน multi-destination

## Architecture

```text
GitHub Pages URL redirect
  → Cloudflare Access
  → Worker static Dashboard + API (same origin)
  → GitHub Actions workflow_dispatch (one workflow)
  → Python media processor (download/validate once per media)
  → Telegram / MEGA / private Actions ZIP artifact
  → Worker Access-protected ZIP stream → Browser
```

Worker ไม่ดาวน์โหลด/แปลง media และไม่เก็บ database/Redis/queue. `fflate` ใช้แตกเฉพาะ sanitized report artifact ที่มีขนาดเล็ก; media ZIP ส่งจาก GitHub artifact แบบ stream โดยไม่ buffer ทั้งก้อนใน Worker

## Configuration

`control-worker/wrangler.toml` กำหนด non-secret values/bindings ได้แก่ GitHub owner/repo/workflow/ref, Dashboard origin, Access team domain/audience และ Static Assets จาก `../web`. Cloudflare secret store มี `ACCESS_ALLOWED_EMAIL` สำหรับ allowlist และ `GH_TOKEN` สำหรับ GitHub Actions API; secret values ไม่อยู่ใน source/Dashboard

เผยแพร่ source จาก root repo:

```bash
cd control-worker
npm ci
npm test
npx wrangler deploy --config wrangler.toml
```

การ publish HTML/static assets ใช้ config เดียวกันและ deploy พร้อม Worker source. ตรวจสถานะจาก Dashboard ผ่าน browser ที่ลงชื่อเข้าใช้ Access แล้ว; สำหรับ HTTP liveness ให้ตรวจเฉพาะ status code และไม่พิมพ์ Access redirect location หรือ auth query ลง log

## Endpoints

| Method/path | Auth | Behavior |
|---|---|---|
| `GET /` และ static assets | Cloudflare Access at edge + Worker JWT identity validation | เสิร์ฟ Dashboard จาก Worker origin; หน้าเว็บและ API ใช้ same-origin |
| `GET /auth/check` | Access JWT + owner email | ให้ Dashboard ตรวจ session ก่อนเปิดปุ่ม submit |
| `GET /health` | Cloudflare Access at edge | Liveness only; ไม่แสดง secret หรือยืนยัน upstream readiness |
| `POST /jobs` | Access JWT + owner email | รับ URL เดี่ยวหรือ batch 1–50; validate และ dispatch `destinations` ไปยัง workflow |
| `GET /jobs/<job_id>` | Access JWT + owner email | คืนสถานะและ sanitized report ต่อ destination/media |
| `GET /jobs/<job_id>/download` | Access JWT + owner email | ตรวจ run/artifact job-match/retention แล้ว stream private media ZIP ไป browser |

Worker ตรวจ Access JWT signature RS256 กับ Cloudflare JWKS, issuer, audience, expiration, not-before และ email allowlist. Request body hard cap 16 KiB; destination values allowlist คือ `telegram`, `mega`, `download`; URL ต้องเป็น HTTPS X/Twitter status URL. CORS จำกัด Dashboard origin เดียว; responses มี `Cache-Control: no-store`

## Dispatch และ idempotency

Request มี `request_id`, URL(s), `large_file_mode` และ optional `destinations`; หาก `destinations` ไม่มีให้ default เป็น Telegram. Worker normalize URL, ปฏิเสธ duplicate post IDs และคำนวณ `job_id` จาก request/payload รวม target list. Request ID เดิมกับ target/URL ที่เปลี่ยนจะเกิด `409 idempotency_conflict`; request เดิมจะคืน run ที่มีอยู่แทน dispatch ซ้ำ

Worker ส่ง `url` เมื่อมี URL เดียวหรือ `urls` newline-separated เมื่อเป็น batch, พร้อม `destinations` JSON array และ correlation IDs. Report sanitizer allowlist destinations/statuses/filenames, strip URLs/credential-like strings from errors และไม่คืน raw logs หรือ signed artifact URL

## ZIP streaming และ result mapping

Actions artifact ชื่อ `x2telegram-media-<run-id>` เป็น private, เก็บ 7 วัน และจำกัด total ZIP ที่ 8 GiB/job. Worker เลือก artifact เฉพาะชื่อ/run ที่ match กับ job และ stream `application/zip` พร้อม `Content-Disposition: attachment`. Artifact missing/expired ถูกแสดงเป็น Download target failure ไม่ใช่ ready state เท็จ

ผล Job เป็น `completed` ถ้ามีอย่างน้อยหนึ่ง destination success; target ที่ล้มเหลวยังคงรายงาน `failed`/`partial_success`. ถ้าทุก target ล้มเหลว job เป็น `failed`. Media-level statuses และ error codes ผ่าน sanitizer ก่อน Dashboard

## Tests และ live coverage

- Worker: `npm test --prefix control-worker` — **25 passed**, ครอบ Access/auth-check, static asset gate, destination validation/dispatch, idempotency, partial success, ZIP streaming และ missing artifact
- Python: `python3 -m pytest -q` — **71 passed**, ครอบ per-destination retry/dedupe, MEGA/Download fakes, size limits และ sanitization
- Live: Telegram normal path, 2-URL duplicate/no-resend batch, Download-only 2-URL + browser ZIP download ผ่าน
- MEGA account upload, combined Telegram+MEGA live run, Local Bot API large-file และ mobile browser ยังไม่ได้ live-test; MEGA ต้องมี repository Actions Secrets ตาม [`MULTI_DESTINATION.md`](MULTI_DESTINATION.md)

รายละเอียด API contract: [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md); Access policy: [`CLOUDFLARE_ACCESS.md`](CLOUDFLARE_ACCESS.md); ผลทดสอบ: [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md)
