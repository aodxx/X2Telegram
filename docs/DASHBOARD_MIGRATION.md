# Dashboard Migration — Zone 5

## เปลี่ยนแปลง

`web/index.html` เปลี่ยนจาก Apps Script action API ไปยัง Cloudflare Control Worker:

- health check: `GET /health`
- submit: `POST /jobs` พร้อม JSON `{url, large_file_mode, request_id}`
- poll/restore: `GET /jobs/<job_id>`
- browser fetch ใช้ `credentials: include` สำหรับ Cloudflare Access cookie; ไม่มี GitHub/Telegram credential
- request body ไม่ใส่ X URL ใน query string
- Dashboard บังคับหนึ่ง X URL ต่อหนึ่ง job ตาม Zone 1 contract
- `request_id` ถูก persist ไว้ก่อนส่งเพื่อให้ refresh/network retry ใช้ ID เดิม
- current job เก็บใน localStorage และ recover โดย retry POST ด้วย request ID เดิมเมื่อ response แรกสูญหาย
- recent jobs สูงสุด 10 รายการเก็บเฉพาะใน browser localStorage; กดรายการเพื่อโหลด status/report จาก Worker
- แสดง accepted/duplicate/processing/completed/failed พร้อม error ภาษาอ่านง่าย, result, Telegram message IDs และ GitHub run link เมื่อมี
- เพิ่ม link เปิด `/health` ของ API เพื่อให้ลงชื่อเข้าใช้ Access ก่อนเรียก cross-origin API
- `web/config.js` มีเฉพาะ public API base URL; ห้ามใส่ secrets

## Settings

```js
window.X2TELEGRAM_CONFIG = Object.freeze({
  apiBase: "https://x2telegram-control-plane.pantipa3826.workers.dev",
});
```

Worker URL เป็นค่าที่คำนวณจาก account `workers.dev` subdomain และ Wrangler Worker name; endpoint **ยังไม่ได้ deploy** ใน Zone 1–5. Dashboard จึงยังเรียก production API ไม่ได้จนกว่าจะ deploy/ผูก Access/ตั้ง GitHub secret ตาม checklist ใน `docs/CLOUDFLARE_WORKER.md` และ `docs/CLOUDFLARE_ACCESS.md`

## UI states

- Idle / URL review / Submitting
- Accepted / Duplicate / Processing
- Completed / Failed
- Invalid URL, Unauthorized, Forbidden, Rate limited, Worker/GitHub error
- Worker/API not configured or unreachable

## Security notes

- Frontend เก็บ `request_id`, job IDs, URL ที่ผู้ใช้ submit และ recent-job metadata ใน localStorage ของ browser เครื่องนั้น; ไม่มี server-side recent jobs
- API ใช้ exact-origin CORS และ `credentials: include`; Cloudflare Access ต้องตั้ง CORS preflight OPTIONS สำหรับ Pages origin แยกต่างหาก
- การเปิด API URL ผ่าน link ช่วยสร้าง Access session สำหรับ Worker hostname; หลัง login ให้กลับมา refresh Dashboard
- Dashboard result เป็น sanitized artifact เท่านั้น; ไม่แสดง Telegram token, GitHub token, raw logs หรือ media URLs

## Verification

- ตรวจ HTML/JS syntax และ static source checks
- Offline Worker tests ครอบคลุม API shape, dispatch/status/report, auth validation และ CORS
- Browser-to-Worker, real Access login, GitHub dispatch และ Telegram delivery ยังไม่ได้ทดสอบ end-to-end เพราะ Worker ยังไม่ deploy/Access configuration ยังติด permission
