# Cloudflare Control Worker

## สถานะ live (2026-10-12)

- Worker `x2telegram-control-plane` ใช้งานที่ <https://x2telegram-control-plane.pantipa3826.workers.dev>
- Version ID ปัจจุบัน: `c44298fb-47f9-4798-a3db-9cd6946018fb`
- Source: `main`, commit `fe3170fb3fc23cf06ee8a9a838866e38d207480c`
- Deploy ผ่าน GitHub Actions run [#38171587335](https://github.com/aodxx/X2Telegram/actions/runs/38171587335) และใช้ `JOB_DISPATCH_RATE_LIMITER` 20 requests/60 seconds
- Cloudflare Access จำกัด hostname นี้ตาม email owner policy; Dashboard static assets และ API อยู่ origin เดียวกัน
- Worker-hosted Dashboard แสดง Access session ผ่าน browser จริงและมี destination selectors
- Live Download-only run #37843359593 ประมวลผล 2 URLs และ browser ดาวน์โหลด ZIP จริงผ่าน protected endpoint; report มี Download 2 files พร้อม ZIP CRC check ผ่าน
- Live Telegram normal-path run #37807253687 และ Dashboard batch/no-resend run #37816856323 ยังคงเป็นหลักฐาน Telegram/batch ก่อน multi-destination
- Live MEGA-only run [#37848879753](https://github.com/aodxx/X2Telegram/actions/runs/37848879753) ผ่าน; Dashboard report แสดง MEGA สำเร็จ 1 รายการโดยไม่เลือก Telegram หรือ Browser ZIP

## Architecture

```text
GitHub Pages URL redirect
  → Cloudflare Access
  → Worker static Dashboard + API (same origin)
  → GitHub Actions workflow_dispatch (one workflow)
  → Python media processor (download/validate once per media)
  → Telegram / MEGA / Dropbox / private Actions ZIP artifact
  → Worker Access-protected ZIP stream → Browser
```

Worker ไม่ดาวน์โหลด/แปลง media และไม่เก็บ database/Redis/queue. `fflate` ใช้แตกเฉพาะ sanitized report artifact ที่มีขนาดเล็ก; media ZIP ส่งจาก GitHub artifact แบบ stream โดยไม่ buffer ทั้งก้อนใน Worker

## Configuration

`control-worker/wrangler.toml` กำหนด non-secret values/bindings ได้แก่ GitHub owner/repo/workflow/ref, Dashboard origin, Access team domain/audience และ Static Assets จาก `../web`. Cloudflare secret store มี `ACCESS_ALLOWED_EMAIL` สำหรับ identity หลัก, optional `ACCESS_ADDITIONAL_EMAIL` สำหรับ identity ที่สองซึ่งอนุมัติเป็นรายอีเมล, และ `GH_TOKEN` สำหรับ GitHub Actions API; secret values ไม่อยู่ใน source/Dashboard. Worker ยอมรับเฉพาะ email claim ที่ตรงกับหนึ่งในสอง bindings นี้แบบ exact (case-insensitive); ห้ามแทนค่าบัญชีหลักเมื่อต้องเพิ่มบัญชีที่สอง

เผยแพร่ source จาก root repo:

```bash
cd control-worker
npm ci
npm test
npx wrangler deploy --config wrangler.toml  # local/manual; production ใช้ .github/workflows/deploy-worker.yml
```

การ publish HTML/static assets ใช้ config เดียวกันและ deploy พร้อม Worker source. **หมายเหตุ:** source route `/health` ไม่เรียก `verifyAccess()` แต่ Cloudflare Access เป็น edge layer แยกจาก Worker จึงสามารถ redirect ก่อนถึง Worker ได้ตาม production behavior ปัจจุบัน ตรวจสถานะจาก Dashboard ผ่าน browser ที่ลงชื่อเข้าใช้ Access แล้ว; สำหรับ HTTP liveness ให้ตรวจเฉพาะ status code และไม่พิมพ์ Access redirect location หรือ auth query ลง log

## Endpoints

| Method/path | Auth | Behavior |
|---|---|---|
| `GET /` และ static assets | Cloudflare Access at edge + Worker JWT identity validation | เสิร์ฟ Dashboard จาก Worker origin; หน้าเว็บและ API ใช้ same-origin |
| `GET /auth/check` | Access JWT + owner email | ให้ Dashboard ตรวจ session ก่อนเปิดปุ่ม submit |
| `GET /health` | Worker route ไม่ต้องใช้ JWT; **production edge ยังถูก Cloudflare Access ครอบอยู่** | Liveness only; ไม่แสดง secret หรือยืนยัน upstream readiness. หากต้องการ public monitoring ต้องตั้ง Access bypass เฉพาะ path นี้ |
| `POST /jobs` | Access JWT + owner email | รับ URL เดี่ยวหรือ batch 1–50; validate และ dispatch `destinations` ไปยัง workflow |
| `GET /jobs/<job_id>` | Access JWT + owner email | คืนสถานะและ sanitized report ต่อ destination/media |
| `GET /jobs/<job_id>/download` | Access JWT + owner email | ตรวจ run/artifact job-match/retention แล้ว stream private media ZIP ไป browser |

Worker ตรวจ Access JWT signature RS256 กับ Cloudflare JWKS, issuer, audience, expiration, not-before และ email allowlist. `POST /jobs` ใช้ `JOB_DISPATCH_RATE_LIMITER` 20 requests/60 seconds ต่อ Access identity; binding error fail-closed เป็น `503 rate_limiter_unavailable`. Request body hard cap 16 KiB; destination values allowlist คือ `telegram`, `mega`, `dropbox`, `download`; URL ต้องเป็น HTTPS X/Twitter status URL. CORS จำกัด Dashboard origin เดียว; responses มี `Cache-Control: no-store`

## Dispatch และ idempotency

Request มี `request_id`, URL(s), `large_file_mode` และ optional `destinations`; หาก `destinations` ไม่มีให้ default เป็น Telegram. Worker normalize URL, ปฏิเสธ duplicate post IDs และคำนวณ `job_id` จาก request/payload รวม target list. Request ID เดิมกับ target/URL ที่เปลี่ยนจะเกิด `409 idempotency_conflict`; request เดิมจะคืน run ที่มีอยู่แทน dispatch ซ้ำ

Worker ส่ง `url` เมื่อมี URL เดียวหรือ `urls` newline-separated เมื่อเป็น batch, พร้อม `destinations` JSON array และ correlation IDs. Report sanitizer allowlist destinations/statuses/filenames, strip URLs/credential-like strings from errors และไม่คืน raw logs หรือ signed artifact URL

## ZIP streaming และ result mapping

Actions artifact ชื่อ `x2telegram-media-<run-id>` เป็น private, เก็บ 7 วัน และจำกัด total ZIP ที่ 8 GiB/job. Worker เลือก artifact เฉพาะชื่อ/run ที่ match กับ job และ stream `application/zip` พร้อม `Content-Disposition: attachment`. Artifact missing/expired ถูกแสดงเป็น Download target failure ไม่ใช่ ready state เท็จ

ผล Job เป็น `completed` ถ้ามีอย่างน้อยหนึ่ง destination success; target ที่ล้มเหลวยังคงรายงาน `failed`/`partial_success`. ถ้าทุก target ล้มเหลว job เป็น `failed`. Media-level statuses และ error codes ผ่าน sanitizer ก่อน Dashboard

## Tests และ live coverage

- Worker: `npm test --prefix control-worker` — **27 passed**, ครอบ Access/auth-check, static asset gate, destination validation/dispatch, idempotency, rate limiter binding/fail-closed, partial success, ZIP streaming และ missing artifact
- Python: `python3 -m pytest -q` — **95 passed**, ครอบ per-destination retry/dedupe, privacy-minimized state, MEGA/Dropbox/Download fakes, size limits และ sanitization
- Live: Telegram normal path, 2-URL duplicate/no-resend batch, Download-only 2-URL + browser ZIP download และ MEGA-only upload ผ่าน
- Combined Telegram+MEGA live run, Local Bot API large-file และ mobile browser ยังไม่ได้ live-test; การทดสอบปลายทางรวมมี automated coverage. Production deploy ล่าสุดผ่านแล้ว แต่ไม่ได้สร้างงานส่ง media ใหม่

รายละเอียด API contract: [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md); Access policy: [`CLOUDFLARE_ACCESS.md`](CLOUDFLARE_ACCESS.md); ผลทดสอบ: [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md)
