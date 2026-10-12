# X2Telegram — Project Status

**อัปเดต:** 2026-10-13
**สถานะ:** P1/P2 ผ่านหลักฐานตามขอบเขตเดิม. P3 ถูก squash-merge จาก PR [#24](https://github.com/aodxx/X2Telegram/pull/24) เป็น main commit `9e9e9f8`; main CI [#38293276028](https://github.com/aodxx/X2Telegram/actions/runs/38293276028) และ GitHub Pages publish [#38293276008](https://github.com/aodxx/X2Telegram/actions/runs/38293276008) ผ่าน. Cloudflare Worker deploy [#38293345118](https://github.com/aodxx/X2Telegram/actions/runs/38293345118) ผ่านด้วย version `f2e1afaf-db8e-4356-be75-215f60eb53e5`. P3 คงสถานะ partial: ไม่มี live destination invocation และยังมี cross-isolate race / success-checkpoint storage failure ที่ไม่รับประกัน exactly-once.

สำหรับ agent ที่เข้ามาทำงานต่อ ให้เริ่มจาก [`AGENT_HANDOFF.md`](AGENT_HANDOFF.md) ซึ่งมีลำดับ backlog, acceptance criteria และ deploy protocol ปัจจุบัน

## ภาพรวม

ระบบรับ X post URL จาก Dashboard ส่วนตัว, ตรวจ Cloudflare Access, dispatch GitHub Actions แล้วประมวลผล media **หนึ่งครั้งต่อ media item** ก่อนส่งไปยังปลายทางที่เลือกได้: Telegram, MEGA, Dropbox และ Browser ZIP. ยังคงใช้ workflow หลักเพียง workflow เดียว และไม่เพิ่ม database/Redis/queue/Google Drive ใน production path

Dashboard เดิมอยู่ที่ [X2Telegram Dashboard](https://aodxx.github.io/X2Telegram/) และเสิร์ฟ static assets/API จาก Worker origin เดียวกัน. เลือกได้สูงสุด 50 URLs ต่อ job และหนึ่งหรือหลาย destinations

## Deployment ปัจจุบัน

- Worker `x2telegram-control-plane` deploy แล้วที่ `https://x2telegram-control-plane.pantipa3826.workers.dev`
- Current Worker version ID: `f2e1afaf-db8e-4356-be75-215f60eb53e5`
- Deploy commit: `9e9e9f8fcbcb09f2dfa980dd418b34681af2eed6` (P3 / PR #24)
- Deploy workflow: [#38293345118](https://github.com/aodxx/X2Telegram/actions/runs/38293345118) — success; Worker tests, Wrangler dry-run และ deploy ผ่าน
- `JOB_DISPATCH_RATE_LIMITER`: 20 requests/60 seconds per Access identity
- GitHub Pages deploy run [#38293276008](https://github.com/aodxx/X2Telegram/actions/runs/38293276008) ผ่านบน P3 merge commit `9e9e9f8`; Dashboard includes lookup-only job recovery and failed-target-only retry
- Production smoke check หลัง deploy: unauthenticated `/health` ตอบ HTTP 302 (Cloudflare Access redirect; ไม่ติดตามหรือบันทึก redirect URL); เนื้อหา API/Dashboard ต้องมี Access session จึงจะเปิดได้

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
8. P1 post-fix source-only test ใช้ URL เดิมจาก run #38102121635 (post ID `2108928241461551160`): direct MP4 fallback ดาวน์โหลดได้และ validated ที่ 29,799,397 bytes; ไม่ได้เรียกปลายทางใด. P2 source-only test (post ID `2108081184366604583`) พบ 1 รูป + 1 วิดีโอ, exported 2/2 local files และ manifest size/hash ตรงกับ bytes; test temp ถูกลบและไม่มี remote write

MEGA live version-retention test ใช้ synthetic media fixtures ไม่ใช่การดึง X จริง; combined run ยืนยัน live send ครบ 4 targets สำหรับหนึ่ง media item. Deployment ล่าสุดยืนยัน Wrangler dry-run และ edge rate-limit binding แล้ว; Dropbox large-file upload และ Telegram Local Bot API large-file path ยังไม่มี live evidence

## Validation ล่าสุด

- Python: **143 passed** in main CI [#38293276028](https://github.com/aodxx/X2Telegram/actions/runs/38293276028)
- Cloudflare Worker: `npm test --prefix control-worker` — **40 passed** on main CI and deploy workflow
- `node --check control-worker/src/index.js`, Dashboard inline JavaScript syntax, `python -m compileall -q src tests`, workflow YAML parse, `git diff --check`, `npm ci` และ Wrangler dry-run ผ่าน
- Live Actions run #37843359593 ผ่าน automated tests, process, report upload และ browser media artifact upload
- P2 merge commit `a5711e1`: main CI [#38288698022](https://github.com/aodxx/X2Telegram/actions/runs/38288698022) and MEGA multi-item/version-retention integration [#38288698061](https://github.com/aodxx/X2Telegram/actions/runs/38288698061) both succeeded. The integration verified 3 remote objects by listing/download-back bytes/SHA-256 and cleaned the run-isolated folder.
- P3 production release (2026-10-13): merged as `9e9e9f8` (PR #24); main CI [#38293276028](https://github.com/aodxx/X2Telegram/actions/runs/38293276028), Pages [#38293276008](https://github.com/aodxx/X2Telegram/actions/runs/38293276008), and Worker deploy [#38293345118](https://github.com/aodxx/X2Telegram/actions/runs/38293345118) succeeded; Worker version `f2e1afaf-db8e-4356-be75-215f60eb53e5`. Python 143 and Worker 40 tests passed. No live destination was invoked. Failure-injection demonstrates that a later manually-created full-target job may resend if success-checkpoint storage fails; cross-isolate dispatch remains non-durable.

## การตั้งค่า MEGA

ไปที่ GitHub repository → **Settings → Secrets and variables → Actions** แล้วเพิ่ม `MEGA_EMAIL` และ `MEGA_PASSWORD`; เพิ่ม `MEGA_TOTP_SECRET` เฉพาะเมื่อบัญชีใช้ TOTP (ถ้าปิด 2FA ให้ไม่สร้าง secret นี้). หากต้องการเปลี่ยนโฟลเดอร์ root ให้เพิ่ม repository variable `MEGA_REMOTE_FOLDER`. ตั้ง credential เฉพาะใน GitHub Secrets—ไม่ต้องนำมาใส่ใน Dashboard

## ขอบเขต/ข้อจำกัดที่ยังเหลือ

- P2 media completeness: **complete on main commit `a5711e1` via PR #23**. Adds distinct yt-dlp playlist-entry identities and `media_manifest`/`media_reconciliation` with size/SHA-256; Python suite **134 passed**. Real source-only mixed post verified 2/2 local files; main CI [#38288698022](https://github.com/aodxx/X2Telegram/actions/runs/38288698022) and main MEGA integration [#38288698061](https://github.com/aodxx/X2Telegram/actions/runs/38288698061) passed. No Worker deploy was needed.
- X media fetch ยังมี `download_error` ในบาง run; เมื่อเกิดก่อน destination dispatch จะล้มพร้อมกันทุก target สำหรับ URL นั้น (เช่น run #38037210973)
- Telegram >50 MB ต้องเปิด Large-file mode และ Local Bot API; run #38102024465 ยืนยันว่า standard mode ปฏิเสธไฟล์ใหญ่ตาม limit; Local Bot API path ยังไม่ live-tested
- Dropbox live upload ผ่านหนึ่ง media แล้ว; OAuth refresh หลัง token expiry และ large-file upload session ยังมีเพียง automated coverage
- ยังไม่ได้ทดสอบ browser มือถือจริง
- GitHub artifact หมดอายุ 7 วัน; สร้าง job ใหม่เพื่อได้ ZIP ใหม่
- ระบบไม่อ้าง exactly-once เมื่อ destination รับไฟล์แล้ว response/checkpoint สูญหาย
- P3 production limits: Worker single-flight reservation protects requests only within one isolate and for 30 seconds; no durable/global coordination exists across isolates or restarts. A narrow pre-visibility race remains; no exactly-once dispatch guarantee is claimed. Destination live retry was not tested because no new test target was explicitly approved.
- P3 storage limit: if the destination confirms success but the durable dedupe checkpoint cannot be written, the report warns `dedupe_checkpoint_failed`; Dashboard's failed-only retry excludes that target, but a later new full-target job may resend it because the prior success was not persisted.

## Priority 1 — X/source reliability release (deployed; historical failure URL passed post-fix source-only live check)

- Historical failure #38102121635: fetch-only reproduction พบว่าวิดีโอมี direct MP4 variants ที่ไม่ระบุขนาด; ตัวเลือกที่ bitrate สูงสุดและตัวเลือกระดับกลางเกิน 50 MB แต่ variant bitrate ต่ำกว่าดาวน์โหลด/validate ได้ที่ 29,799,397 bytes. ใน run #38037210973, yt-dlp รายงาน HLS/DASH playlist เสมือน MP4; CDN ตอบ `application/x-mpegurl`; public metadata fallbacks มี direct MP4 ให้ใช้แทน
- Candidate แก้โดยกรอง HLS/DASH ออกจาก direct MP4 metadata, ลอง bounded lower variants, classify HTTP/timeout/format/size/metadata errors พร้อม attempts/stage, ไม่ปล่อยให้ empty provider ซ่อน transient failure, ส่ง `MAX_RETRIES` เข้า metadata provider, ตรวจ same-host HTTPS redirects และเก็บผล accepted/duplicate/normalized duplicate/rejected แยกทุก URL โดยไม่นับ blank lines เป็น URL
- Local validation: Python `pytest -q` **129 passed**, Worker `npm test --prefix control-worker` **27 passed**, compile/Node/inline dashboard JavaScript/workflow YAML/diff checks ผ่าน
- P1 post-fix live source-only fetch ผ่านสำหรับ URL historical failure ที่มี direct MP4 fallback; ไม่มีการส่ง destination ในการตรวจนั้น. ยังคงไม่อ้างว่า X ทุกโพสต์รองรับ. ดู evidence matrix ที่ [`P1_X_SOURCE_DOWNLOAD_RELIABILITY.md`](plan/P1_X_SOURCE_DOWNLOAD_RELIABILITY.md)

## เอกสาร

- [คู่มือใช้งาน Dashboard ภาษาไทย](USER_GUIDE_TH.md)
- [ปลายทางหลายแบบและ MEGA setup](MULTI_DESTINATION.md)
- [คู่มือตั้งค่า Dropbox OAuth และไฟล์ใหญ่](DROPBOX_SETUP_TH.md)
- [Deployment guide](DEPLOYMENT.md)
- [Cloudflare Worker deployment workflow](../.github/workflows/deploy-worker.yml)
- [Architecture](ARCHITECTURE.md)
- [Control Plane contract](CONTROL_PLANE_CONTRACT.md)
- [E2E test report](E2E_TEST_REPORT.md)
