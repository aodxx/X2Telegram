# Dashboard Status Recovery Implementation Plan

> **For agentic workers:** Execute this plan inline in the current session, one testable step at a time.

**Goal:** ให้ Dashboard กลับมาตรวจคำขอเดิมแบบไม่ส่งซ้ำและปลดล็อกการเริ่มงานใหม่ เมื่อผู้ใช้กลับมาเชื่อมต่อหรือกลับมาที่แท็บหลังสถานะยังยืนยันไม่ได้

**Architecture:** ใช้ browser recovery harness ที่มีอยู่เพื่อจำลองสถานะเดิมค้างหลัง temporary status failures จากนั้นให้ `checkBackend()` เรียก recovery-only lookup เมื่อ backend พร้อมและมีสถานะค้างอยู่ การกู้คืนต้องไม่เรียก `POST /jobs`; แสดงคำแนะนำ Cloudflare Access เมื่อเครือข่าย/response ไม่ใช่ JSON

**Tech Stack:** Inline dashboard JavaScript, Node.js `node:test` + `vm` recovery harness.

**Spec:** รายงานอาการผู้ใช้ 2026-11-05: Dashboard แสดง “ยังไม่ได้ยืนยัน”, ตรวจสอบรายการไม่เปลี่ยน progress, ล้าง tracking แล้วเริ่มใหม่กลับสู่สถานะเดิม.

## Global Constraints

- ห้าม dispatch URL หรือสร้างงานจริงระหว่างแก้และทดสอบ
- Recovery ใช้เฉพาะ endpoint `/jobs/recover` (ค้นหาเท่านั้น) หรือ `GET /jobs/{job_id}`
- ห้ามล้าง tracking อัตโนมัติ และห้าม bypass Cloudflare Access
- คงการป้องกันส่งซ้ำเมื่อผลของงานเดิมยังไม่ยืนยัน
- ทดสอบใน branch แยกจาก `origin/main`; deploy เฉพาะหลัง tests ผ่าน

---

### Task 1: เพิ่ม regression test สำหรับกลับมาเชื่อมต่อหลังสถานะค้าง

**Files:**
- Modify: `control-worker/test/dashboard-recovery.test.js`

**Interfaces:**
- ใช้ `makeBrowser()` และ fake `window:focus` event ที่มีอยู่
- คาดหวังให้ focus trigger read-only status recovery เมื่อ `recoveryUnconfirmed === true`

- [x] เพิ่ม test ที่ทำให้สถานะงานเดิมผ่าน temporary status failures จนเป็น unconfirmed จากนั้นจำลอง `window.focus` แล้ว assert ว่ามี `GET /jobs/{job_id}` หรือ recovery-only lookup, ไม่มี `POST /jobs`, สถานะ terminal ปลดล็อกปุ่มเริ่มงาน และซ่อน recovery actions
- [x] รัน `node --test control-worker/test/dashboard-recovery.test.js` ให้ล้มด้วย assertion ที่คาดหวัง เพราะ focus ปัจจุบันตรวจเฉพาะ auth

### Task 2: แก้ recovery เมื่อ backend กลับมา

**Files:**
- Modify: `web/index.html`

**Interfaces:**
- เพิ่ม guard ป้องกัน concurrent automatic recovery lookups
- เมื่อ `checkBackend()` ยืนยัน authenticated และยังมี `recoveryUnconfirmed` ให้เรียก `lookupCurrentJob()` แบบไม่ dispatch
- ถ้า lookup ยังล้มเหลว ให้คง lock ป้องกัน duplicate และคง recovery actions
- สำหรับ network/invalid response ให้ข้อความ recovery แนะนำตรวจ session Cloudflare Access/การเชื่อมต่อและกดตรวจสถานะ ไม่สื่อว่าคำขอถูกปฏิเสธแน่นอน

- [x] เพิ่ม implementation ขั้นต่ำให้ test จาก Task 1 ผ่าน
- [x] ตรวจว่า auto recovery เรียกได้จาก focus/visibility แต่ไม่เริ่ม job ใหม่

### Task 3: ตรวจและยืนยัน

**Files:**
- Test: `control-worker/test/dashboard-recovery.test.js`
- Test: `tests/test_dashboard_contract.py`
- Test: `control-worker/test/index.test.js`

- [x] รัน focused recovery test
- [x] ติดตั้ง dependencies ตาม lockfiles ใน worktree แล้วรัน test suites ที่มีอยู่
- [x] รัน `node --check` กับ inline dashboard script และ `git diff --check`
- [ ] ตรวจ diff ว่าไม่มี URL ที่ผู้ใช้เคยส่ง, secrets หรือ runtime dispatch
- [ ] Commit แยกหนึ่ง logical change; เปิด PR และ deploy Worker ผ่าน workflow ที่ทดสอบ/validate ก่อน deploy
