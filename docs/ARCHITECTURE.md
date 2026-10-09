# Architecture

## ภาพรวมปัจจุบัน

```text
Dashboard (static, Worker origin)
  → Cloudflare Access + Control Worker
  → GitHub Actions workflow เดียว
  → Python worker
  → metadata + media retrieval/validation (หนึ่งครั้งต่อ post/media)
  → Destination dispatcher
      ├── Telegram
      ├── MEGA ผ่าน MEGAcmd
      └── private Actions artifact → Worker streaming → Browser ZIP
```

GitHub Pages entry URL redirect ไปยัง Dashboard ที่เสิร์ฟจาก Cloudflare Worker origin เดียวกับ API เพื่อให้ Access session เป็น same-origin. Worker ตรวจ Access JWT/owner allowlist, URL, destinations, body size และ request idempotency ก่อน dispatch workflow; Worker ไม่เก็บ Telegram/MEGA/Dropbox credential และไม่เป็น media processing backend

## Processing และ destination boundary

`PostProcessor` ค้น metadata และดาวน์โหลด/ตรวจ media ลงไฟล์ชั่วคราวครั้งเดียว จากนั้น `DestinationDispatcher` ส่งไฟล์เดียวกันไปยังทุกปลายทางที่เลือก. ผลลัพธ์เก็บ status ต่อ post, destination และ media item; failure ของ target หนึ่งไม่หยุด target อื่น

- Telegram ยังคงล็อก group destination; Telegram error/size limit อยู่เฉพาะ target นั้น
- MEGA ใช้ official MEGAcmd scriptable CLI ใน runner ชั่วคราว; secret อยู่ใน GitHub Actions Secrets และ path เริ่มต้นคือ `/X2Telegram/YYYY-MM-DD`
- Download คัดลอกไฟล์ไปยังโฟลเดอร์ export, upload เป็น private GitHub Actions artifact 7 วัน แล้ว Worker stream ZIP ผ่าน Access-protected endpoint; จำกัดรวม 8 GiB ต่อ job เพื่อไม่ชนพื้นที่ runner/artifact โดยไม่จำเป็น

## Retry และ state

`state/dedupe.json` ใช้ SHA-256 media fingerprint และสถานะ destination แยกกัน (state v3); รุ่นเดิมอ่านต่อได้. Target ที่สำเร็จแล้วไม่ถูกส่งซ้ำเมื่อ retry post เดิม ขณะที่ target ที่ล้มเหลวยังลองใหม่ได้. Download ZIP เป็น artifact เฉพาะ job ไม่ใช่ dedupe-persistent destination; เริ่ม job ใหม่เพื่อสร้าง artifact อีกครั้ง. GitHub Actions concurrency ป้องกันการเขียน state พร้อมกัน

ไม่ใช้ database/Redis/queue. Idempotency ของ Worker ป้องกัน dispatch ซ้ำเมื่อใช้ request ID เดิม แต่ระบบไม่รับประกัน exactly-once หากบริการปลายทางรับไฟล์แล้ว response/checkpoint หายก่อนบันทึก state

## Contract และ deployment

- API contract: [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md)
- Worker deployment/Access: [`CLOUDFLARE_WORKER.md`](CLOUDFLARE_WORKER.md), [`CLOUDFLARE_ACCESS.md`](CLOUDFLARE_ACCESS.md)
- GitHub Actions inputs: [`GITHUB_ACTIONS_INTERFACE.md`](GITHUB_ACTIONS_INTERFACE.md)
- การตั้งค่า destinations: [`MULTI_DESTINATION.md`](MULTI_DESTINATION.md)
- คู่มือ Dashboard: [`USER_GUIDE_TH.md`](USER_GUIDE_TH.md)

Google Apps Script ใน `gas/` เป็น legacy/reference เท่านั้น; production path ไม่เรียก GAS และไม่สร้าง Google Drive integration.
