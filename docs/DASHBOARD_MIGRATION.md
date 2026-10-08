# Dashboard Migration — Access UX, batch และปลายทางหลายแบบ

## Architecture ที่ deploy อยู่

```text
GitHub Pages entry → redirect → Cloudflare Access + Worker-hosted Dashboard/API
  → GitHub Actions → Python processor → Telegram / MEGA / Browser ZIP
```

Dashboard assets และ API อยู่ Worker origin เดียวกันเพื่อให้ Access session เป็น first-party cookie; หน้า Pages ทำหน้าที่เป็น entry/redirect. Worker ตรวจ Access JWT ก่อน serve static assets และบนทุก API endpoint ที่มีข้อมูลหรือ side effects. Browser session ที่ทดสอบหลัง merge แสดง **Access ลงชื่อเข้าใช้แล้ว · พร้อมส่ง**

## URL และ destination flow

- วาง X URL หนึ่งรายการต่อบรรทัด; 1–50 URL ต่อ job
- Frontend preview บอก valid/invalid/duplicate; Worker ตรวจ URL และ duplicate post ID ซ้ำอีกครั้ง
- URL เดี่ยวถูกส่งเป็น workflow input `url`; batch ถูกส่งเป็น `urls` newline-separated; หนึ่ง job คือหนึ่ง GitHub Actions run
- เลือกได้หนึ่งหรือหลาย targets จาก `telegram`, `mega`, `download`; ถ้าไม่ระบุโดย manual Actions จะ default Telegram
- Job fingerprint รวม request ID, ordered normalized URL(s), large-file flag และ normalized destinations; `request_id` เดิมกับ payload/target ที่เปลี่ยนถูกปฏิเสธด้วย `409 idempotency_conflict`
- Dashboard แสดง status/error แยก post, media และ destination; target ที่ล้มเหลวไม่ยกเลิก target อื่น

## Login และ recovery

- `GET /auth/check` ต้องผ่าน Access JWT และ owner email; Dashboard ใช้ตรวจ session ก่อนเปิด submit
- เมื่อกลับมาที่แท็บเดิมหลัง login, focus/visibility check และ refresh จะยืนยันสถานะใหม่
- ปุ่ม Access เปิด Worker-hosted Dashboard ในแท็บใหม่; Pages และ Worker entry ยังคงใช้ same-origin backend config
- สถานะ recent jobs เก็บใน `localStorage` ของ browser นี้; ไม่มี server-side job database

## Browser ZIP

เมื่อเลือก Download ระบบสร้าง private GitHub Actions artifact 7 วัน แล้วเพิ่ม link ใน Dashboard. `GET /jobs/<job_id>/download` ตรวจ Access และ artifact ที่ตรงกับ run ก่อน stream ZIP ไปยัง browser; Worker ไม่คืน signed GitHub URL และไม่ buffer media ZIP ทั้งก้อน. ขีดจำกัด 2,000 MB ต่อไฟล์และ 8 GiB รวมต่อ job; artifact ที่หาย/หมดอายุถูกแสดงเป็น Download failure

บนมือถือ download ทำงานผ่าน browser Downloads/Files/Share sheet ตามแพลตฟอร์ม ไม่ได้เขียนไฟล์จาก Actions runner ลง device โดยตรง

## Live evidence หลัง deploy

- Worker version `0a099878-485a-43ef-9097-cf4f44e24373` จาก PR #6 / commit `389621b`
- Access authenticated Dashboard ถูกตรวจใน browser
- Actions run [#37843359593](https://github.com/aodxx/X2Telegram/actions/runs/37843359593) ประมวลผล Download-only 2 URLs; report แสดง 2 ready files, media ZIP upload ผ่าน และ ZIP ดาวน์โหลดผ่าน protected Worker route ได้จริง (2 entries, CRC ผ่าน)
- MEGA-only run [#37848879753](https://github.com/aodxx/X2Telegram/actions/runs/37848879753) ผ่าน; Dashboard report แสดง upload success หนึ่งรายการ. Telegram normal-path และ batch/no-resend evidence อยู่ใน [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md)

## ข้อจำกัด

- Batch เกิน 50 URLs ต้องแบ่งหลาย jobs
- MEGA-only upload ผ่าน live แล้ว; live Telegram+MEGA combined send ยังไม่ยืนยัน เพื่อหลีกเลี่ยงการส่ง Telegram ซ้ำโดยไม่จำเป็น
- Large-file mode และมือถือยังไม่ได้ live-test รอบนี้
- Network timeout หลัง Telegram/MEGA รับไฟล์แล้วแต่ก่อน dedupe checkpoint อาจต้องตรวจ report ก่อน retry

รายละเอียดผู้ใช้: [`USER_GUIDE_TH.md`](USER_GUIDE_TH.md); API schema: [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md); multi-destination setup: [`MULTI_DESTINATION.md`](MULTI_DESTINATION.md).
