/**
 * X2Telegram Google Apps Script control-plane API.
 *
 * Deploy this project as a Web app. Keep all Script Properties private:
 * GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO, GITHUB_WORKFLOW_ID,
 * GITHUB_REF, ALLOWED_EMAILS, and MAX_URLS.
 *
 * The script starts GitHub Actions, polls workflow status, and reads only the
 * sanitized dashboard artifact. Telegram credentials remain in GitHub Actions.
 */

const API_VERSION = '1';
const DEFAULT_OWNER = 'aodxx';
const DEFAULT_REPO = 'X2Telegram';
const DEFAULT_WORKFLOW_ID = 'x2telegram.yml';
const DEFAULT_REF = 'main';
const DEFAULT_MAX_URLS = 20;
const IDEMPOTENCY_TTL_SECONDS = 21600; // 6 hours
const REPORT_CACHE_TTL_SECONDS = 300; // 5 minutes

function doGet(e) {
  return handleRequest_(function () {
    requireAuthorizedUser_();
    const params = (e && e.parameter) || {};
    const action = String(params.action || 'health').toLowerCase();
    if (action === 'health') return health_();
    if (action === 'status') return status_(params);
    if (action === 'report') return report_(params);
    throw apiError_('unknown_action', 'Supported actions: health, status, report');
  });
}

function doPost(e) {
  return handleRequest_(function () {
    requireAuthorizedUser_();
    const body = parseJsonBody_(e);
    const action = String(body.action || 'start').toLowerCase();
    if (action === 'start') return start_(body);
    throw apiError_('unknown_action', 'Supported POST action: start');
  });
}

function handleRequest_(handler) {
  try {
    const data = handler();
    return jsonResponse_({ ok: true, api_version: API_VERSION, data: data });
  } catch (err) {
    const safe = err && err.apiCode ? err : apiError_('internal_error', 'Backend request failed');
    console.error(safe.apiCode + ': ' + safe.message);
    return jsonResponse_({
      ok: false,
      api_version: API_VERSION,
      error: { code: safe.apiCode, message: safe.message }
    });
  }
}

function health_() {
  const config = getConfig_();
  return {
    service: 'x2telegram-gas-backend',
    status: 'ok',
    github_repository: config.owner + '/' + config.repo,
    workflow_id: config.workflowId,
    ref: config.ref
  };
}

function start_(body) {
  const config = getConfig_();
  const parsed = validateUrls_(body.urls, config.maxUrls);
  const largeFileMode = parseBoolean_(body.large_file_mode);
  const idempotencyKey = validateIdempotencyKey_(body.idempotency_key);
  const requestId = validateRequestId_(body.request_id) || makeRequestId_();
  const cache = CacheService.getScriptCache();
  const cacheKey = idempotencyKey ? 'idem:' + hash_(currentUser_() + ':' + idempotencyKey) : '';

  if (cacheKey) {
    const previous = cache.get(cacheKey);
    if (previous) return JSON.parse(previous);
  }

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) throw apiError_('busy', 'Another request is being started; try again shortly');
  try {
    if (cacheKey) {
      const previous = cache.get(cacheKey);
      if (previous) return JSON.parse(previous);
    }

    const dispatchStartedAt = new Date().toISOString();
    dispatchWorkflow_(config, parsed.normalizedUrls, largeFileMode, requestId);
    const run = findRun_(config, requestId, dispatchStartedAt);
    const result = {
      request_id: requestId,
      run_id: run ? String(run.id) : null,
      status: run ? normalizeRunStatus_(run) : 'queued',
      html_url: run ? run.html_url || null : null
    };
    if (cacheKey) cache.put(cacheKey, JSON.stringify(result), IDEMPOTENCY_TTL_SECONDS);
    return result;
  } finally {
    lock.releaseLock();
  }
}

function status_(params) {
  const config = getConfig_();
  const run = resolveRun_(config, params.run_id, params.request_id);
  if (!run) throw apiError_('run_not_found', 'Workflow run was not found');
  return {
    request_id: params.request_id || null,
    run_id: String(run.id),
    status: normalizeRunStatus_(run),
    conclusion: run.conclusion || null,
    html_url: run.html_url || null,
    created_at: run.created_at || null,
    started_at: run.run_started_at || null,
    updated_at: run.updated_at || null,
    completed: run.status === 'completed',
    report_available: run.status === 'completed' && run.conclusion === 'success'
  };
}

function report_(params) {
  const config = getConfig_();
  const run = resolveRun_(config, params.run_id, params.request_id);
  if (!run) throw apiError_('run_not_found', 'Workflow run was not found');
  if (run.status !== 'completed') {
    return { run_id: String(run.id), status: normalizeRunStatus_(run), report: null };
  }
  const cache = CacheService.getScriptCache();
  const cacheKey = 'report:' + String(run.id);
  const cached = cache.get(cacheKey);
  if (cached) return { run_id: String(run.id), status: normalizeRunStatus_(run), report: JSON.parse(cached) };
  const report = downloadDashboardReport_(config, run.id);
  cache.put(cacheKey, JSON.stringify(report), REPORT_CACHE_TTL_SECONDS);
  return { run_id: String(run.id), status: normalizeRunStatus_(run), report: report };
}

function dispatchWorkflow_(config, urls, largeFileMode, requestId) {
  const path = '/repos/' + encodeURIComponent(config.owner) + '/' + encodeURIComponent(config.repo) +
    '/actions/workflows/' + encodeURIComponent(config.workflowId) + '/dispatches';
  githubRequest_(config, path, 'post', {
    ref: config.ref,
    inputs: {
      urls: urls.join('\n'),
      large_file_mode: largeFileMode ? 'true' : 'false',
      request_id: requestId
    }
  }, [204]);
}

function findRun_(config, requestId, notBefore) {
  for (let attempt = 0; attempt < 4; attempt++) {
    const runs = listRuns_(config);
    const match = runs.find(function (run) {
      const title = String(run.display_title || run.name || '');
      return title.indexOf(requestId) !== -1 && (!notBefore || String(run.created_at) >= notBefore);
    });
    if (match) return match;
    Utilities.sleep(1000);
  }
  return null;
}

function listRuns_(config) {
  const path = '/repos/' + encodeURIComponent(config.owner) + '/' + encodeURIComponent(config.repo) +
    '/actions/workflows/' + encodeURIComponent(config.workflowId) + '/runs?event=workflow_dispatch&branch=' +
    encodeURIComponent(config.ref) + '&per_page=30';
  const data = githubRequest_(config, path, 'get', null, [200]);
  return Array.isArray(data.workflow_runs) ? data.workflow_runs : [];
}

function resolveRun_(config, runId, requestId) {
  if (runId) {
    const path = '/repos/' + encodeURIComponent(config.owner) + '/' + encodeURIComponent(config.repo) +
      '/actions/runs/' + encodeURIComponent(String(runId));
    return githubRequest_(config, path, 'get', null, [200]);
  }
  if (requestId) return findRun_(config, validateRequestId_(requestId), null);
  throw apiError_('missing_run_identifier', 'Provide run_id or request_id');
}

function downloadDashboardReport_(config, runId) {
  const path = '/repos/' + encodeURIComponent(config.owner) + '/' + encodeURIComponent(config.repo) +
    '/actions/runs/' + encodeURIComponent(String(runId)) + '/artifacts?per_page=100';
  const data = githubRequest_(config, path, 'get', null, [200]);
  const expectedName = 'x2telegram-dashboard-report-' + String(runId);
  const artifact = (data.artifacts || []).find(function (item) {
    return item.name === expectedName && !item.expired;
  });
  if (!artifact) throw apiError_('report_not_found', 'Dashboard report artifact is not available yet');

  const response = githubRawRequest_(config, artifact.archive_download_url, 'get', true);
  let blob = response.getBlob();
  const code = response.getResponseCode();
  if (code >= 300 && code < 400) {
    const location = response.getHeaders().Location || response.getHeaders().location;
    if (!location) throw apiError_('artifact_download_failed', 'GitHub did not provide an artifact redirect');
    blob = UrlFetchApp.fetch(location, { muteHttpExceptions: true, followRedirects: true }).getBlob();
  } else if (code !== 200) {
    throw apiError_('artifact_download_failed', 'GitHub artifact download failed');
  }

  const files = Utilities.unzip(blob);
  const reportFile = files.find(function (file) {
    return /(^|\/)dashboard-report\.json$/i.test(file.getName());
  });
  if (!reportFile) throw apiError_('invalid_report', 'Dashboard report file is missing from artifact');
  let report;
  try {
    report = JSON.parse(reportFile.getDataAsString('UTF-8'));
  } catch (err) {
    throw apiError_('invalid_report', 'Dashboard report is not valid JSON');
  }
  if (!report || typeof report !== 'object' || !Array.isArray(report.results)) {
    throw apiError_('invalid_report', 'Dashboard report has an invalid schema');
  }
  return report;
}

function githubRequest_(config, path, method, payload, acceptedCodes) {
  const response = githubRawRequest_(config, config.apiBase + path, method, false, payload);
  const code = response.getResponseCode();
  if (acceptedCodes.indexOf(code) === -1) {
    let message = 'GitHub API request failed';
    try {
      const body = JSON.parse(response.getContentText());
      if (body.message) message = String(body.message).slice(0, 200);
    } catch (ignore) {}
    throw apiError_('github_api_error', message);
  }
  if (code === 204 || !response.getContentText()) return {};
  try { return JSON.parse(response.getContentText()); } catch (err) {
    throw apiError_('github_api_error', 'GitHub returned invalid JSON');
  }
}

function githubRawRequest_(config, url, method, isArtifactDownload, payload) {
  const options = {
    method: method,
    muteHttpExceptions: true,
    followRedirects: !isArtifactDownload,
    headers: {
      Authorization: 'Bearer ' + config.token,
      Accept: isArtifactDownload ? 'application/vnd.github+json' : 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28'
    }
  };
  if (payload !== null && payload !== undefined) {
    options.contentType = 'application/json';
    options.payload = JSON.stringify(payload);
  }
  return UrlFetchApp.fetch(url, options);
}

function validateUrls_(value, maxUrls) {
  if (!Array.isArray(value)) throw apiError_('invalid_urls', 'urls must be an array');
  const lines = value.map(function (item) { return String(item || '').trim(); }).filter(Boolean);
  if (!lines.length) throw apiError_('invalid_urls', 'At least one X URL is required');
  if (lines.length > maxUrls) throw apiError_('too_many_urls', 'Maximum URLs per request: ' + maxUrls);
  const seen = {};
  const normalizedUrls = [];
  lines.forEach(function (line) {
    const match = line.match(/^(?:https?:\/\/)?(?:www\.)?(x\.com|twitter\.com)\/([^\/]+)\/status\/(\d+)(?:[/?#].*)?$/i);
    if (!match) throw apiError_('invalid_url', 'Every URL must be a public x.com or twitter.com status URL');
    const normalized = 'https://x.com/' + match[2] + '/status/' + match[3];
    if (!seen[match[3]]) { seen[match[3]] = true; normalizedUrls.push(normalized); }
  });
  return { normalizedUrls: normalizedUrls };
}

function parseBoolean_(value) {
  if (value === true || value === 'true' || value === 1 || value === '1') return true;
  if (value === false || value === 'false' || value === 0 || value === '0' || value === undefined) return false;
  throw apiError_('invalid_large_file_mode', 'large_file_mode must be boolean');
}

function validateRequestId_(value) {
  if (value === undefined || value === null || value === '') return null;
  const candidate = String(value);
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(candidate)) {
    throw apiError_('invalid_request_id', 'request_id contains unsupported characters');
  }
  return candidate;
}

function validateIdempotencyKey_(value) {
  if (value === undefined || value === null || value === '') return null;
  const candidate = String(value);
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(candidate)) {
    throw apiError_('invalid_idempotency_key', 'idempotency_key contains unsupported characters');
  }
  return candidate;
}

function normalizeRunStatus_(run) {
  if (run.status === 'completed') return run.conclusion || 'completed';
  return run.status || 'unknown';
}

function getConfig_() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('GITHUB_TOKEN');
  const owner = props.getProperty('GITHUB_OWNER') || DEFAULT_OWNER;
  const repo = props.getProperty('GITHUB_REPO') || DEFAULT_REPO;
  if (!token) throw apiError_('backend_not_configured', 'GITHUB_TOKEN is missing');
  const maxUrls = Number(props.getProperty('MAX_URLS') || DEFAULT_MAX_URLS);
  if (!isFinite(maxUrls) || maxUrls < 1 || maxUrls > 100) throw apiError_('backend_not_configured', 'MAX_URLS must be between 1 and 100');
  return {
    token: token,
    owner: owner,
    repo: repo,
    workflowId: props.getProperty('GITHUB_WORKFLOW_ID') || DEFAULT_WORKFLOW_ID,
    ref: props.getProperty('GITHUB_REF') || DEFAULT_REF,
    maxUrls: Math.floor(maxUrls),
    apiBase: 'https://api.github.com'
  };
}

function requireAuthorizedUser_() {
  const allowed = (PropertiesService.getScriptProperties().getProperty('ALLOWED_EMAILS') || '')
    .split(',').map(function (email) { return email.trim().toLowerCase(); }).filter(Boolean);
  const email = currentUser_();
  if (!allowed.length || !email || allowed.indexOf(email) === -1) {
    throw apiError_('unauthorized', 'This private backend is not available to this user');
  }
}

function currentUser_() {
  return String(Session.getActiveUser().getEmail() || '').trim().toLowerCase();
}

function parseJsonBody_(e) {
  if (!e || !e.postData || !e.postData.contents) throw apiError_('invalid_json', 'A JSON request body is required');
  try { return JSON.parse(e.postData.contents); } catch (err) { throw apiError_('invalid_json', 'Request body must be valid JSON'); }
}

function makeRequestId_() {
  return 'gas-' + Utilities.getUuid().replace(/-/g, '').slice(0, 24);
}

function hash_(value) {
  const bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, value, Utilities.Charset.UTF_8);
  return bytes.map(function (byte) { const n = byte < 0 ? byte + 256 : byte; return ('0' + n.toString(16)).slice(-2); }).join('');
}

function apiError_(code, message) {
  const err = new Error(message);
  err.apiCode = code;
  return err;
}

function jsonResponse_(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(ContentService.MimeType.JSON);
}
