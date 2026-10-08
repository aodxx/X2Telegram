from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/x2telegram.yml"


def test_workflow_dispatch_keeps_manual_urls_and_adds_control_inputs():
    text = WORKFLOW.read_text(encoding="utf-8")
    inputs = text.split("  workflow_dispatch:", 1)[1].split("\npermissions:", 1)[0]
    for name in ("url", "urls", "large_file_mode", "request_id", "job_id"):
        assert f"      {name}:" in inputs
    assert 'description: "One or more X post URLs, one per line (Dashboard batch or manual input)"' in inputs


def test_workflow_requires_exactly_one_url_input_and_correlates_job():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'test -z "$INPUT_URLS" || (echo "Provide url or urls, not both"' in text
    assert 'echo "Provide url or urls"' in text
    assert 'JOB_ID: ${{ inputs.job_id }}' in text
    assert 'REQUEST_ID: ${{ inputs.request_id }}' in text
    assert 'X2Telegram {0} {1}' in text
