# คู่มือใช้งาน X2Telegram Dashboard

**หน้าใช้งาน:** [X2Telegram Dashboard](https://aodxx.github.io/X2Telegram/) — จะ redirect ไปยัง Dashboard/API ที่อยู่บน Cloudflare Worker origin เดียวกันและถูกป้องกันด้วย Cloudflare Access

## 1. ลงชื่อเข้าใช้

1. เปิด Dashboard; หาก Access session หมดอายุ ระบบจะพาไปหน้า Cloudflare Access
2. กรอกอีเมลที่ได้รับอนุญาต รับ OTP จากอีเมล แล้วกลับมาที่ Dashboard
3. สถานะด้านบนที่ถูกต้องคือ **Access ลงชื่อเข้าใช้แล้ว · พร้อมส่ง**. หากเปิด Dashboard ไว้ก่อน login ให้กลับแท็บเดิมหรือ refresh เพื่อให้ระบบตรวจ session ใหม่

## 2. วาง URL และเลือกปลายทาง

1. วางลิงก์สาธารณะของโพสต์ X **หนึ่งลิงก์ต่อหนึ่งบรรทัด**; หนึ่งงานรับได้สูงสุด 200 ลิงก์ ตัวอย่าง:

   ```text
   https://x.com/username/status/1234567890
   https://x.com/username/status/1234567891
   https://twitter.com/another/status/1234567892
   ```

2. เลือกปลายทางได้หนึ่งหรือหลายรายการ:
   - **Telegram** — ส่งเข้า Telegram Supergroup ที่กำหนดไว้ (ไม่สามารถเปลี่ยน target จาก Dashboard)
   - **Dropbox** — อัปโหลดเข้าบัญชี Dropbox ผ่าน OAuth ที่ตั้งค่าใน GitHub Secrets; รองรับไฟล์ใหญ่และ retry โดยไม่เขียนทับไฟล์เดิม
   - **MEGA** — อัปโหลดไปบัญชี MEGA ที่ตั้งไว้ใน GitHub Actions Secrets; ต้องมี `MEGA_EMAIL` และ `MEGA_PASSWORD` (บัญชีเปิด TOTP ให้ตั้ง `MEGA_TOTP_SECRET` ด้วย)
   - **ดาวน์โหลด ZIP** — ให้ browser ดาวน์โหลดไฟล์ media ที่รวมเป็น ZIP; ไม่ต้องตั้ง secret เพิ่ม
3. ตรวจรายการว่าลิงก์ทุกบรรทัดถูกต้องและไม่ซ้ำ; แก้รายการที่ผิดหรือซ้ำ และไม่เกิน 200 ลิงก์
4. เปิด **Large-file mode** เมื่อต้องการส่ง Telegram เกิน 50 MB และระบบถูกตั้งค่า Local Bot API แล้ว; ตัวเลือกนี้ไม่จำเป็นสำหรับ MEGA/Dropbox/Download และแต่ละปลายทางมีขีดจำกัดของตัวเอง
5. กดปุ่มเริ่มงานหนึ่งครั้ง. Dashboard ส่ง URL และ destinations ไป Worker; หนึ่งชุดจะสร้างหนึ่ง GitHub Actions run

ระบบจะเลือกวิดีโอที่มี **bitrate และความละเอียดสูงสุดที่ต้นทางเปิดให้ดาวน์โหลด** ก่อนเสมอ โดยจะพยายามไม่ลดคุณภาพเอง. หากไฟล์คุณภาพสูงเกินขนาดที่ปลายทางรับได้ ระบบจะลอง variant ที่ต่ำลงตามลำดับ; Dropbox/MEGA/ZIP ใช้เพดานไฟล์ของระบบได้สูงสุด 2,000 MB ส่วน Telegram ปกติจำกัด 50 MB และต้องเปิด Large-file mode สำหรับไฟล์ใหญ่

การกดเริ่มงานเป็นการประมวลผลจริงและอาจส่งไฟล์เข้า Telegram/MEGA หรือสร้าง private download artifact. อย่ากดชุดเดิมซ้ำขณะงานกำลังทำงาน; เปิด Job/Run link และดูผลก่อน

## 3. ดูผลและดาวน์โหลด

Dashboard แสดงสถานะแยกตามโพสต์, media และปลายทาง. ตัวอย่าง: Telegram `success`, MEGA `failed`, Download `ready` จะเห็นได้ว่าไฟล์ถูกส่งบางปลายทางและ job ไม่ได้ล้มเหลวทั้งหมด. การ retry post เดิมจะข้าม destination/media ที่สำเร็จไปแล้วและพยายามเฉพาะส่วนที่ยังไม่สำเร็จ

เมื่อ ZIP พร้อม ให้กด **ดาวน์โหลดไฟล์ ZIP**. ไฟล์ถูกส่งจาก GitHub Actions artifact ผ่าน Worker แบบ streaming และมีอายุ 7 วัน; หลังหมดอายุให้เริ่ม job ใหม่เพื่อสร้าง ZIP อีกครั้ง. iOS/Android อาจแสดง Downloads, Share หรือ Files ตาม browser และการตั้งค่าเครื่อง; สำหรับไฟล์ใหญ่ควรใช้ Wi‑Fi และมีพื้นที่ว่างเพียงพอ

## 4. ตั้งค่า MEGA (ทำครั้งเดียว)

ถ้าต้องการเลือก MEGA ผู้ดูแล repository ต้องเพิ่ม credentials ที่ GitHub โดยตรง:

1. เปิด [GitHub Actions Secrets สำหรับ X2Telegram](https://github.com/aodxx/X2Telegram/settings/secrets/actions)
2. กด **New repository secret** และเพิ่ม `MEGA_EMAIL` เป็นอีเมลบัญชี MEGA
3. เพิ่ม `MEGA_PASSWORD` เป็นรหัสผ่านบัญชี MEGA
4. หากบัญชีใช้ MFA/TOTP ให้เพิ่ม `MEGA_TOTP_SECRET` เป็น seed สำหรับ authenticator; หากไม่ได้ใช้ MFA ให้ไม่ต้องสร้าง secret นี้
5. กลับ Dashboard แล้วเลือก MEGA

**อย่าวาง MEGA password หรือ TOTP seed ใน Dashboard, source code, log, issue หรือข้อความแชต**. ค่าเหล่านี้ใช้เฉพาะภายใน runner และไม่แสดงใน report. โฟลเดอร์เริ่มต้นใน MEGA คือ `X2Telegram/YYYY-MM-DD`; ชื่อไฟล์ MEGA ต่อท้ายด้วย SHA-256 ของเนื้อหาเพื่อเก็บ media คนละเวอร์ชันเป็นคนละไฟล์ ไม่ทับชื่อเดิม. หากต้องการเปลี่ยน root ให้เพิ่ม repository variable `MEGA_REMOTE_FOLDER` ที่ Settings → Secrets and variables → Actions → Variables (เช่น `Archive/X2Telegram`)

## 5. ขนาดและพฤติกรรม

| ปลายทาง | ขีดจำกัดปัจจุบัน |
|---|---|
| Telegram Bot API ปกติ | 50 MB ต่อไฟล์ |
| Telegram Local Bot API (Large-file mode) | 2,000 MB ต่อไฟล์ |
| MEGA | ขึ้นกับบัญชี/พื้นที่ MEGA และเพดาน downloader 2,000 MB ต่อไฟล์ |
| Browser ZIP | 2,000 MB ต่อไฟล์ และ 8 GiB รวมต่อ job; artifact เก็บ 7 วัน |

Python ดาวน์โหลด media หนึ่งครั้งแล้ว dispatch ไปยังปลายทางที่เลือก. เมื่อปลายทางหนึ่งล้มเหลว ปลายทางอื่นยังทำต่อ; Dashboard แสดง `partial_success` เมื่อมีทั้งผลสำเร็จและความล้มเหลว

## 6. งานล่าสุดและการแก้ปัญหา

- Job ล่าสุดเก็บใน local storage ของ browser เครื่องนี้; ใช้ **งานล่าสุด** เพื่อเรียกสถานะกลับหลัง refresh
- **ยังไม่ได้ยืนยัน Access**: กด **ลงชื่อเข้าใช้**, ทำ OTP แล้วกลับมา Dashboard/refresh
- **ปุ่มเริ่มยังใช้ไม่ได้**: แก้ลิงก์ที่ผิด/ซ้ำ ตรวจจำนวนไม่เกิน 200 และเลือกอย่างน้อยหนึ่งปลายทาง
- **MEGA `mega_credentials_missing`**: ตรวจว่ามี GitHub secrets ชื่อ `MEGA_EMAIL` และ `MEGA_PASSWORD`
- **MEGA `mega_authentication_failed`**: ตรวจอีเมล/รหัสผ่าน; หากบัญชีปิด 2FA ให้ลบ Secret `MEGA_TOTP_SECRET` ที่ไม่จำเป็นออก แต่ถ้าเปิด TOTP ให้เก็บ seed แบบ Base32 (ไม่ใช่รหัส 6 หลัก) ใน Secret นี้. ห้ามใส่ค่า credential ใน report
- **ไฟล์เก่าถูกเขียนทับก่อนแก้ไข**: ใน MEGA ตรวจเมนูสามจุด → **Previous versions** (ไอคอนรูปนาฬิกา) หากเปิด File versioning ไว้; [คู่มือ MEGA เรื่อง file version history](https://help.mega.io/files-folders/data-restoration/file-version-history). การกู้คืนขึ้นกับการตั้งค่าและข้อมูลที่บัญชียังเก็บอยู่
- **Download `download_expired`**: artifact หมดอายุหลัง 7 วัน ให้เริ่ม job ใหม่
- **Download `download_artifact_size_limit`**: รวมไฟล์เกิน 8 GiB ต่อ job; แบ่ง URL เป็นหลายชุด
- **Telegram `telegram_file_too_large`**: เปิด Large-file mode เฉพาะเมื่อ Local Bot API credentials ถูกตั้งแล้ว
- **Workflow `failed`**: เปิด GitHub Run link และดู target/error code ก่อน retry
- **ไม่มี media / metadata error**: โพสต์อาจ private, ถูกลบ, จำกัดการเข้าถึง หรือไม่มี media ที่รองรับ

## 7. GitHub Actions โดยตรง

เป็นทางเลือกสำรอง: เปิด [X2Telegram workflow](https://github.com/aodxx/X2Telegram/actions/workflows/x2telegram.yml), เลือก branch `main`, กด **Run workflow** แล้วใส่ URL เดี่ยวใน `url` หรือหลายรายการใน `urls` (หนึ่ง URL ต่อบรรทัด). หากตั้งค่า destinations ให้ส่ง JSON array เช่น `["telegram","download"]`; หากไม่ส่ง ค่าเริ่มต้นคือ Telegram. ห้ามกรอก `url` และ `urls` พร้อมกัน

## ขอบเขตการทดสอบ

ชุดทดสอบอัตโนมัติครอบคลุมปลายทางเดี่ยว/ผสม, การ retry เฉพาะ target ที่ยังไม่สำเร็จ, artifact ZIP streaming, missing-artifact handling, Access และ batch. Live E2E ยืนยัน Telegram normal path, 2-URL batch no-resend, Download-only 2 URLs, MEGA-only upload และ combined Telegram+MEGA/Dropbox/Download สำหรับ media ที่ดึงได้หนึ่งรายการใน run [#38037210973](https://github.com/aodxx/X2Telegram/actions/runs/38037210973). **Telegram Local Bot API สำหรับไฟล์เกิน 50 MB, Dropbox refresh-token-only/large-file session และ mobile browser ยังไม่มี live evidence**. อ่าน [`MULTI_DESTINATION.md`](MULTI_DESTINATION.md), [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md) และ [`DEPLOYMENT.md`](DEPLOYMENT.md) เพิ่มเติม

### ตั้งค่า Dropbox

ผู้ดูแลระบบต้องสร้าง Dropbox Scoped App แล้ว authorize แบบ offline (`token_access_type=offline`) เพื่อรับ Refresh Token. เพิ่ม `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET` และ `DROPBOX_REFRESH_TOKEN` ใน GitHub Actions Secrets; `DROPBOX_ACCESS_TOKEN` ไม่จำเป็นสำหรับการตั้งค่าใหม่. ตั้งโฟลเดอร์ด้วย Repository variable `DROPBOX_REMOTE_FOLDER` ได้. ห้ามใส่ credential ใน Dashboard หรือข้อความรายงาน. ดูขั้นตอนทีละจุดและวิธีทดสอบ upload session สำหรับไฟล์ใหญ่ใน [คู่มือตั้งค่า Dropbox ภาษาไทย](DROPBOX_SETUP_TH.md).
