# X2Telegram — Agent Operating Guide

เอกสารนี้เป็น **จุดเริ่มต้นบังคับสำหรับ agent ทุกตัว** ที่เข้ามาพัฒนา repository นี้

## 1. อ่านก่อนเริ่มงาน

อ่านตามลำดับนี้ก่อนแก้โค้ดหรือ deploy:

1. `AGENTS.md` ไฟล์นี้
2. [`docs/AGENT_HANDOFF.md`](docs/AGENT_HANDOFF.md) — สถานะจริงและ backlog ปัจจุบัน
3. [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) — ภาพรวม production
4. [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — วิธีทดสอบและ deploy
5. [`docs/CONTROL_PLANE_CONTRACT.md`](docs/CONTROL_PLANE_CONTRACT.md) — API contract
6. อ่านเอกสารเฉพาะส่วนที่เกี่ยวข้องกับงานที่จะทำ
7. สำหรับงานตามแผน 5 อันดับ ให้อ่าน `docs/MANUS_EXECUTION_PLAN.md` และเอกสารเฉพาะอันดับใน `docs/plan/` ตามลำดับก่อนเริ่ม implementation:
   - `docs/plan/P1_X_SOURCE_DOWNLOAD_RELIABILITY.md`
   - `docs/plan/P2_MEDIA_COMPLETENESS_AND_FILE_IDENTITY.md`
   - `docs/plan/P3_RETRY_AND_JOB_RECOVERY.md`
   - `docs/plan/P4_LARGE_FILE_TELEGRAM_AND_DROPBOX.md`
   - `docs/plan/P5_MOBILE_DASHBOARD_UX.md`

ห้ามสรุปว่าเอกสารแผนมีไม่ครบก่อนตรวจไฟล์ทั้งห้าตาม path เหล่านี้ และห้ามหยุดเพียงแค่ส่ง checklist กลับมา: ต้องเริ่มแก้ปัญหาตามลำดับที่แผนกำหนด หากติด blocker ภายนอก ให้ระบุหลักฐานและทำงานส่วนที่ไม่ติด blocker ต่อ

ห้ามยึดเอกสาร migration/audit รุ่นเก่าเป็นสถานะ runtime โดยไม่ตรวจ `PROJECT_STATUS.md` และ `AGENT_HANDOFF.md` ก่อน

## 2. สถานะปัจจุบันที่เชื่อถือได้

- Branch หลัก: `main`
- Production Worker: `x2telegram-control-plane`
- Production URL: `https://x2telegram-control-plane.pantipa3826.workers.dev`
- Current Worker version: `649353cf-fd9a-498b-9415-14bae01de486`
- P2 merge commit included in `main`: `a5711e1` (media identity/manifest; PR #23)
- P3 merge commit included in `main`: `9e9e9f8` (safe retry/job recovery; PR #24)
- Latest application code commit on main: `4bd1abf` (metadata diagnostics/media quality; later commits only persist delivery state)
- Production Worker deployment commit: `f5372e5` (Access secondary-email support; PR #25)
- Deploy workflow: `.github/workflows/deploy-worker.yml`
- Deploy ล่าสุด: GitHub Actions run [#38295769200](https://github.com/aodxx/X2Telegram/actions/runs/38295769200) — success; Wrangler dry-run and deploy passed
- Dashboard Pages: run [#38968970271](https://github.com/aodxx/X2Telegram/actions/runs/38968970271) — success on application commit `4bd1abf`
- Main CI: run [#38968970038](https://github.com/aodxx/X2Telegram/actions/runs/38968970038) — success; Python **156** and Worker/Dashboard **45** tests
- Python tests: **156 passed**; Worker tests: **45 passed**
- Edge rate limit: `JOB_DISPATCH_RATE_LIMITER`, 20 requests/60 seconds ต่อ Access identity
- Cloudflare Access อนุญาตอีเมลที่ระบุแบบ exact สองรายการ (primary + optional secondary); Worker secret หลักยังคงอยู่ และไม่มี `Everyone`/domain-wide rule
- Production ถูกป้องกันด้วย Cloudflare Access; smoke check แบบไม่ส่ง credentials พบ unauthenticated `GET /` ตอบ HTTP 302 (Access redirect) เมื่อ 2026-10-13

ถ้าสถานะข้างต้นไม่ตรงกับ GitHub/production ให้ตรวจระบบจริงก่อนแก้เอกสารหรือสรุปผล

## 3. Architecture ที่ห้ามทำให้ถอยหลัง

```text
GitHub Pages entry
  → Cloudflare Access
  → Cloudflare Worker (Dashboard + control API)
  → GitHub Actions execution workflow
  → Python media processor
  → Telegram / MEGA / Dropbox / private Browser ZIP
```

- Worker เป็น control plane ไม่ใช่ media-processing backend
- Python ดาวน์โหลด/validate media หนึ่งครั้งต่อ media item แล้วส่งไปยังปลายทางที่เลือก
- `state/dedupe.json` เป็น state ที่ติดตามใน repository; ต้องรักษา dedupe และ concurrency contract
- ห้ามนำ credential ของ Telegram, GitHub, Cloudflare, MEGA หรือ Dropbox ไปไว้ใน frontend, workflow input, source หรือ log
- ห้ามเพิ่ม database/Redis/queue/Google Drive ใน production path โดยไม่เปลี่ยน architecture decision อย่างชัดเจน

## 4. กติกาการพัฒนา

- ตรวจ `git status` ก่อนเริ่มและก่อนจบ
- เปลี่ยนแปลงให้เล็กและแยก commit ตามเรื่อง
- แก้โค้ดต้องเพิ่ม/ปรับ regression test ที่เกี่ยวข้อง
- ถ้าเปลี่ยน behavior, API, workflow, secret, limit หรือ deployment ต้องอัปเดตเอกสารที่เกี่ยวข้องใน commit เดียวกัน
- ห้ามแสดงหรือคัดลอกค่า secret จริงใน chat, terminal output, report หรือ commit
- ห้ามส่งงาน Telegram/MEGA/Dropbox จริงเพื่อทดสอบโดยไม่มีปลายทางและ fixture ที่ผู้ใช้อนุญาตชัดเจน
- ห้าม force-push `main`; หาก remote มี commit ใหม่ให้ `git fetch origin main` แล้ว `git rebase origin/main`
- อย่าใช้ Wrangler login ใน sandbox เป็นวิธีมาตรฐานสำหรับ production deploy

## 5. Validation ขั้นต่ำก่อน commit

```bash
python3 -m pytest -q
npm test --prefix control-worker
python3 -m compileall -q src tests
node --check control-worker/src/index.js
python3 - <<'PY'
import yaml
from pathlib import Path
for path in Path('.github/workflows').glob('*.yml'):
    yaml.safe_load(path.read_text())
    print('YAML_OK', path)
PY
git diff --check
```

ถ้าแก้เฉพาะเอกสาร อย่างน้อยต้องตรวจ internal links, YAML ถ้าแตะ workflow และ `git diff --check`

## 6. Production deploy protocol

Production deploy ใช้ GitHub Actions เท่านั้น:

1. รัน validation ในข้อ 5
2. commit และ push ไป `main`
3. เรียก workflow แบบ manual:
   ```bash
   gh workflow run deploy-worker.yml --repo aodxx/X2Telegram --ref main
   ```
4. รอ run ให้จบและตรวจว่า `Test Worker`, `Validate Wrangler configuration` และ `Deploy Worker` ผ่านทั้งหมด
5. ตรวจ run head SHA ตรงกับ commit ที่ต้องการ deploy
6. บันทึก run URL และ Worker version ใน `docs/PROJECT_STATUS.md`, `docs/E2E_TEST_REPORT.md` หรือเอกสารที่เกี่ยวข้องเมื่อมีการเปลี่ยนแปลงจริง
7. ตรวจ production endpoint โดยไม่พิมพ์ Access redirect URL/query ลง log

Workflow จะใช้ GitHub Environment `production` secrets `CLOUDFLARE_API_TOKEN` และ `CLOUDFLARE_ACCOUNT_ID`; agent ไม่ควรขอให้ผู้ใช้ส่งค่า secret ในข้อความ

**ห้าม deploy** หาก tests ไม่ผ่าน, dry-run ไม่ผ่าน, head SHA ไม่ตรง หรือพบการเปลี่ยนแปลงที่ไม่เกี่ยวข้องใน working tree

## 7. Completion report ที่ agent ต้องส่ง

ทุกงานต้องสรุป:

- ทำอะไรและไฟล์ใดเปลี่ยน
- tests/validation ที่รันและผล
- deploy หรือไม่; ถ้า deploy ให้ระบุ workflow run และ version
- known limitations หรือรายการที่ยัง blocked
- งานถัดไปที่แนะนำตาม `docs/AGENT_HANDOFF.md`
