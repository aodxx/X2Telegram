# X2Telegram Google Apps Script Backend

โฟลเดอร์นี้เป็น control-plane backend สำหรับ Dashboard ของ X2Telegram โดยให้ GitHub Actions ยังคงเป็น execution plane เดิม

```text
GitHub Pages → Apps Script Web App → GitHub Actions → Telegram
                                      ↓
                            private dashboard artifact
```

## ความรับผิดชอบของ backend

- `GET ?action=health` — ตรวจ backend/config
- `GET ?action=start&payload=...` — fallback สำหรับ Dashboard เพื่อเริ่มงานผ่าน GET เมื่อ browser จัดการ redirect ของ POST ไม่ได้
- `POST` `{"action":"start", ...}` — ตรวจ URL และเรียก `workflow_dispatch`
- `GET ?action=status&run_id=...` — ตรวจสถานะ workflow
- `GET ?action=report&run_id=...` — ดาวน์โหลดและอ่าน sanitized artifact
- ใช้ `LockService` ป้องกัน start พร้อมกัน
- ใช้ `CacheService` ป้องกัน idempotency key ซ้ำและ cache report ชั่วคราว
- ไม่รับหรือเก็บ Telegram token

## ตั้งค่า Script Properties

สร้าง Apps Script project แล้ววาง `Code.gs` จากโฟลเดอร์นี้ จากนั้นตั้งค่า **Project Settings → Script properties**:

| Property | ตัวอย่าง | รายละเอียด |
|---|---|---|
| `GITHUB_TOKEN` | `github_pat_...` | Fine-grained token สำหรับ repository เดียว ห้ามใส่ใน frontend |
| `GITHUB_OWNER` | `aodxx` | GitHub owner |
| `GITHUB_REPO` | `X2Telegram` | ชื่อ repository |
| `GITHUB_WORKFLOW_ID` | `x2telegram.yml` | workflow file หรือ workflow ID |
| `GITHUB_REF` | `main` | branch ที่จะ dispatch |
| `ALLOWED_EMAILS` | `your@gmail.com` | รายชื่อ Google account ที่อนุญาต คั่นด้วย comma |
| `MAX_URLS` | `20` | จำนวน URL สูงสุดต่อ request |

### GitHub token permissions

ใช้ fine-grained token ที่จำกัด repository นี้เท่านั้น และให้สิทธิ์เท่าที่จำเป็น:

- Actions: **Read and write** — dispatch workflow และอ่าน runs/artifacts
- Metadata: **Read**
- Contents: **Read** เท่าที่จำเป็นสำหรับ repository

ห้ามนำ token ไปใส่ใน `web/index.html`, query string หรือ response ของ API

## Deploy เป็น Web app

1. เปิด Apps Script project
2. Deploy → New deployment → Web app
3. ตั้ง **Execute as** เป็นเจ้าของ script
4. ตั้งผู้มีสิทธิ์เข้าถึงให้สอดคล้องกับ Google account ที่อยู่ใน `ALLOWED_EMAILS`
5. คัดลอก Web app URL ไปใช้ใน frontend

> ไม่ควร deploy เป็น anonymous ถ้าต้องการ private dashboard เพราะ `Session.getActiveUser().getEmail()` อาจว่างและไม่สามารถตรวจสิทธิ์ได้

## API examples

### Health

```text
GET https://script.google.com/macros/s/DEPLOYMENT_ID/exec?action=health
```

### Start

```json
{
  "action": "start",
  "urls": [
    "https://x.com/user/status/1234567890",
    "https://x.com/user/status/1234567891?s=20"
  ],
  "large_file_mode": false,
  "request_id": "dashboard-abc123",
  "idempotency_key": "dashboard-submit-abc123"
}
```

Response เมื่อหา run ได้ทันที:

```json
{
  "ok": true,
  "data": {
    "request_id": "dashboard-abc123",
    "run_id": "37010000000",
    "status": "queued",
    "html_url": "https://github.com/..."
  }
}
```

GitHub อาจใช้เวลาสร้าง run หลัง dispatch; กรณีนี้ `run_id` อาจเป็น `null` และให้ polling ด้วย `request_id`:

```text
GET .../exec?action=status&request_id=dashboard-abc123
```

### Status และ report

```text
GET .../exec?action=status&run_id=37010000000
GET .../exec?action=report&run_id=37010000000
```

เมื่อ workflow เสร็จ backend จะหา artifact ชื่อ:

```text
x2telegram-dashboard-report-37010000000
```

แล้วอ่าน `dashboard-report.json` จาก zip โดยใช้ GitHub token ฝั่ง Apps Script เท่านั้น

## ข้อจำกัดที่ต้องรู้

- Apps Script `ContentService` ไม่เปิดให้กำหนด CORS header แบบอิสระ; ต้องทดสอบการเรียกจาก GitHub Pages จริงก่อนเชื่อม frontend
- บาง browser/proxy อาจเปลี่ยน POST redirect ของ Apps Script เป็น `405 Method Not Allowed`; Dashboard จึงใช้ GET start fallback ที่ส่ง payload เป็น base64url และจำกัดความยาว payload
- หาก cross-origin `fetch()` ใช้ไม่ได้ ให้พิจารณาใช้ Apps Script HTML Service เป็น frontend เดียวกัน หรือทำ proxy ที่รองรับ CORS
- Apps Script มี execution time และ quota จำกัด จึงไม่ควรให้ backend รอ workflow จนเสร็จใน request เดียว
- `start` คืนเร็ว แล้ว frontend ต้อง polling ทุก 5–10 วินาที
- artifact download ใช้ GitHub API แบบ authenticated และ report ที่ frontend ได้เป็น sanitized projection เท่านั้น
- ต้องตรวจสิทธิ์ artifact/repository ของ public repository ก่อน production; หากต้องการ privacy สูงสุดควรใช้ private repository สำหรับ workflow/report
