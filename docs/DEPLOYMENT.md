# X2Telegram — คู่มือเผยแพร่และตั้งค่า

ระบบใช้งาน flow เดิม Dashboard → Cloudflare Access/Worker → GitHub Actions → Python worker. ผู้ใช้เลือกปลายทางต่อ job ได้: Telegram, MEGA, Dropbox และ Browser ZIP. ไม่มี database/Redis/queue หรือ Google Drive ใน production path

## 1. Architecture และ limits

```text
Dashboard → Access-protected Worker → GitHub Actions → Python processor
  → download/validate X media once → selected destination(s)
      ├── Telegram
      ├── MEGA (MEGAcmd)
      └── private Actions artifact → Access-protected ZIP stream → Browser
```

หนึ่ง job รองรับ X URL ได้สูงสุด 200 รายการ; Worker จำกัด request body ที่ 64 KiB และ workflow เดียวประมวลผล media แล้วใช้ local file เดียวกันกับทุกปลายทางที่เลือก. ผลลัพธ์แยกสถานะต่อปลายทาง/สื่อ; ปัญหาของปลายทางหนึ่งไม่หยุดปลายทางอื่น. ปลายทางเริ่มต้นหากไม่ได้ระบุคือ Telegram เพื่อรักษาความเข้ากันได้

| Target | ขนาดสูงสุดที่ระบบกำหนด | เก็บผลลัพธ์ |
|---|---:|---|
| Telegram Bot API | 50 MB/ไฟล์ | Telegram chat ที่ workflow ล็อกไว้ |
| Telegram Local Bot API (Large-file mode) | 2,000 MB/ไฟล์ | Telegram chat ที่ workflow ล็อกไว้ |
| MEGA | 2,000 MB/ไฟล์ตาม media downloader | `/X2Telegram/YYYY-MM-DD`; filename ต่อท้าย SHA-256 ของ media |
| Browser ZIP | 2,000 MB/ไฟล์; ZIP รวม 8 GiB/job | Private GitHub Actions artifact 7 วัน |

## 2. GitHub Actions Secrets

เปิด repository `aodxx/X2Telegram` → **Settings → Secrets and variables → Actions → New repository secret**. เพิ่มเฉพาะ secret ของปลายทางที่ต้องการใช้

| Secret | จำเป็นเมื่อ | รายละเอียด |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | เลือก Telegram | token จาก BotFather; เก็บใน Actions Secrets |
| `TELEGRAM_API_ID` | Telegram Large-file mode | API ID จาก my.telegram.org |
| `TELEGRAM_API_HASH` | Telegram Large-file mode | API hash จาก my.telegram.org |
| `MEGA_EMAIL` | เลือก MEGA | อีเมล MEGA account |
| `MEGA_PASSWORD` | เลือก MEGA | รหัสผ่าน MEGA account |
| `MEGA_TOTP_SECRET` | MEGA account เปิด MFA/TOTP | seed/secret สำหรับสร้าง TOTP; ไม่ต้องตั้งถ้าบัญชีไม่ใช้ MFA |
| `MEGA_SESSION` | ทางเลือกแทน email/password | session ID จาก MEGAcmd สำหรับ resume login; ใช้เมื่อ password login ถูกปฏิเสธหรือบัญชีมี MFA |
| `DROPBOX_REFRESH_TOKEN` | เลือก Dropbox | OAuth refresh token จาก Dropbox App ที่ authorize แบบ offline |
| `DROPBOX_APP_KEY` | เลือก Dropbox | Dropbox App key |
| `DROPBOX_APP_SECRET` | เลือก Dropbox | Dropbox App secret |
| `DROPBOX_ACCESS_TOKEN` | ไม่บังคับ | short-lived access token; ใช้ร่วมกับ refresh token เพื่อรองรับการ refresh |
| `ALERT_WEBHOOK_URL` | แจ้งเตือนเสริม | HTTPS webhook; optional |

`TELEGRAM_CHAT_ID` ถูกล็อกไว้ใน workflow และไม่รับจาก browser. Download-only ไม่ต้องเพิ่ม Telegram หรือ MEGA credential. **อย่าใส่ค่า credential ใน code, workflow inputs, Dashboard หรือข้อความแชต**. หากใช้ `MEGA_SESSION` ระบบจะใช้ session ก่อน email/password และไม่ส่ง password ไปกับคำสั่ง login.

MEGAcmd จะติดตั้งใน runner เฉพาะเมื่อเลือก MEGA; login uses official `mega-login` command and optional `--auth-code` when TOTP is configured. Output ของ login/upload command ไม่ถูกคัดลง dashboard report. เมื่อ job จบจะสั่ง `mega-logout` และ Actions runner เป็นชั่วคราว

โฟลเดอร์รากเริ่มต้นคือ `X2Telegram`; เปลี่ยนได้โดยสร้าง **Repository variable** ชื่อ `MEGA_REMOTE_FOLDER` ใน **Settings → Secrets and variables → Actions → Variables**. ใช้ path แบบ `Archive/X2Telegram` ได้; worker จะเพิ่ม subfolder วันที่ `YYYY-MM-DD` ต่อท้ายและ validate path ก่อน upload. Python ต่อ SHA-256 เต็มของเนื้อหาเข้ากับ basename สำหรับ MEGA/Dropbox; media ต่างเวอร์ชันจึงไม่ชนชื่อเดิม และ uploader ตรวจไฟล์ remote หลังอัปโหลด

เอกสารการใช้งาน MEGAcmd: [คำสั่ง login/MFA ทางการ](https://github.com/meganz/MEGAcmd/blob/master/contrib/docs/commands/login.md). คำแนะนำการใช้งานผู้ใช้: [`MULTI_DESTINATION.md`](MULTI_DESTINATION.md)

## 3. Cloudflare Worker และ Access

Dashboard static assets และ API ใช้ Worker origin เดียวกันภายใต้ Cloudflare Access ซึ่งอนุญาตเฉพาะอีเมลที่ระบุแบบ exact. Worker ต้องมี variables/bindings ที่กำหนดใน `control-worker/wrangler.toml` และ server-side secrets ที่จำเป็นสำหรับ Access/GitHub API. รายละเอียด routes/deployment อยู่ใน [`CLOUDFLARE_WORKER.md`](CLOUDFLARE_WORKER.md), Access setup อยู่ใน [`CLOUDFLARE_ACCESS.md`](CLOUDFLARE_ACCESS.md)

การเพิ่มผู้ใช้รายที่สองต้องทำ **ทั้งสองชั้น**: เพิ่มอีเมลนั้นเป็น `Include → Emails` รายการใหม่ใน Access policy ของแอป X2Telegram และตั้ง Cloudflare Worker secret `ACCESS_ADDITIONAL_EMAIL` เป็นอีเมลเดียวกันหลัง deploy source ที่รองรับ secret นี้แล้ว. คง `ACCESS_ALLOWED_EMAIL` ของผู้ใช้เดิมไว้; ห้ามใช้ `Everyone` หรือ email-domain rule. เมื่อต้องถอนสิทธิ์ ให้นำอีเมลออกจาก policy และลบ secret `ACCESS_ADDITIONAL_EMAIL` ด้วย

Worker รับ `POST /jobs` ที่มี URL เดี่ยวหรือ batch, `destinations`, `large_file_mode`, `request_id`; ตรวจ Access JWT/allowlist, payload, destination allowlist, idempotency และ body cap ก่อน dispatch. `POST /jobs/recover` เป็น lookup-only สำหรับคำขอเดิม; ถ้าไม่พบ workflow run ที่ตรงกันจะคืน not-found โดยไม่ dispatch งานใหม่. Worker ไม่รับ Telegram/MEGA/Dropbox credentials จาก Dashboard

Production deploy ใช้ workflow แบบ manual: `.github/workflows/deploy-worker.yml` ที่ GitHub Actions → Run workflow โดยต้องมี GitHub Environment `production` secrets `CLOUDFLARE_API_TOKEN` และ `CLOUDFLARE_ACCOUNT_ID`. Workflow จะรัน Worker tests, Wrangler dry-run และ deploy ตามลำดับ. Worker snapshot ที่บันทึกไว้ล่าสุดคือ deploy commit `f5372e5`, run [#38295769200](https://github.com/aodxx/X2Telegram/actions/runs/38295769200), Worker version `649353cf-fd9a-498b-9415-14bae01de486`; main branch หลังจากนั้นมีการปรับ Python/Dashboard และ state persistence โดยไม่เปลี่ยน Worker production code. ตรวจ `docs/AGENT_HANDOFF.md` และ `docs/PROJECT_STATUS.md` ก่อน deploy ครั้งถัดไป.

หากเผยแพร่ source ใหม่จาก `control-worker/` แบบ local/manual:

```bash
cd control-worker
npm ci
npm test
npx wrangler deploy --config wrangler.toml
```

## 4. GitHub Actions workflow contract

ใช้ workflow เดียว `.github/workflows/x2telegram.yml`:

- `url`: URL เดี่ยว (backward-compatible)
- `urls`: batch 1–200 รายการ คั่นด้วยบรรทัดใหม่
- `destinations`: JSON array จาก `telegram`, `mega`, `dropbox`, `download`; ค่า default `['telegram']`
- `large_file_mode`: เปิด Telegram Local Bot API เฉพาะเมื่อเลือก Telegram
- `request_id`, `job_id`: tracking/idempotency

ต้องใช้ `url` หรือ `urls` อย่างใดอย่างหนึ่งเท่านั้น. Dashboard จะส่ง `url` เมื่อมีรายการเดียว หรือ `urls` เมื่อเป็น batch; ทั้งสอง flow ถูก normalize เข้า Python `INPUT_URL/INPUT_URLS`. ดู [`GITHUB_ACTIONS_INTERFACE.md`](GITHUB_ACTIONS_INTERFACE.md)

## 5. ผู้ใช้รันงานอย่างไร

1. เปิด [Dashboard](https://aodxx.github.io/X2Telegram/) และลงชื่อเข้าใช้ Cloudflare Access
2. วางลิงก์หนึ่งรายการต่อบรรทัด ไม่เกิน 200 รายการ
3. เลือกหนึ่งหรือหลาย destination; ก่อนเลือก MEGA ตรวจว่าตั้ง Actions secrets แล้ว
4. เปิด Large-file mode เฉพาะเมื่อส่ง Telegram >50 MB และ Local Bot API พร้อม
5. กดเริ่มงานหนึ่งครั้ง แล้วติดตามผลแยกปลายทาง
6. ถ้าเลือก Download ให้กด link ZIP เมื่อแสดง; artifact เก็บ 7 วัน

คู่มือฉบับผู้ใช้: [`USER_GUIDE_TH.md`](USER_GUIDE_TH.md)

## 6. Retry, dedupe และ report

- Media ถูกดาวน์โหลดและตรวจครั้งเดียวก่อนส่งให้ dispatcher
- `state/dedupe.json` รุ่น v4 เก็บ SHA-256 fingerprint, success และ `outcome_unconfirmed` แยกตาม destination (Telegram/MEGA/Dropbox); retry จะข้าม target ที่สำเร็จหรือผลยังไม่ยืนยัน และลองเฉพาะ confirmed failures. Telegram/Dropbox upload timeout หรือ 5xx และ MEGA upload/read-back uncertainty จะไม่ถูก replay อัตโนมัติ. Dashboard reload ใช้ lookup-only recovery; รายงาน missing/expired/unavailable แยกกัน
- Browser artifact เป็นผลลัพธ์ของ job ไม่ได้บันทึกเป็น persistent target-dedupe; เริ่ม job ใหม่เพื่อสร้าง ZIP ใหม่
- `report.json` และ sanitized Dashboard artifact มี status ต่อ post/destination/media; private media ZIP แยก artifact จาก report
- Worker ดึง media ZIP แบบ streaming ผ่าน Access ไม่ส่ง signed GitHub URL ให้ frontend และไม่ buffer archive ทั้งก้อนใน Worker
- GitHub Actions concurrency serialize การเขียน state. Worker's concurrent-dispatch single-flight อยู่ภายใน isolate เท่านั้นและเก็บ reservation 30 วินาที; ไม่ใช่ global/durable lock. ระบบไม่ได้อ้าง exactly-once เมื่อ dispatch แข่งข้าม isolates หรือปลายทางตอบ success แล้วการเขียน success checkpoint ล้มเหลว; ในกรณีหลัง report เตือน `dedupe_checkpoint_failed`, Dashboard failed-only retry ไม่เลือก target ที่รายงาน success แต่ full job ใหม่ที่ผู้ใช้สร้างเองอาจส่งซ้ำ

## 7. Tests และ local checks

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
npm ci --prefix control-worker
npm test --prefix control-worker
node --check control-worker/src/index.js
python -m compileall -q src tests
```

Tests ใช้ mocks/fakes สำหรับ MEGA/Telegram และ GitHub API; ไม่เปิดเผย credential และไม่แทน live verification ของ MEGA. อย่าทดสอบด้วย destination จริงโดยไม่ตรวจรายการและผลกระทบก่อน

### State persistence ใน GitHub Actions

Job `persist-state` จะ `git add` และ commit `state/dedupe.json` ก่อน `fetch/rebase` แล้วจึง push พร้อม retry สูงสุด 3 ครั้ง. ห้ามย้าย `rebase` กลับไปก่อน commit เพราะ artifact ที่ดาวน์โหลดมาจะเป็น unstaged change และทำให้ job ล้มด้วย `cannot rebase: You have unstaged changes`. หาก rebase conflict ให้หยุดและปฏิเสธการเขียนทับ state เพื่อให้ตรวจสอบแบบ manual.

### Branch protection สำหรับ state writer

`main` ควรใช้ repository ruleset ที่บังคับ Pull Request, review อย่างน้อย 1 ครั้ง, required checks ของ `Automated Tests` และปิด force-push/branch deletion. ข้อยกเว้น direct push ให้เฉพาะ GitHub Actions integration ที่ใช้โดย `persist-state` (GitHub App ID `15368`) และต้องเปิด bypass เท่าที่จำเป็น เพราะ workflow มี guard ตรวจ repository, `refs/heads/main`, `workflow_dispatch` และยอมให้มีไฟล์เปลี่ยนเฉพาะ `state/dedupe.json` เท่านั้น. ห้ามใช้ personal PAT หรือเปิด bypass ให้ administrator เป็นทางลัด.

ก่อนเปิด ruleset เป็น Active ให้ทดสอบใน Evaluate mode แล้วตรวจว่า state commit ผ่าน, ไม่มีไฟล์อื่นถูกเขียน, ไม่เกิด CI loop จาก `[skip ci]` และ concurrent state runs ทำ rebase/retry ได้. หาก `persist-state` ล้ม ให้เก็บ state artifact จาก run, ห้าม force-push, แก้ ruleset/permission เฉพาะจุด และใช้ manual reconciliation เมื่อเกิด conflict. รายละเอียด policy ปัจจุบันต้องตรวจจาก GitHub repository rulesets ก่อน deploy ทุกครั้ง.

ณ 2026-10-22 PR #29 ถูก merge เป็น `359041e` และ guard ของ state-writer ผ่าน CI แล้ว แต่การสร้าง ruleset ถูก GitHub API ปฏิเสธด้วยข้อกำหนดว่า GitHub Actions integration ต้องเป็นส่วนหนึ่งของ ruleset source หรือ owner organization. Repository นี้อยู่ใต้ user owner จึงยังไม่มี active protection ที่ปลอดภัยสำหรับ workflow ปัจจุบัน; ห้ามสร้าง ruleset ที่ไม่มี bypass ของ integration เพราะจะบล็อกการ persist `state/dedupe.json`. ทางแก้ที่ต้องพิจารณาแยกคือย้าย repository เข้า organization ที่รองรับ integration bypass หรือเปลี่ยน state-writer ให้ใช้ PR/กลไกอื่นก่อนเปิด protection.

## 8. Error ที่พบบ่อย

| Error/status | วิธีตรวจ |
|---|---|
| `mega_credentials_missing` | เพิ่ม `MEGA_EMAIL`, `MEGA_PASSWORD` ใน repository Actions Secrets |
| `mega_authentication_failed` | ตรวจข้อมูล MEGA/TOTP ใน Secrets; หาก password login ถูกปฏิเสธ ให้ใช้ `MEGA_SESSION`; report ไม่แสดงรหัสผ่าน/command output |
| `mega_mfa_required` | บัญชีเปิด MFA แต่ไม่มี TOTP/session ที่ใช้ได้ ให้ตั้ง `MEGA_TOTP_SECRET` หรือ `MEGA_SESSION` |
| `mega_client_unavailable` | ตรวจขั้นติดตั้ง MEGAcmd ใน Actions log; target อื่นยังทำงานต่อได้ |
| `telegram_file_too_large` | ใช้ Telegram Large-file mode ที่ตั้งค่า Local Bot API แล้ว หรือเลือก MEGA/Dropbox/Download เพิ่ม |
| `download_artifact_size_limit` | แบ่งรายการเป็นหลาย jobs; ZIP limit คือ 8 GiB/job |
| `download_expired` | GitHub artifact มีอายุ 7 วัน; เริ่ม job ใหม่เพื่อสร้าง ZIP ใหม่ |
| `partial_success` | เปิดผลราย target แล้ว retry post เดิม; target ที่สำเร็จแล้วจะถูกข้ามตาม dedupe state |
| `dropbox_path_conflict` | Dropbox มีไฟล์ชื่อเดียวกัน ระบบจะตรวจขนาด/ลายนิ้วมือเนื้อหา; ถ้าตรงกันจะถือว่าไฟล์มีอยู่แล้วและไม่ส่งซ้ำ |
| `dropbox_hash_mismatch` | มีไฟล์ชื่อเดียวกันแต่เนื้อหาไม่ตรง ระบบไม่เขียนทับ ให้ตรวจไฟล์เดิมก่อนเริ่มงานใหม่ |
| `metadata_error` / `no_media` | ตรวจว่า X post เป็นสาธารณะและยังมี media ที่ระบบรองรับ |

## 9. ขอบเขต/นโยบาย

- ใช้เฉพาะ media ที่ผู้ใช้มีสิทธิ์ดาวน์โหลดและเผยแพร่
- X post private/ถูกลบ/ถูกจำกัดอายุหรือ rate limit อาจดึงไม่ได้
- Browser download เป็น ZIP; มือถือรับไฟล์ผ่าน browser Downloads/Files/Share UI ตามแพลตฟอร์ม ไม่ใช่การเขียนไฟล์จาก runner ไปยังเครื่องโดยตรง
- `gas/` เป็น legacy/reference เท่านั้น ไม่ใช่ production endpoint; ไม่เพิ่ม Google Drive

## Dropbox

ให้สร้าง scoped Dropbox App และ authorize ด้วย OAuth code flow พร้อม `token_access_type=offline`; เก็บ App Key, App Secret และ Refresh Token เป็น GitHub Actions Secrets. ตั้ง Repository variable `DROPBOX_REMOTE_FOLDER` ได้ (ค่าเริ่มต้น `X2Telegram`). ระบบไม่แสดงสถานะ Dropbox ว่าเชื่อมต่อสำเร็จล่วงหน้า: ต้องเลือกปลายทางและให้ workflow เรียก API จริงก่อนจึงจะรายงาน `success`.
