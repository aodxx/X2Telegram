# X2Telegram — Project Status

**สถานะเอกสาร:** อัปเดตล่าสุด 2026-10-02  
**Branch:** `main`  
**อ้างอิงโค้ด:** `a2dd320` (`feat: add FxTwitter metadata fallback and local runner`)

## สรุปผู้บริหาร

แกนหลักของ X2Telegram อยู่ในสถานะ **พร้อมใช้งานจริงผ่าน GitHub Actions** สำหรับการดาวน์โหลด media จากโพสต์ X ที่เข้าถึงได้แบบสาธารณะและส่งเข้า Telegram กลุ่มปลายทางที่ล็อกไว้ ระบบได้รับการทดสอบด้วย workflow จริงและยืนยันการส่งวิดีโอสำเร็จแล้ว

> ขอบเขตการใช้งาน: ใช้เฉพาะ media ที่ผู้ใช้มีสิทธิ์ดาวน์โหลดและเผยแพร่ และต้องปฏิบัติตามกฎหมาย/เงื่อนไขของแพลตฟอร์ม เนื้อหา 18+ ต้องเป็นเนื้อหาที่ถูกกฎหมายและได้รับความยินยอมตามข้อกำหนดที่เกี่ยวข้อง

## สิ่งที่ทำสำเร็จแล้ว

### 1. Workflow และการประมวลผล

- รับ URL X หลายรายการผ่าน `workflow_dispatch` โดยใช้หนึ่ง URL ต่อหนึ่งบรรทัด
- ตรวจสอบ host และรูปแบบ post ID ของ `x.com` / `twitter.com`
- ตัด query string ของ source post URL เช่น `?s=20` ก่อนใช้ lookup โดยไม่ทำลาย query ที่จำเป็นบน direct media URL
- ประมวลผลแต่ละโพสต์แยกจากกัน URL ที่ล้มเหลวไม่หยุดรายการอื่น
- มี timeout และการ retry สำหรับการเรียกบริการที่เหมาะสม
- ลบไฟล์ชั่วคราวหลังการส่ง และไม่ commit media เข้า repository

### 2. Metadata fallback และการดาวน์โหลด

ลำดับ provider ปัจจุบันคือ:

```text
yt-dlp → X syndication → public FxTwitter API
```

- เลือก video variant ที่มี bitrate สูงสุด
- รองรับ photo fallback ตามชนิด media
- รับเฉพาะ MP4 variant จาก FxTwitter fallback
- ตรวจสอบ URL และ host ก่อนดาวน์โหลด
- เขียนไฟล์แบบ atomic และตรวจ content type / file signature
- รองรับโพสต์ที่ provider หลักหา media ไม่พบมากขึ้น

### 3. Telegram และความปลอดภัย

- ปลายทางถูกล็อกไว้ที่กลุ่ม Telegram chat ID `-1003906817580`
- ใช้ `TELEGRAM_BOT_TOKEN` จาก GitHub Actions Secrets เท่านั้น
- ทำ Telegram preflight ก่อนดาวน์โหลดทุกครั้งด้วยการตรวจ token, chat, membership และสิทธิ์ส่งข้อความ/media
- ไม่เปิดให้ผู้ใช้เปลี่ยน chat ID จาก input workflow
- ไม่ส่ง token, API credentials หรือ media URL ลับเข้า log/report
- ไม่อัปโหลดไฟล์ไป Google Drive ใน flow ปัจจุบัน

### 4. Large-file mode

- โหมดมาตรฐานใช้ Telegram Bot API และจำกัดไฟล์ที่ 50 MB
- `large_file_mode=true` จะเริ่ม Telegram Local Bot API Server เฉพาะใน job นั้น
- ต้องมี `TELEGRAM_API_ID` และ `TELEGRAM_API_HASH` เป็น repository secrets
- เพดานที่ตั้งไว้สำหรับ large-file mode คือ 2000 MB
- Local Bot API Server มี health check และถูกหยุดเมื่อจบงาน

### 5. Duplicate prevention

- ใช้ `state/dedupe.json` เป็น state ข้าม workflow run
- ใช้ post ID เป็น key หลัก และ normalized URL เป็น fallback
- บันทึกเฉพาะหลัง Telegram ยืนยันการส่งสำเร็จและมี message ID
- ใช้ lock + atomic replace เพื่อลดความเสี่ยง state เสียหาย
- ใช้ GitHub Actions concurrency ป้องกัน run ชนกัน
- workflow commit state กลับไปยัง branch เมื่อมีการเปลี่ยนแปลง
- รายการซ้ำจะได้สถานะ `skipped_duplicate`

### 6. Reporting และ observability

แต่ละ run สร้าง:

- `report.json` — สถานะรวม, preflight, ผลรายโพสต์, stage, error code และ Telegram message IDs
- `run.jsonl` — structured execution log
- GitHub Step Summary — สรุปผลบนหน้า workflow
- optional redacted webhook alert ผ่าน `ALERT_WEBHOOK_URL`
- local dry-run และ preflight runner ที่ `scripts/local_test.sh`

## หลักฐานการทดสอบจริงล่าสุด

Workflow run ล่าสุดที่ใช้โค้ด `a2dd320`:

- Run: [GitHub Actions run 36980600244](https://github.com/aodxx/X2Telegram/actions/runs/36980600244)
- Commit: `a2dd320a6c75bad206e4cfa843964764ca77d9ed`
- Workflow conclusion: `success`
- โหมด: `large_file_mode=true`
- Telegram preflight: ผ่าน
- Target: `-1003906817580`
- Post ที่ทดสอบ: `2105840724075798807`
- Result: `sent`
- Media count: `3`
- Telegram message ID: `345`
- Error: ไม่มี

ผลนี้ยืนยันว่า **เส้นทางตั้งแต่ metadata fallback/download ไปจนถึงการส่งเข้า Telegram ทำงานจริงอย่างน้อยกับโพสต์ทดสอบนี้** แต่ไม่ใช่การรับประกันว่าโพสต์ X ทุกประเภทจะดาวน์โหลดได้ เนื่องจากโพสต์อาจถูกลบ เป็น private ถูกจำกัดอายุ ต้อง login หรือถูก rate limit

## สิ่งที่ยังต้องตรวจสอบ/ดูแลใน production

- ตรวจว่า repository Settings → Actions → General → Workflow permissions อนุญาต `Read and write` เพื่อให้ dedupe state push กลับได้
- ตรวจและหมุน secrets หากมีเหตุสงสัยว่า token รั่ว
- ติดตามการเปลี่ยนแปลงของ X, yt-dlp, syndication และ FxTwitter API
- ทดสอบกรณีไฟล์ใหญ่จริงเป็นระยะ ไม่ใช่เฉพาะการเปิดโหมด large-file
- ตรวจ artifact `report.json` เมื่อมีรายการ `no_media`, `metadata_error`, `download_error` หรือ `telegram_error`
- พิจารณา retention ของ artifacts และ log ให้เหมาะกับข้อมูลที่ประมวลผล

## สิ่งที่จะพัฒนาต่อ — Phase 6.1: Private Dashboard MVP

เป้าหมายคือให้ผู้ใช้วางลิงก์และกด Run ผ่านหน้าจอที่ใช้งานง่าย โดยยังคงใช้ workflow และระบบความปลอดภัยเดิมเป็น backend หลัก

### ขอบเขตที่เสนอ

1. หน้า Dashboard responsive สำหรับ desktop และมือถือ
2. textarea สำหรับวาง X URL หลายรายการ หนึ่ง URL ต่อบรรทัด
3. ตรวจและนับ URL ที่ valid / duplicate / invalid ก่อนเริ่ม
4. หน้าสรุปให้ review รายการก่อนกดส่ง
5. ปุ่มเริ่ม workflow ผ่าน backend ที่ปลอดภัย
6. ตัวเลือก `large_file_mode` พร้อมคำเตือนเรื่อง credentials/ขนาดไฟล์
7. ติดตามสถานะ run และแสดงผลรายโพสต์จาก `report.json`
8. แสดง `sent`, `skipped_duplicate`, `no_media` และ error states แบบอ่านง่าย
9. แสดง Telegram message ID และชื่อไฟล์เมื่อมีใน report
10. เก็บ recent run summary โดยไม่เปิดเผย secrets

### ข้อกำหนดความปลอดภัยของ Phase 6.1

- ห้ามใส่ GitHub token หรือ Telegram bot token ใน frontend
- ต้องมี backend/API ที่เก็บ credential ใน secret store
- ต้องล็อก target chat ID เป็น `-1003906817580`
- ต้องตรวจ URL ฝั่ง server ซ้ำ แม้ frontend จะตรวจแล้ว
- ต้องมี authentication อย่างน้อยระดับ private access ก่อนเปิดใช้งานจริง
- ต้องมี rate limit และจำกัดจำนวน URL ต่อ request
- ห้ามเพิ่ม Google Drive เป็นปลายทางโดยอัตโนมัติ

### ยังไม่อยู่ใน Phase 6.1

- ระบบ multi-user และ role/permission แบบเต็มรูปแบบ
- การแก้ไข Telegram destination จากหน้าเว็บ
- การชำระเงินหรือการให้บริการสาธารณะ
- การย้าย downloader ออกจาก GitHub Actions
- การรับประกันการดาวน์โหลดโพสต์ private หรือ content ที่ต้อง login

## Decision ที่แนะนำ

เริ่ม Phase 6.1 เป็น **private dashboard MVP** โดยให้ GitHub Actions เป็น execution backend ต่อไปก่อน วิธีนี้ลดการเปลี่ยนแปลงในแกนที่ผ่านการทดสอบแล้ว และทำให้สามารถ rollback กลับไปใช้ GitHub Actions UI ได้ง่ายหาก dashboard มีปัญหา

## จุดอ้างอิงสำคัญใน repository

- Workflow: `.github/workflows/x2telegram.yml`
- Telegram API/preflight: `src/telegram_api.py`
- Metadata fallback: `src/metadata.py`
- Duplicate state: `src/dedupe.py`
- Local runner: `scripts/local_test.sh`
- Deployment guide: `docs/DEPLOYMENT.md`
- Architecture notes: `docs/ARCHITECTURE.md`
- UX prototype: `web/index.html`
