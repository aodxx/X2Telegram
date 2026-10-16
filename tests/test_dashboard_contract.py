from pathlib import Path


WEB = Path(__file__).resolve().parents[1] / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")


def test_github_pages_entry_redirects_to_worker_hosted_dashboard():
    assert "location.hostname === 'aodxx.github.io'" in HTML
    assert "location.replace('https://x2telegram-control-plane.pantipa3826.workers.dev/')" in HTML


def test_dashboard_checks_authenticated_access_session_before_enabling_submit():
    assert "api('/auth/check')" in HTML
    assert "data.authenticated === true" in HTML
    assert "!backendReady" in HTML
    assert "window.addEventListener('focus'" in HTML


def test_dashboard_accepts_batches_with_a_200_url_ceiling():
    assert "const MAX_BATCH_URLS = 200" in HTML
    assert "function makeJobPayload(urlList, largeFileMode, requestId, destinations = selectedDestinations())" in HTML
    assert "if (urlList.length === 1) payload.url = urlList[0]" in HTML
    assert "else payload.urls = urlList" in HTML
    assert "makeJobPayload(r.validLines, $('largeMode').checked, makeId('dashboard'), selectedDestinations())" in HTML
    assert "lastReview.validLines.length === lastReview.lines.length" in HTML
    assert "lastReview.overLimit" in HTML


def test_dashboard_supports_multiple_destinations_and_browser_zip_download():
    assert 'id="destTelegram" type="checkbox" checked' in HTML
    assert 'id="destMega" type="checkbox"' in HTML
    assert 'id="destDownload" type="checkbox"' in HTML
    assert "destinations }" in HTML
    assert "data.download?.url" in HTML
    assert "ดาวน์โหลด ZIP" in HTML


def test_dashboard_supports_dropbox_destination():
    assert 'id="destDropbox" type="checkbox"' in HTML
    assert "['dropbox', 'destDropbox']" in HTML
    assert "dropbox: 'Dropbox'" in HTML


def test_dashboard_shows_clear_job_progress_and_human_readable_statuses():
    assert 'id="jobStepper"' in HTML
    assert 'data-stage="1"' in HTML
    assert 'data-stage="4"' in HTML
    assert 'id="progressTrack" role="progressbar"' in HTML
    assert 'id="runDescription"' in HTML
    assert "รับงานแล้ว" in HTML
    assert "กำลังทำงาน" in HTML
    assert "งานเสร็จแล้ว" in HTML
    assert "aria-valuenow" in HTML


def test_dashboard_hides_internal_implementation_explanations_from_main_page():
    assert "yt-dlp → syndication → FxTwitter" not in HTML
    assert "หลักการระบบ" not in HTML
    assert "กลุ่ม Telegram ที่กำหนดตายตัว" not in HTML
    assert 'href="https://github.com/aodxx/X2Telegram/actions/workflows/x2telegram.yml"' not in HTML


def test_dashboard_explains_source_error_stage_and_input_duplicates_without_raw_values():
    assert "media_too_large: 'ไฟล์ใหญ่เกินกำหนด'" in HTML
    assert "source_rate_limited: 'แหล่งต้นทางจำกัดคำขอ'" in HTML
    assert "stageNames" in HTML and "ดาวน์โหลดสื่อ" in HTML
    assert "report.input_summary" in HTML
    assert "normalized_duplicate" in HTML
    assert "ประมวลผลโพสต์นี้ครั้งเดียว" in HTML


def test_dashboard_translates_actionable_source_errors_into_thai_guidance():
    assert "function humanError(code, raw, destination = '')" in HTML
    assert "โพสต์อาจถูกลบ ตั้งเป็นส่วนตัว หรือ X ไม่ส่งข้อมูลชั่วคราว" in HTML
    assert "โพสต์นี้ไม่มีรูปหรือวิดีโอที่ระบบรองรับ" in HTML
    assert "ตรวจว่าโพสต์เป็นสาธารณะแล้วลองใหม่" in HTML
    assert "ส่งไป Dropbox ไม่สำเร็จ ลองใหม่อีกครั้ง" in HTML


def test_dashboard_distinguishes_partial_completion_from_total_failure():
    assert "function reportOutcome(report)" in HTML
    assert "เสร็จบางส่วน" in HTML
    assert "จัดการแล้ว ${handled} รายการ แต่ยังมี ${attention} รายการ" in HTML
    assert "status-badge[data-state=\"partial_success\"]" in HTML


def test_dashboard_shows_selected_media_quality_and_counts_no_media_as_attention():
    assert "function mediaQualityText(manifest)" in HTML
    assert "พิกเซล" in HTML and "kbps" in HTML and "คุณภาพไฟล์:" in HTML
    assert "const noMedia = Number(summary.no_media || 0)" in HTML
    assert "const attention = failed + noMedia + uncertain" in HTML
