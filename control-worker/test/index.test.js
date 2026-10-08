import test, { before, after, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, createSign } from "node:crypto";
import { zipSync, strToU8 } from "fflate";
import worker from "../src/index.js";

const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
const publicJwk = publicKey.export({ format: "jwk" });
publicJwk.kid = "test-key";
publicJwk.alg = "RS256";
publicJwk.use = "sig";
const originalFetch = globalThis.fetch;
const ENV = {
  GH_TOKEN: "test-token", GH_OWNER: "aodxx", GH_REPO: "X2Telegram", GH_WORKFLOW_ID: "x2telegram.yml", GH_REF: "main",
  ACCESS_TEAM_DOMAIN: "https://team.cloudflareaccess.com", ACCESS_AUD: "test-aud", ACCESS_ALLOWED_EMAIL: "owner@example.com",
  DASHBOARD_ORIGIN: "https://x2telegram-control-plane.pantipa3826.workers.dev",
  ASSETS: {
    async fetch(request) {
      const path = new URL(request.url).pathname;
      if (path === "/") return new Response("<html>dashboard</html>", { headers: { "Content-Type": "text/html" } });
      if (path === "/config.js") return new Response("window.X2TELEGRAM_CONFIG = {}", { headers: { "Content-Type": "text/javascript" } });
      return new Response("Not found", { status: 404 });
    },
  },
};
let githubRuns = [];
let failDispatch = false;
let dispatches = [];
let artifactReport = null;
let artifactRunId = "123";
let requestSerial = 0;
let omitMediaArtifact = false;

function b64url(value) {
  return Buffer.from(value).toString("base64url");
}

function accessJwt(email = "owner@example.com", overrides = {}) {
  const now = Math.floor(Date.now() / 1000);
  const head = b64url(JSON.stringify({ alg: "RS256", kid: "test-key", typ: "JWT" }));
  const claims = b64url(JSON.stringify({
    iss: ENV.ACCESS_TEAM_DOMAIN, aud: ENV.ACCESS_AUD, email,
    exp: now + 600, nbf: now - 10, ...overrides,
  }));
  const signing = `${head}.${claims}`;
  const signer = createSign("RSA-SHA256");
  signer.update(signing);
  signer.end();
  return `${signing}.${signer.sign(privateKey).toString("base64url")}`;
}

function request(path, { method = "GET", body, authenticated = true, headers = {} } = {}) {
  const actualHeaders = new Headers(headers);
  if (!actualHeaders.has("Origin")) actualHeaders.set("Origin", ENV.DASHBOARD_ORIGIN);
  if (authenticated) {
    const email = `unit-${++requestSerial}@example.com`;
    ENV.ACCESS_ALLOWED_EMAIL = email;
    actualHeaders.set("Cf-Access-Jwt-Assertion", accessJwt(email));
  }
  if (body !== undefined) actualHeaders.set("Content-Type", "application/json");
  return new Request(`https://worker.test${path}`, {
    method, headers: actualHeaders, body: body === undefined ? undefined : typeof body === "string" ? body : JSON.stringify(body),
  });
}

function run(id, title, status = "queued", conclusion = null) {
  return { id, display_title: title, status, conclusion, created_at: "2026-10-08T00:00:00Z", updated_at: "2026-10-08T00:00:01Z", html_url: `https://github.com/aodxx/X2Telegram/actions/runs/${id}` };
}

before(() => {
  globalThis.fetch = async (input, init = {}) => {
    const url = String(input);
    if (url.endsWith("/cdn-cgi/access/certs")) return Response.json({ keys: [publicJwk] });
    if (url.startsWith("https://api.github.com")) {
      const path = new URL(url).pathname;
      if (path.endsWith("/actions/workflows/x2telegram.yml/runs")) return Response.json({ workflow_runs: githubRuns });
      if (path.endsWith("/actions/workflows/x2telegram.yml/dispatches")) {
        if (failDispatch) return Response.json({ message: "private details must not leak" }, { status: 500 });
        dispatches.push(JSON.parse(init.body));
        return new Response(null, { status: 204 });
      }
      if (path.endsWith(`/actions/runs/${artifactRunId}/artifacts`)) {
        const artifacts = [{ id: "artifact-1", name: `x2telegram-dashboard-report-${artifactRunId}`, expired: false }];
        if (!omitMediaArtifact && artifactReport?.selected_destinations?.includes("download")) artifacts.push({ id: "artifact-media", name: `x2telegram-media-${artifactRunId}`, expired: false, size_in_bytes: 4 });
        return Response.json({ artifacts });
      }
      if (path.endsWith("/actions/artifacts/artifact-1/zip")) {
        return new Response(null, { status: 302, headers: { Location: "https://blob.test/report.zip" } });
      }
      if (path.endsWith("/actions/artifacts/artifact-media/zip")) {
        return new Response(null, { status: 302, headers: { Location: "https://blob.test/media.zip" } });
      }
    }
    if (url === "https://blob.test/report.zip" && artifactReport) {
      return new Response(zipSync({ "dashboard-report.json": strToU8(JSON.stringify(artifactReport)) }));
    }
    if (url === "https://blob.test/media.zip" && artifactReport) return new Response(new Uint8Array([80, 75, 3, 4]));
    return Response.json({ message: "unexpected mocked request" }, { status: 500 });
  };
});

after(() => { globalThis.fetch = originalFetch; });
beforeEach(() => { githubRuns = []; failDispatch = false; dispatches = []; artifactReport = null; artifactRunId = "123"; omitMediaArtifact = false; });

test("health is public and does not expose credentials", async () => {
  const response = await worker.fetch(new Request("https://worker.test/health"), ENV);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ok", service: "x2telegram-control" });
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("session probe verifies Access identity before reporting signed-in state", async () => {
  const allowed = await worker.fetch(request("/auth/check"), ENV);
  assert.equal(allowed.status, 200);
  assert.deepEqual(await allowed.json(), { status: "ok", authenticated: true });
  const denied = await worker.fetch(request("/auth/check", { authenticated: false }), ENV);
  assert.equal(denied.status, 401);
});

test("Dashboard static assets are served only after Access verification", async () => {
  const allowed = await worker.fetch(request("/"), ENV);
  assert.equal(allowed.status, 200);
  assert.match(await allowed.text(), /dashboard/);
  const denied = await worker.fetch(request("/", { authenticated: false }), ENV);
  assert.equal(denied.status, 401);
});

test("missing Access JWT is denied before any GitHub access", async () => {
  const response = await worker.fetch(request("/jobs", { method: "POST", authenticated: false, body: {} }), ENV);
  assert.equal(response.status, 401);
  assert.equal((await response.json()).error.code, "unauthorized");
});

test("Access JWT with a non-allowlisted identity is denied", async () => {
  const req = new Request("https://worker.test/jobs", {
    method: "POST", headers: { "Cf-Access-Jwt-Assertion": accessJwt("other@example.com"), "Content-Type": "application/json" }, body: JSON.stringify({}),
  });
  const response = await worker.fetch(req, ENV);
  assert.equal(response.status, 403);
});

test("malformed JSON is rejected with a bounded error", async () => {
  const response = await worker.fetch(request("/jobs", { method: "POST", body: "{" }), ENV);
  assert.equal(response.status, 400);
  assert.equal((await response.json()).error.code, "invalid_json");
});

test("oversized declared body is rejected before reading or dispatch", async () => {
  const req = request("/jobs", {
    method: "POST", body: "{}", headers: { "Content-Length": "17000" },
  });
  const response = await worker.fetch(req, ENV);
  assert.equal(response.status, 413);
  assert.equal((await response.json()).error.code, "request_too_large");
  assert.equal(dispatches.length, 0);
});

test("oversized streamed body without Content-Length is cancelled before dispatch", async () => {
  const email = "oversized-stream@example.com";
  ENV.ACCESS_ALLOWED_EMAIL = email;
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode("x".repeat(17000)));
      controller.close();
    },
  });
  const req = new Request("https://worker.test/jobs", {
    method: "POST",
    headers: {
      Origin: ENV.DASHBOARD_ORIGIN,
      "Content-Type": "application/json",
      "Cf-Access-Jwt-Assertion": accessJwt(email),
    },
    body: stream,
    duplex: "half",
  });
  const response = await worker.fetch(req, ENV);
  assert.equal(response.status, 413);
  assert.equal((await response.json()).error.code, "request_too_large");
  assert.equal(dispatches.length, 0);
});

test("per-isolate POST rate limit blocks the 21st request without dispatch", async () => {
  const originalEmail = ENV.ACCESS_ALLOWED_EMAIL;
  ENV.ACCESS_ALLOWED_EMAIL = "rate-test@example.com";
  try {
    const statuses = [];
    for (let index = 0; index < 21; index += 1) {
      const req = new Request("https://worker.test/jobs", {
        method: "POST",
        headers: {
          Origin: ENV.DASHBOARD_ORIGIN,
          "Content-Type": "application/json",
          "Cf-Access-Jwt-Assertion": accessJwt("rate-test@example.com"),
        },
        body: "{}",
      });
      statuses.push((await worker.fetch(req, ENV)).status);
    }
    assert.deepEqual(statuses.slice(0, 20), Array(20).fill(400));
    assert.equal(statuses[20], 429);
    assert.equal(dispatches.length, 0);
  } finally {
    ENV.ACCESS_ALLOWED_EMAIL = originalEmail;
  }
});

test("unsupported client fields are rejected", async () => {
  const response = await worker.fetch(request("/jobs", { method: "POST", body: { url: "https://x.com/u/status/1", request_id: "fields-1", github_token: "not-accepted" } }), ENV);
  assert.equal(response.status, 400);
  assert.equal((await response.json()).error.code, "invalid_request");
  assert.equal(dispatches.length, 0);
});

test("invalid or non-HTTPS X URLs are rejected before dispatch", async () => {
  for (const url of ["http://x.com/u/status/123", "https://example.com/u/status/123", "https://x.com/u/profile"]) {
    const response = await worker.fetch(request("/jobs", { method: "POST", body: { url, request_id: "test-1" } }), ENV);
    assert.equal(response.status, 400);
    assert.equal((await response.json()).error.code, "invalid_url");
  }
  assert.equal(dispatches.length, 0);
});

test("valid request dispatches a single URL input and returns a stable job ID", async () => {
  const body = { url: "https://x.com/person/status/123?s=20", large_file_mode: false, request_id: "test-submit-1" };
  const response = await worker.fetch(request("/jobs", { method: "POST", body }), ENV);
  const data = await response.json();
  assert.equal(response.status, 202);
  assert.equal(data.state, "accepted");
  assert.match(data.job_id, /^job-[a-f0-9]{32}$/);
  assert.equal(dispatches.length, 1);
  assert.deepEqual(dispatches[0].inputs, {
    url: "https://x.com/person/status/123", large_file_mode: "false",
    destinations: '["telegram"]',
    request_id: "test-submit-1", job_id: data.job_id,
  });
  assert.equal(Object.hasOwn(dispatches[0].inputs, "urls"), false);
});

test("multi-destination request is validated and dispatched as one JSON workflow input", async () => {
  const body = { url: "https://x.com/person/status/123", destinations: ["mega", "telegram", "download"], request_id: "multi-target-1" };
  const response = await worker.fetch(request("/jobs", { method: "POST", body }), ENV);
  const data = await response.json();
  assert.equal(response.status, 202);
  assert.deepEqual(data.destinations, ["telegram", "mega", "download"]);
  assert.equal(dispatches.length, 1);
  assert.equal(dispatches[0].inputs.destinations, '["telegram","mega","download"]');
});

test("empty, duplicate, or unsupported destinations are rejected before dispatch", async () => {
  for (const destinations of [[], ["telegram", "telegram"], ["gdrive"]]) {
    const response = await worker.fetch(request("/jobs", { method: "POST", body: { url: "https://x.com/u/status/1", destinations, request_id: `bad-${dispatches.length}` } }), ENV);
    assert.equal(response.status, 400);
    assert.equal((await response.json()).error.code, "invalid_destinations");
  }
  assert.equal(dispatches.length, 0);
});

test("batch request dispatches up to 50 URLs in one workflow run", async () => {
  const body = { urls: ["https://x.com/person/status/123", "https://twitter.com/other/status/456?s=20"], request_id: "batch-submit-1" };
  const response = await worker.fetch(request("/jobs", { method: "POST", body }), ENV);
  const data = await response.json();
  assert.equal(response.status, 202);
  assert.equal(data.url_count, 2);
  assert.equal(dispatches.length, 1);
  assert.equal(dispatches[0].inputs.urls, "https://x.com/person/status/123\nhttps://x.com/other/status/456");
  assert.equal(Object.hasOwn(dispatches[0].inputs, "url"), false);
});

test("batches above 50 URLs and duplicate posts are rejected before dispatch", async () => {
  const tooMany = Array.from({ length: 51 }, (_, index) => `https://x.com/u/status/${index + 1}`);
  const tooManyResponse = await worker.fetch(request("/jobs", { method: "POST", body: { urls: tooMany, request_id: "batch-too-many" } }), ENV);
  assert.equal(tooManyResponse.status, 400);
  assert.equal((await tooManyResponse.json()).error.code, "too_many_urls");
  const duplicateResponse = await worker.fetch(request("/jobs", { method: "POST", body: { urls: ["https://x.com/u/status/1", "https://twitter.com/other/status/1"], request_id: "batch-duplicate" } }), ENV);
  assert.equal(duplicateResponse.status, 400);
  assert.equal((await duplicateResponse.json()).error.code, "duplicate_url");
  assert.equal(dispatches.length, 0);
});

test("same request and changed payload return idempotency conflict", async () => {
  const a = await worker.fetch(request("/jobs", { method: "POST", body: { url: "https://x.com/u/status/1", request_id: "same-key" } }), ENV);
  const first = await a.json();
  githubRuns = [run("1", `X2Telegram same-key ${first.job_id}`)];
  const response = await worker.fetch(request("/jobs", { method: "POST", body: { url: "https://x.com/u/status/2", request_id: "same-key" } }), ENV);
  assert.equal(response.status, 409);
  assert.equal((await response.json()).error.code, "idempotency_conflict");
  assert.equal(dispatches.length, 1);
});

test("same URL and request ID with changed destinations is an idempotency conflict", async () => {
  const body = { url: "https://x.com/u/status/1", request_id: "destination-conflict" };
  const first = await worker.fetch(request("/jobs", { method: "POST", body }), ENV);
  const jobId = (await first.json()).job_id;
  githubRuns = [run("12", `X2Telegram destination-conflict ${jobId}`)];
  const changed = await worker.fetch(request("/jobs", { method: "POST", body: { ...body, destinations: ["mega"] } }), ENV);
  assert.equal(changed.status, 409);
  assert.equal((await changed.json()).error.code, "idempotency_conflict");
  assert.equal(dispatches.length, 1);
});

test("retry with the same request returns the existing workflow instead of dispatching", async () => {
  const body = { url: "https://x.com/u/status/1", large_file_mode: false, request_id: "retry-key" };
  const first = await worker.fetch(request("/jobs", { method: "POST", body }), ENV);
  const jobId = (await first.json()).job_id;
  githubRuns = [run("77", `X2Telegram retry-key ${jobId}`, "in_progress")];
  const response = await worker.fetch(request("/jobs", { method: "POST", body }), ENV);
  const data = await response.json();
  assert.equal(response.status, 200);
  assert.equal(data.duplicate, true);
  assert.equal(data.job_id, jobId);
  assert.equal(data.run_id, "77");
  assert.equal(dispatches.length, 1);
});

test("GitHub dispatch errors are sanitized", async () => {
  failDispatch = true;
  const response = await worker.fetch(request("/jobs", { method: "POST", body: { url: "https://x.com/u/status/9", request_id: "fail-dispatch" } }), ENV);
  const text = await response.text();
  assert.equal(response.status, 502);
  assert.match(text, /github_dispatch_failed/);
  assert.doesNotMatch(text, /private details|test-token/);
});

test("status endpoint reads workflow state and a sanitized report artifact", async () => {
  const jobId = "job-0123456789abcdef0123456789abcdef";
  artifactReport = { summary: { sent: 1 }, results: [{ message_ids: [42] }] };
  githubRuns = [run("123", `X2Telegram status-key ${jobId}`, "completed", "success")];
  const response = await worker.fetch(request(`/jobs/${jobId}`), ENV);
  const data = await response.json();
  assert.equal(response.status, 200);
  assert.equal(data.state, "completed");
  assert.equal(data.result.summary.sent, 1);
  assert.deepEqual(data.telegram, { message_ids: [42], count: 1 });
});

test("partial destination delivery remains completed when another target failed", async () => {
  const jobId = "job-0123456789abcdef0123456789abcdef";
  artifactReport = { status: "partial_success", selected_destinations: ["telegram", "mega"], results: [{
    status: "partial_success", destinations: { telegram: { status: "success" }, mega: { status: "failed" } },
  }] };
  githubRuns = [run("123", `X2Telegram partial-key ${jobId}`, "completed", "failure")];
  const response = await worker.fetch(request(`/jobs/${jobId}`), ENV);
  const data = await response.json();
  assert.equal(response.status, 200);
  assert.equal(data.state, "completed");
  assert.equal(data.error, null);
  assert.deepEqual(data.destinations, ["telegram", "mega"]);
});

test("browser download endpoint streams only the completed job's private media artifact", async () => {
  const jobId = "job-0123456789abcdef0123456789abcdef";
  artifactReport = { selected_destinations: ["download"], results: [{
    destinations: { download: { status: "ready", items: [{ status: "ready", filename: "user_123_01.mp4" }] } },
  }] };
  githubRuns = [run("123", `X2Telegram download-key ${jobId}`, "completed", "success")];
  const response = await worker.fetch(request(`/jobs/${jobId}/download`), ENV);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("content-type"), "application/zip");
  assert.equal(response.headers.get("cache-control"), "private, no-store, max-age=0");
  assert.match(response.headers.get("content-disposition"), /attachment; filename="x2telegram-job-/);
  assert.deepEqual(Array.from(new Uint8Array(await response.arrayBuffer())), [80, 75, 3, 4]);
});

test("missing media artifact is reported as a failed Download destination", async () => {
  const jobId = "job-0123456789abcdef0123456789abcdef";
  artifactReport = { selected_destinations: ["download"], summary: { total: 1, sent: 1, failed: 0, destinations: { download: { ready: 1 } } }, results: [{
    status: "success", destinations: { download: { status: "ready", items: [{ status: "ready", filename: "user_123_01.mp4" }] } },
  }] };
  omitMediaArtifact = true;
  githubRuns = [run("123", `X2Telegram missing-artifact ${jobId}`, "completed", "success")];
  const response = await worker.fetch(request(`/jobs/${jobId}`), ENV);
  const data = await response.json();
  assert.equal(response.status, 200);
  assert.equal(data.state, "failed");
  assert.equal(data.error.code, "destinations_failed");
  assert.equal(data.download.status, "unavailable");
  assert.equal(data.result.results[0].destinations.download.status, "failed");
  assert.equal(data.result.results[0].destinations.download.items[0].error_code, "download_artifact_missing");
  assert.equal(data.result.summary.destinations.download.failed, 1);
});

test("CORS is restricted to the configured Dashboard origin", async () => {
  const ok = await worker.fetch(new Request("https://worker.test/health", { headers: { Origin: ENV.DASHBOARD_ORIGIN } }), ENV);
  assert.equal(ok.headers.get("access-control-allow-origin"), ENV.DASHBOARD_ORIGIN);
  const denied = await worker.fetch(request("/jobs", { method: "POST", headers: { Origin: "https://evil.example" }, body: {} }), ENV);
  assert.equal(denied.status, 403);
  assert.equal((await denied.json()).error.code, "forbidden_origin");
  const preflight = await worker.fetch(new Request("https://worker.test/jobs", { method: "OPTIONS", headers: { Origin: ENV.DASHBOARD_ORIGIN } }), ENV);
  assert.equal(preflight.status, 200);
  assert.equal(preflight.headers.get("access-control-allow-methods"), "GET, POST, OPTIONS");
  const deniedPreflight = await worker.fetch(new Request("https://worker.test/jobs", { method: "OPTIONS", headers: { Origin: "https://evil.example" } }), ENV);
  assert.equal(deniedPreflight.status, 403);
});
