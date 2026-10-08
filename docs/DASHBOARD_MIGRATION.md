# Dashboard Migration — Access UX และ URL batches

## สถาปัตยกรรมปัจจุบัน

```text
GitHub Pages link → redirect → Cloudflare Access + Worker-hosted Dashboard/API → GitHub Actions → X2Telegram → Telegram
```

หน้าเดิมจาก GitHub Pages ต่าง origin กับ `workers.dev`; browser บางตัวจึงไม่ส่ง Access cookie ใน cross-site fetch ทำให้ login แล้วหน้าเดิมยังมองว่าไม่ได้ login. Dashboard assets ถูกเสิร์ฟจาก Cloudflare Worker host ที่ป้องกันด้วย Access เดียวกับ API; GitHub Pages URL ทำหน้าที่พาไป origin นี้. Worker ตรวจ JWT ทั้งบนหน้า static assets และ API routes.

## API และ authentication

- `GET /auth/check`: endpoint ที่ต้องผ่าน Access JWT; Dashboard ใช้ยืนยันว่าลงชื่อเข้าใช้จริงก่อนเปิดปุ่มส่ง
- `GET /health`: liveness endpoint สำหรับตรวจว่า Worker ตอบสนอง
- `POST /jobs`: รับ `url` หนึ่งรายการเพื่อ backward compatibility หรือ `urls` array 1–50 รายการ; ห้ามส่งทั้งสองแบบพร้อมกัน
- `GET /jobs/<job_id>`: อ่านสถานะและ sanitized report
- Dashboard ใช้ `credentials: include`; เมื่อเสิร์ฟหน้าและ API จาก Worker origin เดียวกัน cookie เป็น first-party ไม่พึ่ง third-party-cookie behavior
- ปุ่ม Access เปิด Worker-hosted Dashboard ในแท็บใหม่; เมื่อกลับแท็บเดิม ระบบตรวจสถานะอีกครั้งบน focus/visibility change

## Batch behavior

- วางหนึ่ง URL ต่อบรรทัด; limit สูงสุด 50 รายการต่อ job
- Frontend preview แสดงจำนวน, URL ที่ผ่าน, URL ผิด และ duplicate; รายการผิด/ซ้ำหรือเกิน limit จะปิดปุ่มส่ง
- Worker ตรวจชนิด/รูปแบบ URL ซ้ำอีกครั้ง และปฏิเสธ duplicate post ID
- Worker normalize URL แล้ว map หนึ่ง URL ไปยัง workflow input `url`; หลาย URL ไปยัง workflow input `urls` แบบหนึ่ง URL ต่อบรรทัด
- หนึ่ง batch เป็นหนึ่ง GitHub Actions run; report แสดงผลแยกรายโพสต์
- `request_id` ถูก persist ก่อนส่ง; `job_id` เป็น deterministic fingerprint จาก request ID, URL ที่ normalize แล้วเรียงตาม input, และโหมด large-file
- Workflow รองรับ `url`/`urls` อยู่แล้ว; Python worker ยังคงอ่าน batch จาก `INPUT_URLS`

## Static assets และ settings

`control-worker/wrangler.toml` ผูก `../web` เป็น Static Assets และตั้ง `run_worker_first = true`; Worker ตรวจ Access ก่อนเรียก `env.ASSETS.fetch(request)`. `DASHBOARD_ORIGIN` เป็น Worker origin เดียวกับ `apiBase`:

```js
window.X2TELEGRAM_CONFIG = Object.freeze({
  apiBase: "https://x2telegram-control-plane.pantipa3826.workers.dev",
});
```

หน้า GitHub Pages จะ redirect เฉพาะ repository path `/X2Telegram` ไปยัง Worker dashboard. Static assets ไม่มี GitHub/Telegram credentials.

## ข้อจำกัดและการตรวจ

- Batch มากกว่า 50 รายการต้องแบ่งเป็นหลายชุด
- Live batch E2E run `37816856323` dispatch 2 URL ใน Actions run เดียวและจบสำเร็จ; ทั้งคู่มี completed dedupe records จึง `skipped_duplicate` และไม่มีการส่ง Telegram ซ้ำ. นี่ยืนยัน live batch dispatch/no-resend แต่ยังไม่ใช่การทดสอบส่ง media ใหม่หลายโพสต์ใน batch
- สถานะงานล่าสุดเก็บใน browser `localStorage`; ไม่มี server-side history database
- ผลการส่ง Telegram ดูจาก sanitized report artifact และ message IDs; network timeout หลัง Telegram รับไฟล์ยังต้องตรวจผลก่อน retry
