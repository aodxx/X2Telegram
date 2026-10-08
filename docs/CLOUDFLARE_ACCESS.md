# Cloudflare Access — Zone 4

## สถานะการตั้งค่า

เอกสารนี้ระบุค่าที่ต้องตั้งสำหรับ Worker ที่วางแผนไว้ แต่ **ยังไม่มี Access policy ถูกสร้าง/เปิดใช้งาน**. ไม่ได้ deploy Worker ใน Zone 3 และ Cloudflare API ปฏิเสธการอ่าน Access applications ของ account ด้วย HTTP 403 (permission ไม่พอ). ไม่มีการแก้ Cloudflare account settings

ตรวจสอบแบบ read-only:

- API token เข้าถึง Cloudflare account เดียว (account identifier แสดงใน account inventory)
- account มี `workers.dev` subdomain `pantipa3826`
- API แสดง 0 Cloudflare DNS zones; อย่างไรก็ตาม Worker-level Access รองรับ `workers.dev` โดยไม่ต้องมี custom domain
- มี Worker เดิมชื่อ `raspy-darkness-422d`; `x2telegram-control-plane` ยังไม่อยู่ในรายการเมื่ออ่าน
- ไม่พบสิทธิ์/API access สำหรับ Access application endpoint; ยังยืนยันไม่ได้ว่า Zero Trust เปิดใช้หรือมี policy ที่ใช้งานจริงหรือไม่

Cloudflare รองรับ Worker-level Access ที่ครอบคลุม production `workers.dev`/routes/previews; ไม่จำเป็นต้องสร้าง custom DNS zone สำหรับรูปแบบนี้. อ้างอิง [Workers Access](https://developers.cloudflare.com/workers/configuration/cloudflare-access/) และ [workers.dev](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/)

## Configuration เป้าหมาย

เมื่อ Worker ถูก deploy, ใน Cloudflare Dashboard ไปที่ **Workers & Pages → `x2telegram-control-plane` → Access → Protect this Worker behind Access**:

1. เลือก **All traffic** (อย่าเลือกเฉพาะ preview)
2. policy decision `Allow`
3. Include เฉพาะ email identity ของเจ้าของที่ใช้ Dashboard (ไม่ใช้ `Everyone` และไม่ใช้ email domain กว้าง)
4. บันทึก Access app audience (AUD) และ team domain; ใส่ใน Worker vars `ACCESS_AUD`, `ACCESS_TEAM_DOMAIN`
5. ตั้ง `ACCESS_ALLOWED_EMAIL` ให้ตรง identity เดียวกัน เพื่อให้ Worker ตรวจซ้ำ
6. ตรวจว่า policy ครอบคลุม production `workers.dev` hostname ของ Worker

Access JWT ตรวจใน Worker ด้วย signature/JWKS, issuer, audience, expiry/not-before และ exact owner email. หาก Access ไม่ผ่าน JWT หรือ Worker configuration ขาด Worker ตอบ deny/error; ห้าม fallback ไปเปิด endpoint สาธารณะ

## CORS จาก GitHub Pages

Origin ที่ config ปัจจุบันตั้งไว้: `https://aodxx.github.io` (หาก GitHub Pages ใช้ custom domain ในอนาคต ต้องปรับทั้ง Wrangler var และ Dashboard config ให้ตรงกัน)

Dashboard ใช้ cross-origin `fetch(..., credentials: 'include')`; browser ต้องมี Access `CF_Authorization` cookie สำหรับ Worker host. เปิดลิงก์ **ลงชื่อเข้าใช้ API** ใน Dashboard ก่อน แล้วกลับมา refresh หน้า Dashboard

POST JSON ทำให้ browser ส่ง preflight `OPTIONS`. ตาม Cloudflare Access docs ให้ตั้ง application CORS response ให้ตรงกับ:

- Allowed origin: `https://aodxx.github.io`
- Allowed credentials: `true`
- Allowed methods: `GET, POST, OPTIONS`
- Allowed request headers: `Content-Type`

Worker ตอบ CORS เฉพาะ origin ข้างต้นและ `OPTIONS` เท่านั้น; CORS ไม่แทน authentication. ห้ามใช้ wildcard origin/credentials. หากเลือก bypass OPTIONS ถึง origin แทนการตั้ง CORS response ต้องรักษา exact-origin enforcement ใน Worker และทดสอบจริงก่อนใช้งาน

Cloudflare Access CORS reference: [Cross-Origin Resource Sharing](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/cors/). เอกสารระบุว่า Access preflight โดยค่าเริ่มต้นอาจถูกปฏิเสธก่อนถึง Worker; ต้องตั้งค่า CORS บน Access application ด้วย

## Rate limiting

Worker มี best-effort per-isolate cap 20 `POST /jobs` ต่อหนึ่งนาทีต่อ identity. เนื่องจาก memory ใน isolate ไม่ใช่ shared/durable state จึงไม่ใช่ global rate limit; สำหรับ production ให้ตั้ง rate limiting ที่ Cloudflare edge/Worker platform หาก account plan/permissions รองรับ และทดสอบ burst requests. Workflow concurrency และ dedupe ปกป้อง execution/delivery ต่อเนื่อง แต่ไม่ใช่ API flood control

## Verification checklist

- [ ] Worker-level Access policy เปิด All traffic บน Worker
- [ ] Allowed identities มีเพียงเจ้าของระบบ
- [ ] `GET /health` ใช้งานหลังผ่าน Access; unauthenticated call ถูกปฏิเสธโดย Access (ยกเว้นกรณี health endpoint ถูกตั้งเป็น public—ห้ามตั้งเช่นนั้นสำหรับ Access app production)
- [ ] Worker ตรวจ JWT issuer/AUD/exp/owner email
- [ ] GitHub Pages preflight ผ่านเฉพาะ origin ที่กำหนด
- [ ] Authenticated POST ผ่าน; unauthenticated และ identity อื่นไม่สามารถ dispatch
- [ ] burst test แสดง 429/edge limit ที่คาดไว้
- [ ] ไม่พบ credential ใน network responses/frontend/logs

## Blocker

การทำ policy จริงต้องมีสิทธิ์จัดการ Cloudflare Access และต้อง deploy Worker ก่อนเลือก Worker-level Access destination. ขณะนี้ API อ่าน Access applications ตอบ 403; ไม่ได้พยายามเขียน/แก้ configuration เพื่อหลีกเลี่ยงเปลี่ยน security boundary โดยไม่มี permission ที่ยืนยันแล้ว
