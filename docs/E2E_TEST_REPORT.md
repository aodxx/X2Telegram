# X2Telegram — E2E Test Report

**วันที่:** 2026-10-09
**สรุป:** Telegram normal path, batch no-resend, Dashboard Access และ Browser ZIP live smoke tests ผ่าน; destination combinations ครอบคลุมด้วย automated tests. ยังไม่มี live MEGA upload หรือ live Telegram+MEGA combined send

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

- Worker version `0a099878-485a-43ef-9097-cf4f44e24373`, deployed หลัง PR #6 / commit `389621b`
- Dashboard แสดง Access authenticated, destinations picker และฟอร์ม 2 URLs
- เลือก **Download-only** แล้ว dispatch run [#37843359593](https://github.com/aodxx/X2Telegram/actions/runs/37843359593), job `job-601fc374e2d57b21b0528137602cba7d`
- Actions success; Telegram Local Bot API และ MEGAcmd setup ถูกข้าม; process/report/artifact upload ผ่าน; report แสดง Download `ready` 2 files
- เปิด `/jobs/<job_id>/download` ผ่าน browser session ที่ผ่าน Access แล้ว browser ดาวน์โหลดไฟล์ ZIP จริง; archive มี 2 entries, ขนาด 256,966,632 bytes, CRC check ผ่าน
- งานนี้ไม่เลือก Telegram หรือ MEGA จึงไม่ได้ส่งข้อความหรืออัปโหลดไป MEGA

## Scenario status

| Scenario | ผล | หลักฐาน/ขอบเขต |
|---|---|---|
| Dashboard Access/login same-origin | PASS (live) | Browser แสดง `Access ลงชื่อเข้าใช้แล้ว · พร้อมส่ง` |
| Telegram normal path | PASS (live) | Run #37807253687, MP4 1 ไฟล์, message ID 347 |
| Batch URL dispatch 1–50 | PASS (live 2 URLs) | Run #37816856323; completed posts ถูก dedupe ไม่ส่งซ้ำ |
| Download-only, multiple URL job | PASS (live 2 URLs) | Run #37843359593; private artifact พร้อมและ report แสดง 2 files |
| Worker protected ZIP streaming | PASS (live) | Browser ดาวน์โหลดจริงผ่าน Access route; ZIP CRC ผ่าน |
| Telegram/MEGA/Download combinations | PASS (automated mock) | Python processor tests ครอบ single/pair/all-three paths; live combination ยังไม่ทำ |
| Retry เฉพาะ destination ที่ล้มเหลว | PASS (automated mock) | Mega failure แล้ว retry; Telegram ที่สำเร็จไม่ถูกส่งซ้ำ |
| ภาพ+วิดีโอในโพสต์เดียว | PASS (automated mock) | ภาพยังคงอยู่ และเลือก video variant สูงสุด; download หนึ่งครั้งต่อ media |
| Invalid MEGA folder/credential failure | PASS (automated mock) | MEGA failure ไม่หยุด Telegram/Download; ไม่มี command output ใน report |
| MEGA upload จริง | NOT RUN | ต้องตั้ง GitHub Actions Secrets ของบัญชี MEGA ก่อน |
| Telegram+MEGA live combined send | NOT RUN | เพื่อไม่ส่ง Telegram ซ้ำโดยไม่จำเป็น; live MEGA ยังรอตั้งค่า account credentials |
| Telegram Local Bot API large file | NOT RUN (live) | Standard-size target policy มี local tests; ยังไม่ส่งไฟล์ใหญ่จริง |
| Mobile browser | NOT RUN | ยังไม่มีการทดสอบบนอุปกรณ์มือถือจริง |
| Invalid URL, body cap, unauthorized | PASS (Worker tests/live safe checks เดิม) | 400/413/401/403 paths ปฏิเสธก่อน dispatch ตาม report/contract เดิม |

## Automated validation หลัง merge

- Python: `python3 -m pytest -q` — **71 passed**
- Cloudflare Worker: `npm test --prefix control-worker` — **25 passed**
- Python compile, Node syntax, workflow YAML parse, `git diff --check`, `npm ci` และ Wrangler dry-run ผ่าน
- Live run #37843359593 ผ่าน automated Python/Worker tests ก่อน process, report และ media artifact upload

## ข้อสรุป

ระบบ deployed และใช้งานได้สำหรับ Telegram และ Browser ZIP. Live ZIP path ผ่านตั้งแต่ Dashboard → Access → Worker → GitHub Actions → report/artifact → Access-protected Worker stream → browser file ที่ตรวจ ZIP CRC ผ่าน. โค้ด multi-destination, per-target dedupe/retry และ MEGA ได้รับ automated coverage; live MEGA และ live destination combination ยังไม่ยืนยันจนกว่าจะตั้ง credentials/ปลายทางที่ต้องใช้
