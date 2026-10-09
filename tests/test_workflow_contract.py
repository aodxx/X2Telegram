from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/x2telegram.yml"


def test_workflow_dispatch_keeps_manual_urls_and_adds_control_inputs():
    text = WORKFLOW.read_text(encoding="utf-8")
    inputs = text.split("  workflow_dispatch:", 1)[1].split("\npermissions:", 1)[0]
    for name in ("url", "urls", "destinations", "large_file_mode", "request_id", "job_id"):
        assert f"      {name}:" in inputs
    assert 'description: "One or more X post URLs, one per line (Dashboard batch or manual input)"' in inputs
    assert "default: '[\"telegram\"]'" in inputs


def test_workflow_requires_exactly_one_url_input_and_correlates_job():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'test -z "$INPUT_URLS" || (echo "Provide url or urls, not both"' in text
    assert 'echo "Provide url or urls"' in text
    assert 'JOB_ID: ${{ inputs.job_id }}' in text
    assert 'REQUEST_ID: ${{ inputs.request_id }}' in text
    assert 'X2Telegram {0} {1}' in text


def test_workflow_keeps_megacredentials_server_side_and_uploads_download_artifact():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "MEGA_EMAIL: ${{ secrets.MEGA_EMAIL }}" in text
    assert "MEGA_PASSWORD: ${{ secrets.MEGA_PASSWORD }}" in text
    assert "MEGA_TOTP_SECRET: ${{ secrets.MEGA_TOTP_SECRET }}" in text
    assert "MEGA_REMOTE_FOLDER: ${{ vars.MEGA_REMOTE_FOLDER || 'X2Telegram' }}" in text
    assert "DESTINATIONS_JSON: ${{ inputs.destinations" in text
    assert "name: x2telegram-media-${{ github.run_id }}" in text
    assert "compression-level: 0" in text
    assert "retention-days: 7" in text


def test_workflow_keeps_dropbox_oauth_credentials_server_side():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "DROPBOX_ACCESS_TOKEN: ${{ secrets.DROPBOX_ACCESS_TOKEN }}" in text
    assert "DROPBOX_REFRESH_TOKEN: ${{ secrets.DROPBOX_REFRESH_TOKEN }}" in text
    assert "DROPBOX_APP_KEY: ${{ secrets.DROPBOX_APP_KEY }}" in text
    assert "DROPBOX_APP_SECRET: ${{ secrets.DROPBOX_APP_SECRET }}" in text
    assert "DROPBOX_REMOTE_FOLDER: ${{ vars.DROPBOX_REMOTE_FOLDER || 'X2Telegram' }}" in text
    assert "contains(fromJSON(inputs.destinations || '[\"telegram\"]'), 'dropbox')" in text


def test_media_processing_job_has_read_only_contents_permission():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in text
    send_media = text.split("  send-media:", 1)[1].split("  persist-state:", 1)[0]
    assert "persist-credentials: false" in send_media
    assert "git push" not in send_media


def test_dedupe_state_is_transferred_to_a_separate_write_job():
    text = WORKFLOW.read_text(encoding="utf-8")
    persist_state = text.split("  persist-state:", 1)[1]
    assert "needs: send-media" in persist_state
    assert "if: always()" in persist_state
    assert "permissions:\n      contents: write" in persist_state
    assert "actions/upload-artifact" in text
    assert "actions/download-artifact" in persist_state
    assert "state/dedupe.json" in persist_state
    assert "git push" in persist_state
