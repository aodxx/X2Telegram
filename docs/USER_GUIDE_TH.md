# คู่มือใช้งาน X2Telegram Dashboard

**สถานะ:** หน้า Dashboard เผยแพร่แล้ว และผ่านการตรวจ `Control Worker พร้อม` จาก GitHub Pages origin  
**Dashboard:** <https://aodxx.github.io/X2Telegram/>  
**Pages deploy:** [GitHub Actions run #37809007472](https://github.com/aodxx/X2Telegram/actions/runs/37809007472)  
**PR ที่นำ migration ขึ้น main:** [PR #2 (merged)](https://github.com/aodxx/X2Telegram/pull/2)

> **คำเตือนความปลอดภัย P1:** ค่า GitHub `GH_TOKEN` ที่ใช้กับ Worker เคยถูกส่งในแชตและยังไม่ได้ rotate/revoke ตามคำสั่งก่อนหน้าของเจ้าของ. หน้าเว็บและ Worker ทำงานทางเทคนิคแล้ว แต่ยังไม่ควรถือว่าเป็น production-secure จนกว่าจะเปลี่ยน token. อย่าส่ง token มาในแชต; ขั้นตอนแนะนำอยู่ท้ายคู่มือนี้.

## เริ่มส่งหนึ่งโพสต์

1. เปิด [X2Telegram Dashboard](https://aodxx.github.io/X2Telegram/).
2. ดูแถบสถานะด้านบน ถ้าเห็น **Control Worker พร้อม** แปลว่า browser เข้าถึง API ได้แล้ว. ถ้าไม่พร้อม ให้กด **ลงชื่อเข้าใช้ API ↗**.
3. ที่หน้า Cloudflare Access ใส่อีเมลเจ้าของที่ได้รับอนุญาต แล้วกด **Send login code**. เปิดอีเมลจาก Cloudflare, กรอกรหัส OTP และกลับมา refresh Dashboard. Session มีอายุประมาณ 24 ชั่วโมง.
4. วาง URL สาธารณะของโพสต์ X หนึ่งรายการ เช่น `https://x.com/username/status/1234567890`.
5. กด **ตรวจสอบรายการ** และแก้รายการที่แสดงว่าไม่ถูกต้องก่อน.
6. ตรวจปลายทางที่ล็อกไว้ให้ถูกต้อง: Telegram Supergroup `-1003906817580`.
7. กด **เริ่มส่งเข้า Telegram** เมื่อพร้อมส่งจริง. ปุ่มนี้เริ่ม GitHub Actions และอาจส่ง media เข้า Telegram; ไม่มีโหมด dry-run ในปุ่มนี้.
8. รอให้สถานะจบเป็น `completed` หรือ `failed`. เปิดลิงก์ Run ได้จากงานนั้น และดูผล `sent`/`skipped_duplicate`/ข้อผิดพลาด รวมถึง Telegram message ID.

Dashboard ตั้งใจให้ **หนึ่งโพสต์ต่อหนึ่งงาน**. หากต้องการหลายโพสต์ ให้ตรวจและเริ่มทีละ URL เพื่อแยกสถานะและข้อผิดพลาด. งานล่าสุดและสถานะบางส่วนเก็บใน `localStorage` ของ browser; หลีกเลี่ยงคอมพิวเตอร์สาธารณะหรือ profile browser ที่แชร์กับผู้อื่น.

## สิ่งที่ทดสอบแล้วและข้อจำกัด

- [Normal-path E2E run #37807253687](https://github.com/aodxx/X2Telegram/actions/runs/37807253687) ส่ง MP4 หนึ่งรายการจากโพสต์ทดสอบไปยังกลุ่มที่ล็อกไว้; รายงานยืนยัน message ID `347` และ state v2 ถูกบันทึก.
- โพสต์ทดสอบนั้นถูกบันทึกใน duplicate-prevention state บน `main` แล้ว; **อย่าใช้โพสต์เดิมเป็นการทดสอบส่งซ้ำ**—ระบบควรข้ามเป็น duplicate.
- หลัง merge, Pages deploy run #37809007472 สำเร็จ; หน้าเว็บตอบ `200`, config ชี้ Worker ถูกต้อง, และ health indicator ในหน้าแสดง **Control Worker พร้อม**. ไม่มีการสร้างงาน/ส่ง Telegram เพิ่มระหว่างตรวจหลัง deploy.
- ยังไม่ได้ทดสอบ live: การโหลดหน้าใหม่ระหว่าง run, mobile, large-file mode, multi-photo/หลาย media, partial-failure recovery และ duplicate run เพิ่มเติม. ดู [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md).

## Large-file mode

เปิดตัวเลือก **Large-file mode** เฉพาะเมื่อ media เกิน 50 MB. Workflow ต้องมี secrets `TELEGRAM_API_ID` และ `TELEGRAM_API_HASH` พร้อม Docker Local Bot API Server; scenario นี้ยังไม่ได้ทดสอบจริงครบ. ถ้าไม่แน่ใจให้ปิดตัวเลือกและอย่ากดส่งจนกว่าจะตรวจว่า secrets/runner พร้อม.

## แก้ปัญหาเบื้องต้น

| อาการ | แนวทาง |
|---|---|
| แถบสถานะไม่ขึ้น **Control Worker พร้อม** | กด **ลงชื่อเข้าใช้ API**, ใช้อีเมล owner ที่ allowlist ไว้, กรอก OTP แล้วกลับมา refresh หน้า |
| URL ถูกปฏิเสธ | ใช้ URL `https://x.com/.../status/<id>` หรือ `https://twitter.com/.../status/<id>` ของโพสต์สาธารณะ ไม่ใช้หน้าโปรไฟล์หรือโพสต์ส่วนตัว |
| ได้ 401/403 หรือวนกลับหน้า login | ยืนยันว่าใช้บัญชี/อีเมลที่ได้รับอนุญาต และ Access session ยังไม่หมดอายุ |
| Workflow จบ `failed` | เปิด Run link และอ่าน step ที่ล้มเหลว; อย่ากดส่งซ้ำทันทีหากยังไม่รู้ว่า Telegram รับไฟล์ไปแล้วหรือไม่ |
| ขึ้น `skipped_duplicate` | โพสต์หรือ media ถูกส่งไปแล้ว; ตรวจ Telegram message ID/ปลายทางก่อน ไม่ต้องส่งซ้ำ |
| ไม่มี media หรือโพสต์อ่านไม่ได้ | โพสต์อาจเป็น private, ถูกลบ, จำกัดการเข้าถึง หรือไม่มี media รูปแบบที่รองรับ |
| ไฟล์เกิน 50 MB | ต้องใช้ Large-file mode และ secrets ที่กล่าวไว้ข้างต้น; ถ้าไม่มี อย่าลองส่งซ้ำหลายครั้ง |

**หลังการส่งไม่แน่ใจ:** เปิด Run ที่สัมพันธ์กับงานและตรวจ result/message ID ใน Dashboard ก่อน retry. ระบบมี per-media dedupe แต่ไม่รับประกัน exactly-once ในกรณี Telegram รับไฟล์แล้ว connection ขาดก่อนระบบบันทึก checkpoint.

## ถ้าจำเป็นต้องใช้ GitHub Actions โดยตรง

กด **เปิด Actions ↗**, เลือก workflow **X2Telegram**, เลือก branch `main`, แล้วกด **Run workflow**. สำหรับโพสต์เดียวใช้ input `url`; สำหรับ batch ใช้ `urls` โดยวางหนึ่ง URL ต่อบรรทัด. **ห้ามกรอก `url` และ `urls` พร้อมกัน.** ปลายทาง Telegram ยังล็อกไว้ที่กลุ่มเดิม.

## คำแนะนำก่อนใช้ต่อเนื่อง/production

### P1 — ทำก่อนใช้งานจริงต่อเนื่อง

1. **Rotate/revoke `GH_TOKEN` ที่เปิดเผย**. สร้าง Fine-grained PAT ใหม่ จำกัดเฉพาะ repository `aodxx/X2Telegram`, ให้ `Actions: Read and write` และ `Metadata: Read-only`, ตั้งวันหมดอายุ แล้วบันทึกค่าใหม่เป็น Worker Secret ชื่อ `GH_TOKEN` ใน Cloudflare Dashboard (`Workers & Pages` → `x2telegram-control-plane` → `Settings` → `Variables and Secrets`). ตรวจว่า Worker ใช้ secret ใหม่แล้วจึง revoke token เดิม. อย่าพิมพ์ token ในแชต, source code, screenshot หรือ log.
2. ใช้เฉพาะโพสต์ที่มีสิทธิ์ดาวน์โหลดและเผยแพร่ และทวน URL ก่อนกดส่ง เพราะการกดปุ่มเริ่มงานเป็นการส่งจริง.

### P2 — ลดความเสี่ยงที่ยังเหลือ

- ตั้ง/ทดสอบ global หรือ edge rate limiting; limit ปัจจุบันเป็น best-effort ต่อ Worker isolate.
- จำกัด `contents: write` ใน GitHub Actions ให้แคบลง และ pin Actions/container image เป็น immutable SHA/digest แทน mutable tags.
- ทดสอบ duplicate/no-resend, multi-media, partial failure, refresh, mobile และ large-file ใน test cases ที่ควบคุมได้.
- อย่าสมมติว่าการ retry ปลอด duplicate ในทุก network timeout; ตรวจ Telegram ก่อน retry เมื่อสถานะไม่ชัด.

ดูผลตรวจรายละเอียดใน [`SECURITY_AUDIT.md`](SECURITY_AUDIT.md), [`CLOUDFLARE_ACCESS.md`](CLOUDFLARE_ACCESS.md) และ [`CLOUDFLARE_WORKER.md`](CLOUDFLARE_WORKER.md).
