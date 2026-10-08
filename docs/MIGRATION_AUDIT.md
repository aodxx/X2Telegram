# X2Telegram — Migration Audit (Zone 0)

ตรวจสอบเพื่อเตรียมย้าย control plane จาก Google Apps Script (GAS) ไปเป็น Cloudflare Worker โดยคง GitHub Actions และ X2Telegram execution worker ที่มีอยู่ไว้

- Repository: `aodxx/X2Telegram`
- Branch ที่ตรวจ: `main`
- Commit ที่ตรวจ: `f8609ffed79cc71c77bfd6d3d67c5bce1a84e30b` (`feat: allow public Apps Script API mode`)
- ขอบเขต: อ่าน runtime, workflow, tests และเอกสาร; ไม่แก้ runtime, ไม่ลบไฟล์, ไม่ deploy และไม่เรียกส่ง Telegram

## สรุป

ระบบประมวลผลหลักอยู่ใน GitHub Actions และมีโมดูล Python สำหรับ parsing, metadata, download, Telegram, dedupe และ report ที่นำกลับมาใช้ได้ การตัด GAS ออกจึงควรเปลี่ยนเฉพาะส่วนรับคำสั่ง/ตรวจสถานะระหว่าง Dashboard กับ workflow ไม่ควรรื้อ processing worker

จุดที่ต้องแก้/ตกลงใน Zone ถัดไปก่อนเริ่ม Cloudflare Worker ได้แก่:

1. ปัจจุบัน GAS เป็น public API ตามเอกสาร (`Who has access: Anyone`) และ `Code.gs` ไม่มีการตรวจ identity เอง การคุ้มครองด้วย Cloudflare Access ยังไม่อยู่ใน request path ปัจจุบัน
2. Dashboard ส่งข้อมูลเริ่มงานผ่าน `GET` โดย base64url-encode payload ไว้ใน query string ทำให้ URL ของ X และ request identifiers อาจไปอยู่ใน browser/proxy/access logs
3. request contract ของแผนเป็น URL เดี่ยวพร้อม `job_id` แต่ workflow ปัจจุบันรับ `urls` หลายรายการ และไม่มี `job_id`; ต้องกำหนด compatibility contract ก่อนแก้ workflow/Worker
4. idempotency ปัจจุบันอาศัย CacheService 6 ชั่วโมงและ key ที่ Dashboard สุ่มใหม่ทุกครั้ง จึงไม่เท่ากับการป้องกัน double-click ข้ามการกดซ้ำที่สร้าง key ใหม่
5. status/report ปัจจุบันอ่านผ่าน GitHub Actions API และ sanitized private artifact โดย GAS; ต้องย้ายการอ่านผลฝั่ง server-side ไปยัง control Worker โดยไม่เปิด credential ให้ browser

## Dependency graph ปัจจุบัน

```text
ผู้ใช้
  ↓
GitHub Pages (web/index.html)
  ├─ ตรวจรูปแบบ X URL ใน browser
  └─ fetch ไปยัง Google Apps Script Web App
       ├─ health / start / status / report
       ├─ Script Properties: GitHub credential และ config
       ├─ CacheService: idempotency (TTL 6 ชั่วโมง) และ report cache (TTL 5 นาที)
       └─ GitHub REST API
            ├─ workflow_dispatch: urls, large_file_mode, request_id
            ├─ list/read workflow runs
            └─ อ่าน sanitized dashboard artifact
                 ↑
GitHub Actions workflow (.github/workflows/x2telegram.yml)
  ├─ รัน pytest
  ├─ เรียก src/cli.py
  │    └─ parse → metadata (yt-dlp → syndication → FxTwitter)
  │       → validate/download media → dedupe → Telegram
  ├─ state/dedupe.json (commit กลับ branch ด้วย GITHUB_TOKEN)
  └─ report.json / run.jsonl → sanitized dashboard artifact + report artifact
```

## คำตอบตามข้อกำหนด Zone 0

### 1. Dashboard ปัจจุบันเรียก backend อย่างไร

`web/index.html` ใช้ `API_URL` เป็น Apps Script Web App URL และเรียก `fetch()` ด้วย `credentials: 'omit'` และ `Content-Type: text/plain;charset=utf-8` มี action `health`, `start`, `status` และ `report` ผ่าน query string

การเริ่มงานใช้ `GET ?action=start&payload=...` โดย payload JSON ถูกแปลงเป็น base64url แล้วใส่ใน URL เพื่อเลี่ยงปัญหา POST redirect/CORS ที่ระบุในประวัติการพัฒนา Dashboard ส่ง `urls[]`, `large_file_mode`, `request_id` และ `idempotency_key` จาก browser สร้าง request ID ใหม่ต่อการกดเริ่มงาน มี polling ทุก 7–10 วินาทีหลังเริ่มสำเร็จ

Dashboard แสดง run ปัจจุบันและ report ของ run ที่กำลังดู; ไม่พบการ persist job ปัจจุบันหรือ recent jobs ข้าม refresh ใน source ที่ตรวจ

### 2. GAS รับ request อย่างไร

`gas/Code.gs` มี `doGet` รองรับ `health`, `start`, `status`, `report`; `doPost` รองรับ `start` โดยอ่าน JSON body การเริ่มงานตรวจรายการ URL, `large_file_mode`, `request_id` และ `idempotency_key` จำกัดจำนวน URL ตาม Script Property `MAX_URLS` (default 20) ใช้ `LockService` ครอบ dispatch และ `CacheService` สำหรับ key ซ้ำ/รายงาน

`gas/README.md` และ `gas/SETUP_VALUES.md` กำหนดให้เผยแพร่ Web App แบบ `Anyone` และระบุว่าเป็น public API mode ส่วน `Code.gs` ไม่พบการตรวจอีเมล Google, session หรือ shared authentication token ใน handler

### 3. GAS dispatch workflow อย่างไร

ใช้ GitHub REST API `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches` ด้วย Bearer token จาก `GITHUB_TOKEN` ใน Apps Script Script Properties ส่ง `ref` และ inputs: `urls` (รวมด้วย newline), `large_file_mode` และ `request_id` หลัง dispatch GAS ค้นหา workflow run โดย correlation กับ `request_id`

### 4. GitHub Actions รับ input อะไร

`.github/workflows/x2telegram.yml` ใช้ `workflow_dispatch` inputs ดังนี้:

| Input | ชนิด | หน้าที่ |
|---|---|---|
| `urls` | string, required | URL หนึ่งรายการต่อบรรทัด |
| `large_file_mode` | boolean, required, default `false` | เลือก Local Bot API / เพดานไฟล์ |
| `request_id` | string, optional | correlation ID และ run name |

ยังไม่มี `url` แบบเอกพจน์และไม่มี `job_id` ตาม API shape ใน Master Plan ปัจจุบัน GAS ส่ง `urls` ไม่ใช่ `url` ด้วย

### 5. Worker รับ input อย่างไร

ขั้น entrypoint คือ workflow ไม่ใช่ HTTP worker ที่รับ request โดยตรง Workflow ใส่ `inputs.urls` ลง `INPUT_URLS`, ตั้ง `LARGE_FILE_MODE`, `REQUEST_ID` และ config Telegram ผ่าน environment แล้วเรียก `printf ... | python -m src.cli ...` ตัว `src/cli.py` อ่าน URL batch จาก stdin และใช้ `parse_batch()` เพื่อ normalize/dedupe URL ก่อนประมวลผล

Telegram bot token และ optional Telegram API credentials ถูกส่งให้ job จาก GitHub Actions Secrets; target chat ถูกล็อกไว้ใน workflow/config

### 6. Worker สร้าง report ที่ไหน

`src/cli.py` เขียน full report เป็น `report.json` และ structured log เป็น `run.jsonl` ใน workspace ของ runner; สร้าง GitHub Step Summary และ optional webhook summary เพิ่มเติม Workflow แปลง `report.json` ด้วย `src/dashboard_report.py` เป็น `/tmp/dashboard-report.json` ซึ่งเป็น allow-listed/sanitized projection แล้ว upload เป็น artifact `x2telegram-dashboard-report-<run_id>` อายุ 30 วัน อีก artifact ชื่อ `x2telegram-report-<run_id>` เก็บ report/log เต็มตาม workflow configuration

### 7. Dashboard อ่าน status/report อย่างไร

Dashboard ถาม GAS ด้วย `action=status` โดยใช้ `run_id` หรือ `request_id`; GAS อ่าน workflow run ผ่าน GitHub API เมื่อ workflow completed และ conclusion เป็น success Dashboard เรียก `action=report`; GAS หา private artifact ที่ชื่อผูกกับ run ID ดาวน์โหลด ZIP และคืนเฉพาะ sanitized JSON

ข้อจำกัดจาก implementation: dashboard ขอ report เมื่อ workflow conclusion เป็น `success` เท่านั้น; เมื่อ workflow ล้มเหลวแสดงสถานะ/ข้อความ แต่ไม่ดึง report เพื่อแสดง per-post failure ใน branch นั้น

### 8. ส่วนใด reuse ได้

- `src/cli.py`, `src/processor.py`, `src/urls.py`
- metadata/download/media validation: `src/metadata.py`, `src/downloader.py`, `src/security.py`, `src/media.py`
- Telegram integration/preflight: `src/telegram_api.py`, `src/telegram.py`
- dedupe state: `src/dedupe.py` และ `state/dedupe.json`
- report serialization/sanitization: `src/dashboard_report.py` และรูปแบบ report ปัจจุบัน
- `.github/workflows/x2telegram.yml` ในฐานะ execution entry point หลังตกลง input compatibility
- หน้า UI, URL validation, layout และแสดงผลส่วนใหญ่ใน `web/index.html` โดยเปลี่ยน API client/backend wording และเพิ่มความสามารถตาม contract ใหม่เท่าที่ต้องใช้
- GitHub Pages workflow และ deployment flow

### 9. ส่วนใดต้องเปลี่ยน

เพื่อเอา GAS ออกโดยกระทบ worker น้อยที่สุด:

1. เพิ่ม Cloudflare control Worker ขนาดเล็กสำหรับรับ POST job, validate, ป้องกันซ้ำ, เรียก GitHub workflow dispatch และอ่าน status/report ผ่าน GitHub API
2. กำหนด contract ให้ชัดก่อน implement: URL เดี่ยวหรือ batch; การสร้าง/ผูก `job_id`; mapping กับ `request_id` และ run ID; status/error states; duplicate/retry semantics
3. ปรับ workflow inputs เฉพาะส่วนจำเป็นให้รองรับ contract ใหม่ โดยรักษา `urls`/manual run เดิมให้ backward-compatible หากทำได้ และให้ worker ภายใน Python ไม่เปลี่ยน
4. เปลี่ยน Dashboard จาก GAS endpoint ไปยัง control Worker; เพิ่มการจัดการ Access/session, error mapping และ restore job หลัง refresh ตาม UX ที่ตกลง
5. ย้าย GitHub credential ออกจาก GAS Script Properties ไปเป็น Cloudflare Worker Secret และปิด/เลิกใช้ deployment GAS หลัง migration ได้ผ่านการทดสอบแล้วใน Zone 6 เท่านั้น
6. จัดทำ tests สำหรับ control API/auth/idempotency/status/report และ integration/E2E boundary เพิ่มเติมตาม Zone ที่เกี่ยวข้อง

ไม่ควรเปลี่ยน provider metadata, downloader, Telegram API หรือรูปแบบ dedupe ของ processing worker ใน Zone 0/การย้าย control plane เว้นแต่พบหลักฐานว่าจำเป็นและได้รับการตัดสินใจตามแผน

### 10. Secret อยู่ที่ไหน

จาก source และเอกสารที่ตรวจ (ไม่สามารถอ่านค่า secret จริงจาก repository):

- `GITHUB_TOKEN` สำหรับ GAS → GitHub API: ระบุให้เก็บใน GAS Script Properties (`gas/README.md`, `gas/SETUP_VALUES.md`)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, optional `ALERT_WEBHOOK_URL`: ใช้จาก GitHub Actions Secrets ใน workflow
- Telegram chat ID ถูกกำหนดใน workflow/config ไม่ใช่ secret
- frontend ไม่มีค่า GitHub PAT หรือ Telegram bot token เป็น literal ที่พบจากการตรวจ source; URL ของ GAS เป็น endpoint identifier ไม่ใช่ credential
- `GITHUB_TOKEN` ของ Actions ถูกใช้เพื่อ checkout/commit `state/dedupe.json` ตาม workflow permissions `contents: write`

ข้อสังเกต: audit นี้ยืนยันเพียงตำแหน่งที่ code/config ระบุ ไม่ได้ตรวจค่า secret ใน GitHub/GAS account และไม่ได้ตรวจการตั้งค่า Cloudflare/GitHub Pages production

### 11. Security boundary อยู่ตรงไหน

**ปัจจุบัน:** browser → GAS Web App ที่เอกสารตั้งเป็น `Anyone` → GitHub API ด้วย server-side PAT → Actions runner/Actions secrets → Telegram API. ไม่มี authentication/authorization check ใน `Code.gs`; Apps Script public endpoint เป็น boundary ที่เปิดรับก่อนถึง GitHub credential

**เป้าหมายตาม Master Plan:** Dashboard → Cloudflare Access → control Worker (GitHub credential เป็น Worker Secret) → GitHub Actions → Telegram; browser ไม่ถือ GitHub/Telegram secret

### 12. Test ใดครอบคลุมแต่ละ boundary

| Boundary / module | Tests ที่พบ | ข้อจำกัด |
|---|---|---|
| URL parsing/normalization | `tests/test_urls.py` | ครอบคลุม URL และ batch parsing ไม่ได้ทดสอบ browser กับ backend ร่วมกัน |
| Python worker / Telegram send path | `tests/test_worker.py` | ใช้ fake metadata/Telegram; ไม่มีการส่งจริง |
| Dedupe | `tests/test_dedupe.py` | ทดสอบ local state/processor แบบ unit; ไม่มี dispatch ซ้ำจริงพร้อมกันข้าม workflow |
| Metadata fallback | `tests/test_metadata.py` | mock provider; ไม่เรียก X จริง |
| Downloader/security | `tests/test_security_and_telegram.py` | unit/mock; ไม่ได้จำลอง redirect/SSRF integration เต็มรูปแบบ |
| Report sanitization | `tests/test_dashboard_report.py` | ทดสอบ allow-list/error redaction; ไม่มีการอ่าน artifact ผ่าน GAS integration |
| Logging/notifications | `tests/test_observability.py` | unit/mock |
| GAS endpoints/lock/cache/GitHub calls | ไม่พบ automated GAS tests | ไม่มี test framework หรือ mock boundary สำหรับ Apps Script ใน repository |
| Dashboard ↔ GAS ↔ GitHub Actions ↔ Telegram | ไม่พบ automated E2E/integration suite | เอกสารมีหลักฐาน workflow run เก่า แต่ไม่ใช่ regression test ที่รันในชุดนี้ |

`python3 -m pytest -q` ผ่าน: **34 passed** (รันทดสอบเดิมใน sandbox; ติดตั้ง pytest ใน user environment ของ sandbox เท่านั้น ไม่แก้ repository) ไม่มี test ที่ส่ง Telegram หรือเรียก workflow จริงในการตรวจรอบนี้

## Findings / security notes

### High — public control endpoint ไม่มี authentication ใน code

คู่มือ GAS ระบุ `Who has access: Anyone`; handler รับ start/status/report โดยไม่ตรวจ identity/token ภายในสคริปต์ และ `start` dispatch workflow ด้วย PAT ฝั่ง server การเข้าถึง endpoint ได้จึงอาจเปิดทางให้บุคคลภายนอกสั่ง workflow หรืออ่านข้อมูลที่ endpoint คืนได้ ทั้งนี้ยังไม่ได้ตรวจ deployment จริงจาก Google account ใน Zone 0

### High — start payload อยู่ใน GET query string

URL ที่ส่งและ identifiers ถูก serialize ลง query parameter `payload` ของ `GET action=start` แม้จะ encode เป็น base64url ก็ไม่ใช่ encryption และ query string อาจถูกบันทึกใน browser history, proxy/server logs หรือระบบ analytics ควรเลิกส่งข้อมูลเริ่มงานผ่าน URL และใช้ request body บน endpoint ที่รองรับ CORS/Access ตาม contract ใหม่

### Medium — idempotency ไม่รับประกัน duplicate intent

GAS CacheService เก็บ key 6 ชั่วโมง แต่ Dashboard สร้าง UUID ใหม่ในทุกการกด start และใช้ UUID เดียวเป็น idempotency key การกดซ้ำจึงกลายเป็น key ใหม่; lock ป้องกันการเข้า critical section พร้อมกัน แต่ไม่ได้ dedupe คำขอที่มี key คนละค่า ส่วน state dedupe ของ worker ป้องกัน post ที่เคยส่งสำเร็จ ไม่ได้ทดแทน request-level idempotency ที่ control plane

### Medium — least privilege ของ workflow ยังควรทบทวน

Workflow กำหนดระดับ workflow เป็น `permissions: contents: write` เพื่อ persist dedupe state กลับ repository แต่ไม่ได้แยก scope ลงระดับ job/step และยังเป็นสิทธิ์กว้างกว่า read-only งานอื่นใน workflow ควรตรวจว่าต้องใช้ `contents: write` เฉพาะขั้น persist หรือไม่ใน security zone โดยรักษาพฤติกรรม dedupe

### Medium — contract ปัจจุบันไม่ตรงกับ contract เป้าหมาย

แผนระบุ `{url, large_file_mode, request_id}`, `job_id`, `GET /jobs/<job_id>` และ status schema ใหม่ แต่ระบบรับ `urls`, สร้าง/ใช้ `request_id`, ใช้ action query ของ GAS และ GitHub run ID แทน `job_id` ต้องล็อก mapping/compatibility ก่อนแก้ interface

### Low — Dashboard state หลัง refresh / failure report

ไม่พบการ restore งานที่กำลังทำหรือ recent jobs หลัง refresh; และ report รายโพสต์ถูกขอเฉพาะ conclusion `success` จึงแสดงรายละเอียด per-post failure ได้น้อยเมื่อ workflow จบด้วย failure ทั้งสองประเด็นควรตรวจใน Zone Dashboard โดยไม่ขยาย architecture เกินแผน

ไม่พบหลักฐาน secret literal ใน frontend จาก source ที่ตรวจ อย่างไรก็ตามไม่สามารถยืนยัน secret store จริงหรือค่าที่ deploy อยู่ได้จาก repository อย่างเดียว

## ข้อสรุป Zone 0

การเปลี่ยนที่เล็กที่สุดเพื่อเอา GAS ออกคือ **แทนที่ GAS control plane ด้วย Cloudflare Worker/Access และปรับ Dashboard/workflow input contract เฉพาะจุด** โดยคง Python worker, metadata/download, Telegram, report format/sanitizer และ dedupe ไว้ให้มากที่สุด

**สถานะ Zone 0: PASS** — ตรวจ repository และทดสอบชุดเดิมครบ; สร้างเอกสาร audit แล้ว ไม่มี runtime code เปลี่ยนแปลง ไม่มีไฟล์ถูกลบ และไม่มี deployment

## สิ่งที่ยังไม่ตรวจใน Zone 0

- สถานะจริงของ Apps Script deployment/Script Properties และผู้ที่เข้าถึงได้
- GitHub repository settings, effective token permissions, Actions secrets, branch protection และ Pages configuration
- Cloudflare account/zone/Access policy (ระบบใหม่ยังไม่ถูก deploy)
- live end-to-end dispatch หรือ Telegram delivery ในรอบตรวจนี้

## Next step

หยุดตามกฎ Zone 0 และรอคำสั่งก่อนเริ่ม **Zone 1 — Control Plane Contract**
