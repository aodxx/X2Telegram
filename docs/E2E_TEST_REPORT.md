# X2Telegram — E2E Test Report

**วันที่:** 2026-10-12
**สรุป:** Telegram, Browser ZIP, MEGA และ Dropbox ต่างมีหลักฐาน live success อย่างน้อยหนึ่ง media; combined run เลือกครบ 4 destinations และส่ง media สำเร็จทั้ง 4. MEGA content-version retention integration หลัง fix ผ่านจริง. มีบาง URL ล้มที่ shared `download_error` ก่อนถึง destinations; Telegram >50 MB ใน standard mode ล้มตาม size limit ที่กำหนด ไม่ใช่ปลายทางอื่นล้มตาม

## หลักฐาน live

### Telegram normal path (เดิม)

- Actions run [#37807253687](https://github.com/aodxx/X2Telegram/actions/runs/37807253687) ประมวลผล `https://x.com/ninmopmn/status/2107508912392171879` แล้วส่ง MP4 หนึ่งไฟล์เข้า Telegram group ที่ล็อกไว้
- Run conclusion `success`; report `sent=1`, `failed=0`, `skipped_duplicate=0`; Telegram message ID `347`
- โพสต์มี video variants 2 format; เลือก variant สูงสุดและส่งหนึ่งไฟล์

### Dashboard batch no-resend (เดิม)

- Actions run [#37816856323](https://github.com/aodxx/X2Telegram/actions/runs/37816856323) รับ 2 URLs ใน workflow run เดียว
- ทั้งสอง post มี completed dedupe state จึงถูกข้าม; report `sent=0`, `skipped_duplicate=2`, `failed=0`
- ยืนยัน live batch dispatch/no-resend โดยไม่ส่ง Telegram ซ้ำ แต่ไม่ใช่ fresh-media batch delivery

### Live Browser ZIP / Worker streaming (หลัง multi-destination deploy)

- Worker version `c44298fb-47f9-4798-a3db-9cd6946018fb`, deployed by commit `fe3170fb` via [deploy run #38171587335](https://github.com/aodxx/X2Telegram/actions/runs/38171587335)
- Dashboard แสดง Access authenticated, destinations picker และฟอร์ม 2 URLs
- เลือก **Download-only** แล้ว dispatch run [#37843359593](https://github.com/aodxx/X2Telegram/actions/runs/37843359593), job `job-601fc374e2d57b21b0528137602cba7d`
- Actions success; Telegram Local Bot API และ MEGAcmd setup ถูกข้าม; process/report/artifact upload ผ่าน; report แสดง Download `ready` 2 files
- เปิด `/jobs/<job_id>/download` ผ่าน browser session ที่ผ่าน Access แล้ว browser ดาวน์โหลดไฟล์ ZIP จริง; archive มี 2 entries, ขนาด 256,966,632 bytes, CRC check ผ่าน
- งานนี้ไม่เลือก Telegram หรือ MEGA จึงไม่ได้ส่งข้อความหรืออัปโหลดไป MEGA

### Live MEGA-only upload

- Dashboard dispatch run [#37848879753](https://github.com/aodxx/X2Telegram/actions/runs/37848879753), job `job-c1a0a40e4e92b6d35ed17eeb39319d04`, สำหรับ URL ที่เจ้าของระบุก่อนหน้า
- เลือก **MEGA-only**; Telegram และ Browser ZIP ไม่ได้เลือก. Actions success และ sanitized Dashboard report แสดง `MEGA: สำเร็จ`, `sent=1`, `failed=0`
- Attempt ก่อนหน้า run [#37848220624](https://github.com/aodxx/X2Telegram/actions/runs/37848220624) หยุดก่อน login เพราะพบ TOTP setting ที่ไม่ใช่ Base32; หลังเจ้าของยืนยันว่า MEGA 2FA ปิดและลบ secret ที่ไม่จำเป็น การ retry ผ่าน. ไม่มี Telegram send ในทั้งสอง run
- ผู้ใช้รายงานภายหลังว่า media ที่ชื่อเดิมถูกแทนที่เมื่ออัปโหลดเนื้อหาใหม่. PR [#9](https://github.com/aodxx/X2Telegram/pull/9) แก้ MEGA โดยต่อ SHA-256 เต็มของ media เข้า filename, migrate checkpoint เก่าที่ใช้ชื่อ legacy และตรวจชื่อไฟล์จากรายการ remote หลัง upload.

### Live MEGA version-retention integration หลัง fix

- Run [#37984146026](https://github.com/aodxx/X2Telegram/actions/runs/37984146026) ผ่าน workflow `MEGA version-retention integration` บน commit ที่เป็นบรรพบุรุษของ main ปัจจุบัน
- ใช้ fixture media สองชุดแทนเนื้อหาคนละเวอร์ชันของ post ID เดียว; upload ผ่าน MEGAcmd, ยืนยันว่า remote listing มีทั้งสอง filename แล้วดาวน์โหลดกลับมาเทียบ byte content กับ fixture
- ผ่าน; เป็น live storage integration test แต่ **ไม่ใช่การดาวน์โหลด media จริงจาก X**. ใช้ folder แยกตาม run ID

### Combined four-destination live run

- Run [#38037210973](https://github.com/aodxx/X2Telegram/actions/runs/38037210973) เลือก Telegram, MEGA, Dropbox และ Download
- ผล URL/media รายการแรก: ดาวน์โหลดได้หนึ่ง media และทั้ง 4 destinations สำเร็จ (`telegram=success`, `mega=success`, `dropbox=success`, `download=ready`)
- ผลรายการที่สอง: shared `download_error` ก่อนเริ่ม dispatch; ทั้ง 4 destinations จึงไม่มีไฟล์สำหรับรายการนั้น. Workflow สรุปเป็น partial success และ Actions conclusion เป็น failure
- ข้อสรุป: ยืนยัน live path ของ Dropbox และการส่งร่วม 4 destinations สำหรับหนึ่ง media; run นี้ไม่ใช่ full-pass สำหรับ URL ทั้งคู่

### Telegram recent outcomes

- Run [#38102180526](https://github.com/aodxx/X2Telegram/actions/runs/38102180526): Telegram-only send success
- Run [#38102024465](https://github.com/aodxx/X2Telegram/actions/runs/38102024465): MEGA success แต่ Telegram item fail ด้วย `telegram_file_too_large`; standard Telegram Bot API policy คือ 50 MB เมื่อไม่ได้เปิด Large-file mode
- Run [#38102121635](https://github.com/aodxx/X2Telegram/actions/runs/38102121635): `download_error` ก่อนถึง Telegram send; จัดเป็น X/media source retrieval issue ไม่ใช่ Telegram API error

### Priority 1 — X/source reliability (deployed; post-fix live source check pending)

- Run [#38102121635](https://github.com/aodxx/X2Telegram/actions/runs/38102121635) source-only probes found three direct MP4 variants without sizes; the preferred 2,176,000-bitrate and 950,000-bitrate candidates exceeded the 50 MB cap, while the 632,000-bitrate candidate fetched and validated at **29,799,397 bytes**. No destination adapter was called.
- In combined run [#38037210973](https://github.com/aodxx/X2Telegram/actions/runs/38037210973), yt-dlp variants were marked MP4 despite HLS protocol/playlist URLs; the source returned `application/x-mpegurl`. Public syndication/FxTwitter fallbacks exposed direct MP4 variants. The first historical URL's other post reached all four destinations; the failed post did not reach any.
- Candidate code filters HLS/DASH, bounds lower-variant fallback, classifies and redacts source errors, and reports accepted/duplicate/normalized-duplicate/rejected outcomes while accounting for blank lines separately.
- Independent review also identified three reliability gaps, now covered by regressions: an empty metadata provider no longer masks another provider's timeout/server error as `no_media`; configured `MAX_RETRIES` is passed to the provider; metadata HTTP redirects are followed only after same-host HTTPS validation and are bounded.
- Local validation: Python **129 passed**, Worker **27 passed**; compile, Node/inline dashboard JS syntax, workflow YAML and diff checks passed. CI run [#38254729760](https://github.com/aodxx/X2Telegram/actions/runs/38254729760) passed Python 129 and Worker 27 tests on commit `8fb4427`.
- Release: synthetic MEGA version-retention run [#38254729778](https://github.com/aodxx/X2Telegram/actions/runs/38254729778) passed; Dashboard Pages run [#38254729838](https://github.com/aodxx/X2Telegram/actions/runs/38254729838) passed; Worker deploy run [#38263528272](https://github.com/aodxx/X2Telegram/actions/runs/38263528272) passed on the same commit. Production Worker version is `e6bff44f-12e9-4a55-bfdb-c7b7cfb6587f`.
- Synthetic batch input=5 nonblank tokens + 1 blank line → 3 accepted unique + 1 normalized duplicate + 1 rejected; 3 ordered post results (2 success, 1 failure) remain visible. The batch fixture injects a failure carrying 2 attempts; downloader tests independently verify two mocked HTTP calls and `Retry-After` handling.
- **Not live-verified after the code change:** no post-fix X request or real destination send. The failure-surrounded-by-success regression is download-only mocked. See [`P1_X_SOURCE_DOWNLOAD_RELIABILITY.md`](plan/P1_X_SOURCE_DOWNLOAD_RELIABILITY.md) for the evidence matrix.

## Scenario status

| Scenario | ผล | หลักฐาน/ขอบเขต |
|---|---|---|
| Dashboard Access/login same-origin | PASS (live) | Browser แสดง `Access ลงชื่อเข้าใช้แล้ว · พร้อมส่ง` |
| Telegram normal path | PASS (live) | Run #37807253687, MP4 1 ไฟล์, message ID 347 |
| Batch URL dispatch 1–50 | PASS (live 2 URLs) | Run #37816856323; completed posts ถูก dedupe ไม่ส่งซ้ำ |
| Download-only, multiple URL job | PASS (live 2 URLs) | Run #37843359593; private artifact พร้อมและ report แสดง 2 files |
| Worker protected ZIP streaming | PASS (live) | Browser ดาวน์โหลดจริงผ่าน Access route; ZIP CRC ผ่าน |
| Telegram/MEGA/Dropbox/Download combinations | PASS สำหรับ media 1 รายการ (live); อีก URL ล้มก่อนถึง targets | Run #38037210973; all 4 destinations success/ready สำหรับรายการที่ดึงได้ |
| Retry เฉพาะ destination ที่ล้มเหลว | PASS (automated mock) | Mega failure แล้ว retry; Telegram ที่สำเร็จไม่ถูกส่งซ้ำ |
| ภาพ+วิดีโอในโพสต์เดียว | PASS (automated mock) | ภาพยังคงอยู่ และเลือก video variant สูงสุด; download หนึ่งครั้งต่อ media |
| Invalid MEGA folder/credential failure | PASS (automated mock) | MEGA failure ไม่หยุด Telegram/Download; ไม่มี command output ใน report |
| MEGA upload จริง | PASS (live MEGA-only) | Run #37848879753; หนึ่ง media upload สำเร็จ; Telegram ไม่ได้เลือก |
| MEGA changed content preserves prior file | PASS (live integration + regression) | Run #37984146026 อัปโหลด fixture สองเวอร์ชันใน post เดียว, ตรวจ listing และ downloaded bytes; ไม่ได้ใช้ media จาก X |
| Dropbox connector | PASS (one live item + automated edge cases) | Run #38037210973; OAuth refresh (รวม refresh-token-only), 429 และ large-file session ยัง automated only |
| Dropbox upload จริง | PASS (live one media) | Run #38037210973; รายการที่ดึงได้อัปโหลดสำเร็จ; ไม่มี Dropbox-specific error |
| Telegram+MEGA live combined send | PASS (one live media item) | Run #38037210973; ทั้ง Telegram และ MEGA สำเร็จ; Telegram >50 MB ยังต้องใช้ Large-file mode |
| Telegram Local Bot API large file | NOT RUN (live) | Run #38102024465 เจอ `telegram_file_too_large` ใน standard mode; ไม่ได้ยืนยัน large-file mode จริง |
| X/media shared download | PARTIAL (live failures observed) | `download_error` ใน runs #38037210973 และ #38102121635; เมื่อ source media ดึงไม่ได้ ทุก target ของ URL นั้น fail ก่อน dispatch |
| X/source reliability P1 release | PARTIAL (local/CI automated + production deployed; no post-change live source) | Python 129, Worker 27; CI #38254729760; Worker #38263528272; fallback, stage/error classification, per-input reconciliation and sanitized retry evidence |
| Mobile browser | NOT RUN | ยังไม่มีการทดสอบบนอุปกรณ์มือถือจริง |
| Invalid URL, body cap, unauthorized | PASS (Worker tests/live safe checks เดิม) | 400/413/401/403 paths ปฏิเสธก่อน dispatch ตาม report/contract เดิม |

## Automated validation baseline and candidate

- Previously recorded Python baseline: `python3 -m pytest -q` — **95 passed**; current local/CI P1 release: **129 passed** (CI #38254729760)
- Cloudflare Worker: `npm test --prefix control-worker` — **27 passed**
- Deploy workflow [#38263528272](https://github.com/aodxx/X2Telegram/actions/runs/38263528272): Worker tests 27/27, Wrangler dry-run และ production deploy ผ่าน on commit `8fb4427`; Worker version `e6bff44f-12e9-4a55-bfdb-c7b7cfb6587f`
- Python compile, Node syntax, workflow YAML parse, `git diff --check`, `npm ci` และ Wrangler dry-run ผ่าน
- Live run #37843359593 ผ่าน automated Python/Worker tests ก่อน process, report และ media artifact upload

## ข้อสรุป

ระบบ production deployed; ทุก destination มีหลักฐาน live success อย่างน้อยหนึ่งรายการ และ run #38037210973 ยืนยัน combined 4-destination success สำหรับ media หนึ่งชิ้น. P1 release commit `8fb4427` ผ่าน CI, synthetic MEGA integration, Pages deploy และ Worker deploy; Worker run [#38263528272](https://github.com/aodxx/X2Telegram/actions/runs/38263528272) ยืนยัน Worker tests, Wrangler dry-run และ production rollout เป็น version `e6bff44f-12e9-4a55-bfdb-c7b7cfb6587f`. สิ่งที่ยังไม่ยืนยัน live คือ post-fix X source fetch, Telegram Local Bot API สำหรับไฟล์เกิน 50 MB, Dropbox token-refresh และ large-file edge paths, รวมถึงการใช้งาน browser บนมือถือจริง
