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


def test_dashboard_accepts_batches_with_a_50_url_ceiling():
    assert "const MAX_BATCH_URLS = 50" in HTML
    assert "function makeJobPayload(urlList, largeFileMode, requestId, destinations = selectedDestinations())" in HTML
    assert "if (urlList.length === 1) payload.url = urlList[0]" in HTML
    assert "else payload.urls = urlList" in HTML
    assert "makeJobPayload(r.validLines, $('largeMode').checked, requestId, selectedDestinations())" in HTML
    assert "lastReview.validLines.length === lastReview.lines.length" in HTML
    assert "lastReview.overLimit" in HTML


def test_dashboard_supports_multiple_destinations_and_browser_zip_download():
    assert 'id="destTelegram" type="checkbox" checked' in HTML
    assert 'id="destMega" type="checkbox"' in HTML
    assert 'id="destDownload" type="checkbox"' in HTML
    assert "destinations }" in HTML
    assert "data.download?.url" in HTML
    assert "Browser download" in HTML


def test_dashboard_supports_dropbox_destination():
    assert 'id="destDropbox" type="checkbox"' in HTML
    assert "['dropbox', 'destDropbox']" in HTML
    assert "dropbox: 'Dropbox'" in HTML
