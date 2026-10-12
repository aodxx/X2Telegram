# Cloudflare Access — Zone 4

## สถานะปัจจุบัน (2026-10-13)

ตั้งค่า Cloudflare Zero Trust สำหรับ **X2Telegram Control Worker เท่านั้น** แล้ว:

- Access application: `X2Telegram Control Worker`
- ครอบคลุม production host: `x2telegram-control-plane.pantipa3826.workers.dev`
- Policy: `Allow X2Telegram approved emails` จำกัดเฉพาะสอง exact email entries (primary + secondary ที่อนุมัติ); ไม่มี `Everyone` หรือ domain-wide allow
- Login: Cloudflare One-time PIN (email OTP) provider และจำกัด `allowed_idps` ของแอปไว้ที่ provider นี้
- Session duration: 24 ชั่วโมง
- CORS: origin `https://aodxx.github.io`, credentials `true`, methods `GET, POST, OPTIONS`, request header `Content-Type`
- Worker ตรวจ JWT signature/JWKS, issuer, audience, expiry/not-before และอีเมลที่ตรงกับ `ACCESS_ALLOWED_EMAIL` หรือ `ACCESS_ADDITIONAL_EMAIL` ซ้ำใน runtime; secret primary เดิมยังคงอยู่

ไม่พบ Access applications เดิมใน account ตอนตั้งค่า. การเพิ่ม One-time PIN เป็น identity provider เป็นวิธี login ที่เบาที่สุดเมื่อบัญชียังไม่มี login method; policy ยังคงจำกัดเฉพาะ Worker app และอีเมลสองรายการที่ระบุแบบ exact.

## การยืนยันที่ทำแล้ว

- เปิด Worker hostname ใน browser แล้วถูกพาไปหน้า Access login; หลังตั้ง One-time PIN หน้าลงชื่อเข้าใช้แสดงฟอร์ม email และปุ่มส่งรหัส
- ทดสอบ unauthenticated POST จาก origin `https://aodxx.github.io`: browser ส่งต่อจนได้ opaque redirect จาก Access; ไม่มี Access session จึงไม่เข้าถึง API และไม่มี GitHub workflow ถูก dispatch
- ตั้งค่า preflight headers ใน Access app และ Worker exact-origin enforcement; ไม่ได้ใช้ wildcard origin
- เจ้าของ sign in ด้วย OTP แล้ว; authenticated `GET /health` ตอบ `200`, และ `GET /jobs/<random-id>` ตอบ expected `404 job_not_found` จาก GitHub-backed lookup
- PR [#25](https://github.com/aodxx/X2Telegram/pull/25) เพิ่ม optional second exact-email identity; production Worker version `649353cf-fd9a-498b-9415-14bae01de486` (deploy [#38295769200](https://github.com/aodxx/X2Telegram/actions/runs/38295769200)) มี `ACCESS_ADDITIONAL_EMAIL`; Access policy มี email rule สองรายการและไม่มี `Everyone`/domain-wide rule
- ผู้ใช้รองยังไม่ได้ sign in ด้วย OTP; ยังไม่มีการส่ง login code ระหว่าง rollout จึงยังไม่มีหลักฐาน authenticated session ของบัญชีนี้
- หลัง deploy hardening ทดสอบจาก GitHub Pages origin: `GET /health` ได้ `200`, invalid URL POST ได้ `400 invalid_url`, body 17 KiB ได้ `413 request_too_large`; ทั้งสอง POST ถูกปฏิเสธก่อน dispatch
- Normal-path E2E ผ่านเมื่อ 2026-10-08: run `37807253687` สำเร็จ, sanitized report คืน `sent=1`, Telegram `message_id=347`; Worker ถูกคืน `GH_REF=main` หลังทดสอบ

## Dashboard origin และ login flow

Dashboard assets และ API อยู่บน Worker hostname เดียวกันเพื่อให้ `CF_Authorization` cookie เป็น first-party. GitHub Pages URL ทำหน้าที่ redirect ไปยัง Worker-hosted Dashboard ก่อนมีการเรียก API. Worker ตรวจ Access JWT สำหรับ static assets และ API; Dashboard ใช้ `GET /auth/check` แทนการอนุมานสถานะ login จาก liveness endpoint.

Worker ตั้ง `DASHBOARD_ORIGIN` เป็น `https://x2telegram-control-plane.pantipa3826.workers.dev` และตรวจ exact origin. Access app ยังคงมี CORS allowlist เดิมสำหรับ GitHub Pages เพื่อ compatibility; same-origin Dashboard ไม่พึ่ง cross-origin preflight. CORS ไม่แทน authentication. หากเปลี่ยน Worker host ให้ปรับ Access app, `DASHBOARD_ORIGIN`, frontend config และ tests ให้ตรงกัน

## Rate limiting

Worker มี fallback best-effort per-isolate cap 20 `POST /jobs` ต่อหนึ่งนาทีต่อ identity. สำหรับ production เพิ่ม Cloudflare Workers Rate Limiting binding ชื่อ `JOB_DISPATCH_RATE_LIMITER` ใน `control-worker/wrangler.toml` ที่ 20 ครั้ง/60 วินาที โดยใช้ key `jobs:<Access email>`; เมื่อ binding มีอยู่ Worker จะใช้ binding และ fail-closed เป็น `503 rate_limiter_unavailable` หาก binding error. Cloudflare binding ช่วยกระจายการนับระดับ edge แต่เอกสาร Cloudflare ระบุว่า counter แยกตาม Cloudflare location และ eventually consistent จึงไม่ใช่ global exact accounting. หากต้องการ hard global block ข้ามทุก location ให้เพิ่ม Cloudflare WAF Rate Limiting Rule ที่ route `/jobs` เป็นชั้นนอกเพิ่มเติม. Local unit tests ครอบทั้ง binding `429` และ fail-closed; ต้อง deploy และทดสอบ burst/cross-location จริงหลังยืนยัน namespace ID ไม่ชนกับ binding อื่น. Workflow concurrency และ dedupe ปกป้อง execution/delivery ต่อเนื่อง แต่ไม่ใช่ API flood control

## ขั้นตอนเข้าใช้งานครั้งแรกของผู้ใช้ที่ได้รับอนุญาต

1. เปิด <https://aodxx.github.io/X2Telegram/>; ระบบจะ redirect ไปยัง Worker-hosted Dashboard หรือกดลิงก์ **ลงชื่อเข้าใช้** ใน Dashboard เพื่อเปิด origin เดียวกันในแท็บใหม่
2. ใส่อีเมลที่ได้รับอนุญาตแบบ exact แล้วกด **Send login code**
3. เปิดอีเมลจาก Cloudflare, นำ One-time PIN มากรอก และกด sign in; PIN ใช้ครั้งเดียวและหมดอายุใน 10 นาที
4. หลังยืนยัน OTP จะกลับมายัง Dashboard. เมื่อกลับไปแท็บเดิม ระบบตรวจ `/auth/check` ซ้ำอัตโนมัติ; Cloudflare session มีอายุ 24 ชั่วโมง

ไม่มีการส่ง OTP ระหว่างตั้งค่า rollout นี้; Cloudflare จะส่งรหัสเมื่อผู้ใช้ที่ได้รับอนุญาตกด **Send login code** เองเท่านั้น.

## Verification checklist

- [x] Worker-level Access application ครอบ hostname production
- [x] Allowed identities มีสอง exact email entries ที่ได้รับอนุมัติ; ไม่มี `Everyone` หรือ domain-wide rule
- [x] กำหนด email OTP provider และจำกัด app ให้ใช้ provider นี้เท่านั้น
- [x] Access CORS origin/method/header/credentials ตรงกับ Dashboard
- [x] Browser unauthenticated request ถูก redirect ไปหน้า Access login
- [x] เจ้าของ sign in ด้วย OTP สำเร็จและ authenticated `GET /health` ผ่าน
- [x] GitHub Actions credential ถูกเก็บเป็น Worker secret `GH_TOKEN` (`secret_text`) และเปลี่ยนค่าแล้ว
- [x] Authenticated status lookup อ่าน GitHub Actions ได้ (สุ่ม job ID, ได้ expected 404; ไม่ dispatch)
- [x] Live cross-origin invalid URL และ oversized-body validation ถูก reject ก่อน dispatch
- [x] Authenticated report retrieval ผ่านจาก run ที่มี artifact
- [x] Normal-path E2E dispatch จริง/ส่ง Telegram ผ่านโดยใช้ URL ที่เจ้าของอนุมัติหนึ่งรายการ (รายละเอียดใน `E2E_TEST_REPORT.md`)
- [ ] E2E scenarios ที่เหลือ: multi-photo live, partial-failure live recovery, UI refresh, mobile และ Telegram Local Bot API large-file
- [x] Local test ยืนยัน per-isolate fallback: 21st POST ได้ `429` โดยไม่ dispatch
- [x] Production deploy ยืนยัน `JOB_DISPATCH_RATE_LIMITER` binding 20 requests/60 seconds
- [x] Worker มี primary `ACCESS_ALLOWED_EMAIL` และ optional `ACCESS_ADDITIONAL_EMAIL`; Access policy อนุญาตตรงกับสอง identity
- [ ] ผู้ใช้รอง sign in ด้วย OTP และยืนยัน Dashboard session ด้วยตนเอง
- [ ] ไม่พบ credential ใน network responses/frontend/logs

**สถานะปัจจุบัน:** Worker และ Dashboard production live แล้ว; Access ครอบ hostname และจำกัดไว้ที่สอง exact email identities. `GET /` แบบไม่มี Access session ยังคงตอบ HTTP 302 ไป Cloudflare Access. ผู้ใช้รองต้องกดส่ง OTP และยืนยัน session เองก่อนจึงจะนับว่าทดสอบ login end-to-end แล้ว; ไม่มี OTP ถูกส่งโดย agent.
