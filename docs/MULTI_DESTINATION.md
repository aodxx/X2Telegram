# X2Telegram — ปลายทางหลายแบบ

เอกสารนี้อธิบายการใช้ Dashboard แบบ **ประมวลผล media หนึ่งครั้ง แล้วส่งไฟล์เดียวกันไปยังปลายทางที่เลือก** โดยต่อยอดจาก Cloudflare Worker และ GitHub Actions เดิม ไม่เพิ่ม database, Redis, queue หรือ Google Drive

## Flow

```text
Dashboard → Cloudflare Access/Worker → GitHub Actions → Python worker
  → ดึงและตรวจ media ครั้งเดียว
  → Destination dispatcher
      ├── Telegram
      ├── MEGA
      └── Browser download ZIP
```

เลือกได้หนึ่งปลายทางหรือหลายปลายทางพร้อมกันต่อหนึ่ง job; หนึ่ง job รองรับ X URL สูงสุด 50 รายการ และยังคงใช้ workflow หลักเพียง workflow เดียว

## ตัวเลือกปลายทาง

| ปลายทาง | ผลลัพธ์ | ข้อจำกัด/การตั้งค่า |
|---|---|---|
| **Telegram** | ส่งวิดีโอ/รูปภาพ/เอกสารไปยังกลุ่มที่ล็อกไว้ | Bot API ปกติรองรับไม่เกิน 50 MB ต่อไฟล์; Large-file mode ใช้ Local Bot API และเพดานระบบ 2,000 MB |
| **MEGA** | อัปโหลดไปยัง `/X2Telegram/YYYY-MM-DD/` (หรือ folder ที่ตั้งในฝั่ง workflow) | ต้องตั้ง `MEGA_EMAIL`, `MEGA_PASSWORD`; `MEGA_TOTP_SECRET` ใช้เมื่อบัญชีเปิด MFA/TOTP. ใช้ MEGAcmd ทางการใน runner ชั่วคราว |
| **Download** | สร้างไฟล์ ZIP และให้ browser ดาวน์โหลดผ่าน Dashboard | เก็บเป็น private GitHub Actions artifact 7 วัน; ขนาด media ต่อไฟล์ไม่เกิน 2,000 MB และ ZIP ต่อ job รวมไม่เกิน 8 GiB |

วิดีโอ/ภาพหลายรายการจากโพสต์เดียวกันจะถูกส่งออกเป็นหลายไฟล์ใน ZIP เดียว และใช้ชื่อไฟล์ที่สร้างจาก username/post ID/index/นามสกุล โดยตัด path และอักขระที่ไม่รองรับออก

### การดาวน์โหลดผ่านมือถือ

Dashboard ใช้ browser download มาตรฐานผ่านลิงก์ `Content-Disposition: attachment` และ Worker ส่ง ZIP แบบ streaming โดยไม่ buffer ZIP ทั้งก้อนใน Worker. บน iOS/Android การบันทึกอาจแสดงแผง Downloads, Share หรือ Files ตาม browser/การตั้งค่าเครื่อง; GitHub Actions ไม่สามารถเขียนไฟล์ลงมือถือโดยตรงได้. หากไฟล์ใหญ่ ควรใช้ Wi‑Fi และพื้นที่ว่างเพียงพอ

## การติดตั้ง MEGA

ใน GitHub repository `aodxx/X2Telegram` ไปที่ **Settings → Secrets and variables → Actions → New repository secret** แล้วสร้าง:

| Secret name | ค่า |
|---|---|
| `MEGA_EMAIL` | อีเมลบัญชี MEGA ที่จะรับไฟล์ |
| `MEGA_PASSWORD` | รหัสผ่านบัญชี MEGA |
| `MEGA_TOTP_SECRET` | (ไม่บังคับ) MFA/TOTP seed สำหรับบัญชีที่เปิด two-factor authentication; ให้เว้นว่างหากไม่ได้ใช้ TOTP |

ใส่ค่าเฉพาะใน GitHub Secrets; **อย่าวาง credential ใน Dashboard, source code, issue หรือข้อความแชต**. MEGAcmd จะถูกติดตั้งเฉพาะเมื่อเลือก MEGA; หาก secret ไม่มี/การติดตั้งหรือ login ล้มเหลว จะรายงานความล้มเหลวของ MEGA แยกจาก Telegram/Download และไม่พิมพ์ output ของคำสั่ง login ลง report

หากต้องการเปลี่ยนโฟลเดอร์ราก ให้ตั้ง **Repository variable** `MEGA_REMOTE_FOLDER` ที่ Settings → Secrets and variables → Actions → Variables (เช่น `Archive/X2Telegram`). ถ้าไม่ตั้ง ระบบใช้ `X2Telegram`; ทุก job จะสร้างโฟลเดอร์วันที่ `YYYY-MM-DD` ใต้โฟลเดอร์นั้น. ระบบปฏิเสธ path ที่มี `.`/`..` หรืออักขระที่ไม่อนุญาต

เอกสารคำสั่ง login/MFA ของผู้พัฒนา MEGAcmd: [MEGAcmd login](https://github.com/meganz/MEGAcmd/blob/master/contrib/docs/commands/login.md). ระบบใช้ `mega-login --auth-code=... email password` เมื่อกำหนด TOTP secret และเรียก `mega-logout` หลังประมวลผล

## การส่งและสถานะ

1. วาง URL หนึ่งรายการต่อบรรทัด (สูงสุด 50)
2. เลือก Telegram, MEGA, Download ได้หนึ่งหรือหลายรายการ
3. เปิด Large-file mode เฉพาะเมื่อต้องการส่ง Telegram ไฟล์เกิน 50 MB และตั้งค่าฝั่ง Telegram Local Bot API แล้ว
4. กดเริ่มงานหนึ่งครั้ง; Dashboard dispatch หนึ่ง Actions run
5. เมื่อเสร็จ Dashboard แสดง status แยกตามปลายทางและแต่ละ media; ถ้าเลือก Download จะมีลิงก์ ZIP เมื่อ artifact พร้อม

ค่า status หลัก ได้แก่ `success`, `failed`, `partial_success`, `duplicate`, `ready` (Browser download) และ `processing`. ถ้าปลายทางหนึ่งล้มเหลวแต่อีกปลายทางสำเร็จ งานจะเป็น partial success/สำเร็จบางส่วน ไม่ถูกแสดงเป็นงานทั้งหมดล้มเหลว

## Retry และ duplicate prevention

- Python ดาวน์โหลดและตรวจ media ก่อน จากนั้นส่งไฟล์ local เดิมไปยังแต่ละปลายทางที่เลือก; ไม่ดาวน์โหลดจาก X ซ้ำเพียงเพราะเลือกหลายปลายทาง
- Dedupe state v3 บันทึกผลสำเร็จแยกตาม media และปลายทางที่เป็นการส่งซ้ำได้ (Telegram/MEGA). เมื่อ retry post เดิม ระบบข้าม destination ที่สำเร็จแล้วและลองเฉพาะ target ที่ยังไม่สำเร็จ
- Browser download เป็น artifact ของ job นั้น ไม่ใช่สำเนาถาวรใน dedupe state; เริ่ม job ใหม่เพื่อสร้าง ZIP ใหม่ได้
- GitHub Actions concurrency ยัง serialize งานที่แก้ไข dedupe state. ไม่รับประกัน exactly-once หากบริการปลายทางรับไฟล์แล้ว response/checkpoint สูญหายก่อน state ถูกบันทึก

## ข้อจำกัดและการแก้ปัญหา

- ไฟล์ใหญ่เกินขีดจำกัดเฉพาะปลายทางจะทำให้ target นั้นล้มเหลวโดยไม่หยุด target อื่น
- Browser ZIP หมดอายุหลัง 7 วัน; ถ้าขึ้น `download_expired` ให้เริ่ม job ใหม่
- หาก MEGA ขึ้น `mega_credentials_missing` ให้ตรวจชื่อ GitHub Actions secrets ให้ตรงตาราง; `mega_authentication_failed` ให้ตรวจบัญชี/รหัสผ่าน/TOTP โดยไม่ใส่ credential ใน report
- หาก X post เข้าถึงไม่ได้, ถูกลบ/private หรือไม่มี media ที่รองรับ จะมีผลลัพธ์รายโพสต์และ target ที่เกี่ยวข้องอาจไม่เกิดไฟล์
- ใช้เฉพาะ media ที่มีสิทธิ์ดาวน์โหลดและเผยแพร่ และปฏิบัติตามกฎหมาย/เงื่อนไขแพลตฟอร์ม

รายละเอียดขั้นตอนใช้งานอยู่ใน [`USER_GUIDE_TH.md`](USER_GUIDE_TH.md); การติดตั้งระบบอยู่ใน [`DEPLOYMENT.md`](DEPLOYMENT.md); หลักฐานทดสอบอยู่ใน [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md).
