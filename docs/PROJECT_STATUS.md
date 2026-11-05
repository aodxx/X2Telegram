# X2Telegram — Project Status

**อัปเดต:** 2026-11-06
**สถานะ:** P1/P2 ผ่าน acceptance ตามหลักฐานเดิม; P3 ยัง partial ตามข้อจำกัด exactly-once/cross-isolate. MEGA authentication hardening บน `0943983` ผ่าน main CI [#42102315080](https://github.com/aodxx/X2Telegram/actions/runs/42102315080) (Python 183, Worker/Dashboard 47 tests), Pages [#42102314959](https://github.com/aodxx/X2Telegram/actions/runs/42102314959) และ Worker deploy [#42102540417](https://github.com/aodxx/X2Telegram/actions/runs/42102540417) ผ่าน; Worker version `6c8819b6-f9ed-4fd4-8b72-21f13557a21f`. Synthetic MEGA integration [#42102315328](https://github.com/aodxx/X2Telegram/actions/runs/42102315328) หยุดที่ install เพราะ package checksum pin ไม่ตรง ก่อน login/upload; จึงยังไม่มี live verification ของ auth code ใหม่. ผู้ใช้รายงานล่าสุด run #42100323436 authentication failed ทั้ง 99 URLs และไม่มี upload. Unauthenticated Worker `/` ยังตอบ HTTP 302 ตาม Cloudflare Access; real-mobile authenticated smoke test ยังรอยืนยัน. Ruleset protection ยัง blocked ตามเหตุผลใน audit; P4 ยัง partial และ P5 ยังรอ mobile smoke test.

สำหรับ agent ที่เข้ามาทำงานต่อ ให้เริ่มจาก [`AGENT_HANDOFF.md`](AGENT_HANDOFF.md) ซึ่งมีลำดับ backlog, acceptance criteria และ deploy protocol ปัจจุบัน

### Dashboard recovery hotfix — 2026-11-05

- PR [#31](https://github.com/aodxx/X2Telegram/pull/31) merged เป็น `8fae5ac`; main CI [#41919883724](https://github.com/aodxx/X2Telegram/actions/runs/41919883724) และ Pages deploy [#41919883762](https://github.com/aodxx/X2Telegram/actions/runs/41919883762) ผ่าน
- Worker deploy [#41919996688](https://github.com/aodxx/X2Telegram/actions/runs/41919996688) ผ่านบน commit เดียวกัน; version `d07ab6a9-b130-4ada-a510-97aa3e8989e3`; Worker tests และ Wrangler dry-run ผ่าน
- Dashboard จะตรวจคำขอเดิมใหม่แบบ lookup-only หลัง Access/session กลับมา; ไม่มี `POST /jobs` ซ้ำ. ปุ่มตรวจลิงก์ระบุชัดว่าเป็น validation เท่านั้น และ ZIP ต้องเลือกเอง
- Validation ล่าสุด: Python **164 passed**, Worker/Dashboard **47 passed**; no live URL/destination send เกิดใน regression run. HTTP `/` และ `/health` แบบไม่ล็อกอินตอบ 302 ตาม Cloudflare Access; authenticated interactive smoke test ยังรอยืนยัน

### Release note — ขั้นที่ 2–4

- แยก metadata error กรณีโพสต์ไม่มีวิดีโอ/สื่อที่รองรับออกจากระบบ metadata ล้มเหลว และ Dashboard แนะนำสาเหตุเป็นภาษาไทย
- เพิ่ม `bitrate`, `width`, `height` และขนาดไฟล์ที่ตรวจสอบแล้วใน `media_manifest` เพื่อแสดงคุณภาพ variant ที่เลือกจริง
- ปรับการเลือกวิดีโอให้เรียงความละเอียดก่อน bitrate, เพิ่ม fallback สูงสุด 5 variants และไม่ใช้ Telegram 50 MB ลดคุณภาพร่วมกับ Dropbox/MEGA/Download ในงานหลายปลายทาง; เพิ่ม regression tests ครบแล้ว
- Dashboard นับ `no_media` และผลที่ยังยืนยันไม่ได้เป็นรายการที่ต้องตรวจสอบ พร้อมแสดง “เสร็จบางส่วน” เมื่อมีทั้งรายการที่จัดการแล้วและรายการที่ต้องแก้ไข
- PR #29 merged เป็น `359041e` พร้อม guard ของ state-writer: ตรวจ repository/ref/event และยอมให้ state writer เปลี่ยนเฉพาะ `state/dedupe.json`
- ตรวจ GitHub repository ruleset แล้ว; การสร้าง ruleset ที่ bypass GitHub Actions integration ถูก GitHub API ปฏิเสธสำหรับ repository owner แบบ user จึงยังไม่เปิด protection ที่จะบล็อกการ persist state
- Validation สำหรับ release ขั้นที่ 2–4 ในเวลานั้น: Python **156 passed**, Worker/Dashboard **45 passed**; ไม่ได้ทำ live upload ซ้ำตามขอบเขตที่ผู้ใช้กำหนด

### MEGA incident review — 2026-10-22

- Run ล่าสุด `39651933138` ติดตั้ง MEGAcmd สำเร็จและตรวจ checksum ผ่าน แต่ทุก media จบด้วย `mega_authentication_failed` ที่ขั้น `mega-login`; จึงไม่ใช่ปัญหาการดาวน์โหลดหรือ `mega-put`
- เพิ่มทางเลือก `MEGA_SESSION` แบบ GitHub Actions Secret เพื่อ resume session โดยไม่ต้องส่ง email/password และเพิ่มการแยกกรณีบัญชีเปิด MFA แต่ไม่มี TOTP/session เป็น `mega_mfa_required`
- หากยังใช้ email/password ให้ตรวจหรือบันทึก `MEGA_EMAIL`, `MEGA_PASSWORD` ใหม่ใน GitHub Actions Secrets; ระบบไม่สามารถอ่านหรือแก้ค่า secret ที่ซ่อนอยู่ได้

### MEGA authentication follow-up — 2026-11-06

- ผู้ใช้ส่ง 99 URLs เข้า MEGA ผ่าน run [#42100323436](https://github.com/aodxx/X2Telegram/actions/runs/42100323436). Sanitized report ยืนยัน `mega_authentication_failed` ทั้ง 99 รายการ และไม่มีไฟล์ใดอัปโหลดสำเร็จ; raw MEGAcmd output ไม่อยู่ใน report จึงระบุไม่ได้ว่าเป็น password, MFA seed หรือ session ที่ถูกปฏิเสธ
- ปรับ MEGA login ให้ลอง credentials/TOTP หนึ่งครั้งเมื่อ `MEGA_SESSION` resume ไม่ผ่าน, แยก `mega_session_invalid`, `mega_totp_invalid`, `mega_mfa_required` และ `mega_login_unavailable`, และ cache login failure/timeout เพื่อไม่ลองซ้ำต่อทุก URL
- Regression tests ใช้ fake MEGAcmd เท่านั้น; ไม่มีการส่ง media จริงซ้ำระหว่างการแก้ไข และยังต้องรอการแก้ credential โดยเจ้าของบัญชีก่อน live verification
- Main CI #42102315080 ผ่าน Python 183 และ Worker/Dashboard 47 tests; Pages #42102314959 และ Worker deploy #42102540417 ผ่าน, Worker version `6c8819b6-f9ed-4fd4-8b72-21f13557a21f`. Synthetic integration #42102315328 ไม่ผ่านก่อน auth เพราะ MEGAcmd package checksum pin ใน workflow เก่าไม่ตรงกับ package ที่ดาวน์โหลด; ไม่มี login หรือ remote write ใน run นั้น.

## ภาพรวม

ระบบรับ X post URL จาก Dashboard ส่วนตัว, ตรวจ Cloudflare Access, dispatch GitHub Actions แล้วประมวลผล media **หนึ่งครั้งต่อ media item** ก่อนส่งไปยังปลายทางที่เลือกได้: Telegram, MEGA, Dropbox และ Browser ZIP. ยังคงใช้ workflow หลักเพียง workflow เดียว และไม่เพิ่ม database/Redis/queue/Google Drive ใน production path

Dashboard เดิมอยู่ที่ [X2Telegram Dashboard](https://aodxx.github.io/X2Telegram/) และเสิร์ฟ static assets/API จาก Worker origin เดียวกัน. เลือกได้สูงสุด 200 ลิงก์ต่องาน (request body ไม่เกิน 64 KiB) และหนึ่งหรือหลาย destinations

## Deployment ปัจจุบัน

- Worker `x2telegram-control-plane` deploy แล้วที่ `https://x2telegram-control-plane.pantipa3826.workers.dev`
- Latest application code commit on main: `0943983` (MEGA authentication edge-case hardening)
- Current Worker version ID: `6c8819b6-f9ed-4fd4-8b72-21f13557a21f`
- Latest deploy commit: `094398359e10c661e3ce3827a293de1bf59ae973`
- Latest deploy workflow: [#42102540417](https://github.com/aodxx/X2Telegram/actions/runs/42102540417) — success; Worker tests, Wrangler validation และ deploy ผ่าน
- `JOB_DISPATCH_RATE_LIMITER`: 20 requests/60 seconds per Access identity
- Prior feature-baseline Pages deploy [#38968970271](https://github.com/aodxx/X2Telegram/actions/runs/38968970271) ผ่านบน application commit `4bd1abf`; Dashboard ใน release นั้นมี lookup-only recovery, failed-target-only retry, resilient polling/clear labeling between URL batches, mobile full-width actions, accessible busy/result announcements และคำอธิบาย metadata/media quality
- Cloudflare Access policy ปัจจุบันมีสอง exact email rules; Worker `ACCESS_ADDITIONAL_EMAIL` ตั้งแล้ว ขณะที่ `ACCESS_ALLOWED_EMAIL` เดิมยังคงอยู่. ไม่มี `Everyone` หรือ domain-wide allow
- GitHub Pages deploy สำหรับ Dashboard MEGA error guidance: [#42102314959](https://github.com/aodxx/X2Telegram/actions/runs/42102314959) — success on `0943983`
- Production smoke check หลัง deploy: GitHub Pages entry ตอบ HTTP 200 และ unauthenticated Worker `/` ตอบ HTTP 302 ตาม Cloudflare Access; authenticated interactive/mobile smoke test ยังรอยืนยัน

## ปลายทาง

| ปลายทาง | สถานะ | หมายเหตุ |
|---|---|---|
| Telegram | ใช้งานได้สำหรับ standard-size media; มี failure ที่เป็นขีดจำกัดตาม config | Normal sends ผ่าน live; `telegram_file_too_large` เกิดเมื่อไม่เปิด Large-file mode สำหรับไฟล์เกิน 50 MB; Local Bot API large-file mode ยังไม่ live-tested |
| Browser ZIP | ใช้งานได้และผ่าน live smoke test | private Actions artifact อายุ 7 วัน; 2,000 MB ต่อไฟล์และ 8 GiB รวมต่อ job; Worker stream ผ่าน Access |
| MEGA | Historical live upload/version-retention ผ่าน; current authentication ยังต้องยืนยันใหม่ | Run [#42100323436](https://github.com/aodxx/X2Telegram/actions/runs/42100323436) ล้มที่ `mega_authentication_failed` ทั้ง 99 URLs; 0 uploads. Auth code hardening ผ่าน automated tests; synthetic live integration #42102315328 ถูกหยุดก่อน login เพราะ package checksum pin mismatch. โฟลเดอร์ default `X2Telegram/YYYY-MM-DD` |
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

- Python: **183 passed** in local validation and main CI [#42102315080](https://github.com/aodxx/X2Telegram/actions/runs/42102315080)
- Cloudflare Worker/Dashboard: `npm test --prefix control-worker` — **47 passed** in local validation and main CI [#42102315080](https://github.com/aodxx/X2Telegram/actions/runs/42102315080)
- `node --check control-worker/src/index.js`, Dashboard inline JavaScript syntax, `python -m compileall -q src tests`, workflow YAML parse, `git diff --check`, `npm ci` และ Wrangler dry-run ผ่าน
- Live Actions run #37843359593 ผ่าน automated tests, process, report upload และ browser media artifact upload
- P2 merge commit `a5711e1`: main CI [#38288698022](https://github.com/aodxx/X2Telegram/actions/runs/38288698022) and MEGA multi-item/version-retention integration [#38288698061](https://github.com/aodxx/X2Telegram/actions/runs/38288698061) both succeeded. The integration verified 3 remote objects by listing/download-back bytes/SHA-256 and cleaned the run-isolated folder.
- Access expansion release (2026-10-13): PR #25 merged as `f5372e5`; main CI [#38295563125](https://github.com/aodxx/X2Telegram/actions/runs/38295563125) and Worker deploy [#38295769200](https://github.com/aodxx/X2Telegram/actions/runs/38295769200) succeeded; Worker version `649353cf-fd9a-498b-9415-14bae01de486`. Python 143 and Worker 42 tests passed. Two exact Access email rules are configured; no new OTP was sent and the secondary user's sign-in remains unverified.
- P3 production release (2026-10-13): merged as `9e9e9f8` (PR #24); main CI [#38293276028](https://github.com/aodxx/X2Telegram/actions/runs/38293276028), Pages [#38293276008](https://github.com/aodxx/X2Telegram/actions/runs/38293276008), and Worker deploy [#38293345118](https://github.com/aodxx/X2Telegram/actions/runs/38293345118) succeeded; Worker version `f2e1afaf-db8e-4356-be75-215f60eb53e5`. No live destination was invoked. Failure-injection demonstrates that a later manually-created full-target job may resend if success-checkpoint storage fails; cross-isolate dispatch remains non-durable.
- Dashboard/P4 automated release (2026-10-13): PR #27 merged as `763bd9a`; CI [#38300530120](https://github.com/aodxx/X2Telegram/actions/runs/38300530120) passed with Python 147 and Worker/Dashboard 45; Pages [#38300619373](https://github.com/aodxx/X2Telegram/actions/runs/38300619373) succeeded. Dashboard status polling now retries transient read failures and distinguishes the prior result from a newly pasted batch. Telegram 50 MB boundary/Local Bot API and Dropbox refresh/session regressions are mock-based only; both live tracks remain blocked pending authorized test destinations. Worker code was unchanged and no live destination upload occurred.
- Latest repair release (2026-10-16): commit `f08c0aa` fixes the `persist-state` ordering bug that caused GitHub Actions to fail with `cannot rebase: You have unstaged changes`; state is now committed before fetch/rebase, with a contract regression test. Automated Tests [#38923942624](https://github.com/aodxx/X2Telegram/actions/runs/38923942624) passed and Pages [#38923942619](https://github.com/aodxx/X2Telegram/actions/runs/38923942619) passed. Local validation: Python **148 passed**, Worker/Dashboard **45 passed**.
- Dropbox/batch usability release (2026-10-16): แก้ Dropbox HTTP 409 path conflict โดยตรวจ metadata และ Dropbox content hash ก่อนถือว่าเป็นไฟล์เดิม; ถ้า hash ไม่ตรงจะไม่เขียนทับและรายงานภาษาไทยที่อธิบายสาเหตุ. เพิ่มเพดาน Dashboard/Worker จาก 50 เป็น **200 ลิงก์ต่องาน** และ request body จาก 16 เป็น **64 KiB** พร้อม regression tests. Local validation หลังแก้: Python **150 passed**, Worker/Dashboard **45 passed**.

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
- Operational review (2026-10-16): GitHub reports `main` is currently unprotected. ไม่เปิด branch protection อัตโนมัติในงานนี้ เพราะต้องออกแบบให้สอดคล้องกับ `persist-state` bot ที่เขียน dedupe commit เข้า `main`; ควรทำเป็น security change แยกพร้อมทดสอบ workflow และ rollback plan. ยังไม่มี Access session ของผู้ใช้รอง, real-mobile smoke test, หรือปลายทาง Telegram/Dropbox test ที่ได้รับอนุญาตสำหรับ live P3/P4.

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
