# X2Telegram — คู่มือเผยแพร่และตั้งค่า

เอกสารนี้อธิบายการนำ X2Telegram ไปใช้งานจริงผ่าน GitHub Actions ตั้งแต่การเตรียม Telegram ไปจนถึงการทดสอบและแก้ปัญหา

## 1. ภาพรวมการเผยแพร่

X2Telegram รุ่นนี้ **ไม่ต้องติดตั้งเซิร์ฟเวอร์แยก** ระบบทำงานบน GitHub Actions เมื่อผู้ใช้กด `Run workflow`:

```text
ผู้ใช้วางลิงก์ X
  -> GitHub Actions checkout โค้ด
  -> ติดตั้ง Python dependency
  -> รันทดสอบอัตโนมัติ
  -> ดึง metadata จาก X ด้วย yt-dlp
  -> ดาวน์โหลด media ลงไฟล์ชั่วคราว
  -> ส่งเข้า Telegram Bot API
  -> ลบไฟล์ชั่วคราว
  -> อัปโหลด JSON report เป็น workflow artifact
```

ข้อจำกัดสำคัญ:

- ต้องเป็นโพสต์ X ที่ระบบเข้าถึงได้แบบสาธารณะ
- โพสต์ private, ถูกลบ, age-restricted หรือถูก rate limit อาจส่งไม่สำเร็จ
- ใช้ media ที่คุณมีสิทธิ์ดาวน์โหลดและเผยแพร่เท่านั้น
- ระบบตัด query parameter เช่น `?s=20` และ `utm_source=...` ออกจาก URL ก่อนดึง metadata และใช้เป็น source URL
- ไฟล์ถูกดาวน์โหลดชั่วคราวใน runner และถูกลบหลังส่ง
- โหมดมาตรฐานใช้ Telegram Bot API ปกติและจำกัดไฟล์ที่ 50 MB
- หากต้องส่งไฟล์ใหญ่กว่า 50 MB ให้เปิด `large_file_mode` ตอนกด Run workflow และต้องมี `TELEGRAM_API_ID` กับ `TELEGRAM_API_HASH` ใน repository secrets
- large-file mode เริ่ม Telegram Local Bot API Server เฉพาะใน job นั้นและจำกัดเพดานเริ่มต้นไว้ที่ 2000 MB

## 2. เตรียม Telegram Bot

### 2.1 สร้าง Bot

1. เปิด Telegram แล้วค้นหา `@BotFather`
2. ส่งคำสั่ง `/newbot`
3. ตั้งชื่อที่แสดงของ bot
4. ตั้ง username ที่ลงท้ายด้วย `bot`
5. BotFather จะส่ง **HTTP API token** กลับมาในรูปแบบคล้าย:

   ```text
   123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

เก็บ token นี้เป็นความลับ ห้ามใส่ใน source code, README, issue, log หรือส่งในแชตสาธารณะ

### 2.2 เลือกปลายทางที่จะรับ media

#### ส่งเข้าหาแชตส่วนตัว

1. เปิดหน้า bot ของคุณ
2. กด `Start` หรือส่ง `/start`
3. โปรเจกต์นี้ไม่รองรับแชตส่วนตัวเป็นปลายทาง โดยล็อกไว้ที่กลุ่ม `-1003906817580`

#### ส่งเข้ากลุ่ม

1. เพิ่ม bot เข้ากลุ่ม `-1003906817580`
2. กำหนด bot เป็นสมาชิกที่มีสิทธิ์ส่งข้อความและ media
3. ระบบจะตรวจ token, กลุ่ม, membership และสิทธิ์ด้วย `getMe`, `getChat`, `getChatMember` ก่อนดาวน์โหลดทุกครั้ง

#### ส่งเข้า Channel

1. เพิ่ม bot เป็น administrator ของ Channel
2. เปิดสิทธิ์ให้ bot โพสต์ข้อความ/media หากใช้ channel เป็นแหล่งทดสอบ
3. การใช้งาน production ของโปรเจกต์นี้ยังล็อกปลายทางไว้ที่กลุ่ม `-1003906817580`

## 3. หา Telegram Chat ID

วิธีที่ปลอดภัยคือใช้ Bot API จากเครื่องของคุณเองและไม่บันทึกผลลัพธ์ลง Git:

```bash
export TELEGRAM_BOT_TOKEN='ใส่ token เฉพาะใน terminal ของคุณ'
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates"
unset TELEGRAM_BOT_TOKEN
```

ก่อนเรียก `getUpdates` ให้ส่งข้อความใหม่ในแชตเป้าหมายก่อน แล้วค้นหาใน JSON ตรงส่วน:

```json
"chat": {
  "id": -1001234567890,
  "title": "Example Group",
  "type": "supergroup"
}
```

ค่า `id` คือ `TELEGRAM_CHAT_ID`

ถ้าไม่พบ update:

- ตรวจว่า bot ถูกเพิ่มเข้ากลุ่มหรือ Channel แล้ว
- ส่งข้อความใหม่หลังจากเปิด bot/เพิ่ม bot
- สำหรับกลุ่ม อาจต้องปิด privacy mode ผ่าน BotFather หากต้องการให้ bot เห็นข้อความทั่วไป
- ห้ามเผยแพร่ผลลัพธ์ `getUpdates` เพราะอาจมี token หรือข้อมูลแชต

## 4. ตั้งค่า GitHub Repository Secrets

เปิด repository:

`https://github.com/aodxx/X2Telegram`

จากนั้นไปที่:

```text
Settings
-> Secrets and variables
-> Actions
-> New repository secret
```

สร้าง secret สองรายการแบบสะกดตรงตามนี้:

| Name | Value | หมายเหตุ |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | token จาก BotFather | ห้ามมีช่องว่างหรือ backticks |
| `TELEGRAM_CHAT_ID` | กำหนดโดย workflow เป็น `-1003906817580` | ไม่ต้องสร้าง secret รายการนี้ |
| `TELEGRAM_API_ID` | API ID จาก my.telegram.org | จำเป็นเฉพาะ large-file mode |
| `TELEGRAM_API_HASH` | API hash จาก my.telegram.org | จำเป็นเฉพาะ large-file mode |
| `ALERT_WEBHOOK_URL` | HTTPS webhook สำหรับรับสรุปสถานะ | ไม่บังคับ; ใช้เฉพาะเมื่อต้องการแจ้งเตือนภายนอก |

กด `Add secret` แยกทีละรายการ

ข้อควรระวัง:

- ชื่อ secret ต้องเป็นตัวพิมพ์ใหญ่และตรงตามตาราง
- ไม่ต้องใส่ `${{ }}` ในช่อง Value
- ห้ามใส่ token ลงใน workflow file
- หาก token รั่ว ให้ไปที่ BotFather ใช้ `/revoke` แล้วสร้าง token ใหม่ จากนั้นอัปเดต secret

## 5. ตรวจว่า GitHub Actions เปิดใช้งาน

ไปที่แท็บ **Actions** ของ repository:

1. ถ้ามีข้อความให้เปิดใช้งาน workflow ให้กดเปิดใช้งาน
2. เลือก workflow ชื่อ **X2Telegram**
3. ต้องเห็นปุ่ม **Run workflow**
4. ถ้าไม่เห็น ให้ตรวจว่าอยู่ branch `main` และไฟล์ `.github/workflows/x2telegram.yml` ถูก push แล้ว

โค้ดรุ่นที่ใช้งานจริงอยู่บน branch `main` และ workflow ต้องมี trigger `workflow_dispatch`

## 6. รันงานครั้งแรก

1. ไปที่ **Actions → X2Telegram**
2. กด **Run workflow**
3. เลือก branch `main`
4. วาง URL X ทีละรายการ โดยใช้ 1 URL ต่อ 1 บรรทัด เช่น:

   ```text
   https://x.com/example/status/1234567890123456789
   https://x.com/example/status/1234567890123456790
   ```

5. กด **Run workflow**
6. เปิด run ที่เพิ่งสร้างและรอจนขั้นตอนเป็นสีเขียว
7. ตรวจ media ใน Telegram
8. เปิดส่วน **Artifacts** ด้านล่างของ run แล้วดาวน์โหลดไฟล์ชื่อประมาณ:

   ```text
   x2telegram-report-<run_id>
   ```

## 7. ลำดับขั้นตอนใน workflow

workflow จะทำตามลำดับนี้:

1. Checkout source code
2. ติดตั้ง Python 3.12
3. ติดตั้ง `yt-dlp` และ `requests`
4. รัน automated tests
5. ตรวจว่า `TELEGRAM_BOT_TOKEN` มีค่า และตรวจ Telegram preflight ผ่าน
6. ประมวลผล URL แต่ละรายการ
7. เลือกวิดีโอ bitrate สูงสุด โดยลองตามลำดับ `yt-dlp` → X syndication → public FxTwitter API
8. ส่งเข้า Telegram
9. สร้าง `report.json` พร้อมสถานะรายขั้นตอน
10. สร้าง `run.jsonl` เป็น structured execution log และเขียน GitHub Step Summary
11. ส่ง redacted summary ไปยัง `ALERT_WEBHOOK_URL` หากตั้งค่าไว้
12. อัปโหลด report และ log เป็น artifact แม้งานล้มเหลวบางส่วน

### 7.1 Large-file mode

ในหน้า **Run workflow** ให้เปิดตัวเลือก `large_file_mode` เฉพาะเมื่อจำเป็น ระบบจะตรวจ API credentials, เริ่ม Local Bot API Server ใน runner ชั่วคราว, ตรวจ health ด้วย `getMe`, ส่งไฟล์ผ่าน endpoint local และหยุด container เมื่อจบงาน

หากไม่ได้เปิดโหมดนี้ ค่าเกิน 50 MB จะถูกปฏิเสธก่อนส่ง เพื่อไม่ให้เข้าใจผิดว่า Bot API ปกติรองรับไฟล์ใหญ่

## 8. Duplicate prevention

Workflow ใช้ `state/dedupe.json` เป็น state ข้ามการรัน:

- key หลักคือ X post ID และใช้ normalized URL เป็น fallback
- ตรวจ state ก่อน metadata lookup และ download
- บันทึกเฉพาะหลัง Telegram ส่งสำเร็จและได้ message ID
- เขียน JSON แบบ lock + atomic replace เพื่อไม่ให้ไฟล์เสียหายเมื่อ runner หยุดกลางทาง
- commit state กลับไปที่ branch ด้วย `GITHUB_TOKEN`
- ใช้ GitHub Actions concurrency เพื่อไม่ให้ workflow สองตัวแก้ state พร้อมกัน

สถานะที่เพิ่มใน report คือ `skipped_duplicate` พร้อม `error_code: already_sent`

หาก branch `main` เปิด branch protection ที่ไม่อนุญาตให้ `GITHUB_TOKEN` push การส่งจะยังทำงานได้ แต่ state จะไม่ถูกบันทึกข้าม run ต้องอนุญาตให้ Actions อัปเดต state หรือเปลี่ยนไปใช้ external state store ก่อนเปิดใช้งาน production

## 8. Observability และการแจ้งเตือน

### 8.1 ไฟล์ที่ได้จากแต่ละ run

- `report.json`: report แบบ JSON มี `schema_version`, run ID, เวลาเริ่ม/จบ, duration, preflight, สถานะต่อโพสต์, stage, error code และ Telegram message IDs
- `run.jsonl`: log แบบ JSON Lines สำหรับค้นหาตาม event เช่น `run_started`, `post_started`, `post_sent`, `post_failed`, `alert_sent`
- GitHub Step Summary: สรุปจำนวน `sent`, `no_media`, `download_error` และสถานะรวมที่หน้า run

Log จะปกปิด bot token, API key, authorization และ query secrets ก่อนเขียนออกไป แต่ไม่ควรใส่ credential ลงใน URL หรือข้อความ error ตั้งแต่ต้น

### 8.2 เปิดใช้งาน webhook alert

สร้าง repository secret ชื่อ `ALERT_WEBHOOK_URL` เป็น HTTPS endpoint ของระบบแจ้งเตือนที่คุณควบคุม เช่น incident webhook หรือระบบ automation ของคุณเอง หากไม่ตั้งค่า ระบบจะยังสร้าง report/log ตามปกติแต่ไม่ส่งแจ้งเตือนภายนอก

ข้อมูลที่ส่งมีเฉพาะ:

- สถานะรวมของ run
- จำนวน input และ unique posts
- จำนวนผลลัพธ์แยกตาม status
- duration และ GitHub run ID

จะไม่ส่ง bot token, API credentials, media URL, caption หรือข้อความ error รายโพสต์ไปยัง webhook

## 9. ความหมายของสถานะใน report

| Status | ความหมาย |
|---|---|
| `sent` | ส่ง media เข้า Telegram สำเร็จ |
| `no_media` | โพสต์เข้าถึงได้แต่ไม่พบ media ที่ส่งได้ |
| `metadata_error` | ดึงข้อมูลโพสต์จาก X ไม่สำเร็จ |
| `download_error` | พบ media แต่ดาวน์โหลด/ตรวจไฟล์ไม่สำเร็จ |
| `telegram_error` | Telegram ปฏิเสธหรือเรียก API ไม่สำเร็จ |
| `configuration_error` | secret หรือค่าตั้งค่าหลักไม่ครบ |
| `skipped_duplicate` | post นี้ถูกส่งสำเร็จและอยู่ใน dedupe state แล้ว |

ระบบประมวลผลแยกต่อโพสต์ ดังนั้น error ของ URL หนึ่งไม่ควรหยุด URL อื่น

### Metadata fallback สำหรับวิดีโอ

เมื่อ `yt-dlp` ไม่พบ media ระบบจะลอง X syndication ก่อน แล้วจึงเรียก public FxTwitter API ที่ endpoint:

```text
https://api.fxtwitter.com/2/status/{post_id}
```

ระบบเลือกเฉพาะ variants ที่เป็น MP4 และคง query parameter ของ direct media URL เช่น `?tag=12` ไว้ เพราะพารามิเตอร์เหล่านี้อาจจำเป็นต่อการดาวน์โหลด CDN media ส่วน query parameter ของ URL โพสต์ เช่น `?s=20` จะถูกตัดเฉพาะตอน normalize source URL เท่านั้น

## 10. ตรวจ URL ในเครื่องโดยไม่ส่ง Telegram

ไม่จำเป็นต้องตั้ง Telegram secret หากต้องการตรวจรูปแบบ URL อย่างเดียว:

```bash
printf '%s\n' 'https://x.com/user/status/123' | python -m src.cli --parse-only
```

ใน repository หลัง clone สามารถรันทดสอบได้ด้วย:

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
pytest -q
```

### 10.1 Local test runner

ก่อนรัน GitHub Actions ให้ใช้สคริปต์ที่ repository จัดเตรียมไว้:

```bash
scripts/local_test.sh
```

สคริปต์จะทำตามลำดับนี้:

1. รัน automated tests
2. ตรวจ Python syntax ด้วย `compileall`
3. parse URL แบบ `--parse-only`
4. ไม่เรียก Telegram และไม่ส่ง media โดยค่าเริ่มต้น

ใช้ไฟล์ URL ของคุณเองได้:

```bash
scripts/local_test.sh --urls-file urls.txt
```

หากต้องการตรวจ token, กลุ่ม, membership และสิทธิ์ของ bot โดยไม่ส่งข้อความหรือไฟล์:

```bash
export TELEGRAM_BOT_TOKEN='ใส่เฉพาะใน terminal เครื่องตัวเอง'
scripts/local_test.sh --preflight
unset TELEGRAM_BOT_TOKEN
```

โหมด `--preflight` เรียกเฉพาะ `getMe`, `getChat` และ `getChatMember`; ไม่เรียก `sendVideo`, `sendPhoto` หรือ `sendDocument` และสคริปต์ไม่พิมพ์ token ออกมา

## 11. แก้ปัญหาที่พบบ่อย

### ไม่เห็นปุ่ม Run workflow

- ตรวจว่า workflow อยู่ที่ `.github/workflows/x2telegram.yml`
- ตรวจว่าอยู่ branch `main`
- เปิดใช้งาน Actions ใน repository settings
- รีเฟรชหน้า Actions หลัง push commit

### ขึ้น `Missing TELEGRAM_BOT_TOKEN secret`

- ตรวจชื่อ secret ให้ตรงตัวพิมพ์ใหญ่
- ตรวจว่าเพิ่มเป็น **Repository secret** ไม่ใช่ Environment secret ที่ยังไม่ได้ผูกกับ job
- ตรวจว่ากำลังรันจาก repository เดียวกับที่เพิ่ม secret

### Telegram ไม่ได้รับข้อความ

- ตรวจ token ด้วย BotFather
- ตรวจ chat ID
- แชตส่วนตัวต้องกด `/start` กับ bot ก่อน
- กลุ่มต้องเพิ่ม bot เข้ากลุ่ม
- Channel ต้องเพิ่ม bot เป็น administrator และอนุญาตให้โพสต์
- ตรวจ error รายโพสต์ใน workflow log และ `report.json`

### ขึ้น `No video could be found` หรือ metadata error

- ตรวจว่า URL เปิดดูได้โดยไม่ต้อง login
- ตรวจว่าโพสต์ไม่ถูกลบหรือจำกัดการเข้าถึง
- ระบบจะลอง fallback สำหรับรูปภาพและ media ที่เปิดเผยผ่าน X syndication endpoint อัตโนมัติ
- หาก fallback ได้ `no_media` แปลว่าโพสต์ไม่เปิดเผย media ให้ runner เข้าถึงได้
- รอสักระยะหาก X ตอบ rate limit

### ไฟล์ใหญ่หรือส่งไม่ผ่าน

- ระบบมีเพดาน `MAX_FILE_SIZE_MB` ค่าเริ่มต้น 50 MB ใน standard mode และ 2000 MB ใน large-file mode
- large-file mode ต้องมี `TELEGRAM_API_ID` และ `TELEGRAM_API_HASH` ใน repository secrets
- large-file mode ต้องเริ่ม Local Bot API Server สำเร็จและผ่าน `getMe` ก่อนส่ง
- หากไฟล์เกิน 2000 MB ระบบจะปฏิเสธและไม่ส่งไฟล์นั้น

## 12. การอัปเดตระบบ

เมื่อแก้โค้ดแล้ว push ไปที่ `main`:

```bash
git add .
git commit -m "Describe the change"
git push origin main
```

การรันครั้งถัดไปจะใช้โค้ด commit ล่าสุดโดยอัตโนมัติ

ก่อน push ควรรัน:

```bash
pytest -q
python -m compileall -q src tests
git diff --check
```

## 13. Checklist ก่อนใช้งานจริง

- [ ] Bot ถูกสร้างผ่าน BotFather
- [ ] Bot อยู่ในแชตเป้าหมาย
- [ ] Bot มีสิทธิ์ส่งข้อความ/media
- [ ] มี `TELEGRAM_BOT_TOKEN` ใน GitHub Actions Secrets
- [ ] Workflow ใช้กลุ่มปลายทาง `-1003906817580`
- [ ] Actions เปิดใช้งาน
- [ ] workflow เห็นปุ่ม `Run workflow`
- [ ] ทดสอบด้วย URL สาธารณะ 1 รายการ
- [ ] Telegram ได้รับ media
- [ ] ดาวน์โหลดและตรวจ `report.json`
- [ ] ไม่เคย commit token หรือ credential ลง repository
