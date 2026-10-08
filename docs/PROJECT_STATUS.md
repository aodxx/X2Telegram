# X2Telegram — Project Status

**อัปเดต:** 2026-10-09
**สถานะ:** Multi-destination Dashboard/API merge และ deploy แล้ว; Telegram เดิมและ Browser ZIP พร้อมใช้งาน; MEGA integration ติดตั้งใน source แล้วและรอเจ้าของตั้งบัญชี Actions Secrets ก่อนใช้งานจริง

## ภาพรวม

ระบบรับ X post URL จาก Dashboard ส่วนตัว, ตรวจ Cloudflare Access, dispatch GitHub Actions แล้วประมวลผล media **หนึ่งครั้งต่อ media item** ก่อนส่งไปยังปลายทางที่เลือกได้: Telegram, MEGA และ Browser ZIP. ยังคงใช้ workflow หลักเพียง workflow เดียว และไม่เพิ่ม database/Redis/queue/Google Drive ใน production path

Dashboard เดิมอยู่ที่ [X2Telegram Dashboard](https://aodxx.github.io/X2Telegram/) และเสิร์ฟ static assets/API จาก Worker origin เดียวกัน. เลือกได้สูงสุด 50 URLs ต่อ job และหนึ่งหรือหลาย destinations

## Deployment ปัจจุบัน

- PR [#6](https://github.com/aodxx/X2Telegram/pull/6) merged เป็น commit `389621bab764d15aa7ded722b74a944314693274` (2026-10-09)
- Worker `x2telegram-control-plane` deploy แล้วที่ `https://x2telegram-control-plane.pantipa3826.workers.dev`
- Worker version ID: `0a099878-485a-43ef-9097-cf4f44e24373`
- GitHub Pages deploy run [#37842981450](https://github.com/aodxx/X2Telegram/actions/runs/37842981450) ผ่าน; URL redirect ไปยัง Worker-hosted Dashboard ที่ป้องกันด้วย Access และ browser live แสดง `Access ลงชื่อเข้าใช้แล้ว · พร้อมส่ง`

## ปลายทาง

| ปลายทาง | สถานะ | หมายเหตุ |
|---|---|---|
| Telegram | ใช้งานได้ | Chat ถูกล็อกไว้; Bot API ปกติ 50 MB/ไฟล์; Large-file mode ใช้ Local Bot API (ยังไม่ทดสอบ live ในรอบนี้) |
| Browser ZIP | ใช้งานได้และผ่าน live smoke test | private Actions artifact อายุ 7 วัน; 2,000 MB ต่อไฟล์และ 8 GiB รวมต่อ job; Worker stream ผ่าน Access |
| MEGA | Implementation พร้อม; ต้องตั้งบัญชี | `MEGA_EMAIL`, `MEGA_PASSWORD`, optional `MEGA_TOTP_SECRET` ใน Actions Secrets; โฟลเดอร์ default `X2Telegram/YYYY-MM-DD`, ปรับด้วย `MEGA_REMOTE_FOLDER` repository variable |

## Live evidence

1. Telegram normal path เดิม: Actions run [#37807253687](https://github.com/aodxx/X2Telegram/actions/runs/37807253687) ส่ง MP4 หนึ่งไฟล์สำเร็จ
2. Dashboard batch เดิม: run [#37816856323](https://github.com/aodxx/X2Telegram/actions/runs/37816856323) รับ 2 URLs ในหนึ่ง workflow และข้าม completed posts ทั้งคู่โดยไม่ส่งซ้ำ
3. Download-only หลัง merge/deploy: run [#37843359593](https://github.com/aodxx/X2Telegram/actions/runs/37843359593) จาก Dashboard ประมวลผล 2 URLs, รายงาน Download `ready` 2 files, upload private artifact ผ่าน และ browser ดาวน์โหลด ZIP ผ่าน `/jobs/<job_id>/download` ภายใต้ Access ได้จริง; ZIP 256,966,632 bytes, 2 entries, CRC check ผ่าน. Telegram และ MEGA ไม่ได้เลือกใน run นี้

การส่งหลายปลายทางใน job เดียว, isolated failure, retry เฉพาะ failed destination, mixed photo/video, MEGA login/TOTP และ archive size boundary ครอบคลุม automated mock/local tests. **ยังไม่มี live MEGA upload หรือ live combined Telegram+MEGA run**; ต้องตั้ง credentials ก่อนยืนยัน MEGA

## Validation ล่าสุด

- Python: `python3 -m pytest -q` — **71 passed**
- Cloudflare Worker: `npm test --prefix control-worker` — **25 passed**
- `node --check control-worker/src/index.js`, `python -m compileall -q src tests`, workflow YAML parse, `git diff --check`, `npm ci` และ Wrangler dry-run ผ่าน
- Live Actions run #37843359593 ผ่าน automated tests, process, report upload และ browser media artifact upload

## การตั้งค่า MEGA

ไปที่ GitHub repository → **Settings → Secrets and variables → Actions** แล้วเพิ่ม `MEGA_EMAIL` และ `MEGA_PASSWORD`; เพิ่ม `MEGA_TOTP_SECRET` เฉพาะเมื่อบัญชีใช้ TOTP. หากต้องการเปลี่ยนโฟลเดอร์ root ให้เพิ่ม repository variable `MEGA_REMOTE_FOLDER`. ตั้ง credential เฉพาะใน GitHub Secrets—ไม่ต้องนำมาใส่ใน Dashboard

## ขอบเขต/ข้อจำกัดที่ยังเหลือ

- ไม่ได้ทำ live MEGA upload เพราะต้องใช้บัญชี/credentials ของเจ้าของ
- ไม่ได้ส่ง Telegram ซ้ำเพื่อทดสอบ combined target; mock tests ตรวจ retry/dedupe และ live smoke รอบนี้เลือก Download-only โดยตั้งใจ
- ยังไม่ได้ทดสอบ browser มือถือจริงหรือ Telegram Local Bot API large-file path ในรอบนี้
- GitHub artifact หมดอายุ 7 วัน; สร้าง job ใหม่เพื่อได้ ZIP ใหม่
- ระบบไม่อ้าง exactly-once เมื่อ destination รับไฟล์แล้ว response/checkpoint สูญหาย

## เอกสาร

- [คู่มือใช้งาน Dashboard ภาษาไทย](USER_GUIDE_TH.md)
- [ปลายทางหลายแบบและ MEGA setup](MULTI_DESTINATION.md)
- [Deployment guide](DEPLOYMENT.md)
- [Architecture](ARCHITECTURE.md)
- [Control Plane contract](CONTROL_PLANE_CONTRACT.md)
- [E2E test report](E2E_TEST_REPORT.md)
