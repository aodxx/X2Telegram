# ตั้งค่า Dropbox สำหรับ X2Telegram

คู่มือนี้อธิบายการสร้าง Dropbox App แบบใช้สิทธิ์เท่าที่จำเป็น การสร้าง OAuth **refresh token** สำหรับงานอัตโนมัติ และวิธีตรวจการอัปโหลดไฟล์ใหญ่ของ X2Telegram

## สรุปสิ่งที่ต้องมี

| GitHub Actions Secret / Variable | จำเป็นหรือไม่ | ใช้ทำอะไร |
|---|---:|---|
| `DROPBOX_APP_KEY` | จำเป็น | App key (OAuth `client_id`) |
| `DROPBOX_APP_SECRET` | จำเป็น | App secret (OAuth `client_secret`) ใช้แลก refresh token เป็น access token |
| `DROPBOX_REFRESH_TOKEN` | จำเป็น | ให้ workflow ขอ short-lived access token ใหม่ได้โดยไม่ต้อง login ซ้ำ |
| `DROPBOX_ACCESS_TOKEN` | ไม่จำเป็น | access token ชั่วคราว; ถ้ามีแล้วหมดอายุ connector จะลอง refresh เมื่อได้ HTTP 401 |
| `DROPBOX_REMOTE_FOLDER` | ไม่จำเป็น; เป็น Repository variable | โฟลเดอร์ปลายทาง; ค่าเริ่มต้น `X2Telegram` |

**วิธีที่แนะนำ:** ตั้ง App Key, App Secret และ Refresh Token ให้ครบ แล้วไม่ต้องตั้ง `DROPBOX_ACCESS_TOKEN` เพิ่ม ระบบจะขอ access token จาก refresh token ก่อนอัปโหลดเอง

## 1. สร้าง Dropbox App และให้สิทธิ์เฉพาะการเขียนไฟล์

1. เปิด [Dropbox App Console](https://www.dropbox.com/developers/apps) แล้วเลือก **Create app**.
2. เลือก **Scoped access** และเลือก **App folder** (แนะนำให้สิทธิ์เฉพาะโฟลเดอร์ของแอป แทนการเข้าถึง Dropbox ทั้งบัญชี). ตั้งชื่อแอป เช่น `X2Telegram`.
3. เปิดแท็บ **Permissions** แล้วเลือก `files.content.write` จากนั้นกด **Submit**.
4. เปิดแท็บ **Settings** แล้วจด **App key** และ **App secret**. App key ใช้เป็น `client_id`; App secret ใช้เป็น `client_secret`.
5. หากเคย authorize แอปก่อนเพิ่ม scope นี้ ให้ authorize ใหม่หลังจากเพิ่มสิทธิ์ เพื่อให้ token ได้รับ scope ปัจจุบัน.

`files.content.write` เป็น scope ที่ Dropbox ระบุว่าจำเป็นสำหรับ `files/upload` และ upload-session endpoints ทั้งหมดที่ connector เรียกใช้. ไม่มีความจำเป็นต้องเปิด scope สำหรับอ่าน แชร์ หรือลบไฟล์เพื่อให้การอัปโหลดนี้ทำงาน

> เมื่อเลือก App folder แล้ว path `/X2Telegram` ที่ X2Telegram ใช้จะอยู่ภายในโฟลเดอร์ของแอปใน Dropbox (มักแสดงใต้ `Apps/<ชื่อแอป>/X2Telegram`). หากต้องการให้ไฟล์อยู่ที่ root `/X2Telegram` ของ Dropbox ทั้งบัญชี ให้เลือก Full Dropbox แทน แต่จะให้ขอบเขตสิทธิ์กว้างกว่า

## 2. ขอ Refresh Token ด้วย OAuth แบบ offline

ปุ่ม **Generate** ใน App Console ใช้สร้าง access token เพื่อทดสอบอย่างรวดเร็วเท่านั้น; อย่านำ access token นั้นมาใส่ช่อง `DROPBOX_REFRESH_TOKEN`. สำหรับ workflow ที่ทำงานเบื้องหลัง ให้ใช้ OAuth authorization-code flow และระบุ `token_access_type=offline` ตาม [Dropbox OAuth guide](https://docs.dropboxapi.com/dropbox-api/docs/oauth).

1. แทน `YOUR_APP_KEY` ใน URL ด้านล่างด้วย App key ของแอป แล้วเปิด URL ใน browser:

   ```text
   https://www.dropbox.com/oauth2/authorize?client_id=YOUR_APP_KEY&response_type=code&token_access_type=offline
   ```

2. ลงชื่อเข้า Dropbox และกดอนุญาตให้แอปเข้าถึงไฟล์ตามสิทธิ์ที่เลือก. เมื่อไม่ได้กำหนด redirect URI, Dropbox จะแสดง **authorization code** ให้คัดลอก.
3. ใช้ terminal ที่มี `curl` เพื่อแลก code เป็น token. คำสั่งนี้รับ App secret และ code ผ่าน prompt แทนการพิมพ์ค่าเหล่านั้นไว้ใน command history:

   ```bash
   read -r -p "Dropbox App Key: " DBX_APP_KEY
   read -r -s -p "Dropbox App Secret: " DBX_APP_SECRET; printf '\n'
   read -r -p "Authorization code: " DBX_CODE
   curl -sS --user "$DBX_APP_KEY:$DBX_APP_SECRET" \
     --data-urlencode "grant_type=authorization_code" \
     --data-urlencode "code=$DBX_CODE" \
     https://api.dropboxapi.com/oauth2/token
   ```

4. ผลลัพธ์ JSON จะมี `access_token` และ `refresh_token`. คัดลอกค่า **`refresh_token`** ไปตั้งเป็น `DROPBOX_REFRESH_TOKEN`; ไม่ต้องเก็บ access token ชั่วคราวไว้ใน repository.
5. Authorization code ใช้แลกได้ครั้งเดียวและมีอายุจำกัด. อย่าโพสต์ code, ผล JSON, App secret หรือ token ใน issue, log หรือข้อความแชต. หากใช้ redirect URI แทนการให้ Dropbox แสดง code ต้องลงทะเบียน URI นั้นใน App Console และส่ง URI ค่าเดียวกันทั้งขั้น authorize และแลก code.

> ถ้ารันใน PowerShell ให้ใช้ `curl.exe` (แทน `curl`) และใช้ terminal แบบ Bash/WSL/Git Bash สำหรับคำสั่ง `read` ข้างต้น. ห้ามนำ App secret หรือ token ไปวางในหน้า Dashboard

## 3. เพิ่มค่าใน GitHub repository

1. เปิด [GitHub Actions Secrets ของ X2Telegram](https://github.com/aodxx/X2Telegram/settings/secrets/actions).
2. กด **New repository secret** แล้วเพิ่ม Secret แยก 3 รายการ โดยชื่อสะกดตรงตามนี้:
   - `DROPBOX_APP_KEY` — App key
   - `DROPBOX_APP_SECRET` — App secret
   - `DROPBOX_REFRESH_TOKEN` — refresh token จากขั้นตอนก่อนหน้า
3. ไม่ต้องสร้าง `DROPBOX_ACCESS_TOKEN` สำหรับการตั้งค่าใหม่.
4. ถ้าต้องการเปลี่ยนโฟลเดอร์ ให้เปิด [Actions Variables](https://github.com/aodxx/X2Telegram/settings/variables/actions) แล้วสร้าง Repository variable ชื่อ `DROPBOX_REMOTE_FOLDER` เช่น `Archive/X2Telegram`. ถ้าไม่สร้าง ระบบใช้ `X2Telegram`.
5. เลือก Dropbox จาก Dashboard เพื่อประมวลผล. Dashboard ไม่รับหรือแสดง credential เหล่านี้.

## 4. ทดสอบการ refresh และการอัปโหลด

### ทดสอบ token refresh

- เมื่อ `DROPBOX_ACCESS_TOKEN` ไม่ได้ตั้งไว้ ระบบจะเรียก Dropbox OAuth token endpoint ด้วย `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET` และ `DROPBOX_REFRESH_TOKEN` ก่อนคำขออัปโหลดแรก. การรัน Dropbox-only หนึ่งรายการจึงทดสอบทั้งการ refresh และ upload ใน live path.
- ถ้ามี `DROPBOX_ACCESS_TOKEN` อยู่แล้ว ระบบจะใช้ค่านั้นก่อน และ refresh เมื่อ Dropbox ตอบ HTTP 401. การทดสอบกรณี token หมดอายุมี automated coverage แต่ยังไม่ใช่หลักฐาน live.
- ผล Dropbox live ล่าสุดที่บันทึกไว้คือ combined run [#38037210973](https://github.com/aodxx/X2Telegram/actions/runs/38037210973): media หนึ่งรายการสำเร็จทั้ง Telegram, MEGA, Dropbox และ Download. Refresh-token-only และการอัปโหลดไฟล์ใหญ่ยังมีหลักฐานจาก automated tests เท่านั้น; ยังไม่ควรนับว่า live-tested แล้ว

### ทดสอบ upload session สำหรับไฟล์ใหญ่

1. ใช้ media ที่มีสิทธิ์ดาวน์โหลดและมีขนาด **มากกว่า 150 MiB**; เลือก Dropbox-only และตรวจว่าขนาดยังอยู่ภายในขีดจำกัดของ X2Telegram ซึ่งตั้งไว้ที่ 2,000 MB ต่อ media.
2. รอ Actions จบแล้วตรวจว่า Dropbox รายงาน `success` และมีไฟล์ครบในโฟลเดอร์ที่เลือก. สำหรับ App folder ให้ตรวจใต้ `Apps/<ชื่อแอป>/X2Telegram`; สำหรับ Full Dropbox ให้ตรวจ `/X2Telegram`.
3. ตรวจชื่อไฟล์ด้วย: X2Telegram เติม content fingerprint และใช้โหมด `add`/ห้ามเขียนทับ เพื่อให้เนื้อหาต่างเวอร์ชันไม่ทับชื่อไฟล์เดิม.

การทดสอบขนาดใหญ่จริงยังจำเป็นเพื่อยืนยันเส้นทาง network/runtime กับบัญชี Dropbox นี้โดยเฉพาะ; automated test ยืนยันลำดับ start → append → finish และการ refresh ในโค้ดแล้วเท่านั้น

## 5. X2Telegram จัดการไฟล์ใหญ่อย่างไร

- ไฟล์ขนาดไม่เกิน **150 MiB** ใช้ `files/upload` ในคำขอเดียว.
- ไฟล์ที่ใหญ่กว่า **150 MiB** ใช้ Dropbox upload session: `upload_session/start` → `append_v2` ตาม offset → `finish` เพื่อ commit ไปยัง path ที่กำหนด.
- ขนาด chunk ของ connector คือ **8 MiB**; ต่ำกว่าเพดาน Dropbox ที่ระบุว่าแต่ละ request ใน session ต้องไม่เกิน **150 MiB**. Dropbox ระบุอายุ upload session สูงสุด 7 วันและเพดานไฟล์สูงสุดประมาณ 2 TiB; สำหรับ X2Telegram เพดาน media ที่ตั้งไว้คือ 2,000 MB ต่อไฟล์ ซึ่งเป็นข้อจำกัดที่ควรยึดตามจริง.
- Connector จะ retry network errors และ HTTP 429/5xx ตามนโยบายในโค้ด; สำหรับ HTTP 429 จะอิงค่า `Retry-After` (จำกัดการรอในแต่ละครั้ง). การยกเลิก workflow ไม่ได้หมายความว่าจะ resume session จาก runner ใหม่ได้เสมอ.

อ้างอิง endpoint ทางการ: [Upload Session Start](https://docs.dropboxapi.com/dropbox-api/api-reference/user-endpoints/files/upload-session-start), [Append v2](https://docs.dropboxapi.com/dropbox-api/api-reference/user-endpoints/files/upload-session-append-v-2), [Upload Session Finish](https://docs.dropboxapi.com/dropbox-api/api-reference/user-endpoints/files/upload-session-finish), และ [Data transport limit](https://docs.dropboxapi.com/dropbox-api/docs/technical-reference/data-transport-limit).

## แก้ปัญหาเบื้องต้น

| อาการ | ตรวจสอบ |
|---|---|
| `dropbox_credentials_missing` | ตรวจว่า Secret ทั้งสามชื่อ `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN` สะกดตรง และ workflow ได้รับค่าแล้ว |
| `dropbox_authentication_failed` / HTTP 401 | ตรวจ App key/secret ว่ามาจากแอปเดียวกับ refresh token; ตรวจว่า token ไม่ถูก revoke และสร้างใหม่ด้วย `token_access_type=offline` หากจำเป็น |
| `missing_scope` หรือ HTTP 403 | เปิด `files.content.write` ในแท็บ Permissions และ authorize แอปใหม่หลังเพิ่ม scope |
| HTTP 429 | ระบบจะรอตาม `Retry-After` และ retry; หากเกิดซ้ำ ให้เว้นช่วงก่อนเริ่มงานใหม่ |
| upload session / file conflict | ตรวจ workflow log/status โดยไม่เปิดเผย token; ลองใหม่เมื่อยืนยันว่า job เดิมจบแล้ว |

Dropbox OAuth ใช้ short-lived access tokens และ refresh token สำหรับ background access; เจ้าของ Dropbox ยังสามารถ revoke สิทธิ์ของแอปได้. ดู [เอกสาร OAuth ทางการ](https://docs.dropboxapi.com/dropbox-api/docs/oauth) เพิ่มเติม.
