# X2Telegram End-to-End Test Report — Zone 9

**วันที่:** 2026-10-09
**สถานะ:** **Normal-path 1 URL ผ่าน live; live 2-URL batch dispatch ผ่านและข้าม completed posts ทั้งคู่โดยไม่ส่งซ้ำ; fresh multi-item delivery ยังไม่ทดสอบ**
**ปลายทาง:** Telegram group `-1003906817580` (ล็อกไว้ใน workflow)
**Credential:** ใช้ secrets ที่ตั้งอยู่แล้วตามคำยืนยันของเจ้าของ; รายละเอียดการทบทวน credential อยู่ใน [`SECURITY_AUDIT.md`](SECURITY_AUDIT.md).

## ผล normal-path E2E

- **URL:** `https://x.com/ninmopmn/status/2107508912392171879`
- **Worker request:** `request_id=e2e-20261008-231429-r2`, `job_id=job-72368aeb450a9df8c5b34f016d87e2a8`, HTTP `202`.
- **Workflow:** [run #37807253687](https://github.com/aodxx/X2Telegram/actions/runs/37807253687), branch `migration/zone-1-5-cloudflare-control-plane`, SHA `7327b70d2c7ec4c3c07ac29bc486636ceec50c46`, conclusion `success`.
- **Report ที่ Worker คืน:** `state=completed`; `sent=1`, `failed=0`, `skipped_duplicate=0`; result `status=sent`, file `ninmopmn_2107508912392171879_01.mp4`, Telegram `message_id=347`.
- Metadata มี video formats 2 รายการ; ระบบเลือก video variant สูงสุดหนึ่งรายการและส่งหนึ่งข้อความ/media ไปกลุ่มข้างต้น.
- GitHub Actions persist step สำเร็จ; ตรวจ remote branch ภายหลังพบ `state/dedupe.json` version 2 มี completed record ของ post นี้และ media checkpoint 1 รายการ.
- Dashboard-origin authenticated `GET /jobs/<job_id>` คืน HTTP `200` พร้อม sanitized report และ Telegram message ID.
- หลัง run เสร็จได้คืน Worker `GH_REF` จาก branch ชั่วคราวเป็น `main` (Worker version `29a2c667-cce4-4da9-8bff-d93b89490e0f`). PR #2 ถูก squash-merge เป็น commit `00936856a02261e1969d517157f5591d1a0d0c12`; Pages deploy run #37809007472 สำเร็จ. ตรวจหน้า https://aodxx.github.io/X2Telegram/ ได้ HTTP 200, `config.js` ชี้ Worker, และ health badge แสดง `Control Worker พร้อม`.
- PR #4 รวมเข้า `main` เป็น `2e0cfc0e3dea3c8dd46f5b2e193ea8d693b2435e`; Pages deploy run #37816537609 ผ่าน และ Worker version `9641c2a5-eda8-4eef-b7ba-6667461de2d3` เสิร์ฟ assets/API บน Access-protected origin เดียวกัน. Browser session ตรวจ `/auth/check` ผ่านและ Dashboard แสดง **Access ลงชื่อเข้าใช้แล้ว · พร้อมส่ง**.

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
| 12. Dashboard batch submit (1–50 URLs) | Run [#37816856323](https://github.com/aodxx/X2Telegram/actions/runs/37816856323) รับ 2 URLs ใน workflow เดียวและสำเร็จ; report `sent=0`, `skipped_duplicate=2`, `failed=0`; ทั้งสอง URL มี completed dedupe records จึงไม่มี Telegram send ซ้ำ | **PASS (live dispatch + no-resend)** |

## Validation evidence

- Python: `python3 -m pytest -q` — **50 passed**.
- Control Worker: `npm test --prefix control-worker` — **19 passed**, รวม auth-check, protected asset serving และ batch validation/dispatch mocks.
- Python compile, JavaScript syntax, workflow YAML, Wrangler TOML, `git diff --check`, credential-literal scan และ Wrangler dry-run ผ่าน.
- Live safe checks ก่อน E2E: cross-origin `GET /health` ได้ `200`; invalid URL ได้ `400`; body 17 KiB ได้ `413`; ทั้งหมดไม่ dispatch.
- GitHub Actions แจ้ง non-blocking migration advisories สำหรับ Node 20 → 24 และ `ubuntu-latest` → Ubuntu 26; ไม่ทำให้ run ล้มเหลว.

## Scenarios ที่ยังต้องทดสอบเพิ่มเติม

1. Live batch ที่มี fresh/unprocessed posts, multi-photo/multiple media, partial-failure recovery, refresh/UI, mobile และ large-file scenarios ยังไม่ครอบคลุม; ตรวจ dedupe state ก่อนทดสอบเพื่อไม่ส่งซ้ำ.
2. ทบทวน residual security findings ตาม [`SECURITY_AUDIT.md`](SECURITY_AUDIT.md); จากนั้นพิจารณา Zone 6 GAS removal.

**Conclusion:** พิสูจน์ normal path แบบ live (หนึ่ง MP4, message ID `347`) และ Dashboard batch dispatch แบบ live (2 URLs ในหนึ่ง run, ทั้งคู่ skipped duplicate, ไม่มีการส่งซ้ำ) แล้ว. ยังไม่ได้ทดสอบ batch ที่มีหลายโพสต์ใหม่ซึ่งจะส่ง media จริง หรือ full Zone 9 matrix.
