# X2Telegram — Project Status

**อัปเดต:** 2026-10-12
**สถานะ:** Production Worker deploy แล้วผ่าน GitHub Actions พร้อม edge rate limiting; Telegram, Browser ZIP, MEGA และ Dropbox มีหลักฐาน live สำเร็จอย่างน้อยหนึ่งไฟล์. ขอบเขต large-file ของ Telegram/Dropbox และความสำเร็จในการดึง media จาก X ยังต้องทดสอบ/ติดตามเพิ่ม

## ภาพรวม

ระบบรับ X post URL จาก Dashboard ส่วนตัว, ตรวจ Cloudflare Access, dispatch GitHub Actions แล้วประมวลผล media **หนึ่งครั้งต่อ media item** ก่อนส่งไปยังปลายทางที่เลือกได้: Telegram, MEGA, Dropbox และ Browser ZIP. ยังคงใช้ workflow หลักเพียง workflow เดียว และไม่เพิ่ม database/Redis/queue/Google Drive ใน production path

Dashboard เดิมอยู่ที่ [X2Telegram Dashboard](https://aodxx.github.io/X2Telegram/) และเสิร์ฟ static assets/API จาก Worker origin เดียวกัน. เลือกได้สูงสุด 50 URLs ต่อ job และหนึ่งหรือหลาย destinations

## Deployment ปัจจุบัน

- Worker `x2telegram-control-plane` deploy แล้วที่ `https://x2telegram-control-plane.pantipa3826.workers.dev`
- Current Worker version ID: `c44298fb-47f9-4798-a3db-9cd6946018fb`
- Deploy commit: `fe3170fb3fc23cf06ee8a9a838866e38d207480c`
- Deploy workflow: [#38171587335](https://github.com/aodxx/X2Telegram/actions/runs/38171587335) — success
- `JOB_DISPATCH_RATE_LIMITER`: 20 requests/60 seconds per Access identity
- GitHub Pages deploy run [#37842981450](https://github.com/aodxx/X2Telegram/actions/runs/37842981450) ผ่าน; URL redirect ไปยัง Worker-hosted Dashboard ที่ป้องกันด้วย Access และ browser live แสดง `Access ลงชื่อเข้าใช้แล้ว · พร้อมส่ง`

## ปลายทาง

| ปลายทาง | สถานะ | หมายเหตุ |
|---|---|---|
| Telegram | ใช้งานได้สำหรับ standard-size media; มี failure ที่เป็นขีดจำกัดตาม config | Normal sends ผ่าน live; `telegram_file_too_large` เกิดเมื่อไม่เปิด Large-file mode สำหรับไฟล์เกิน 50 MB; Local Bot API large-file mode ยังไม่ live-tested |
| Browser ZIP | ใช้งานได้และผ่าน live smoke test | private Actions artifact อายุ 7 วัน; 2,000 MB ต่อไฟล์และ 8 GiB รวมต่อ job; Worker stream ผ่าน Access |
| MEGA | ใช้งานได้และผ่าน live upload + version-retention integration | PR [#9](https://github.com/aodxx/X2Telegram/pull/9) แก้ชื่อไฟล์ด้วย SHA-256 เต็ม; run [#37984146026](https://github.com/aodxx/X2Telegram/actions/runs/37984146026) ยืนยันเก็บไฟล์เนื้อหาสองเวอร์ชันได้จริงบน MEGA. โฟลเดอร์ default `X2Telegram/YYYY-MM-DD` |
| Dropbox | live upload ผ่าน 1 media ใน combined run | Run [#38037210973](https://github.com/aodxx/X2Telegram/actions/runs/38037210973) รายงาน Dropbox success สำหรับ media ที่ดาวน์โหลดได้; OAuth refresh/401 recovery และ large-file upload session ยังยืนยันด้วย automated tests เท่านั้น |

## Live evidence

1. Telegram normal path เดิม: Actions run [#37807253687](https://github.com/aodxx/X2Telegram/actions/runs/37807253687) ส่ง MP4 หนึ่งไฟล์สำเร็จ
2. Dashboard batch เดิม: run [#37816856323](https://github.com/aodxx/X2Telegram/actions/runs/37816856323) รับ 2 URLs ในหนึ่ง workflow และข้าม completed posts ทั้งคู่โดยไม่ส่งซ้ำ
3. Download-only หลัง merge/deploy: run [#37843359593](https://github.com/aodxx/X2Telegram/actions/runs/37843359593) จาก Dashboard ประมวลผล 2 URLs, รายงาน Download `ready` 2 files, upload private artifact ผ่าน และ browser ดาวน์โหลด ZIP ผ่าน `/jobs/<job_id>/download` ภายใต้ Access ได้จริง; ZIP 256,966,632 bytes, 2 entries, CRC check ผ่าน. Telegram และ MEGA ไม่ได้เลือกใน run นี้
4. MEGA-only หลังตั้ง Secrets: run [#37848879753](https://github.com/aodxx/X2Telegram/actions/runs/37848879753) ประมวลผล URL ที่เจ้าของให้ไว้; workflow success และ Dashboard report แสดง MEGA สำเร็จ 1, failed 0. Telegram และ Browser ZIP ไม่ได้เลือก

5. MEGA version-retention integration หลัง fix: run [#37984146026](https://github.com/aodxx/X2Telegram/actions/runs/37984146026) ใช้ fixture 2 payloads ที่แทน media คนละเวอร์ชันของ post เดียวกัน; อัปโหลดทั้งสองชื่อ, ตรวจพบใน MEGA และดาวน์โหลดกลับมาเทียบ bytes ผ่าน. ใช้ test folder แยกตาม run ID
6. Combined 4-destination live test: run [#38037210973](https://github.com/aodxx/X2Telegram/actions/runs/38037210973) เลือก Telegram/MEGA/Dropbox/Download. Media 1 ชิ้นส่งสำเร็จทั้ง 4 targets; URL ที่สองล้มที่ `download_error` ก่อนถึง targets. จึงจบเป็น partial success/Actions failure ไม่ใช่ failure ของทั้ง 4 ช่องทาง
7. Telegram ล่าสุด: run [#38102180526](https://github.com/aodxx/X2Telegram/actions/runs/38102180526) ส่งสำเร็จ; run [#38102024465](https://github.com/aodxx/X2Telegram/actions/runs/38102024465) รายงาน `telegram_file_too_large` แต่ MEGA สำเร็จ; run [#38102121635](https://github.com/aodxx/X2Telegram/actions/runs/38102121635) ล้มที่ `download_error` ก่อนส่ง

MEGA live version-retention test ใช้ synthetic media fixtures ไม่ใช่การดึง X จริง; combined run ยืนยัน live send ครบ 4 targets สำหรับหนึ่ง media item. Deployment ล่าสุดยืนยัน Wrangler dry-run และ edge rate-limit binding แล้ว; Dropbox large-file upload และ Telegram Local Bot API large-file path ยังไม่มี live evidence

## Validation ล่าสุด

- Python: `python3 -m pytest -q` — **95 passed**
- Cloudflare Worker: `npm test --prefix control-worker` — **27 passed**
- `node --check control-worker/src/index.js`, `python -m compileall -q src tests`, workflow YAML parse, `git diff --check`, `npm ci` และ Wrangler dry-run ผ่าน
- Live Actions run #37843359593 ผ่าน automated tests, process, report upload และ browser media artifact upload
- Live Actions run #37848879753 ผ่าน automated tests และ MEGA-only process/report; Dashboard report ยืนยัน media success

## การตั้งค่า MEGA

ไปที่ GitHub repository → **Settings → Secrets and variables → Actions** แล้วเพิ่ม `MEGA_EMAIL` และ `MEGA_PASSWORD`; เพิ่ม `MEGA_TOTP_SECRET` เฉพาะเมื่อบัญชีใช้ TOTP (ถ้าปิด 2FA ให้ไม่สร้าง secret นี้). หากต้องการเปลี่ยนโฟลเดอร์ root ให้เพิ่ม repository variable `MEGA_REMOTE_FOLDER`. ตั้ง credential เฉพาะใน GitHub Secrets—ไม่ต้องนำมาใส่ใน Dashboard

## ขอบเขต/ข้อจำกัดที่ยังเหลือ

- X media fetch ยังมี `download_error` ในบาง run; เมื่อเกิดก่อน destination dispatch จะล้มพร้อมกันทุก target สำหรับ URL นั้น (เช่น run #38037210973)
- Telegram >50 MB ต้องเปิด Large-file mode และ Local Bot API; run #38102024465 ยืนยันว่า standard mode ปฏิเสธไฟล์ใหญ่ตาม limit; Local Bot API path ยังไม่ live-tested
- Dropbox live upload ผ่านหนึ่ง media แล้ว; OAuth refresh หลัง token expiry และ large-file upload session ยังมีเพียง automated coverage
- ยังไม่ได้ทดสอบ browser มือถือจริง
- GitHub artifact หมดอายุ 7 วัน; สร้าง job ใหม่เพื่อได้ ZIP ใหม่
- ระบบไม่อ้าง exactly-once เมื่อ destination รับไฟล์แล้ว response/checkpoint สูญหาย

## เอกสาร

- [คู่มือใช้งาน Dashboard ภาษาไทย](USER_GUIDE_TH.md)
- [ปลายทางหลายแบบและ MEGA setup](MULTI_DESTINATION.md)
- [คู่มือตั้งค่า Dropbox OAuth และไฟล์ใหญ่](DROPBOX_SETUP_TH.md)
- [Deployment guide](DEPLOYMENT.md)
- [Cloudflare Worker deployment workflow](../.github/workflows/deploy-worker.yml)
- [Architecture](ARCHITECTURE.md)
- [Control Plane contract](CONTROL_PLANE_CONTRACT.md)
- [E2E test report](E2E_TEST_REPORT.md)
