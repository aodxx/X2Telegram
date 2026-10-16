# X2Telegram Production Security Audit — Zone 8

**วันที่:** 2026-10-12
**ขอบเขต:** `Dashboard → Cloudflare Access/Worker → GitHub Actions → X metadata/downloader → Telegram` ตาม Master Plan Zone 8
**สถานะ:** อัปเดตหลัง production deployment และตรวจ workflow/deployment evidence แล้ว; ยังไม่ใช่การรับรอง exactly-once หรือ full live E2E ทุก scenario

## Executive summary

**พร้อมใช้งาน production ตามขอบเขตที่ทดสอบแล้ว.** ไม่พบ P0 จากการตรวจครั้งนี้. Worker deploy ผ่าน GitHub Actions run `38171587335` พร้อม rate-limit binding; ยังมี residual risk ด้าน exactly-once, Cloudflare locality/ eventual consistency และ live scenarios ที่ยังไม่ได้ทำ. P1 เรื่อง Telegram bot token อาจหลุดผ่าน exception/error report ได้รับการแก้ไขด้วย generic Telegram errors และ final-boundary redaction พร้อม regression tests.

ระหว่าง security audit ไม่มีการ dispatch GitHub workflow หรือส่ง Telegram. **ภายหลัง audit** ได้ทำ owner-approved normal-path E2E หนึ่งครั้ง (run `37807253687`), เรียก X/Telegram จริงและส่งหนึ่ง MP4; รายละเอียดอยู่ใน [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md).

## Findings

| Severity | Finding | สถานะ / หลักฐาน |
|---|---|---|
| **P1 (แก้แล้ว)** | Telegram API `requests` exception/response อาจมี URL `/bot<TOKEN>/...` และถูก serialize ลง raw report หรือ Actions artifact | `src/telegram_api.py` ไม่แนบ raw exception/response description อีกต่อไป; `src/logging_utils.py` redact bot token/secret-like keys; `src/cli.py` redact ก่อน stdout และ raw report file. Regression tests ใส่ fake token แล้วตรวจ stdout/file/error ว่าไม่มีค่า secret. |
| **P2 (แก้แล้ว)** | Downloader ตาม HTTP redirect อัตโนมัติหลังตรวจเฉพาะ URL แรก | `src/downloader.py` ปิด auto-redirect, จำกัด 5 hops และตรวจ HTTPS/allowlisted host ทุก hop; `src/security.py` ปฏิเสธ credentials และ non-standard port. Mock tests ครอบ redirect ไป host ไม่อนุญาตและ redirect ระหว่าง X media hosts. ยังไม่ได้ทำ live attack simulation. |
| **P2 (แก้แล้ว; มี residual risk)** | การ retry หลัง media ก่อนหน้าส่งสำเร็จอาจส่งชิ้นเดิมซ้ำ และ signed URL อาจเปลี่ยน | `src/dedupe.py` state v2 บันทึก SHA-256 fingerprint ของ file content/message ID แยกราย media; `src/processor.py` ข้าม media ที่สำเร็จแล้ว, ส่ง media ใหม่ และ retry ชิ้นที่ยังไม่สำเร็จ. อ่าน state v1 ได้และคง completed post เดิมเป็น duplicate. Tests ครอบ first/middle/last failure, partial retry, URL เปลี่ยนแต่ bytes เดิม และ media ที่เพิ่มใหม่. **ยังรับประกัน exactly-once ไม่ได้** หาก Telegram รับ media แล้ว response หายก่อน checkpoint ถูกบันทึก หรือ checkpoint write ล้มเหลวหลังส่ง. |
| **P2 (แก้แล้ว)** | Worker อ่าน body ทั้งก้อนก่อนตรวจขนาดเมื่อไม่มี/ปลอม `Content-Length` | `control-worker/src/index.js` อ่าน stream พร้อม hard cap 64 KiB, ยกเลิกเมื่อเกิน และคืน `413`; tests ครอบ declared และ streamed oversized body โดยยืนยันว่าไม่ dispatch. |
| **P2 (ลดความเสี่ยงแล้ว; residual)** | Rate limit ไม่ใช่ global exact counter ข้ามทุก Cloudflare location | เพิ่ม Workers Rate Limiting binding 20 ครั้ง/60 วินาทีต่อ Access identity และ fallback local Map สำหรับ dev/test; binding error fail-closed. Cloudflare ระบุว่า binding counter แยกตาม location และ eventually consistent. หากต้องการ hard global block ต้องตั้ง WAF Rate Limiting Rule เพิ่มและยืนยันด้วย cross-location test หลัง deploy. |
| **P2 (บางส่วนแก้แล้ว)** | Supply-chain refs และ package artifact อาจเปลี่ยนได้ | GitHub Actions ทุก workflow ถูก pin ด้วย commit SHA, Local Bot API image ถูก pin ด้วย digest และ MEGAcmd ถูกตรวจ SHA-256 ก่อนติดตั้ง. Dependabot config เพิ่มสำหรับ pip/npm/GitHub Actions. ยังต้องทบทวน checksum เมื่อ MEGAcmd upstream ออกรุ่นใหม่. |
| **P2 (จำกัดหลักฐาน)** | Fine-grained token permission และ repository access จริงยังตรวจจาก dashboard ไม่ได้ครบ | E2E พิสูจน์ว่า dispatch ไป repository นี้สำเร็จ แต่ GitHub integration อ่านรายชื่อ Actions secrets/settings ไม่ได้ (`403`); exact token scope/expiry และ repo restriction ยังยืนยันจาก dashboard ไม่ครบ. |
| **P3 (แก้เอกสารใน branch)** | `docs/ARCHITECTURE.md` เคยระบุว่า Worker/Access ยังไม่ deploy ทั้งที่ตั้งค่าแล้ว | อัปเดตใน branch ให้แยก deployment จริง, GitHub Pages `main`/PR ที่ยังไม่ merge, และ E2E ที่ยังไม่เกิด. `docs/MIGRATION_AUDIT.md` เป็นบันทึก Zone 0 ตามเวลาตรวจเดิม จึงเก็บสถานะ historical ไว้. |

## Boundary checks ที่มีหลักฐาน

- Frontend ใช้ Worker API URL เท่านั้น; ไม่พบ GitHub/Telegram credential literal ในหน้า Dashboard/config.
- Cloudflare Access บังคับ owner email OTP. Production ตรวจจริงหลัง deploy แล้วว่าไม่มี session จะได้ `302` ไป Access login; Worker route `/health` จะตอบ `200` เมื่อ request ผ่าน edge Access.
- Authenticated `GET /jobs/<random-id>` ตอบ expected `404 job_not_found` จาก GitHub-backed lookup จึงยืนยัน Access JWT และ GitHub Actions read path โดยไม่สร้าง run.
- Worker ตรวจ RS256/JWKS, issuer, audience, expiry, owner email, exact Dashboard origin, X URL schema และ request size. Dashboard CORS ไม่ใช้ wildcard. หลัง deploy hardening ทดสอบจาก GitHub Pages origin: `GET /health` ได้ `200`, invalid URL ได้ `400 invalid_url`, และ body 17 KiB ได้ `413 request_too_large`; ทั้งสอง POST ถูก reject ก่อน GitHub API/dispatch.
- Telegram bot credential คงอยู่ใน GitHub Actions secret; Worker ไม่รับ Telegram token. ปลายทางถูกล็อกไว้ที่ group ID ใน repository/workflow.
- Local/CI tests ล่าสุด: **Python 95 passed; Worker 27 passed**. Worker unit tests ใช้ mocked GitHub/JWKS; Python tests ใช้ mock/fake. Deploy workflow run `38171587335` ผ่าน test 27/27 และ Wrangler dry-run/deploy.

## สิ่งที่ยังไม่ทดสอบ

- Live duplicate/no-resend, multi-photo/multiple distinct media, partial-failure recovery, large-file mode, Dashboard UI reload/mobile.
- Telegram failure/accepted-but-timeout, live redirect chain, Cloudflare burst/cross-isolate limit.
- Branch protection, repository visibility, fine-grained token permission matrix และ container/action provenance ใน GitHub settings.

## Production status
1. Worker production deploy ผ่าน GitHub Actions run `38171587335`; current version `c44298fb-47f9-4798-a3db-9cd6946018fb`.
2. Edge rate-limit binding `JOB_DISPATCH_RATE_LIMITER` active ที่ 20 requests/60 seconds ต่อ Access identity และ binding error fail-closed.
3. E2E normal-path และ destination evidence อยู่ใน `docs/E2E_TEST_REPORT.md`; scenarios ที่ยังไม่ live-tested ให้ถือเป็นข้อจำกัดตามรายการนั้น.
4. Dashboard/Worker ถูกป้องกันด้วย owner-only Cloudflare Access.

**ข้อสรุป:** source security regression, CI hardening, privacy-minimized state และ production deployment ผ่าน validation แล้ว; ระบบพร้อมใช้งานตามขอบเขตที่ทดสอบ แต่ยังไม่อ้าง exactly-once หรือ full live E2E ทุกปลายทาง/อุปกรณ์.


## Follow-up — 2026-10-10

บน `main` แยก permission ใน `.github/workflows/x2telegram.yml` แล้ว: `send-media` ใช้ `contents: read` และปิด `actions/checkout` credential persistence; job `persist-state` แยกออกมา รับ state artifact แล้วจึงมี `contents: write` เพื่อ commit `state/dedupe.json`. เพิ่ม `.github/workflows/deploy-worker.yml` สำหรับ manual production deploy โดยใช้ GitHub Environment `production`, secrets `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID`, tests และ Wrangler dry-run ก่อน deploy. ผล validation ล่าสุด: Python **95 passed**, Worker **27 passed**, YAML parse และ `git diff --check` ผ่าน.

Least-privilege workflow, immutable action/container/package checks, Dependabot, privacy-minimized dedupe state และ edge rate-limit binding ถูก merge/deploy หรือยืนยันด้วย CI แล้ว. ยังเหลือ Dropbox refresh/large-file live test, Telegram Local Bot API large-file live test และ mobile browser test ตาม E2E report.
