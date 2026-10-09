# GitHub Actions Least-Privilege Workflow Implementation Plan

> **For agentic workers:** Execute inline as requested; each step is independently testable.

**Goal:** จำกัด `contents: write` เฉพาะ job ที่บันทึก dedupe state และให้ job ประมวลผลมีสิทธิ์อ่านเท่านั้น

**Architecture:** `send-media` checkout/process/upload state artifact ด้วยสิทธิ์ `contents: read` และไม่ persist checkout credentials. Job `persist-state` ทำงานหลัง job แรกเสมอ, ดาวน์โหลด state artifact และ commit เฉพาะ `state/dedupe.json` ด้วยสิทธิ์ `contents: write`. คง workflow concurrency เดิมเพื่อ serialize state writes.

**Tech Stack:** GitHub Actions YAML, Python pytest contract tests, npm Node test suite.

**Spec:** `docs/SECURITY_AUDIT.md` finding P2 on broad `contents: write`; `docs/ARCHITECTURE.md` dedupe concurrency contract.

## Global Constraints

- ไม่เปลี่ยนปลายทางผู้ใช้หรือ secrets.
- ไม่ dispatch workflow จริงหรือ deploy Worker.
- รักษาการ persist dedupe state เมื่อ processor สำเร็จหรือล้มเหลว.
- รัน Python และ Worker tests ครบ.

---

### Task 1: Workflow permission separation

**Files:**
- Modify: `.github/workflows/x2telegram.yml`
- Test: `tests/test_workflow_contract.py`

- [x] เพิ่ม contract tests ที่ยืนยันสิทธิ์อ่านของ `send-media`, `persist-state` ต้อง depends on `send-media` และ `always()`, checkout ฝั่ง processor ไม่ persist credential, และ state artifact ถูก transfer
- [x] รันทดสอบเฉพาะไฟล์เพื่อดู failure ที่คาดไว้ — ก่อน implementation มี 2 tests fail ด้วยเงื่อนไข permission/job ที่ยังไม่มี
- [x] แยก state persistence เป็น job ที่มี `contents: write`; job ที่รัน tests/ประมวลผลให้สิทธิ์ `contents: read`
- [x] อัปโหลดและดาวน์โหลด state artifact โดยใช้ retention 1 วัน และยัง commit เฉพาะไฟล์ dedupe
- [x] รัน Python tests (89 passed), Worker tests (25 passed), YAML parse และ diff check
- [x] ทบทวน diff ว่าไม่มีการเปลี่ยนปลายทาง/credential/deployment แล้วบันทึกผลให้ผู้ใช้

## ขอบเขตนอกแผน

การ rotate GitHub token, Dropbox live test, การทดสอบส่ง media จริง, pin immutable Action/container references และการตั้ง Cloudflare rate limit ต้องการตรวจสอบ/ข้อมูล/การอนุมัติจากเจ้าของบริการ จึงไม่ทำในแผนนี้.
