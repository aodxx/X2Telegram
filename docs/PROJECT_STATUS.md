# X2Telegram — Project Status

**วันที่อัปเดต:** 2026-10-09
**สถานะงานนี้:** multi-destination implementation อยู่บน branch `feat/multi-destination`; local validation ผ่าน; ยังต้อง merge และ deploy Worker/Pages source ก่อนผู้ใช้จะเห็นตัวเลือกใหม่

## สรุป

X2Telegram ต่อจากระบบเดิมให้ประมวลผล media หนึ่งครั้งแล้ว dispatch ไปยังปลายทางที่เลือกได้: Telegram, MEGA และ Browser ZIP. ยังคงใช้ Dashboard → Cloudflare Worker → GitHub Actions → Python worker; ไม่เพิ่ม database/Redis/queue/Google Drive และใช้ workflow หลักเดียว

Production baseline ก่อน feature นี้มี Dashboard/Access same-origin, batch สูงสุด 50 URLs และ Telegram normal-path E2E ที่ยืนยันการส่งหนึ่ง MP4. งานนี้เพิ่ม multi-destination ใน source และ automated tests; ยังไม่อ้าง live MEGA verification เพราะต้องใช้ credentials ของบัญชีเจ้าของ

## สิ่งที่เพิ่มใน feature นี้

- Destination dispatcher ส่ง local media file เดียวไปยัง Telegram/MEGA/Download; ภาพทุกชิ้นและ video variant ที่เลือกถูกประมวลผลแยกตามไฟล์
- Dashboard มี checkbox เลือกหนึ่งหรือหลายปลายทาง, per-target status, error และ Browser ZIP download link
- Worker validate destinations, รวม target selection ใน request/job fingerprint, ส่งต่อไปยัง workflow และ stream private artifact ZIP ผ่าน Access-protected endpoint
- MEGA adapter ใช้ MEGAcmd official CLI, remote folder เริ่มต้น `X2Telegram/YYYY-MM-DD`, optional `MEGA_REMOTE_FOLDER` repository variable; credentials อยู่ใน Actions Secrets
- Download adapter ใช้ browser ZIP จาก private Actions artifact อายุ 7 วัน; จำกัด media 2,000 MB ต่อไฟล์และ archive รวม 8 GiB/job; Worker stream ไม่ buffer ไฟล์ทั้งก้อน
- Dedupe state v3 จด success ต่อ media และ persistent target (Telegram/MEGA); retry ข้าม success เดิมและลองเฉพาะ target ที่ยังไม่สำเร็จ
- Download-only ไม่เขียน persistent delivery dedupe; artifact เป็น output เฉพาะ job
- ถ้า artifact Download หาย/หมดอายุ Worker เปลี่ยนผล target เป็น failed และไม่แสดง false-ready

## Validation

- Python: `python3 -m pytest -q` — **71 passed** (มีทั้ง destination combinations, mixed photo/video, single-download, retry เฉพาะ MEGA failure, invalid MEGA folder isolation, size limits, secret redaction)
- Control Worker: `npm test --prefix control-worker` — **25 passed** (destinations validation/idempotency, partial success, protected streaming ZIP, missing-artifact handling)
- `node --check`, `python -m compileall`, YAML parse, `git diff --check`, CI-equivalent `npm ci` และ Wrangler dry-run ผ่าน
- Existing live evidence: normal-path one MP4 (Actions run `37807253687`) และ two-URL batch/no-resend (run `37816856323`); **ยังไม่ใช่ live multi-destination verification**

## ตั้งค่าเพื่อใช้ MEGA

Repository owner ต้องสร้าง GitHub Actions Secrets `MEGA_EMAIL`, `MEGA_PASSWORD` และ `MEGA_TOTP_SECRET` เฉพาะบัญชีที่เปิด MFA. หากต้องการเปลี่ยนโฟลเดอร์ ให้ตั้ง repository variable `MEGA_REMOTE_FOLDER`; default คือ `X2Telegram`. ค่า credential ไม่ต้องส่งผ่าน Dashboardหรือ source code

## ข้อจำกัด/งานต่อ

1. Merge branch และ deploy Worker/Pages เพื่อให้ Dashboard live แสดงปลายทางใหม่
2. ทดสอบ Download-only หรือ Download+Telegram แบบ no-resend ผ่าน workflow จริงและตรวจ ZIP download route
3. เมื่อตั้ง MEGA credentials แล้วจึงทดสอบ upload จริง; ก่อนมี credentials มีเพียง mocked/credential-missing tests
4. ทดสอบ mobile browser จริงและ live partial failure หากจำเป็น; automated tests ครอบ logic สำคัญแล้ว

## เอกสารอ้างอิง

- [คู่มือ Dashboard ภาษาไทย](USER_GUIDE_TH.md)
- [Multi-destination setup](MULTI_DESTINATION.md)
- [Deployment guide](DEPLOYMENT.md)
- [Architecture](ARCHITECTURE.md)
- [Control Plane API contract](CONTROL_PLANE_CONTRACT.md)
- [E2E test report](E2E_TEST_REPORT.md)
- [Cloudflare Worker](CLOUDFLARE_WORKER.md)
