# Cloudflare Access — Zone 4

## สถานะปัจจุบัน (2026-10-08)

ตั้งค่า Cloudflare Zero Trust สำหรับ **X2Telegram Control Worker เท่านั้น** แล้ว:

- Access application: `X2Telegram Control Worker`
- ครอบคลุม production host: `x2telegram-control-plane.pantipa3826.workers.dev`
- Policy: `Allow` เฉพาะ owner email ที่ระบุไว้ในการอนุมัติ; ไม่มี `Everyone` หรือ domain-wide allow
- Login: Cloudflare One-time PIN (email OTP) provider และจำกัด `allowed_idps` ของแอปไว้ที่ provider นี้
- Session duration: 24 ชั่วโมง
- CORS: origin `https://aodxx.github.io`, credentials `true`, methods `GET, POST, OPTIONS`, request header `Content-Type`
- Worker ตรวจ JWT signature/JWKS, issuer, audience, expiry/not-before และ owner email ซ้ำใน runtime

ไม่พบ Access applications เดิมใน account ตอนตั้งค่า. การเพิ่ม One-time PIN เป็น identity provider เป็นวิธี login ที่เบาที่สุดเมื่อบัญชียังไม่มี login method; policy ยังจำกัดเฉพาะ Worker app และ owner identity.

## การยืนยันที่ทำแล้ว

- เปิด Worker hostname ใน browser แล้วถูกพาไปหน้า Access login; หลังตั้ง One-time PIN หน้าลงชื่อเข้าใช้แสดงฟอร์ม email และปุ่มส่งรหัส
- ทดสอบ unauthenticated POST จาก origin `https://aodxx.github.io`: browser ส่งต่อจนได้ opaque redirect จาก Access; ไม่มี Access session จึงไม่เข้าถึง API และไม่มี GitHub workflow ถูก dispatch
- ตั้งค่า preflight headers ใน Access app และ Worker exact-origin enforcement; ไม่ได้ใช้ wildcard origin
- `GH_TOKEN` อยู่ใน Worker เป็น secret ชนิด `secret_text`; ต้อง rotate ก่อน production เนื่องจากค่าแรกถูกแชร์ระหว่าง setup
- ยังไม่ได้ sign in ด้วย OTP จริง จึงยังไม่ทดสอบ API/job ที่ authenticated; ไม่มี workflow dispatch หรือ Telegram delivery

## CORS จาก GitHub Pages

Dashboard ใหม่ใช้ cross-origin `fetch(..., credentials: 'include')`; browser ต้องมี `CF_Authorization` cookie สำหรับ Worker host. การเปิดลิงก์ login ใน Dashboard จะไปยังหน้า Access; sign in ด้วย email OTP แล้วกลับมา refresh Dashboard.

Access application ตอบ preflight ตามค่าที่ระบุไว้ข้างต้น. Worker ยังตรวจ exact `Origin` เพิ่มอีกชั้น; CORS ไม่แทน authentication. หากเปลี่ยน custom domain ของ GitHub Pages ต้องปรับ CORS ใน Access app, `DASHBOARD_ORIGIN` ใน `wrangler.toml`, frontend config และ tests ให้ตรงกัน

## Rate limiting

Worker มี best-effort per-isolate cap 20 `POST /jobs` ต่อหนึ่งนาทีต่อ identity. เนื่องจาก memory ใน isolate ไม่ใช่ shared/durable state จึงไม่ใช่ global rate limit; สำหรับ production ให้ตั้ง rate limiting ที่ Cloudflare edge/Worker platform หาก account plan/permissions รองรับ และทดสอบ burst requests. Workflow concurrency และ dedupe ปกป้อง execution/delivery ต่อเนื่อง แต่ไม่ใช่ API flood control

## ขั้นตอนเข้าใช้งานครั้งแรกของเจ้าของ

1. เปิด <https://x2telegram-control-plane.pantipa3826.workers.dev/health> หรือกดลิงก์ **ลงชื่อเข้าใช้ API** ใน Dashboard
2. ใส่อีเมลที่ได้รับอนุญาต แล้วกด **Send login code**
3. เปิดอีเมลจาก Cloudflare, นำ One-time PIN มากรอก และกด sign in; PIN ใช้ครั้งเดียวและหมดอายุใน 10 นาที
4. กลับไป Dashboard แล้ว refresh; Cloudflare session มีอายุ 24 ชั่วโมง

ยังไม่มีการส่ง OTP ระหว่างตั้งค่า; จะส่งก็ต่อเมื่อเจ้าของกด Send login code เอง.

## Verification checklist

- [x] Worker-level Access application ครอบ hostname production
- [x] Allowed identities มีเฉพาะ owner
- [x] กำหนด email OTP provider และจำกัด app ให้ใช้ provider นี้เท่านั้น
- [x] Access CORS origin/method/header/credentials ตรงกับ Dashboard
- [x] Browser unauthenticated request ถูก redirect ไปหน้า Access login
- [ ] เจ้าของ sign in ด้วย OTP สำเร็จและ authenticated `GET /health` ผ่าน
- [x] GitHub Actions credential ถูกเก็บเป็น Worker secret `GH_TOKEN` (`secret_text`)
- [ ] Rotate `GH_TOKEN` เป็นค่าใหม่ก่อน production
- [ ] Authenticated submit/status/report ผ่านด้วย test case ที่ไม่ส่ง Telegram
- [ ] ทดสอบ burst/rate-limit ที่ production configuration
- [ ] ไม่พบ credential ใน network responses/frontend/logs

**ข้อจำกัดปัจจุบัน:** Worker deploy, Access และ `GH_TOKEN` secret พร้อม แต่ยังไม่มี authenticated test; token ปัจจุบันควรถูก rotate ก่อน production. อย่า merge PR #2 หรือเปลี่ยนหน้า GitHub Pages production จนกว่าเจ้าของจะ sign in, rotate token และผ่าน authenticated verification.
