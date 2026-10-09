import { unzipSync } from "fflate";

const RUNS_LIMIT = 100;
const BODY_LIMIT = 16 * 1024;
const RATE_WINDOW_MS = 60_000;
const RATE_LIMIT = 20;
const MAX_BATCH_URLS = 50;
const attemptsByIdentity = new Map();
let jwksCache = { until: 0, keys: [] };

function json(data, status, request, env, extraHeaders = {}) {
  const headers = new Headers({
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    ...extraHeaders,
  });
  const origin = request.headers.get("Origin");
  if (origin && origin === env.DASHBOARD_ORIGIN) {
    headers.set("Access-Control-Allow-Origin", origin);
    headers.set("Access-Control-Allow-Credentials", "true");
    headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    headers.set("Access-Control-Allow-Headers", "Content-Type");
    headers.set("Access-Control-Max-Age", "600");
    headers.append("Vary", "Origin");
  }
  return new Response(JSON.stringify(data), { status, headers });
}

function errorResponse(request, env, status, code, message, requestId = null) {
  return json({ error: { code, message }, request_id: requestId }, status, request, env);
}

function decodeBase64Url(value) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((value.length + 3) % 4);
  const raw = atob(padded);
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

function decodeJsonSegment(segment) {
  return JSON.parse(new TextDecoder().decode(decodeBase64Url(segment)));
}

async function getAccessKeys(teamDomain) {
  const now = Date.now();
  if (jwksCache.until > now && jwksCache.keys.length) return jwksCache.keys;
  const url = new URL("/cdn-cgi/access/certs", teamDomain);
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("jwks_unavailable");
  const payload = await response.json();
  if (!Array.isArray(payload.keys)) throw new Error("jwks_invalid");
  jwksCache = { until: now + 5 * 60_000, keys: payload.keys };
  return jwksCache.keys;
}

async function verifyAccess(request, env) {
  if (!env.ACCESS_TEAM_DOMAIN || !env.ACCESS_AUD || !env.ACCESS_ALLOWED_EMAIL) {
    return { ok: false, status: 503, code: "access_not_configured", message: "Cloudflare Access is not configured" };
  }
  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) return { ok: false, status: 401, code: "unauthorized", message: "Cloudflare Access authentication is required" };
  try {
    const parts = token.split(".");
    if (parts.length !== 3) throw new Error("token_format");
    const header = decodeJsonSegment(parts[0]);
    const claims = decodeJsonSegment(parts[1]);
    if (header.alg !== "RS256" || typeof header.kid !== "string") throw new Error("token_algorithm");
    const teamDomain = env.ACCESS_TEAM_DOMAIN.replace(/\/$/, "");
    if (claims.iss !== teamDomain) throw new Error("token_issuer");
    const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
    if (!aud.includes(env.ACCESS_AUD)) throw new Error("token_audience");
    const now = Math.floor(Date.now() / 1000);
    if (typeof claims.exp !== "number" || claims.exp <= now || (claims.nbf && claims.nbf > now + 60)) throw new Error("token_time");
    const jwk = (await getAccessKeys(teamDomain)).find((key) => key.kid === header.kid && key.kty === "RSA");
    if (!jwk) throw new Error("token_key");
    const publicKey = await crypto.subtle.importKey(
      "jwk", { kty: jwk.kty, n: jwk.n, e: jwk.e, alg: "RS256", ext: true },
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"],
    );
    const valid = await crypto.subtle.verify(
      "RSASSA-PKCS1-v1_5", publicKey, decodeBase64Url(parts[2]),
      new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
    );
    if (!valid) throw new Error("token_signature");
    const email = String(claims.email || "").toLowerCase();
    if (!email || email !== env.ACCESS_ALLOWED_EMAIL.toLowerCase()) {
      return { ok: false, status: 403, code: "forbidden", message: "This identity is not allowed" };
    }
    return { ok: true, email };
  } catch (_) {
    return { ok: false, status: 401, code: "unauthorized", message: "Cloudflare Access token is invalid or expired" };
  }
}

function allowedUrl(value) {
  if (typeof value !== "string" || value.length > 2048) return null;
  let parsed;
  try { parsed = new URL(value); } catch (_) { return null; }
  const hosts = new Set(["x.com", "www.x.com", "mobile.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"]);
  if (parsed.protocol !== "https:" || !hosts.has(parsed.hostname.toLowerCase()) || parsed.username || parsed.password) return null;
  const match = parsed.pathname.match(/^\/(?:.+\/)?status\/(\d+)\/?$/i);
  if (!match) return null;
  const prefix = parsed.pathname.slice(1, parsed.pathname.toLowerCase().lastIndexOf("/status/"));
  const username = prefix.split("/").filter(Boolean).at(-1);
  if (!username || username.length > 64 || username.includes(".")) return null;
  return { url: `https://x.com/${username}/status/${match[1]}`, postId: match[1] };
}

function validRequestId(value) {
  return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value);
}

async function makeJobId(requestId, urls, largeFileMode, destinations) {
  const material = new TextEncoder().encode(`${requestId}\n${urls.join("\n")}\n${largeFileMode ? "1" : "0"}\n${destinations.join(",")}`);
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", material));
  const hex = [...digest].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `job-${hex.slice(0, 32)}`;
}

function checkRate(email) {
  const now = Date.now();
  const old = attemptsByIdentity.get(email);
  if (!old || now - old.start >= RATE_WINDOW_MS) {
    attemptsByIdentity.set(email, { start: now, count: 1 });
    return true;
  }
  old.count += 1;
  return old.count <= RATE_LIMIT;
}

function githubConfigError(env) {
  return !env.GH_TOKEN || !env.GH_OWNER || !env.GH_REPO || !env.GH_WORKFLOW_ID || !env.GH_REF;
}

async function readBoundedBody(request) {
  const reader = request.body?.getReader();
  if (!reader) return { raw: "" };
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > BODY_LIMIT) {
        try { await reader.cancel(); } catch (_) { /* the size limit still applies */ }
        return { tooLarge: true };
      }
      chunks.push(value);
    }
  } catch (_) {
    return { invalid: true };
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return { raw: new TextDecoder("utf-8", { fatal: true }).decode(bytes) };
  } catch (_) {
    return { invalid: true };
  }
}

async function github(env, path, options = {}) {
  const response = await fetch(`https://api.github.com${path}`, {
    ...options,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env.GH_TOKEN}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "X2Telegram-Control-Worker",
      ...(options.headers || {}),
    },
  });
  if (response.status === 204) return null;
  if (!response.ok) throw new Error(`github_http_${response.status}`);
  return response.json();
}

function workflowPath(env, suffix = "") {
  return `/repos/${encodeURIComponent(env.GH_OWNER)}/${encodeURIComponent(env.GH_REPO)}/actions/workflows/${encodeURIComponent(env.GH_WORKFLOW_ID)}${suffix}`;
}

async function workflowRuns(env) {
  const query = new URLSearchParams({ event: "workflow_dispatch", branch: env.GH_REF, per_page: String(RUNS_LIMIT) });
  const data = await github(env, `${workflowPath(env, "/runs")}?${query}`);
  return Array.isArray(data?.workflow_runs) ? data.workflow_runs : [];
}

function runTitle(run) {
  return String(run.display_title || run.name || "");
}

function findRunForJob(runs, jobId) {
  return runs.find((run) => runTitle(run).endsWith(` ${jobId}`)) || null;
}

function hasRequestIdConflict(runs, requestId, jobId) {
  const prefix = `X2Telegram ${requestId} `;
  return runs.some((run) => runTitle(run).startsWith(prefix) && !runTitle(run).endsWith(` ${jobId}`));
}

async function dispatch(request, env, identity) {
  if (githubConfigError(env)) return errorResponse(request, env, 503, "backend_not_configured", "Control Worker is missing server configuration");
  if (!checkRate(identity.email)) return errorResponse(request, env, 429, "rate_limited", "Too many requests; retry later");
  const length = Number(request.headers.get("Content-Length") || 0);
  if (Number.isFinite(length) && length > BODY_LIMIT) return errorResponse(request, env, 413, "request_too_large", "Request body is too large");
  const bodyRead = await readBoundedBody(request);
  if (bodyRead.tooLarge) return errorResponse(request, env, 413, "request_too_large", "Request body is too large");
  if (bodyRead.invalid) return errorResponse(request, env, 400, "invalid_json", "Request body must be valid UTF-8 JSON");
  const raw = bodyRead.raw;
  let body;
  try { body = JSON.parse(raw); } catch (_) { return errorResponse(request, env, 400, "invalid_json", "Request body must be valid JSON"); }
  if (!body || typeof body !== "object" || Array.isArray(body)) return errorResponse(request, env, 400, "invalid_request", "Request must be a JSON object");
  if (Object.keys(body).some((key) => !["url", "urls", "large_file_mode", "request_id", "destinations"].includes(key))) return errorResponse(request, env, 400, "invalid_request", "Request contains unsupported fields");
  const hasSingleUrl = Object.hasOwn(body, "url");
  const hasUrlList = Object.hasOwn(body, "urls");
  if (hasSingleUrl === hasUrlList) return errorResponse(request, env, 400, "invalid_request", "Provide exactly one of url or urls");
  const rawUrls = hasSingleUrl ? [body.url] : body.urls;
  if (!Array.isArray(rawUrls) || rawUrls.length === 0) return errorResponse(request, env, 400, "invalid_url_list", "Provide at least one X post URL");
  if (rawUrls.length > MAX_BATCH_URLS) return errorResponse(request, env, 400, "too_many_urls", `A batch can contain at most ${MAX_BATCH_URLS} URLs`);
  if (!validRequestId(body.request_id)) return errorResponse(request, env, 400, "invalid_request_id", "request_id is missing or invalid");
  if (body.large_file_mode !== undefined && typeof body.large_file_mode !== "boolean") return errorResponse(request, env, 400, "invalid_large_file_mode", "large_file_mode must be a boolean", body.request_id);
  const allowedDestinations = ["telegram", "mega", "dropbox", "download"];
  const rawDestinations = body.destinations === undefined ? ["telegram"] : body.destinations;
  if (!Array.isArray(rawDestinations) || rawDestinations.length < 1 || rawDestinations.length > allowedDestinations.length || rawDestinations.some((item) => typeof item !== "string" || !allowedDestinations.includes(item)) || new Set(rawDestinations).size !== rawDestinations.length) {
    return errorResponse(request, env, 400, "invalid_destinations", "Select one or more supported destinations", body.request_id);
  }
  const destinations = allowedDestinations.filter((item) => rawDestinations.includes(item));
  const normalizedUrls = [];
  const postIds = new Set();
  for (const value of rawUrls) {
    const normalized = allowedUrl(value);
    if (!normalized) return errorResponse(request, env, 400, "invalid_url", "Every URL must be a public HTTPS X post URL", body.request_id);
    if (postIds.has(normalized.postId)) return errorResponse(request, env, 400, "duplicate_url", "Remove duplicate X post URLs from the batch", body.request_id);
    postIds.add(normalized.postId);
    normalizedUrls.push(normalized.url);
  }
  const largeFileMode = body.large_file_mode === true;
  const jobId = await makeJobId(body.request_id, normalizedUrls, largeFileMode, destinations);
  let runs;
  try { runs = await workflowRuns(env); } catch (_) { return errorResponse(request, env, 502, "github_read_failed", "Could not check existing workflow jobs", body.request_id); }
  const existing = findRunForJob(runs, jobId);
  if (existing) return json(await jobPayload(existing, jobId, body.request_id, env, true), 200, request, env);
  if (hasRequestIdConflict(runs, body.request_id, jobId)) return errorResponse(request, env, 409, "idempotency_conflict", "request_id was already used with a different payload", body.request_id);
  try {
    await github(env, `${workflowPath(env, "/dispatches")}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ref: env.GH_REF,
        inputs: {
          ...(normalizedUrls.length === 1 ? { url: normalizedUrls[0] } : { urls: normalizedUrls.join("\n") }),
          large_file_mode: String(largeFileMode),
          destinations: JSON.stringify(destinations),
          request_id: body.request_id,
          job_id: jobId,
        },
      }),
    });
  } catch (_) { return errorResponse(request, env, 502, "github_dispatch_failed", "GitHub Actions could not accept the job", body.request_id); }
  const now = new Date().toISOString();
  return json({
    job_id: jobId, request_id: body.request_id, url_count: normalizedUrls.length, destinations, state: "accepted", created_at: now, updated_at: now,
    progress: { phase: "queued", percent: 0 }, result: null, error: null, telegram: null, duplicate: false,
  }, 202, request, env);
}

async function runArtifacts(env, runId) {
  const data = await github(env, `/repos/${encodeURIComponent(env.GH_OWNER)}/${encodeURIComponent(env.GH_REPO)}/actions/runs/${encodeURIComponent(String(runId))}/artifacts?per_page=100`);
  return Array.isArray(data?.artifacts) ? data.artifacts : [];
}

async function downloadArtifact(env, runId) {
  const artifacts = await runArtifacts(env, runId);
  const artifactName = `x2telegram-dashboard-report-${runId}`;
  const artifact = artifacts.find((item) => item.name === artifactName && !item.expired);
  if (!artifact) return null;
  const apiUrl = `https://api.github.com/repos/${encodeURIComponent(env.GH_OWNER)}/${encodeURIComponent(env.GH_REPO)}/actions/artifacts/${encodeURIComponent(String(artifact.id))}/zip`;
  const first = await fetch(apiUrl, { redirect: "manual", headers: {
    Accept: "application/vnd.github+json", Authorization: `Bearer ${env.GH_TOKEN}`,
    "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "X2Telegram-Control-Worker",
  } });
  let archiveResponse = first;
  if (first.status >= 300 && first.status < 400) {
    const location = first.headers.get("Location");
    if (!location) throw new Error("artifact_redirect_missing");
    archiveResponse = await fetch(location);
  }
  if (!archiveResponse.ok) throw new Error("artifact_download_failed");
  const files = unzipSync(new Uint8Array(await archiveResponse.arrayBuffer()));
  const filename = Object.keys(files).find((name) => name.split("/").at(-1) === "dashboard-report.json");
  if (!filename) throw new Error("report_missing");
  const report = JSON.parse(new TextDecoder().decode(files[filename]));
  if (!report || typeof report !== "object" || !Array.isArray(report.results)) throw new Error("report_schema_invalid");
  return report;
}

function downloadFileCount(report) {
  if (!Array.isArray(report?.selected_destinations) || !report.selected_destinations.includes("download")) return 0;
  return (report.results || []).reduce((total, post) => {
    const items = post?.destinations?.download?.items;
    return total + (Array.isArray(items) ? items.filter((item) => item?.status === "ready").length : 0);
  }, 0);
}

async function mediaArtifactForRun(env, runId) {
  const artifacts = await runArtifacts(env, runId);
  return artifacts.find((item) => item.name === `x2telegram-media-${runId}`) || null;
}

function markDownloadArtifactFailure(report, code, message) {
  if (!report || !Array.isArray(report.results)) return report;
  const results = report.results.map((post) => {
    const destination = post?.destinations?.download;
    if (!destination || !Array.isArray(destination.items)) return post;
    let changed = false;
    const items = destination.items.map((item) => {
      if (item?.status !== "ready") return item;
      changed = true;
      return { ...item, status: "failed", error_code: code, error: message };
    });
    if (!changed) return post;
    const destinations = { ...post.destinations, download: { ...destination, status: "failed", error_code: code, error: message, items } };
    const otherDelivered = Object.entries(destinations).some(([name, value]) =>
      name !== "download" && ["success", "ready", "duplicate", "partial_success"].includes(value?.status)
    );
    return { ...post, status: otherDelivered ? "partial_success" : "failed", error_code: code, error: message, destinations };
  });
  const destinationCounts = {};
  for (const post of results) {
    for (const [name, value] of Object.entries(post?.destinations || {})) {
      const counts = destinationCounts[name] || (destinationCounts[name] = {});
      const status = String(value?.status || "failed");
      counts[status] = (counts[status] || 0) + 1;
    }
  }
  const statuses = results.map((post) => post?.status);
  const failedStatuses = new Set(["metadata_error", "download_error", "telegram_error", "error", "failed", "partial_success"]);
  const updatedSummary = {
    ...(report.summary || {}),
    total: results.length,
    sent: statuses.filter((status) => ["sent", "success", "partial_success"].includes(status)).length,
    skipped_duplicate: statuses.filter((status) => status === "skipped_duplicate").length,
    no_media: statuses.filter((status) => status === "no_media").length,
    failed: statuses.filter((status) => failedStatuses.has(status)).length,
    destinations: destinationCounts,
  };
  const delivered = results.some((post) => Object.values(post?.destinations || {}).some((value) =>
    ["success", "ready", "duplicate", "partial_success"].includes(value?.status)
  ));
  return { ...report, status: delivered ? "partial_success" : "completed_with_errors", summary: updatedSummary, results };
}

async function jobPayload(run, jobId, requestId, env, duplicate = false) {
  const completed = run.status === "completed";
  const success = completed && run.conclusion === "success";
  const state = success ? "completed" : completed ? "failed" : duplicate ? "duplicate" : run.status === "queued" || run.status === "requested" || run.status === "waiting" ? "accepted" : "processing";
  let report = null;
  if (completed) {
    try { report = await downloadArtifact(env, run.id); } catch (_) { report = null; }
  }
  let download = null;
  const fileCount = downloadFileCount(report);
  if (completed && fileCount > 0) {
    try {
      const artifact = await mediaArtifactForRun(env, run.id);
      if (artifact && !artifact.expired) download = { available: true, status: "ready", url: `/jobs/${encodeURIComponent(jobId)}/download`, file_count: fileCount, expires_at: artifact.expires_at || null };
      else if (artifact?.expired) {
        download = { available: false, status: "expired", error_code: "download_expired", file_count: fileCount, expires_at: artifact.expires_at || null };
        report = markDownloadArtifactFailure(report, "download_expired", "The browser download artifact has expired. Start a new job to create it again.");
      } else {
        download = { available: false, status: "unavailable", error_code: "download_artifact_missing", file_count: fileCount };
        report = markDownloadArtifactFailure(report, "download_artifact_missing", "The browser download artifact could not be created. Start a new job to retry it.");
      }
    } catch (_) {
      download = { available: false, status: "checking", file_count: fileCount };
    }
  }
  const hasDeliveredDestination = (report?.results || []).some((post) =>
    Object.values(post?.destinations || {}).some((destination) => ["success", "ready", "duplicate", "partial_success"].includes(destination?.status))
  );
  const effectiveState = completed && hasDeliveredDestination ? "completed" : completed && report?.status === "completed_with_errors" ? "failed" : state;
  const allMessageIds = (report?.results || []).flatMap((item) => Array.isArray(item.message_ids) ? item.message_ids : []);
  return {
    job_id: jobId,
    request_id: requestId,
    state: effectiveState,
    created_at: run.created_at || null,
    updated_at: run.updated_at || run.run_started_at || run.created_at || null,
    progress: { phase: completed ? "completed" : state === "accepted" ? "queued" : "running", percent: completed ? 100 : state === "accepted" ? 0 : 50 },
    result: report,
    error: effectiveState === "failed" ? {
      code: run.conclusion && run.conclusion !== "success" ? run.conclusion : "destinations_failed",
      message: report?.error || (report?.status === "completed_with_errors" ? "All requested destinations failed" : "GitHub Actions did not complete successfully"),
    } : null,
    destinations: report?.selected_destinations || null,
    download,
    telegram: allMessageIds.length ? { message_ids: allMessageIds, count: allMessageIds.length } : null,
    run_id: String(run.id), conclusion: run.conclusion || null, html_url: run.html_url || null,
    duplicate,
  };
}

async function getJob(request, env, jobId) {
  if (githubConfigError(env)) return errorResponse(request, env, 503, "backend_not_configured", "Control Worker is missing server configuration");
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(jobId)) return errorResponse(request, env, 400, "invalid_job_id", "job_id is invalid");
  let runs;
  try { runs = await workflowRuns(env); } catch (_) { return errorResponse(request, env, 502, "github_read_failed", "Could not read workflow status"); }
  const run = findRunForJob(runs, jobId);
  if (!run) return errorResponse(request, env, 404, "job_not_found", "Workflow job was not found");
  const requestId = runTitle(run).split(" ")[1] || null;
  return json(await jobPayload(run, jobId, requestId, env), 200, request, env);
}

async function downloadJobMedia(request, env, jobId) {
  if (githubConfigError(env)) return errorResponse(request, env, 503, "backend_not_configured", "Control Worker is missing server configuration");
  if (!/^job-[a-f0-9]{32}$/.test(jobId)) return errorResponse(request, env, 400, "invalid_job_id", "job_id is invalid");
  let runs;
  try { runs = await workflowRuns(env); } catch (_) { return errorResponse(request, env, 502, "github_read_failed", "Could not read workflow status"); }
  const run = findRunForJob(runs, jobId);
  if (!run) return errorResponse(request, env, 404, "job_not_found", "Workflow job was not found");
  if (run.status !== "completed") return errorResponse(request, env, 409, "download_not_ready", "Media download is available after the workflow completes");

  let report;
  try { report = await downloadArtifact(env, run.id); } catch (_) { return errorResponse(request, env, 502, "report_unavailable", "Could not verify the media download artifact"); }
  if (downloadFileCount(report) < 1) return errorResponse(request, env, 404, "download_unavailable", "No browser-download files were produced for this job");

  let artifact;
  try { artifact = await mediaArtifactForRun(env, run.id); } catch (_) { return errorResponse(request, env, 502, "artifact_lookup_failed", "Could not locate the media download artifact"); }
  if (!artifact) return errorResponse(request, env, 404, "download_artifact_missing", "The media download artifact is unavailable");
  if (artifact.expired) return errorResponse(request, env, 404, "download_expired", "The media download has expired");

  const artifactUrl = `https://api.github.com/repos/${encodeURIComponent(env.GH_OWNER)}/${encodeURIComponent(env.GH_REPO)}/actions/artifacts/${encodeURIComponent(String(artifact.id))}/zip`;
  try {
    const redirect = await fetch(artifactUrl, { redirect: "manual", headers: {
      Accept: "application/vnd.github+json", Authorization: `Bearer ${env.GH_TOKEN}`,
      "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "X2Telegram-Control-Worker",
    } });
    if (redirect.status === 410) return errorResponse(request, env, 404, "download_expired", "The media download has expired");
    const location = redirect.headers.get("Location");
    if (redirect.status !== 302 || !location) throw new Error("artifact_redirect_missing");
    const signedUrl = new URL(location);
    if (signedUrl.protocol !== "https:" || signedUrl.username || signedUrl.password) throw new Error("artifact_redirect_invalid");
    const upstream = await fetch(signedUrl.toString(), { redirect: "follow" });
    if (!upstream.ok || !upstream.body) throw new Error("artifact_download_failed");
    const headers = new Headers({
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="x2telegram-${jobId}.zip"`,
      "Cache-Control": "private, no-store, max-age=0",
      "X-Content-Type-Options": "nosniff",
    });
    const contentLength = upstream.headers.get("Content-Length");
    if (contentLength && /^\d+$/.test(contentLength)) headers.set("Content-Length", contentLength);
    return new Response(upstream.body, { status: 200, headers });
  } catch (_) {
    return errorResponse(request, env, 502, "artifact_download_failed", "Could not download the media archive");
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin");
    if (origin && origin !== env.DASHBOARD_ORIGIN) {
      return errorResponse(request, env, 403, "forbidden_origin", "Origin is not allowed");
    }
    if (request.method === "OPTIONS") {
      if (request.headers.get("Origin") !== env.DASHBOARD_ORIGIN) return new Response(null, { status: 403 });
      return json({}, 200, request, env);
    }
    if (request.method === "GET" && url.pathname === "/health") return json({ status: "ok", service: "x2telegram-control" }, 200, request, env);
    const identity = await verifyAccess(request, env);
    if (!identity.ok) return errorResponse(request, env, identity.status, identity.code, identity.message);
    if (request.method === "GET" && url.pathname === "/auth/check") return json({ status: "ok", authenticated: true }, 200, request, env);
    if (request.method === "POST" && url.pathname === "/jobs") return dispatch(request, env, identity);
    const downloadMatch = url.pathname.match(/^\/jobs\/([^/]+)\/download$/);
    if (request.method === "GET" && downloadMatch) return downloadJobMedia(request, env, decodeURIComponent(downloadMatch[1]));
    const match = url.pathname.match(/^\/jobs\/([^/]+)$/);
    if (request.method === "GET" && match) return getJob(request, env, decodeURIComponent(match[1]));
    if ((request.method === "GET" || request.method === "HEAD") && env.ASSETS?.fetch) return env.ASSETS.fetch(request);
    return errorResponse(request, env, 404, "not_found", "Endpoint not found");
  },
};
