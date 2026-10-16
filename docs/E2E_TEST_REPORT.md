# X2Telegram — E2E Test Report

**วันที่:** 2026-10-13
**สรุป:** Telegram, Browser ZIP, MEGA และ Dropbox ต่างมีหลักฐาน live success อย่างน้อยหนึ่ง media; combined run เลือกครบ 4 destinations และส่ง media สำเร็จทั้ง 4 สำหรับ media ที่ดึงได้. Access second-email support ถูก merge เป็น main commit `f5372e5` (PR [#25](https://github.com/aodxx/X2Telegram/pull/25)); main CI [#38295563125](https://github.com/aodxx/X2Telegram/actions/runs/38295563125) และ Worker deploy [#38295769200](https://github.com/aodxx/X2Telegram/actions/runs/38295769200) ผ่าน; production Worker version `649353cf-fd9a-498b-9415-14bae01de486`. Access policy/Worker configuration อนุญาตสอง exact email identities; ผู้ใช้รองยังไม่ได้ sign in ด้วย OTP จึงยังไม่มีหลักฐาน session จริง. P3 remains partial: no live destination retry was invoked; cross-isolate and checkpoint-storage limitations remain.

## Dashboard and P4 update (automated/deployment evidence only)

- PR [#27](https://github.com/aodxx/X2Telegram/pull/27) merged as main commit `763bd9a`; main CI [#38300530120](https://github.com/aodxx/X2Telegram/actions/runs/38300530120) passed (Python **147**, Worker/Dashboard **45**) and Pages deploy [#38300619373](https://github.com/aodxx/X2Telegram/actions/runs/38300619373) succeeded. Worker code was unchanged; no Worker deployment was needed.
- Dashboard status polling now retries transient status-read failures while retaining the existing job lock, uses a generation guard against stale poll results, and labels newly pasted URLs as a separate, unsent batch instead of presenting the previous job result as theirs.
- Automated Telegram coverage: exactly 50 MB boundary, 50 MB + 1 byte rejection in standard mode, no fallback to standard Bot API when Local Bot API is unavailable, and continued processing of an independent destination. Automated Dropbox coverage: exact chunk bytes/offsets, sanitized refresh failure, and ambiguous final-session timeout classified as unconfirmed without replay.
- P4 remains **PARTIAL**. No live Telegram or Dropbox write was performed. Track A needs an explicitly authorized Telegram test chat; Track B needs a designated Dropbox test account/folder and cleanup policy.
- **ภาษาไทย:** แก้กรณี polling สะดุดและแยกงาน URL ชุดใหม่ออกจากผลชุดก่อนหน้าแล้ว; มีเฉพาะ automated/mock tests และ Pages deploy เท่านั้น ยังไม่ได้ส่งไฟล์จริงไป Telegram/Dropbox จึงยังไม่ถือว่า P4 live acceptance ผ่าน

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

### Priority 1 — X/source reliability (deployed; post-fix source-only live check passed)

- Run [#38102121635](https://github.com/aodxx/X2Telegram/actions/runs/38102121635) source-only probes found three direct MP4 variants without sizes; the preferred 2,176,000-bitrate and 950,000-bitrate candidates exceeded the 50 MB cap, while the 632,000-bitrate candidate fetched and validated at **29,799,397 bytes**. No destination adapter was called.
- In combined run [#38037210973](https://github.com/aodxx/X2Telegram/actions/runs/38037210973), yt-dlp variants were marked MP4 despite HLS protocol/playlist URLs; the source returned `application/x-mpegurl`. Public syndication/FxTwitter fallbacks exposed direct MP4 variants. The first historical URL's other post reached all four destinations; the failed post did not reach any.
- P1 release filters HLS/DASH, bounds lower-variant fallback, classifies and redacts source errors, and reports accepted/duplicate/normalized-duplicate/rejected outcomes while accounting for blank lines separately.
- Independent review also identified three reliability gaps, now covered by regressions: an empty metadata provider no longer masks another provider's timeout/server error as `no_media`; configured `MAX_RETRIES` is passed to the provider; metadata HTTP redirects are followed only after same-host HTTPS validation and are bounded.
- Local validation: Python **129 passed**, Worker **27 passed**; compile, Node/inline dashboard JS syntax, workflow YAML and diff checks passed. CI run [#38254729760](https://github.com/aodxx/X2Telegram/actions/runs/38254729760) passed Python 129 and Worker 27 tests on commit `8fb4427`.
- Release at that time: synthetic MEGA version-retention run [#38254729778](https://github.com/aodxx/X2Telegram/actions/runs/38254729778) passed; Dashboard Pages run [#38254729838](https://github.com/aodxx/X2Telegram/actions/runs/38254729838) passed; Worker deploy run [#38263528272](https://github.com/aodxx/X2Telegram/actions/runs/38263528272) passed on the same commit. That deployment used Worker version `e6bff44f-12e9-4a55-bfdb-c7b7cfb6587f`; current production snapshot is recorded above.
- Synthetic batch input=5 nonblank tokens + 1 blank line → 3 accepted unique + 1 normalized duplicate + 1 rejected; 3 ordered post results (2 success, 1 failure) remain visible. The batch fixture injects a failure carrying 2 attempts; downloader tests independently verify two mocked HTTP calls and `Retry-After` handling.
- Post-fix source-only check of the historical failing post (ID `2108928241461551160`) fetched and validated the lower direct MP4 candidate at **29,799,397 bytes**, SHA-256 `58e9b145e35229b9e02dff432bc680e357d065aaa438c55737c648f88166e589`; no destination adapter was invoked. The failure-surrounded-by-success multi-URL case remains mock-based. See [`P1_X_SOURCE_DOWNLOAD_RELIABILITY.md`](plan/P1_X_SOURCE_DOWNLOAD_RELIABILITY.md) for the evidence matrix.

### Priority 2 — multi-media manifest (merged to main; Worker deploy not applicable)

- Historical owner-used post ID `2108081184366604583`: current source-only run found **4 metadata entries** representing **1 photo + 1 video with 3 variants**; processor exported exactly **2 files**, both validated and ready, with **2/2 accounted** and **0 unaccounted**.
- Manifest hashes matched local output bytes: photo **79,517 bytes**, SHA-256 `e309f9c18a4b55322afd56312b7ac6a66f5c5769cd3d3de476105f835422a84a`; video **2,797,748 bytes**, SHA-256 `551ceed75acef2aadccf7f7c2f98d62eece4e304e8c0fa1f55f81adeeba3b8f5`. Temp outputs were removed; no remote destination was called.
- Historical run [#38160545553](https://github.com/aodxx/X2Telegram/actions/runs/38160545553) has a two-item Dropbox report for this source, but its overall conclusion was failure; it is **not** treated as successful remote-integrity evidence.
- Merged implementation preserves yt-dlp playlist-entry identities and emits a per-media SHA/size/status manifest plus reconciliation. PR-stage MEGA runs [#38288011489](https://github.com/aodxx/X2Telegram/actions/runs/38288011489) and [#38288024709](https://github.com/aodxx/X2Telegram/actions/runs/38288024709) both passed; main run [#38288698061](https://github.com/aodxx/X2Telegram/actions/runs/38288698061) passed on commit `a5711e1`. Each verified 3 remote objects (48/55/64 bytes) by listing and download-back with matching hashes, 1 changed-content version, 1 unchanged duplicate, 0 unaccounted items, and run-isolated folder cleanup. These are synthetic MEGA fixtures, not X-downloaded media. Main CI [#38288698022](https://github.com/aodxx/X2Telegram/actions/runs/38288698022) passed Python 134 and Worker 27 tests.

## Scenario status

### Priority 3 — safe retry and job recovery (merged and deployed; live destination retry not run)

- Python DedupeStore state is schema v4 and preserves outcome-unconfirmed checkpoints; retry regression asserts a successful Telegram target remains at exactly one invocation while the failed MEGA target is invoked once on retry.
- Telegram send timeout/non-JSON/5xx, Dropbox upload transport timeout/5xx, and MEGA upload/read-back uncertainty are no longer automatically replayed. New MEGA regression covers `mega-put` success followed by remote listing timeout.
- Worker same-isolate concurrency tests: identical concurrent POSTs share one dispatch (202 + duplicate 200); conflicting payloads under one request ID return 202 + 409; lookup-only recovery can observe the in-flight request. Reservation expires after 30 seconds.
- Browserless Dashboard harness: reload uses `POST /jobs/recover` and resumes the existing job without `POST /jobs`; a not-found lookup stays locked and does not dispatch; retry payload includes only confirmed failed destinations, excluding successful and unconfirmed targets.
- Missing/expired/unavailable report tests return distinct availability states; Dashboard displays safe, actionable messages.
- Failure-injection boundary: when Telegram confirms success but writing its durable dedupe checkpoint fails, the report includes `dedupe_checkpoint_failed`; Dashboard's failed-only retry excludes the successful target, but a later manually-created full-target job may resend because state alone no longer proves prior delivery.
- Validation: Python **143 passed**, Worker/Dashboard **40 passed** locally and in main CI [#38293276028](https://github.com/aodxx/X2Telegram/actions/runs/38293276028); Pages [#38293276008](https://github.com/aodxx/X2Telegram/actions/runs/38293276008) and Worker deploy [#38293345118](https://github.com/aodxx/X2Telegram/actions/runs/38293345118) passed. No live destination was called because no new test chat/folder was approved.
- Limitations: isolate-local single-flight is not a durable/global lock. Concurrent requests reaching separate Cloudflare isolates, an isolate restart, or a request after the 30-second retention window may race before GitHub exposes the run. System does not claim exactly-once dispatch/delivery; no database/queue was introduced.

### Scenario matrix

| Scenario | ผล | หลักฐาน/ขอบเขต |
|---|---|---|
| Additional Cloudflare Access identity | CONFIGURED; login ยังไม่ยืนยัน | PR #25 / main commit `f5372e5`; policy มีสอง exact email rules และ Worker secret ตั้งแล้ว; ไม่มีการส่ง OTP หรือทดสอบ session ของผู้ใช้รอง |
| โพสต์หนึ่งรายการมี media หลายชิ้น | PASS (live source-only + automated mock) | Real source-only mixed photo/video: expected 2, exported 2, both validated/accounted, local size/SHA-256 matched manifest; synthetic MEGA independently verified two identities |
| MEGA multi-media identity, changed version and duplicate | PASS (live synthetic integration on main) | Main run #38288698061: 2 initial items, 1 changed version, 1 true duplicate; 3 remote objects listed and downloaded back with matching bytes/SHA-256; isolated folder cleaned |
| Dashboard Access/login same-origin | PASS (live) | Browser แสดง `Access ลงชื่อเข้าใช้แล้ว · พร้อมส่ง` |
| Telegram normal path | PASS (live) | Run #37807253687, MP4 1 ไฟล์, message ID 347 |
| Batch URL dispatch (ปัจจุบันสูงสุด 200) | PASS (live 2 URLs; regression รับ 200) | Run #37816856323; completed posts ถูก dedupe ไม่ส่งซ้ำ และ Worker/Dashboard tests ครอบคลุมเพดาน 200 |
| Download-only, multiple URL job | PASS (live 2 URLs) | Run #37843359593; private artifact พร้อมและ report แสดง 2 files |
| Worker protected ZIP streaming | PASS (live) | Browser ดาวน์โหลดจริงผ่าน Access route; ZIP CRC ผ่าน |
| Telegram/MEGA/Dropbox/Download combinations | PASS สำหรับ media 1 รายการ (live); อีก URL ล้มก่อนถึง targets | Run #38037210973; all 4 destinations success/ready สำหรับรายการที่ดึงได้ |
| Retry เฉพาะ destination ที่ล้มเหลว | PASS (automated mock) | Mega failure แล้ว retry; Telegram ที่สำเร็จไม่ถูกส่งซ้ำ |
| P3 concurrent duplicate/conflicting POST in one isolate | PASS (automated Worker tests) | Same payload dispatches once; conflicting payload receives 409; cross-isolate race remains documented |
| Dashboard reload/report recovery and retry selection | PASS (browserless harness) | Lookup-only restore/no auto-dispatch; retry contains only confirmed failed targets |
| Dashboard sequential batches and status polling interruptions | PASS (browserless harness; merged/deployed via PR #27) | Transient polling retries/recovery lock and new-batch labeling; Pages #38300619373; no destination write |
| Destination ambiguous outcome recovery | PASS (automated mock) | Timeout/5xx/verification uncertainty is checkpointed and not replayed; no live destination check |
| ภาพ+วิดีโอในโพสต์เดียว | PASS (automated mock) | ภาพยังคงอยู่ และเลือก video variant สูงสุด; download หนึ่งครั้งต่อ media |
| Invalid MEGA folder/credential failure | PASS (automated mock) | MEGA failure ไม่หยุด Telegram/Download; ไม่มี command output ใน report |
| MEGA upload จริง | PASS (live MEGA-only) | Run #37848879753; หนึ่ง media upload สำเร็จ; Telegram ไม่ได้เลือก |
| MEGA changed content preserves prior file | PASS (live integration + regression) | Run #37984146026 อัปโหลด fixture สองเวอร์ชันใน post เดียว, ตรวจ listing และ downloaded bytes; ไม่ได้ใช้ media จาก X |
| Dropbox connector | PASS (one live normal item + automated edge cases) | Run #38037210973; refresh failure sanitization, session chunk bytes/offsets และ ambiguous final timeout ไม่ replay ผ่าน mocks; live refresh/session ยังไม่ยืนยัน |
| Dropbox upload จริง | PASS (live one media) | Run #38037210973; รายการที่ดึงได้อัปโหลดสำเร็จ; ไม่มี Dropbox-specific error |
| Telegram+MEGA live combined send | PASS (one live media item) | Run #38037210973; ทั้ง Telegram และ MEGA สำเร็จ; Telegram >50 MB ยังต้องใช้ Large-file mode |
| Telegram Local Bot API large file | BLOCKED (live; mocked boundaries pass) | Standard-mode boundary/fail-closed fallback มี automated coverage; ไม่มี test-chat authorization และไม่ได้ยืนยัน Local Bot API upload จริง |
| X/media shared download | PARTIAL (live failures observed) | `download_error` ใน runs #38037210973 และ #38102121635; เมื่อ source media ดึงไม่ได้ ทุก target ของ URL นั้น fail ก่อน dispatch |
| X/source reliability P1 release | PASS for declared scope (production deployed + source-only live) | P1 commit `8fb4427` deployed; post-fix historical failure URL fetched 29,799,397 bytes and validated; no destination called; CI #38254729760 |
| Media completeness P2 release | PASS (merged to main) | Main commit `a5711e1`, main CI #38288698022, synthetic MEGA read-back #38288698061; Worker unchanged so no Worker deployment |
| Mobile browser | NOT RUN | ยังไม่มีการทดสอบบนอุปกรณ์มือถือจริง |
| Invalid URL, body cap, unauthorized | PASS (Worker tests/live safe checks เดิม) | 400/413/401/403 paths ปฏิเสธก่อน dispatch ตาม report/contract เดิม |

## Automated validation baseline and production releases

- Previously recorded Python baseline: `python3 -m pytest -q` — **95 passed**; current local/CI P1 release: **129 passed** (CI #38254729760)
- P2 main commit `a5711e1`: destination/metadata/report targeted tests — **54 passed**; full Python suite — **134 passed**; Worker — **27 passed**; compile, workflow YAML/embedded shell/Python syntax, internal links, and `git diff --check` passed. Main CI [#38288698022](https://github.com/aodxx/X2Telegram/actions/runs/38288698022) and synthetic MEGA [#38288698061](https://github.com/aodxx/X2Telegram/actions/runs/38288698061) passed.
- P3 main commit `9e9e9f8` (PR #24): Python **143 passed**, Worker/Dashboard **40 passed**; main CI [#38293276028](https://github.com/aodxx/X2Telegram/actions/runs/38293276028), Pages [#38293276008](https://github.com/aodxx/X2Telegram/actions/runs/38293276008), Worker deploy [#38293345118](https://github.com/aodxx/X2Telegram/actions/runs/38293345118) passed; production version `f2e1afaf-db8e-4356-be75-215f60eb53e5`.
- Access rollout main commit `f5372e5` (PR #25): main CI [#38295563125](https://github.com/aodxx/X2Telegram/actions/runs/38295563125) and Worker deploy [#38295769200](https://github.com/aodxx/X2Telegram/actions/runs/38295769200) passed; Python **143**, Worker **42**; production version `649353cf-fd9a-498b-9415-14bae01de486`. The new identity's OTP sign-in remains unverified.
- Dashboard/P4 automated update main commit `763bd9a` (PR #27): CI [#38300530120](https://github.com/aodxx/X2Telegram/actions/runs/38300530120) passed Python **147** and Worker/Dashboard **45**; Pages [#38300619373](https://github.com/aodxx/X2Telegram/actions/runs/38300619373) passed. P4 live Telegram and Dropbox scenarios remain untested/blocked.
- Cloudflare Worker: latest main CI `npm test --prefix control-worker` — **45 passed**; Worker version remains `649353cf-fd9a-498b-9415-14bae01de486` because PR #27 did not change Worker production code.
- Deploy workflow [#38263528272](https://github.com/aodxx/X2Telegram/actions/runs/38263528272): Worker tests 27/27, Wrangler dry-run และ production deploy ผ่าน on commit `8fb4427`; Worker version `e6bff44f-12e9-4a55-bfdb-c7b7cfb6587f`
- Python compile, Node syntax, workflow YAML parse, `git diff --check`, `npm ci` และ Wrangler dry-run ผ่าน
- Live run #37843359593 ผ่าน automated Python/Worker tests ก่อน process, report และ media artifact upload
- Latest repair release `f08c0aa` (2026-10-16): แก้ลำดับ `persist-state` ให้ commit `state/dedupe.json` ก่อน fetch/rebase จึงไม่เกิด `cannot rebase: You have unstaged changes`; เพิ่ม workflow contract regression test. Automated Tests [#38923942624](https://github.com/aodxx/X2Telegram/actions/runs/38923942624) ผ่าน และ Dashboard Pages [#38923942619](https://github.com/aodxx/X2Telegram/actions/runs/38923942619) ผ่าน. Local validation: Python **148 passed**, Worker/Dashboard **45 passed**, compile, Node syntax, workflow YAML และ diff checks ผ่าน

## ข้อสรุป

P1 source reliability is deployed and the historical failure URL passed a post-fix source-only fetch. P2 is merged on main commit `a5711e1`; P3 is merged on `9e9e9f8` with documented exactly-once limitations. Access second-email support is merged and deployed on main commit `f5372e5` (Worker version `649353cf-fd9a-498b-9415-14bae01de486`); both exact identity rules are configured, but the secondary user's OTP sign-in remains unverified. Commit `f08c0aa` repairs state persistence ordering and improves narrow-mobile action layout/accessibility; its CI and Pages deployment passed. P3 still has no live destination retry; P4 remains partial because Telegram Local Bot API >50 MB and Dropbox token-refresh/large-file session paths need authorized live destinations. A real mobile browser test is also outstanding.
