# X2Telegram — Agent Handoff และแผนพัฒนาต่อ

**อัปเดต:** 2026-10-13
**จุดอ้างอิง:** P2 merge commit `a5711e1` (included in `main`); Cloudflare Worker deployment commit `8fb4427`
**สถานะสั้น:** P1/P2 ใน Manus execution plan ผ่าน acceptance แล้ว; P2 merge และ main CI/MEGA integration ผ่าน. Worker deployment ยังเป็น `8fb4427` เพราะ P2 ไม่เปลี่ยน Worker; backlog ถัดไปคือ P3 ตาม plan และ live blockers ที่ปลอดภัย

**P2 complete (2026-10-13):** PR #23 merged as main commit `a5711e1`. It preserves distinct yt-dlp playlist entries and emits a per-media size/SHA-256 manifest/reconciliation. Main CI [#38288698022](https://github.com/aodxx/X2Telegram/actions/runs/38288698022) passed; main synthetic MEGA integration [#38288698061](https://github.com/aodxx/X2Telegram/actions/runs/38288698061) verified 3 remote objects, changed-version retention, duplicate idempotency, byte/hash integrity, and run-folder cleanup. Real source-only mixed photo/video exported 2/2 local files with matching hashes. No Worker deployment was needed because Worker code was unchanged. See [P2 evidence](plan/P2_MEDIA_COMPLETENESS_AND_FILE_IDENTITY.md).

**Execution Plan Priority 1:** source reliability release ผ่าน local/CI Python suite 129 tests, Worker suite 27 tests, Pages deploy และ production Worker rollout (version `e6bff44f-12e9-4a55-bfdb-c7b7cfb6587f`). ครอบคลุม root-cause fix, per-input reporting, transient metadata failure, retry budget และ provider redirect validation. Historical failing URL ผ่าน post-fix source-only fetch ที่ 29,799,397 bytes; ไม่มี destination send ใน probe นี้. Evidence matrix อยู่ใน [`plan/P1_X_SOURCE_DOWNLOAD_RELIABILITY.md`](plan/P1_X_SOURCE_DOWNLOAD_RELIABILITY.md).

## 1. สรุปสำหรับ agent ที่เพิ่งเข้ามา

ระบบปัจจุบันมี flow ดังนี้:

```text
Dashboard → Cloudflare Access → Cloudflare Worker
  → GitHub Actions execution workflow
  → Python processor
  → Telegram / MEGA / Dropbox / Browser ZIP
```

สิ่งที่ทำเสร็จแล้ว:

- ย้าย control plane จาก GAS มาเป็น Cloudflare Worker/Access ใน production path
- Dashboard และ API ใช้ Worker origin เดียวกัน
- รับ URL เดี่ยวหรือ batch สูงสุด 50 URLs
- เลือกปลายทาง `telegram`, `mega`, `dropbox`, `download`
- มี request idempotency และ dedupe state แบบ privacy-minimized
- มี partial success และ retry เฉพาะ target ที่ยังไม่สำเร็จ
- มี private Browser ZIP streaming ผ่าน Access
- มี edge rate limit 20 requests/60 seconds ต่อ Access identity และ fail-closed เมื่อ binding error
- แยก workflow permission: งานประมวลผลใช้ read, งาน persist state เท่านั้นที่ใช้ write
- GitHub Actions/container/package refs ถูก harden ตามที่ระบุใน security audit
- Production deploy ทำผ่าน `.github/workflows/deploy-worker.yml` โดยทดสอบก่อน deploy

## 2. Production snapshot

| รายการ | ค่าปัจจุบัน |
|---|---|
| Repository | `aodxx/X2Telegram` |
| Branch | `main` |
| P2 merge commit in main | `a5711e1` (media manifest/identity) |
| Worker | `x2telegram-control-plane` |
| Worker URL | `https://x2telegram-control-plane.pantipa3826.workers.dev` |
| Worker version | `e6bff44f-12e9-4a55-bfdb-c7b7cfb6587f` |
| Deploy commit | `8fb44274738d0c0090958f4b880189b0b93d17c7` |
| Deploy run | [#38263528272](https://github.com/aodxx/X2Telegram/actions/runs/38263528272) — success |
| Python tests | 134 passed (main CI [#38288698022](https://github.com/aodxx/X2Telegram/actions/runs/38288698022)) |
| Worker tests | 27 passed |
| Rate limit | `JOB_DISPATCH_RATE_LIMITER`: 20/60s per Access identity |
| Access | owner-only Cloudflare Access; unauthenticated `GET /` and `/health` return HTTP 302 (Access redirect) |

หลักฐานและรายละเอียดอยู่ใน:

- [`PROJECT_STATUS.md`](PROJECT_STATUS.md)
- [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md)
- [`SECURITY_AUDIT.md`](SECURITY_AUDIT.md)
- [`CLOUDFLARE_WORKER.md`](CLOUDFLARE_WORKER.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)

## 3. อะไรที่ยังไม่ควรทำซ้ำ

อย่าเริ่มงานใหม่ด้วยการ:

- สร้าง GAS control plane ใหม่
- ขอ Cloudflare OAuth หรือ login Wrangler ใน sandbox เพื่อ deploy production
- เพิ่ม database/Redis/queue เพื่อแก้ปัญหาเล็กน้อยใน execution flow
- เปลี่ยน Telegram chat ID หรือเปิด public endpoint เพื่อทดสอบโดยไม่จำเป็น
- rotate หรือเปลี่ยน secret เพียงเพราะเห็นเอกสาร historical; ให้ตรวจค่า configuration ปัจจุบันก่อน
- รัน live media test โดยไม่มีปลายทาง test chat/fixture และขอบเขตที่ชัดเจน
- แก้ `state/dedupe.json` แบบทิ้ง fingerprint/checkpoint เดิม

## 4. Backlog ตามลำดับความสำคัญ

> หมายเหตุสำหรับ Manus: รายการย่อยใน handoff นี้เป็น operational backlog โดยเฉพาะ live-validation blockers และอาจใช้การจัดกลุ่ม P1/P2/P3 คนละแบบกับแผนพัฒนา 5 อันดับใน `docs/MANUS_EXECUTION_PLAN.md`. สำหรับลำดับ implementation ให้ยึด P1→P5 ใน `MANUS_EXECUTION_PLAN.md`; ใช้รายการด้านล่างเพื่อเลือกงานตรวจ live ที่ปลอดภัยเมื่อถึงจุดที่เกี่ยวข้องหรือเมื่อมี blocker ที่ระบุหลักฐานแล้ว.

### P1 — ต้องทำต่อเมื่อมีสภาพแวดล้อมพร้อม

#### P1.1 Telegram Local Bot API สำหรับไฟล์เกิน 50 MB

**สถานะ:** โค้ดและ workflow รองรับแล้ว; automated tests ผ่าน; ยังไม่มี live evidence ที่ส่งไฟล์ใหญ่จริงผ่าน Local Bot API

**สิ่งที่ต้องเตรียม:**

- Telegram test chat ID ที่ bot ส่งได้
- synthetic file ขนาดมากกว่า 50 MB แต่ไม่เกิน 2,000 MB
- ยืนยันว่าจะส่งเข้า test chat เท่านั้น

**Acceptance criteria:**

- workflow เปิด `large_file_mode=true` และเลือก Telegram
- Local Bot API server ready ก่อน process
- ส่งไฟล์สำเร็จโดยไม่ใช้ standard Bot API
- report แสดง `telegram=success` และขนาดไฟล์ถูกต้อง
- ไม่ส่งซ้ำจาก retry
- บันทึก run URL โดยไม่บันทึก token หรือ chat credential

**ถ้ายังไม่มี test chat ID:** ให้ทำงานอื่นต่อ ห้ามเดาหรือใช้ production chat

#### P1.2 Dropbox refresh และ large-file session แบบ live

**สถานะ:** upload จริงหนึ่ง media ผ่านแล้วใน combined run; refresh-token-only และ large-file session มี automated coverage เท่านั้น

**Acceptance criteria:**

- ทดสอบด้วย Dropbox test folder
- ยืนยัน refresh token ใช้งานเมื่อ access token หมด/ไม่ส่งมา
- ยืนยัน upload session สำหรับไฟล์ใหญ่
- ตรวจ remote file และ bytes/size
- ลบหรือแยก test artifact ตาม policy ของบัญชี

### P2 — ความถูกต้องและ recovery

#### P2.1 Live partial-failure recovery

ทดสอบกรณี target หนึ่งล้มหลัง target อื่นสำเร็จ แล้ว retry ต้องส่งเฉพาะ target ที่ยังไม่สำเร็จ โดยไม่ส่ง Telegram/MEGA/Dropbox ซ้ำ

#### P2.2 Multi-photo และหลาย media item แบบ live

เสร็จแล้วบน main commit `a5711e1`: live source-only test ยืนยันโพสต์จริงแบบ 1 รูป + 1 วิดีโอ export ครบ 2/2 พร้อม manifest/hash; main CI และ isolated synthetic MEGA run [#38288698061](https://github.com/aodxx/X2Telegram/actions/runs/38288698061) ผ่านการตรวจ remote listing/download-back และ changed-content/dedupe semantics. ห้ามใช้ remote folder production ในการทดสอบใหม่.

#### P2.3 Dashboard reload/recovery

ยืนยันว่า refresh/reopen browser สามารถกู้ recent job จาก `localStorage`, ดึง status/report ต่อได้ และไม่ dispatch ซ้ำ

### P3 — ประสบการณ์ใช้งานและ assurance

- ทดสอบ browser มือถือจริง: login, submit, polling, ZIP download
- ทดสอบ source fetch ที่มี redirect chain/ข้อผิดพลาดจาก X เพิ่มเติมแบบไม่ส่งปลายทางจริงถ้าไม่จำเป็น
- ตรวจ branch protection/repository settings และ effective permission matrix จาก GitHub settings
- พิจารณา WAF Rate Limiting Rule หากต้องการ hard global limit ข้ามทุก Cloudflare location; binding ปัจจุบันเป็น eventually consistent/locality-aware ไม่ใช่ global exact counter
- เพิ่ม operational smoke check ที่ไม่สร้าง workflow เช่น Access-gated health/status probe ตามสิทธิ์ที่มี

## 5. กติกาเลือกงานถัดไป

1. ถ้ามี test chat ID และไฟล์ synthetic พร้อม → ทำ **P1.1 Telegram Local Bot API**
2. ถ้าไม่มี Telegram test chat แต่มี Dropbox sandbox credential → ทำ **P1.2 Dropbox**
3. ถ้าไม่มี credential/ปลายทางสำหรับ live test → ทำ **P2.2/P2.3 ด้วย mock หรือ browser-safe validation**
4. อย่าเลือกงานที่ต้องเปลี่ยน secret หรือ security boundary โดยไม่มีความจำเป็นและแผน rollback
5. เมื่อทำงานหนึ่งเสร็จ ให้อัปเดตเอกสารนี้, `PROJECT_STATUS.md` และ `E2E_TEST_REPORT.md` เฉพาะส่วนที่หลักฐานเปลี่ยนจริง

## 6. ขั้นตอนมาตรฐานของ agent

### เริ่มงาน

```bash
git status --short --branch
git log -3 --oneline
# อ่าน AGENTS.md และเอกสาร handoff นี้
```

### ก่อน commit

```bash
python3 -m pytest -q
npm test --prefix control-worker
python3 -m compileall -q src tests
node --check control-worker/src/index.js
git diff --check
```

ถ้าแตะ workflow ให้ parse YAML ทุกไฟล์ใน `.github/workflows/` ด้วย parser และตรวจ immutable refs ที่เกี่ยวข้อง

### Deploy เมื่อจำเป็นเท่านั้น

```bash
git push origin main
gh workflow run deploy-worker.yml --repo aodxx/X2Telegram --ref main
gh run watch <RUN_ID> --repo aodxx/X2Telegram --exit-status
```

หลัง deploy ต้องตรวจ:

- head SHA ของ run ตรงกับ commit ที่ต้องการ
- test, dry-run และ deploy ผ่าน
- Worker version/URL จาก log
- Access ยังป้องกัน endpoint ตามที่คาด

## 7. รูปแบบรายงานเมื่อจบงาน

ให้ agent รายงานสั้น ๆ ตามหัวข้อนี้:

```text
ทำแล้ว:
ไฟล์/commit:
Validation:
Deploy:
หลักฐาน live:
ข้อจำกัด/blocked:
งานถัดไป:
```

ห้ามรายงานว่า “พร้อม production” หากมีแค่ unit tests แต่ยังไม่มี live evidence ใน scenario ที่ผู้ใช้กำลังถามถึง และห้ามรายงานว่า deploy สำเร็จจนกว่าจะเห็น GitHub Actions run จบเป็น success จริง

## 8. เอกสารที่เป็น historical

`docs/MIGRATION_AUDIT.md` เป็น Zone 0 snapshot ก่อนย้าย control plane. ใช้เพื่อเข้าใจเหตุผลและประวัติการเปลี่ยนแปลงเท่านั้น ไม่ใช่ source of truth สำหรับ production ปัจจุบัน

Source of truth ตามลำดับ:

1. โค้ดและ workflow ที่อยู่บน `main`
2. GitHub Actions run ล่าสุดที่ตรวจสอบจริง
3. `docs/PROJECT_STATUS.md`
4. เอกสารเฉพาะระบบ
5. audit/plan historical
