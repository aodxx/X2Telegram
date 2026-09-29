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
3. ใช้ chat ID ของแชตส่วนตัวเป็น `TELEGRAM_CHAT_ID`

#### ส่งเข้ากลุ่ม

1. เพิ่ม bot เข้ากลุ่ม
2. หากต้องการให้ส่งได้แน่นอน ให้กำหนด bot เป็นสมาชิกที่มีสิทธิ์ส่งข้อความ
3. ส่งข้อความทดสอบในกลุ่มหลังเพิ่ม bot แล้ว
4. ใช้ chat ID ของกลุ่ม ซึ่งมักเป็นเลขติดลบ เช่น `-100...`

#### ส่งเข้า Channel

1. เพิ่ม bot เป็น administrator ของ Channel
2. เปิดสิทธิ์ให้ bot โพสต์ข้อความ/media
3. ใช้ `@channelusername` เป็น `TELEGRAM_CHAT_ID` ได้ถ้า Channel มี public username
4. สำหรับ Channel แบบ private ให้ใช้ numeric chat ID รูปแบบ `-100...`

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
| `TELEGRAM_CHAT_ID` | chat ID ของปลายทาง | ตัวเลขติดลบหรือ `@channelusername` |

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
5. ตรวจว่า `TELEGRAM_BOT_TOKEN` และ `TELEGRAM_CHAT_ID` มีค่า
6. ประมวลผล URL แต่ละรายการ
7. เลือกวิดีโอ bitrate สูงสุด หรือใช้ fallback ของ X สำหรับรูปภาพ/วิดีโอที่ yt-dlp มองไม่เห็น
8. ส่งเข้า Telegram
9. สร้าง `report.json` พร้อมสถานะรายขั้นตอน
10. อัปโหลด report เป็น artifact แม้งานล้มเหลวบางส่วน

## 8. ความหมายของสถานะใน report

| Status | ความหมาย |
|---|---|
| `sent` | ส่ง media เข้า Telegram สำเร็จ |
| `no_media` | โพสต์เข้าถึงได้แต่ไม่พบ media ที่ส่งได้ |
| `metadata_error` | ดึงข้อมูลโพสต์จาก X ไม่สำเร็จ |
| `download_error` | พบ media แต่ดาวน์โหลด/ตรวจไฟล์ไม่สำเร็จ |
| `telegram_error` | Telegram ปฏิเสธหรือเรียก API ไม่สำเร็จ |
| `configuration_error` | secret หรือค่าตั้งค่าหลักไม่ครบ |

ระบบประมวลผลแยกต่อโพสต์ ดังนั้น error ของ URL หนึ่งไม่ควรหยุด URL อื่น

## 9. ตรวจ URL ในเครื่องโดยไม่ส่ง Telegram

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

## 10. แก้ปัญหาที่พบบ่อย

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

- ระบบมีเพดานขนาดไฟล์จากการตั้งค่า `MAX_FILE_SIZE_MB` ค่าเริ่มต้น 50 MB
- Workflow รุ่นนี้ใช้ Telegram Bot API มาตรฐานและไม่รวม Local Bot API Server
- หากต้องรองรับไฟล์ใหญ่กว่านี้ ต้องออกแบบและเปิดใช้เส้นทางอัปโหลดขนาดใหญ่แยกต่างหาก

## 11. การอัปเดตระบบ

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

## 12. Checklist ก่อนใช้งานจริง

- [ ] Bot ถูกสร้างผ่าน BotFather
- [ ] Bot อยู่ในแชตเป้าหมาย
- [ ] Bot มีสิทธิ์ส่งข้อความ/media
- [ ] มี `TELEGRAM_BOT_TOKEN` ใน GitHub Actions Secrets
- [ ] มี `TELEGRAM_CHAT_ID` ใน GitHub Actions Secrets
- [ ] Actions เปิดใช้งาน
- [ ] workflow เห็นปุ่ม `Run workflow`
- [ ] ทดสอบด้วย URL สาธารณะ 1 รายการ
- [ ] Telegram ได้รับ media
- [ ] ดาวน์โหลดและตรวจ `report.json`
- [ ] ไม่เคย commit token หรือ credential ลง repository
