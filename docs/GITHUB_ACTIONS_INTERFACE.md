# GitHub Actions Interface

`.github/workflows/x2telegram.yml` เป็น execution workflow หลักเพียง workflow เดียว. Worker ส่ง input ของ job และ Python worker ประมวลผล media หนึ่งครั้งก่อน dispatch ไปยัง destination ที่เลือก

## `workflow_dispatch` inputs

| Input | Required | Default | ความหมาย |
|---|---:|---|---|
| `url` | no | empty | URL เดี่ยว; backward-compatible |
| `urls` | no | empty | URL หลายรายการ คั่นด้วย newline; Dashboard batch/manual input |
| `destinations` | no | `['telegram']` | JSON array จาก `telegram`, `mega`, `dropbox`, `download` |
| `large_file_mode` | yes | `false` | ใช้ Local Bot API สำหรับ Telegram ไฟล์ใหญ่เมื่อเลือก Telegram |
| `request_id` | no | empty | idempotency/correlation key |
| `job_id` | no | empty | opaque job identifier ใน run title/report |

ส่ง `url` หรือ `urls` อย่างใดอย่างหนึ่งเท่านั้น. Dashboard ส่ง `url` เมื่อมีโพสต์เดียว หรือ `urls` newline-separated เมื่อมีหลายโพสต์; destinations จะส่งเป็น JSON array. หาก manual dispatch ไม่ระบุ destination ระบบ default เป็น Telegram

ตัวอย่างเลือก Telegram+Download:

```json
["telegram", "download"]
```

ค่า destinations ที่ว่าง, ซ้ำ หรือไม่อยู่ใน allowlist ถูกปฏิเสธใน Worker/Python validation. การเปลี่ยน destinations ขณะใช้ `request_id` เดิมถือเป็น payload เปลี่ยนและได้ idempotency conflict

## Runtime และ secrets

| Secret | ใช้เมื่อ |
|---|---|
| `TELEGRAM_BOT_TOKEN` | เลือก Telegram |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | Telegram Large-file mode |
| `MEGA_EMAIL`, `MEGA_PASSWORD` | เลือก MEGA |
| `MEGA_TOTP_SECRET` | บัญชี MEGA เปิด TOTP/MFA |
| `ALERT_WEBHOOK_URL` | ตั้งค่า alert เพิ่มเติม |

`TELEGRAM_CHAT_ID` ถูกกำหนดใน workflow; ไม่มี secret ส่งจาก frontend. MEGAcmd setup ทำเฉพาะเมื่อเลือก MEGA และความล้มเหลวของ installation/login/upload อยู่ใน destination result เพื่อให้ target อื่นทำงานต่อ. Download files ถูก upload เป็น private Actions artifact 7 วัน (ต่อ job รวมไม่เกิน 8 GiB)

## Process stages

1. Checkout และติดตั้ง Python dependencies
2. รัน Python และ Worker regression tests
3. ติดตั้ง MEGAcmd เมื่อเลือก MEGA; เริ่ม Local Bot API เฉพาะเมื่อเปิด Large-file mode+เลือก Telegram
4. Normalize `url`/`urls`, ส่ง input ไป Python CLI พร้อม `DESTINATIONS_JSON`
5. ประมวลผล media; download/validate หนึ่งครั้งและ dispatch local file ไปทุก target ที่เลือก
6. Persist dedupe state v3; target ที่สำเร็จแล้วถูกข้ามในการ retry
7. สร้าง sanitized report; upload private dashboard report และ optional media ZIP artifact; ปิด destination sessions

## Permissions and evidence

- Workflow ใช้ `contents: write` สำหรับ persist `state/dedupe.json`; GitHub credential ที่ Control Worker ใช้ dispatch/read status ไม่ถูกส่งเป็น workflow input
- Secrets อยู่ใน GitHub Actions Secrets; ห้ามพิมพ์ค่าใน workflow input/log/source
- Python tests ใช้ fakes สำหรับ destination uploads และ Worker tests mock GitHub/JWKS, report artifacts และ ZIP stream
- Live Telegram normal-path/batch evidence อยู่ใน [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md); live MEGA path ต้องมี secret ของบัญชี MEGA ก่อนจึงจะตรวจจริงได้
