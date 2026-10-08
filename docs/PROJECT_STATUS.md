# X2Telegram — Project Status

**สถานะเอกสาร:** อัปเดตล่าสุด 2026-10-08
**Branch:** `migration/zone-1-5-cloudflare-control-plane` (PR #2)
**อ้างอิงโค้ด:** baseline `a2dd320`; ดู implementation ปัจจุบันใน PR #2

## สรุปผู้บริหาร

แกนหลักของ X2Telegram อยู่ในสถานะ **พร้อมใช้งานจริงผ่าน GitHub Actions** สำหรับการดาวน์โหลด media จากโพสต์ X ที่เข้าถึงได้แบบสาธารณะและส่งเข้า Telegram กลุ่มปลายทางที่ล็อกไว้ ระบบได้รับการทดสอบด้วย workflow จริงและยืนยันการส่งวิดีโอสำเร็จแล้ว

> ขอบเขตการใช้งาน: ใช้เฉพาะ media ที่ผู้ใช้มีสิทธิ์ดาวน์โหลดและเผยแพร่ และต้องปฏิบัติตามกฎหมาย/เงื่อนไขของแพลตฟอร์ม เนื้อหา 18+ ต้องเป็นเนื้อหาที่ถูกกฎหมายและได้รับความยินยอมตามข้อกำหนดที่เกี่ยวข้อง

## สิ่งที่ทำสำเร็จแล้ว

### 1. Workflow และการประมวลผล

- รับ URL X หลายรายการผ่าน `workflow_dispatch` โดยใช้หนึ่ง URL ต่อหนึ่งบรรทัด
- ตรวจสอบ host และรูปแบบ post ID ของ `x.com` / `twitter.com`
- ตัด query string ของ source post URL เช่น `?s=20` ก่อนใช้ lookup โดยไม่ทำลาย query ที่จำเป็นบน direct media URL
- ประมวลผลแต่ละโพสต์แยกจากกัน URL ที่ล้มเหลวไม่หยุดรายการอื่น
- มี timeout และการ retry สำหรับการเรียกบริการที่เหมาะสม
- ลบไฟล์ชั่วคราวหลังการส่ง และไม่ commit media เข้า repository

### 2. Metadata fallback และการดาวน์โหลด

ลำดับ provider ปัจจุบันคือ:

```text
yt-dlp → X syndication → public FxTwitter API
```

- เลือก video variant ที่มี bitrate สูงสุด
- รองรับ photo fallback ตามชนิด media
- รับเฉพาะ MP4 variant จาก FxTwitter fallback
- ตรวจสอบ URL และ host ก่อนดาวน์โหลด
- เขียนไฟล์แบบ atomic และตรวจ content type / file signature
- รองรับโพสต์ที่ provider หลักหา media ไม่พบมากขึ้น

### 3. Telegram และความปลอดภัย

- ปลายทางถูกล็อกไว้ที่กลุ่ม Telegram chat ID `-1003906817580`
- ใช้ `TELEGRAM_BOT_TOKEN` จาก GitHub Actions Secrets เท่านั้น
- ทำ Telegram preflight ก่อนดาวน์โหลดทุกครั้งด้วยการตรวจ token, chat, membership และสิทธิ์ส่งข้อความ/media
- ไม่เปิดให้ผู้ใช้เปลี่ยน chat ID จาก input workflow
- ไม่ส่ง token, API credentials หรือ media URL ลับเข้า log/report
- ไม่อัปโหลดไฟล์ไป Google Drive ใน flow ปัจจุบัน

### 4. Large-file mode

- โหมดมาตรฐานใช้ Telegram Bot API และจำกัดไฟล์ที่ 50 MB
- `large_file_mode=true` จะเริ่ม Telegram Local Bot API Server เฉพาะใน job นั้น
- ต้องมี `TELEGRAM_API_ID` และ `TELEGRAM_API_HASH` เป็น repository secrets
- เพดานที่ตั้งไว้สำหรับ large-file mode คือ 2000 MB
- Local Bot API Server มี health check และถูกหยุดเมื่อจบงาน

### 5. Duplicate prevention

- ใช้ `state/dedupe.json` เป็น state ข้าม workflow run
- ใช้ post ID เป็น key หลัก และ normalized URL เป็น fallback
- บันทึกเฉพาะหลัง Telegram ยืนยันการส่งสำเร็จและมี message ID
- ใช้ lock + atomic replace เพื่อลดความเสี่ยง state เสียหาย
- ใช้ GitHub Actions concurrency ป้องกัน run ชนกัน
- workflow commit state กลับไปยัง branch เมื่อมีการเปลี่ยนแปลง
- รายการซ้ำจะได้สถานะ `skipped_duplicate`

### 6. Reporting และ observability

แต่ละ run สร้าง:

- `report.json` — สถานะรวม, preflight, ผลรายโพสต์, stage, error code และ Telegram message IDs
- `run.jsonl` — structured execution log
- GitHub Step Summary — สรุปผลบนหน้า workflow
- optional redacted webhook alert ผ่าน `ALERT_WEBHOOK_URL`
- local dry-run และ preflight runner ที่ `scripts/local_test.sh`

## หลักฐานการทดสอบจริงล่าสุด

Workflow run ล่าสุดที่ใช้โค้ด `a2dd320`:

- Run: [GitHub Actions run 36980600244](https://github.com/aodxx/X2Telegram/actions/runs/36980600244)
- Commit: `a2dd320a6c75bad206e4cfa843964764ca77d9ed`
- Workflow conclusion: `success`
- โหมด: `large_file_mode=true`
- Telegram preflight: ผ่าน
- Target: `-1003906817580`
- Post ที่ทดสอบ: `2105840724075798807`
- Result: `sent`
- Media count: `3`
- Telegram message ID: `345`
- Error: ไม่มี

ผลนี้ยืนยันว่า **เส้นทางตั้งแต่ metadata fallback/download ไปจนถึงการส่งเข้า Telegram ทำงานจริงอย่างน้อยกับโพสต์ทดสอบนี้** แต่ไม่ใช่การรับประกันว่าโพสต์ X ทุกประเภทจะดาวน์โหลดได้ เนื่องจากโพสต์อาจถูกลบ เป็น private ถูกจำกัดอายุ ต้อง login หรือถูก rate limit

## สิ่งที่ยังต้องตรวจสอบ/ดูแลใน production

- ตรวจว่า repository Settings → Actions → General → Workflow permissions อนุญาต `Read and write` เพื่อให้ dedupe state push กลับได้
- ตรวจและหมุน secrets หากมีเหตุสงสัยว่า token รั่ว
- ติดตามการเปลี่ยนแปลงของ X, yt-dlp, syndication และ FxTwitter API
- ทดสอบกรณีไฟล์ใหญ่จริงเป็นระยะ ไม่ใช่เฉพาะการเปิดโหมด large-file
- ตรวจ artifact `report.json` เมื่อมีรายการ `no_media`, `metadata_error`, `download_error` หรือ `telegram_error`
- พิจารณา retention ของ artifacts และ log ให้เหมาะกับข้อมูลที่ประมวลผล

## สิ่งที่จะพัฒนาต่อ — Phase 6.1: Private Dashboard MVP

เป้าหมายคือให้ผู้ใช้วางลิงก์และกด Run ผ่านหน้าจอที่ใช้งานง่าย โดยยังคงใช้ workflow และระบบความปลอดภัยเดิมเป็น backend หลัก

### ความคืบหน้าล่าสุด: Phase 6.1A–1E implementation เสร็จใน repository

- สร้าง Static Dashboard ที่ `web/index.html` ด้วย responsive UI สำหรับ desktop และมือถือ
- เพิ่มการตรวจ X URL ฝั่ง browser, การนับ valid/invalid/duplicate และหน้าสรุปรายการก่อนส่ง
- เพิ่มตัวเลือก `large_file_mode` และแสดงปลายทาง Telegram ที่ล็อกไว้
- เพิ่มปุ่มเปิด GitHub Actions workflow และลิงก์ลงชื่อเข้าใช้ Cloudflare Access โดยไม่ฝัง GitHub หรือ Telegram token ในหน้าเว็บ
- เพิ่ม `.github/workflows/pages.yml` สำหรับ deploy โฟลเดอร์ `web/` ไปยัง GitHub Pages อัตโนมัติเมื่อ push เข้า `main`
- เพิ่ม `docs/CONTROL_PLANE_CONTRACT.md` เป็น API/state/idempotency contract ของ Control Plane
- เพิ่ม `control-worker/` สำหรับ Cloudflare Worker ที่ตรวจ Access JWT, validate URL, dispatch/read GitHub Actions, อ่าน sanitized report artifact และบังคับ exact-origin CORS
- เพิ่ม offline Worker tests สำหรับ auth, invalid input, duplicate/conflict, GitHub failure, status/report และ CORS
- Workflow เพิ่ม `url`, `request_id`, `job_id` โดยยังรองรับ `urls` แบบ manual เดิม; Python report และ sanitized projection เพิ่ม `job_id`

> Static UI ใน branch migration ถูกปรับเป็น Dashboard client ของ Cloudflare Control Worker; Worker, owner-only Access และ `GH_TOKEN` secret ตั้งแล้ว. Authenticated health ผ่านและ read-only status lookup ยืนยัน GitHub Actions read ได้; credential ต้อง rotate ก่อน production. GitHub Pages บน `main` ยังเป็นหน้าเดิม เนื่องจาก PR #2 ยังไม่ merge

### Phase 6.1B: Report contract สำหรับ private control plane

- เพิ่ม `request_id`, summary และ filenames ใน workflow report
- เพิ่ม `src/dashboard_report.py` เพื่อสร้าง report แบบ allow-list สำหรับ Backend
- ไม่ push report ไปยัง public branch `dashboard-data`
- อัปโหลด sanitized report เป็น private GitHub Actions artifact ชื่อ `x2telegram-dashboard-report-<run_id>` โดยเก็บ 30 วัน
- Cloudflare Control Worker ใช้ GitHub API credential ฝั่ง server เพื่ออ่าน artifact หลัง workflow เสร็จ

> **Historical status ณ เวลาจัดทำ Phase 6.1B:** Data contract และ private artifact เสร็จแล้ว; ขณะนั้นยังไม่มี dispatch/report/Telegram E2E. ผล normal-path E2E ที่ทำภายหลังบันทึกไว้ในส่วน Zone 9 ด้านล่าง

### Google Apps Script Backend: legacy/reference (ไม่ใช่เส้นทางใหม่)

- เพิ่ม `gas/Code.gs` สำหรับ `doGet`/`doPost`
- รองรับ `health`, `start`, `status` และ `report`
- ตรวจ URL ฝั่ง backend, จำกัดจำนวน URL และตรวจ `large_file_mode`
- ใช้ `LockService`/`CacheService` ป้องกัน double-submit และ cache report ชั่วคราว
- เก็บ GitHub token ใน Apps Script Script Properties และไม่ส่ง token ให้ frontend
- เรียก GitHub Actions API และดาวน์โหลด sanitized dashboard artifact แบบ authenticated
- เพิ่ม `gas/README.md` และ `gas/appsscript.json` สำหรับ deployment/configuration

> `gas/` คงไว้เพื่อ reference/rollback เท่านั้น Dashboard ใหม่ไม่เรียก GAS แล้ว; ไม่ควร deploy เป็น production endpoint คู่ขนานโดยไม่มีเหตุผล

### Dashboard integration: เชื่อมต่อ Control Worker แล้วใน source

- หน้า `web/index.html` เรียก Cloudflare Control Worker REST API โดยตรงผ่าน `web/config.js`
- รองรับการเริ่มงานจากหน้า Dashboard โดยไม่ต้องเปิด GitHub Actions เอง
- แสดง request ID, run ID, สถานะ queued/in progress/completed และลิงก์ workflow
- polling สถานะทุก 5–7 วินาทีและหยุดเมื่อ workflow จบ; current job/recent jobs เก็บใน browser localStorage
- อ่าน sanitized report และแสดงผลรายโพสต์/summary ในหน้าเดียว
- ปุ่มเริ่มงานส่งหนึ่ง URL ที่ผ่านการตรวจฝั่ง browser พร้อม `request_id`; Worker ตรวจซ้ำและคำนวณ `job_id`

> Access owner-only และ email OTP ตั้งแล้ว; browser ที่ไม่มี session ถูก redirect ไปหน้า login. CORS ถูกจำกัดที่ `https://aodxx.github.io`; owner sign-in, read-only lookup, normal-path E2E และ live Dashboard health ผ่านแล้ว (run `37807253687`, ส่งหนึ่ง MP4, message ID `347`; Pages deploy `37809007472`). PR #2 merged และหน้า live. `GH_TOKEN` ยังไม่ได้ rotate ตามคำสั่งเจ้าของ จึงยังมี P1 production blocker

### Zone 7/8 hardening (source complete; production gates remain)

- `src/dedupe.py` state v2 เพิ่ม SHA-256 content fingerprint ต่อ media และ migration path อ่าน completed-post records แบบ v1
- `src/processor.py` ข้าม media ที่ส่งสำเร็จแล้วและ retry เฉพาะชิ้นที่ยังไม่สำเร็จ; tests ครอบ first/middle/last failure และ temporary URL rotation
- `src/telegram_api.py`, `src/logging_utils.py`, `src/cli.py` ไม่ serialize Telegram token/raw response ใน errors และ redact ก่อน report/stdout
- `src/downloader.py` ปิด auto-redirect และ validate HTTPS/host ทุก hop; Worker body cap อ่าน stream แบบ bounded; tests ครอบ oversized body และ per-isolate rate cap
- Local validation ล่าสุด: Python **47 passed**, Worker **15 passed**, syntax/compile/diff checks ผ่าน
- Worker security-hardening source ถูก deploy แล้ว (version ปัจจุบัน `29a2c667-cce4-4da9-8bff-d93b89490e0f`, `GH_REF=main`); live cross-origin health `200`, invalid URL `400`, และ body 17 KiB `413` ผ่านโดยไม่มี workflow dispatch
- Zone 9 normal-path E2E: run `37807253687` บน migration branch สำเร็จ; report ยืนยัน `sent=1`, `failed=0`, Telegram message ID `347`. Run แรก `37806865130` ล้มก่อน process เพราะ Worker ส่ง `url`/`urls` ซ้ำ; แก้ mapping และเพิ่ม regression test แล้ว. Worker ถูกคืน `GH_REF=main` หลังทดสอบ
- PR #2 squash-merged เป็น `00936856a02261e1969d517157f5591d1a0d0c12`; GitHub Pages deploy run `37809007472` ผ่าน และ live dashboard health badge แสดง `Control Worker พร้อม`
- ยังไม่ production-secure: `GH_TOKEN` ค่าแรกถูกเปิดเผยและเจ้าของยังไม่อนุมัติ rotate/revoke; ยังเหลือ P2 สำหรับ edge/global rate limit, workflow permission/supply-chain pinning และ exactly-once หลัง network timeout
- E2E scenarios ที่เหลือ: duplicate/no-resend live, multi-photo/multiple distinct media, partial-failure live recovery, large-file, browser refresh/UI และ mobile

### Historical legacy note: Apps Script POST redirect

- ตรวจพบว่า Apps Script Web App ตอบ `health` แบบ GET ได้ แต่ POST ที่ตาม redirect อาจจบด้วย HTTP 405 ใน browser
- เพิ่ม `GET action=start` ที่รับ JSON แบบ base64url เป็น fallback สำหรับเริ่ม workflow
- Dashboard เปลี่ยนการเริ่มงานมาใช้ GET fallback เพื่อลดปัญหา POST redirect
- Dashboard อ่าน response แบบ text ก่อน parse JSON และแสดงข้อความภาษาไทยเมื่อพบ CORS, 405 หรือ response ที่ไม่ใช่ JSON
- ข้อควรจำ: รายการนี้เป็น history ของ GAS path เดิม ไม่ใช่ขั้นตอน deploy Dashboard/Control Worker รุ่นปัจจุบัน

### ขอบเขตที่เสนอ

1. หน้า Dashboard responsive สำหรับ desktop และมือถือ
2. รับ X URL หนึ่งรายการต่อหนึ่ง job ผ่าน Dashboard; manual GitHub workflow ยังคงรับ batch URLs ได้
3. ตรวจ X URL ก่อนเริ่ม และให้ Worker ตรวจซ้ำฝั่ง server
4. หน้าสรุปให้ review รายการก่อนกดส่ง
5. ปุ่มเริ่ม workflow ผ่าน backend ที่ปลอดภัย
6. ตัวเลือก `large_file_mode` พร้อมคำเตือนเรื่อง credentials/ขนาดไฟล์
7. ติดตามสถานะ run และแสดงผลรายโพสต์จาก `report.json`
8. แสดง `sent`, `skipped_duplicate`, `no_media` และ error states แบบอ่านง่าย
9. แสดง Telegram message ID และชื่อไฟล์เมื่อมีใน report
10. เก็บ recent run summary โดยไม่เปิดเผย secrets

### ข้อกำหนดความปลอดภัยของ Phase 6.1

- ห้ามใส่ GitHub token หรือ Telegram bot token ใน frontend
- ต้องมี backend/API ที่เก็บ credential ใน secret store
- ต้องล็อก target chat ID เป็น `-1003906817580`
- ต้องตรวจ URL ฝั่ง server ซ้ำ แม้ frontend จะตรวจแล้ว
- ต้องมี authentication อย่างน้อยระดับ private access ก่อนเปิดใช้งานจริง
- ต้องมี rate limit และจำกัดจำนวน URL ต่อ request
- ห้ามเพิ่ม Google Drive เป็นปลายทางโดยอัตโนมัติ

### ยังไม่อยู่ใน Phase 6.1

- ระบบ multi-user และ role/permission แบบเต็มรูปแบบ
- การแก้ไข Telegram destination จากหน้าเว็บ
- การชำระเงินหรือการให้บริการสาธารณะ
- การย้าย downloader ออกจาก GitHub Actions
- การรับประกันการดาวน์โหลดโพสต์ private หรือ content ที่ต้อง login

## Decision ที่แนะนำ

คง **GitHub Actions เป็น execution backend**. PR #2 merged และ Dashboard live แล้ว; Pages/Worker health ผ่าน. Normal-path E2E ส่งหนึ่ง MP4 สำเร็จ. ใช้งานได้ทางเทคนิค แต่ยังไม่ production-secure เพราะ `GH_TOKEN` ที่เปิดเผยยังไม่ rotate (เจ้าของยังไม่อนุมัติ), scenarios ที่เหลือและ residual findings ยังอยู่. คู่มือผู้ใช้: [`USER_GUIDE_TH.md`](USER_GUIDE_TH.md); GitHub Actions manual UI เดิมยังเป็น fallback

## จุดอ้างอิงสำคัญใน repository

- Workflow: `.github/workflows/x2telegram.yml`
- Telegram API/preflight: `src/telegram_api.py`
- Metadata fallback: `src/metadata.py`
- Duplicate state: `src/dedupe.py`
- Local runner: `scripts/local_test.sh`
- Deployment guide: `docs/DEPLOYMENT.md`
- Architecture notes: `docs/ARCHITECTURE.md`
- UX prototype: `web/index.html`
