# X2Telegram

ระบบรับ X post URL แล้วดึง media **หนึ่งครั้ง** เพื่อส่งไฟล์เดียวกันไปยังปลายทางที่ผู้ใช้เลือก โดยใช้ Dashboard ส่วนตัว, Cloudflare Access/Worker และ GitHub Actions

## เลือกปลายทางได้

- **Telegram** — กลุ่มเป้าหมายถูกล็อกไว้ใน workflow; Bot API ปกติไม่เกิน 50 MB ต่อไฟล์, Large-file mode ใช้ Local Bot API (เพดาน 2,000 MB)
- **MEGA** — อัปโหลดด้วย MEGAcmd ไปยัง `/X2Telegram/YYYY-MM-DD`; ต้องตั้ง `MEGA_EMAIL` และ `MEGA_PASSWORD` ใน GitHub Actions Secrets; `MEGA_TOTP_SECRET` ใช้เฉพาะบัญชีที่เปิด TOTP
- **Dropbox** — อัปโหลดผ่าน Dropbox API v2; ใช้ OAuth refresh token, upload session สำหรับไฟล์ใหญ่ และชื่อไฟล์ที่มี content fingerprint เพื่อไม่เขียนทับโดยไม่ตั้งใจ
- **ดาวน์โหลด ZIP** — Dashboard ให้ browser รับ media เป็น ZIP ผ่าน Worker แบบ streaming; artifact เป็น private และเก็บ 7 วัน; ขนาดต่อไฟล์ไม่เกิน 2,000 MB และรวมต่อ job ไม่เกิน 8 GiB

เลือกได้หนึ่งหรือหลายปลายทางพร้อมกัน เช่น Telegram+MEGA, MEGA+Dropbox หรือ Telegram+Download. สถานะและข้อผิดพลาดแสดงแยกตามปลายทาง/ไฟล์; ความล้มเหลวของหนึ่งปลายทางไม่ทำให้ความสำเร็จของอีกปลายทางถูกนับเป็น failure ทั้งหมด

## ใช้งาน

1. เปิด [X2Telegram Dashboard](https://aodxx.github.io/X2Telegram/) แล้วลงชื่อเข้าใช้ Cloudflare Access ด้วยอีเมลที่ได้รับอนุญาต
2. วาง X URL หนึ่งรายการต่อบรรทัด (สูงสุด 50 URL ต่อ job)
3. เลือก Telegram, MEGA, Dropbox และ/หรือดาวน์โหลด ZIP
4. กดเริ่มงานหนึ่งครั้ง แล้วติดตามสถานะรายปลายทางใน Dashboard

อ่าน [คู่มือผู้ใช้ภาษาไทย](docs/USER_GUIDE_TH.md) และ [คู่มือปลายทางหลายแบบ](docs/MULTI_DESTINATION.md) สำหรับการตั้งค่าและข้อจำกัด

## Architecture

```text
Dashboard → Cloudflare Access/Worker → GitHub Actions → Python worker
  → metadata/download/validate once → destination dispatcher → Telegram / MEGA / Dropbox / private ZIP
```

ไม่เพิ่ม database, Redis, queue หรือ Google Drive; GitHub Actions ยังคงเป็น execution plane และ credentials ไม่อยู่ใน frontend. การรัน manual จาก GitHub Actions ยังคงรองรับ legacy `url` เดี่ยวหรือ `urls` แบบ batch และค่า destination ที่ไม่ส่งจะ default เป็น Telegram

## ความปลอดภัยและ retry

Python บันทึกผลสำเร็จแยกตาม media fingerprint และ Telegram/MEGA/Dropbox destination; retry จึงข้าม target ที่สำเร็จแล้วและลองเฉพาะ target ที่ยังไม่สำเร็จ. Browser ZIP เป็น artifact ของ job และสร้างใหม่ได้จาก job ใหม่. GitHub Actions concurrency ป้องกันงานเขียน dedupe state พร้อมกัน แต่ระบบไม่อ้าง exactly-once เมื่อปลายทางรับไฟล์แล้ว response/checkpoint สูญหาย

ใช้เฉพาะ media ที่คุณมีสิทธิ์ดาวน์โหลดและเผยแพร่ และปฏิบัติตามกฎหมาย/เงื่อนไขของแพลตฟอร์ม. X อาจจำกัดโพสต์หรือ rate-limit ซึ่งรายงานผลแยกต่อรายการ

## ตรวจโค้ดและทดสอบ

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
npm ci --prefix control-worker
npm test --prefix control-worker
```

Tests ครอบ Telegram-only, MEGA-only, Download-only, การเลือกปลายทางร่วมกัน, isolated failure/retry, Worker validation/idempotency และ protected ZIP route โดยใช้ mocks/fakes; live MEGA/Dropbox ต้องตั้ง secrets และ OAuth ให้เรียบร้อยก่อนใช้งานจริง. ดูผลทดสอบและข้อจำกัดได้ใน [`docs/E2E_TEST_REPORT.md`](docs/E2E_TEST_REPORT.md) และสถานะโครงการใน [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md).

## ไฟล์เอกสารหลัก

- [`docs/MULTI_DESTINATION.md`](docs/MULTI_DESTINATION.md) — ปลายทาง, MEGA secrets, browser ZIP และ retry
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — การติดตั้ง/ตั้งค่า
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — ภาพรวมระบบ
- [`docs/CONTROL_PLANE_CONTRACT.md`](docs/CONTROL_PLANE_CONTRACT.md) — Worker API และ idempotency
