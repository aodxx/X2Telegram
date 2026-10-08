# X2Telegram End-to-End Test Report — Zone 9

**วันที่:** 2026-10-08
**สถานะ:** **Normal-path E2E ผ่าน 1 รายการ; Zone 9 scenarios อื่นยังไม่ครบ**
**ปลายทาง:** Telegram group `-1003906817580` (ล็อกไว้ใน workflow)
**Credential:** ใช้ secrets ที่ตั้งอยู่แล้วตามคำยืนยันของเจ้าของ; `GH_TOKEN` ที่เคยเปิดเผยยังไม่ได้ rotate/revoke ตามคำสั่งก่อนหน้า จึงยังไม่พร้อม production.

## ผล normal-path E2E

- **URL:** `https://x.com/ninmopmn/status/2107508912392171879`
- **Worker request:** `request_id=e2e-20261008-231429-r2`, `job_id=job-72368aeb450a9df8c5b34f016d87e2a8`, HTTP `202`.
- **Workflow:** [run #37807253687](https://github.com/aodxx/X2Telegram/actions/runs/37807253687), branch `migration/zone-1-5-cloudflare-control-plane`, SHA `7327b70d2c7ec4c3c07ac29bc486636ceec50c46`, conclusion `success`.
- **Report ที่ Worker คืน:** `state=completed`; `sent=1`, `failed=0`, `skipped_duplicate=0`; result `status=sent`, file `ninmopmn_2107508912392171879_01.mp4`, Telegram `message_id=347`.
- Metadata มี video formats 2 รายการ; ระบบเลือก video variant สูงสุดหนึ่งรายการและส่งหนึ่งข้อความ/media ไปกลุ่มข้างต้น.
- GitHub Actions persist step สำเร็จ; ตรวจ remote branch ภายหลังพบ `state/dedupe.json` version 2 มี completed record ของ post นี้และ media checkpoint 1 รายการ.
- Dashboard-origin authenticated `GET /jobs/<job_id>` คืน HTTP `200` พร้อม sanitized report และ Telegram message ID.
- หลัง run เสร็จได้คืน Worker `GH_REF` จาก branch ชั่วคราวเป็น `main` แล้ว (Worker version `29a2c667-cce4-4da9-8bff-d93b89490e0f`). GitHub Pages `main` และ PR #2 ยังไม่เปลี่ยน/merge.

### การลองครั้งแรกและการแก้ไข

- Run #37806865130 ล้มเหลวก่อนเริ่มประมวลผล เพราะ Worker รุ่นก่อนส่ง workflow inputs `url` และ `urls` พร้อมกัน; workflow ปฏิเสธด้วย `Provide url or urls, not both`. ตรวจ steps/report แล้วไม่มี Telegram send ใน run นี้.
- แก้ Worker ให้ dispatch `url` เพียงฟิลด์เดียว พร้อม regression assertion; Worker tests ผ่าน 15/15 ก่อน deploy/retry. การลองครั้งที่สองข้างต้นสำเร็จ.

## Scenario results

| Scenario | ผล/หลักฐาน | สถานะ |
|---|---|---|
| 1. Normal Dashboard → Worker → Actions → X → Telegram → report/status | Run #37807253687 สำเร็จและส่งหนึ่ง MP4; status endpoint คืน report และ message ID 347 | **PASS (live, 1 URL)** |
| 2. Duplicate request | Worker idempotency mock tests และ Python dedupe v2 tests ผ่าน; ยังไม่ได้ dispatch duplicate run จริงหลัง state persist | **PASS (local/mock only)** |
| 3. Multiple media | URL จริงมี video variants 2 format แต่เป็นวิดีโอเดียวและส่งหนึ่งรายการ; multi-photo/multiple distinct media ยังไม่ทดสอบจริง | **PARTIAL** |
| 4. Partial failure | Local parametrized tests ครอบ first/middle/last media failure, partial retry และ URL เปลี่ยนแต่ bytes เดิม | **PASS (local/mock only)** |
| 5. Large file mode | ไม่ได้เริ่ม Local Bot API หรือส่งไฟล์ >50 MB | **NOT RUN** |
| 6. Invalid URL | Live cross-origin POST ได้ `400 invalid_url` ก่อน GitHub API; unit test ยืนยันไม่ dispatch | **PASS (live validation; no dispatch)** |
| 7. Unauthorized | Browser ที่ไม่มี Access session ถูก redirect/blocked; Worker mock tests ยืนยัน 401/403 โดยไม่มี dispatch | **PASS (Access gate + mock)** |
| 8. GitHub dispatch failure | Worker mock test คืน sanitized `502 github_dispatch_failed` | **PASS (local/mock only)** |
| 9. Telegram failure | Fake Telegram failure และ redaction tests ผ่าน; ไม่มีการทดสอบให้ Telegram API ล้มเหลวจริง | **PASS (local/mock only)** |
| 10. Browser refresh/recovery | Worker status endpoint ถูกเรียกหลัง run และคืน report; ยังไม่ได้ทดสอบ reload Dashboard UI ระหว่าง run จริง | **PARTIAL** |
| 11. Mobile browser | ยังไม่ได้ทดสอบบนอุปกรณ์/browser มือถือจริง | **NOT RUN** |

## Validation evidence

- Python: `python3 -m pytest -q` — **47 passed**.
- Control Worker: `npm test --prefix control-worker` — **15 passed** หลังแก้ single-URL dispatch contract.
- Python compile, JavaScript syntax, workflow YAML, Wrangler TOML, `git diff --check`, credential-literal scan และ Wrangler dry-run ผ่าน.
- Live safe checks ก่อน E2E: cross-origin `GET /health` ได้ `200`; invalid URL ได้ `400`; body 17 KiB ได้ `413`; ทั้งหมดไม่ dispatch.
- GitHub Actions แจ้ง non-blocking migration advisories สำหรับ Node 20 → 24 และ `ubuntu-latest` → Ubuntu 26; ไม่ทำให้ run ล้มเหลว.

## คงค้างก่อน production

1. เจ้าของยังไม่อนุมัติ rotate/revoke `GH_TOKEN`; token ที่เคยเปิดเผยจึงยังเป็น **P1 blocker**. E2E นี้ใช้ secrets เดิมตามคำยืนยัน แต่ไม่ลบความเสี่ยงจากการเปิดเผย token.
2. ทำ live duplicate/no-resend, multi-photo/multiple media, partial-failure recovery, refresh/UI, mobile และ large-file scenarios ตามที่มี test assets/credentials; อย่าส่งซ้ำหรือทดสอบส่งซ้ำโดยไม่มีการตรวจ dedupe state ก่อน.
3. แก้/ยืนยัน residual security items ใน [`SECURITY_AUDIT.md`](SECURITY_AUDIT.md); จากนั้นจึงพิจารณา Zone 6 GAS removal, merge PR #2 และเปลี่ยน GitHub Pages `main`.

**Conclusion:** ได้พิสูจน์ normal path แบบ live แล้วหนึ่งครั้ง และมีหลักฐานการส่ง Telegram message ID `347`. นี่ไม่ใช่การรับรองว่า full Zone 9 matrix ผ่านหรือระบบพร้อม production; token rotation และ scenarios ที่เหลือยังค้าง.
