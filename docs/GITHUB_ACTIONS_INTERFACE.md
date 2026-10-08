# GitHub Actions Interface — Zone 2

## Entry workflow

`.github/workflows/x2telegram.yml` คือ execution entry point เดียวของ X2Telegram. Control Worker จะ dispatch workflow นี้; Python worker ยังคงรับ batch text ผ่าน `INPUT_URLS` และทำงานเหมือนเดิม

## `workflow_dispatch` inputs

| Input | Required | Default | Meaning |
|---|---:|---|---|
| `url` | no | empty | URL เดี่ยวจาก Control Plane |
| `urls` | no | empty | URL หนึ่งรายการต่อบรรทัดสำหรับ manual/legacy dispatch |
| `large_file_mode` | yes | `false` | เปิด Local Bot API Server สำหรับไฟล์ใหญ่ |
| `request_id` | no | empty | correlation/idempotency request ID |
| `job_id` | no | empty | job identifier ที่ใช้ใน run name และ report |

ต้องส่ง `url` หรือ `urls` อย่างใดอย่างหนึ่งเท่านั้น; เมื่อส่ง `url` จะไม่อนุญาตให้ส่ง `urls` พร้อมกัน Workflow ตรวจเงื่อนไขก่อนเรียก CLI. Manual Run workflow เดิมที่ป้อน `urls` และปล่อย ID ว่างยังทำงานได้

สำหรับ Control Worker, `url` และ `urls` ใส่ URL เดียวกันเพื่อรักษา compatibility; `large_file_mode` ถูกส่งเป็น boolean input; `request_id` เป็น client idempotency key; `job_id` เป็น fingerprinted opaque ID. Workflow run title เป็น `X2Telegram <request_id> <job_id>` เพื่อให้ Worker ค้นหาและตรวจ ID ใช้ซ้ำกับ payload อื่นได้โดยไม่เพิ่ม database

รายงาน `report.json` เพิ่ม `job_id` และ sanitized report allow-list เพิ่ม `job_id` ที่ผ่านการตรวจรูปแบบ; `request_id` และ `run_id` เดิมคงไว้

## Security / permissions

- Workflow ไม่รับ secret ผ่าน input
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `ALERT_WEBHOOK_URL` ยังคงมาจาก GitHub Actions Secrets
- `TELEGRAM_CHAT_ID` ยังคงกำหนดตายตัว
- workflow ใช้ `contents: write` ที่ระดับ workflow เพราะ step persist `state/dedupe.json` commit กลับ branch; การแยก permission ให้แคบกว่านี้ยังต้องทบทวนกับ GitHub Actions token scope และผลต่อ persist state ก่อนปรับ
- GitHub credential ที่ Control Worker ใช้ dispatch/read status/report เป็น credential ฝั่ง server; ไม่ส่งลง input และไม่มีการเปลี่ยน workflow ไปใช้ user token

## Tests / evidence

- `tests/test_dashboard_report.py` ยืนยัน `job_id` อยู่ใน CLI report และ sanitized report
- `npm test --prefix control-worker` ตรวจ mapping input/request → dispatch โดย mock GitHub API (Zone 3)
- `.github/workflows/x2telegram.yml` รัน Python tests และ Control Worker tests ใน CI
- ยังไม่ได้เรียก `workflow_dispatch` จริงใน Zone 2–5 เพราะต้อง trigger execution plane ที่อาจส่ง media ไปยัง Telegram; จึงไม่ทำ destructive/side-effecting test ใน audit รอบนี้
