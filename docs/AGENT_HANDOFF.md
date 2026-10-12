# X2Telegram — Agent Handoff และแผนพัฒนาต่อ

**อัปเดต:** 2026-10-12
**จุดอ้างอิง:** `main` / production deployment commit `6e673c4`
**สถานะสั้น:** Production ใช้งานได้ตามขอบเขตที่ทดสอบแล้ว; deployment ผ่าน GitHub Actions; งานถัดไปคือเก็บ live evidence ของ edge cases ที่ยังค้าง ไม่ใช่ย้าย architecture ใหม่

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
| Worker | `x2telegram-control-plane` |
| Worker URL | `https://x2telegram-control-plane.pantipa3826.workers.dev` |
| Worker version | `25c4517d-56fc-402b-bc62-c65a525d2618` |
| Deploy commit | `6e673c47842343dee9845ceb4d2a4489fced5d39` |
| Deploy run | [#38174506806](https://github.com/aodxx/X2Telegram/actions/runs/38174506806) — success |
| Python tests | 97 passed |
| Worker tests | 27 passed |
| Rate limit | `JOB_DISPATCH_RATE_LIMITER`: 20/60s per Access identity |
| Access | owner-only Cloudflare Access; unauthenticated `GET /` and `/health` return HTTP 403 |

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

ยืนยันว่าโพสต์ที่มีรูป/วิดีโอหลายรายการดาวน์โหลดครบ, report แยกราย media, และ dedupe fingerprint ไม่ทำให้ media คนละชิ้นหายไป

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
