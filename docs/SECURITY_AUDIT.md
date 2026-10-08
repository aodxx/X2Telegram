# X2Telegram Production Security Audit — Zone 8

**วันที่:** 2026-10-08  
**ขอบเขต:** `Dashboard → Cloudflare Access/Worker → GitHub Actions → X metadata/downloader → Telegram` ตาม Master Plan Zone 8  
**สถานะ:** ตรวจ source/docs และ local/mock tests; ยังไม่ใช่การรับรอง production

## Executive summary

**ยังไม่พร้อม production.** ไม่พบ P0 จากการตรวจครั้งนี้ แต่มี P1 ที่ยังเปิดอยู่คือ `GH_TOKEN` ค่าเดิมถูกเปิดเผยในแชตและ terminal warning ระหว่างตั้งค่า; เจ้าของยังไม่อนุมัติ revoke/rotate. Normal-path E2E ที่เจ้าของอนุมัติทำภายหลังสำเร็จหนึ่ง run โดยใช้ secret เดิม; การทดสอบสำเร็จไม่ได้ลบความเสี่ยงจากการเปิดเผย credential. P1 เรื่อง Telegram bot token อาจหลุดผ่าน exception/error report ได้รับการแก้ไขด้วย generic Telegram errors และ final-boundary redaction พร้อม regression tests.

ระหว่าง security audit ไม่มีการ dispatch GitHub workflow หรือส่ง Telegram. **ภายหลัง audit** ได้ทำ owner-approved normal-path E2E หนึ่งครั้ง (run `37807253687`), เรียก X/Telegram จริงและส่งหนึ่ง MP4; รายละเอียดอยู่ใน [`E2E_TEST_REPORT.md`](E2E_TEST_REPORT.md).

## Findings

| Severity | Finding | สถานะ / หลักฐาน |
|---|---|---|
| **P1** | GitHub fine-grained token ที่ใช้เป็น `GH_TOKEN` ถูกเปิดเผยในแชตและ Wrangler warning | **เปิดอยู่ — ต้อง revoke/rotate ก่อน production; เจ้าของยังไม่อนุมัติ.** Cloudflare เก็บค่าใน Worker `secret_text` แล้ว แต่การเก็บเป็น secret ไม่ยกเลิกการเปิดเผยเดิม. E2E run #37807253687 พิสูจน์ว่า credential ปัจจุบัน dispatch workflow ได้; exact permission scope ยังตรวจจาก GitHub settings ไม่ครบ. |
| **P1 (แก้แล้ว)** | Telegram API `requests` exception/response อาจมี URL `/bot<TOKEN>/...` และถูก serialize ลง raw report หรือ Actions artifact | `src/telegram_api.py` ไม่แนบ raw exception/response description อีกต่อไป; `src/logging_utils.py` redact bot token/secret-like keys; `src/cli.py` redact ก่อน stdout และ raw report file. Regression tests ใส่ fake token แล้วตรวจ stdout/file/error ว่าไม่มีค่า secret. |
| **P2 (แก้แล้ว)** | Downloader ตาม HTTP redirect อัตโนมัติหลังตรวจเฉพาะ URL แรก | `src/downloader.py` ปิด auto-redirect, จำกัด 5 hops และตรวจ HTTPS/allowlisted host ทุก hop; `src/security.py` ปฏิเสธ credentials และ non-standard port. Mock tests ครอบ redirect ไป host ไม่อนุญาตและ redirect ระหว่าง X media hosts. ยังไม่ได้ทำ live attack simulation. |
| **P2 (แก้แล้ว; มี residual risk)** | การ retry หลัง media ก่อนหน้าส่งสำเร็จอาจส่งชิ้นเดิมซ้ำ และ signed URL อาจเปลี่ยน | `src/dedupe.py` state v2 บันทึก SHA-256 fingerprint ของ file content/message ID แยกราย media; `src/processor.py` ข้าม media ที่สำเร็จแล้ว, ส่ง media ใหม่ และ retry ชิ้นที่ยังไม่สำเร็จ. อ่าน state v1 ได้และคง completed post เดิมเป็น duplicate. Tests ครอบ first/middle/last failure, partial retry, URL เปลี่ยนแต่ bytes เดิม และ media ที่เพิ่มใหม่. **ยังรับประกัน exactly-once ไม่ได้** หาก Telegram รับ media แล้ว response หายก่อน checkpoint ถูกบันทึก หรือ checkpoint write ล้มเหลวหลังส่ง. |
| **P2 (แก้แล้ว)** | Worker อ่าน body ทั้งก้อนก่อนตรวจขนาดเมื่อไม่มี/ปลอม `Content-Length` | `control-worker/src/index.js` อ่าน stream พร้อม hard cap 16 KiB, ยกเลิกเมื่อเกิน และคืน `413`; tests ครอบ declared และ streamed oversized body โดยยืนยันว่าไม่ dispatch. |
| **P2 (คงอยู่)** | Rate limit เป็น Map ใน memory ต่อ Worker isolate ไม่ใช่ global/edge limit | Local test ยืนยัน request ที่ 21 ใน 1 นาทีได้ `429`; isolate restart/หลาย isolate อาจทำให้ limit ไม่รวมกัน. Access จำกัด owner คนเดียว แต่ยังควรตั้ง/ยืนยัน Cloudflare edge protection ที่เหมาะกับ workers.dev ก่อนเปิด production. |
| **P2 (คงอยู่)** | GitHub Actions `contents: write` มีผลตลอด job และ action/container references ยังเป็น mutable tags | `.github/workflows/x2telegram.yml` ต้อง write เพื่อ persist `state/dedupe.json`; dependency/test/send steps อยู่ใน job เดียวกัน. ควรพิจารณาแยกสิทธิ์ state-writer, ปิด checkout credential persistence ในขั้นที่ไม่ต้องใช้ และ pin Actions/container ด้วย immutable SHA/digest. ไม่ได้แก้เพราะเปลี่ยน workflow trust boundary และต้องทดสอบเพิ่ม. |
| **P2 (จำกัดหลักฐาน)** | Fine-grained token permission และ repository access จริงยังตรวจจาก dashboard ไม่ได้ครบ | E2E พิสูจน์ว่า dispatch ไป repository นี้สำเร็จ แต่ GitHub integration อ่านรายชื่อ Actions secrets/settings ไม่ได้ (`403`); exact token scope/expiry และ repo restriction ยังยืนยันจาก dashboard ไม่ครบ. |
| **P3 (แก้เอกสารใน branch)** | `docs/ARCHITECTURE.md` เคยระบุว่า Worker/Access ยังไม่ deploy ทั้งที่ตั้งค่าแล้ว | อัปเดตใน branch ให้แยก deployment จริง, GitHub Pages `main`/PR ที่ยังไม่ merge, และ E2E ที่ยังไม่เกิด. `docs/MIGRATION_AUDIT.md` เป็นบันทึก Zone 0 ตามเวลาตรวจเดิม จึงเก็บสถานะ historical ไว้. |

## Boundary checks ที่มีหลักฐาน

- Frontend ใช้ Worker API URL เท่านั้น; ไม่พบ GitHub/Telegram credential literal ในหน้า Dashboard/config.
- Cloudflare Access บังคับ owner email OTP; owner sign-in สำเร็จใน browser. `GET /health` ตอบ `200`.
- Authenticated `GET /jobs/<random-id>` ตอบ expected `404 job_not_found` จาก GitHub-backed lookup จึงยืนยัน Access JWT และ GitHub Actions read path โดยไม่สร้าง run.
- Worker ตรวจ RS256/JWKS, issuer, audience, expiry, owner email, exact Dashboard origin, X URL schema และ request size. Dashboard CORS ไม่ใช้ wildcard. หลัง deploy hardening ทดสอบจาก GitHub Pages origin: `GET /health` ได้ `200`, invalid URL ได้ `400 invalid_url`, และ body 17 KiB ได้ `413 request_too_large`; ทั้งสอง POST ถูก reject ก่อน GitHub API/dispatch.
- Telegram bot credential คงอยู่ใน GitHub Actions secret; Worker ไม่รับ Telegram token. ปลายทางถูกล็อกไว้ที่ group ID ใน repository/workflow.
- Local tests: **Python 47 passed; Worker 15 passed**. Worker unit tests ใช้ mocked GitHub/JWKS; Python tests ใช้ mock/fake. เพิ่มเติม: normal-path live E2E run #37807253687 สำเร็จหนึ่งครั้ง.

## สิ่งที่ยังไม่ทดสอบ

- Live duplicate/no-resend, multi-photo/multiple distinct media, partial-failure recovery, large-file mode, Dashboard UI reload/mobile.
- Telegram failure/accepted-but-timeout, live redirect chain, Cloudflare burst/cross-isolate limit.
- Branch protection, repository visibility, fine-grained token permission matrix และ container/action provenance ใน GitHub settings.

## Production gate

1. ก่อน production ให้ revoke token ที่เปิดเผยและตั้ง fine-grained `GH_TOKEN` ใหม่ผ่าน Cloudflare Secret Store โดยไม่ส่งค่าในแชต; เจ้าของยังไม่อนุมัติขั้นนี้.
2. E2E normal-path หนึ่ง URL ผ่านแล้ว; ทำ/บันทึก scenarios ที่เหลือตาม `docs/E2E_TEST_REPORT.md`.
3. จัดการ residual P2 หรือยอมรับความเสี่ยงอย่างชัดเจนก่อน merge/public Dashboard.
4. จึงพิจารณา Zone 6 (ลบ GAS), merge PR #2 และ production release.

**ข้อสรุป:** security regression ที่แก้ได้ใน source มี tests ผ่าน และ normal-path live E2E ผ่านหนึ่งครั้ง แต่ยังห้ามประกาศ production-ready เพราะ `GH_TOKEN` ที่เปิดเผยยังไม่ถูก rotate และ full E2E/release review ยังไม่ครบ.
