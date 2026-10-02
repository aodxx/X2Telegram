# X2Telegram Apps Script — ค่าตั้งค่าจริง

ค่าที่ตรวจสอบจาก repository `aodxx/X2Telegram` และ branch workflow ปัจจุบัน:

| Script Property | ค่าที่ใช้จริง | สถานะ |
|---|---|---|
| `GITHUB_TOKEN` | **ต้องสร้างเอง** | Secret — ห้ามใส่ใน Git หรือส่งในแชต |
| `GITHUB_OWNER` | `aodxx` | ใส่เป็นค่า property ได้ หรือปล่อยว่างเพราะมี default ใน `Code.gs` |
| `GITHUB_REPO` | `X2Telegram` | ใส่เป็นค่า property ได้ หรือปล่อยว่างเพราะมี default ใน `Code.gs` |
| `GITHUB_WORKFLOW_ID` | `x2telegram.yml` | ใส่เป็นค่า property ได้ หรือปล่อยว่างเพราะมี default ใน `Code.gs` |
| `GITHUB_REF` | `main` | ใส่เป็นค่า property ได้ หรือปล่อยว่างเพราะมี default ใน `Code.gs` |
| `MAX_URLS` | `20` | ใส่เป็นค่า property ได้ หรือปล่อยว่างเพราะมี default ใน `Code.gs` |

## ค่าที่ใส่ได้ทันที

ใน Apps Script → Project Settings → Script properties สามารถใส่ได้ดังนี้:

```text
GITHUB_OWNER=aodxx
GITHUB_REPO=X2Telegram
GITHUB_WORKFLOW_ID=x2telegram.yml
GITHUB_REF=main
MAX_URLS=20
```

## ค่าที่ต้องใส่เอง

### `GITHUB_TOKEN`

สร้าง GitHub fine-grained personal access token สำหรับ repository `aodxx/X2Telegram` เท่านั้น โดยให้สิทธิ์อย่างน้อย:

- Actions: Read and write
- Metadata: Read
- Contents: Read หากต้องการใช้งานกับ repository API เพิ่มเติม

นำ token ไปใส่ใน Apps Script Script Properties เท่านั้น ห้าม commit และห้ามส่ง token ในแชต

### โหมด public API

รุ่นนี้ไม่ใช้ `ALLOWED_EMAILS` และไม่ตรวจ Google account ตามที่กำหนดให้ระบบทำงานโดยตรง ให้ตั้ง Web App deployment เป็น `Who has access: Anyone` หากยังตั้งเป็น `Anyone with Google account` ระบบอาจถูก Google ปฏิเสธก่อนถึงโค้ด

## หมายเหตุ

ถ้าไม่ใส่ `GITHUB_OWNER`, `GITHUB_REPO`, `GITHUB_WORKFLOW_ID`, `GITHUB_REF` หรือ `MAX_URLS` ระบบจะใช้ค่าจริงด้านบนจาก default ใน `gas/Code.gs` แต่ `GITHUB_TOKEN` ยังจำเป็นต้องตั้งค่าเอง
