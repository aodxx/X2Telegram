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

async function makeJobId(requestId, urls, largeFileMode) {
  const material = new TextEncoder().encode(`${requestId}\n${urls.join("\n")}\n${largeFileMode ? "1" : "0"}`);
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
  if (Object.keys(body).some((key) => !["url", "urls", "large_file_mode", "request_id"].includes(key))) return errorResponse(request, env, 400, "invalid_request", "Request contains unsupported fields");
  const hasSingleUrl = Object.hasOwn(body, "url");
  const hasUrlList = Object.hasOwn(body, "urls");
  if (hasSingleUrl === hasUrlList) return errorResponse(request, env, 400, "invalid_request", "Provide exactly one of url or urls");
  const rawUrls = hasSingleUrl ? [body.url] : body.urls;
  if (!Array.isArray(rawUrls) || rawUrls.length === 0) return errorResponse(request, env, 400, "invalid_url_list", "Provide at least one X post URL");
  if (rawUrls.length > MAX_BATCH_URLS) return errorResponse(request, env, 400, "too_many_urls", `A batch can contain at most ${MAX_BATCH_URLS} URLs`);
  if (!validRequestId(body.request_id)) return errorResponse(request, env, 400, "invalid_request_id", "request_id is missing or invalid");
  if (body.large_file_mode !== undefined && typeof body.large_file_mode !== "boolean") return errorResponse(request, env, 400, "invalid_large_file_mode", "large_file_mode must be a boolean", body.request_id);
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
  const jobId = await makeJobId(body.request_id, normalizedUrls, largeFileMode);
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
          request_id: body.request_id,
          job_id: jobId,
        },
      }),
    });
  } catch (_) { return errorResponse(request, env, 502, "github_dispatch_failed", "GitHub Actions could not accept the job", body.request_id); }
  const now = new Date().toISOString();
  return json({
    job_id: jobId, request_id: body.request_id, url_count: normalizedUrls.length, state: "accepted", created_at: now, updated_at: now,
    progress: { phase: "queued", percent: 0 }, result: null, error: null, telegram: null, duplicate: false,
  }, 202, request, env);
}

async function downloadArtifact(env, runId) {
  const data = await github(env, `/repos/${encodeURIComponent(env.GH_OWNER)}/${encodeURIComponent(env.GH_REPO)}/actions/runs/${encodeURIComponent(String(runId))}/artifacts?per_page=100`);
  const artifactName = `x2telegram-dashboard-report-${runId}`;
  const artifact = (data?.artifacts || []).find((item) => item.name === artifactName && !item.expired);
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

async function jobPayload(run, jobId, requestId, env, duplicate = false) {
  const completed = run.status === "completed";
  const success = completed && run.conclusion === "success";
  const state = success ? "completed" : completed ? "failed" : duplicate ? "duplicate" : run.status === "queued" || run.status === "requested" || run.status === "waiting" ? "accepted" : "processing";
  let report = null;
  if (completed) {
    try { report = await downloadArtifact(env, run.id); } catch (_) { report = null; }
  }
  const allMessageIds = (report?.results || []).flatMap((item) => Array.isArray(item.message_ids) ? item.message_ids : []);
  return {
    job_id: jobId,
    request_id: requestId,
    state,
    created_at: run.created_at || null,
    updated_at: run.updated_at || run.run_started_at || run.created_at || null,
    progress: { phase: completed ? "completed" : state === "accepted" ? "queued" : "running", percent: completed ? 100 : state === "accepted" ? 0 : 50 },
    result: report,
    error: completed && !success ? { code: run.conclusion || "workflow_failed", message: report?.error || "GitHub Actions did not complete successfully" } : null,
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
    const match = url.pathname.match(/^\/jobs\/([^/]+)$/);
    if (request.method === "GET" && match) return getJob(request, env, decodeURIComponent(match[1]));
    if ((request.method === "GET" || request.method === "HEAD") && env.ASSETS?.fetch) return env.ASSETS.fetch(request);
    return errorResponse(request, env, 404, "not_found", "Endpoint not found");
  },
};
