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
let omitReportArtifact = false;
let expireReportArtifact = false;
let failReportZip = false;
let runListGate = null;

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
      if (path.endsWith("/actions/workflows/x2telegram.yml/runs")) {
        if (runListGate) return runListGate();
        return Response.json({ workflow_runs: githubRuns });
      }
      if (path.endsWith("/actions/workflows/x2telegram.yml/dispatches")) {
        if (failDispatch) return Response.json({ message: "private details must not leak" }, { status: 500 });
        dispatches.push(JSON.parse(init.body));
        return new Response(null, { status: 204 });
      }
      if (path.endsWith(`/actions/runs/${artifactRunId}/artifacts`)) {
        const artifacts = [];
        if (!omitReportArtifact) artifacts.push({ id: "artifact-1", name: `x2telegram-dashboard-report-${artifactRunId}`, expired: expireReportArtifact, expires_at: expireReportArtifact ? "2026-10-01T00:00:00Z" : "2026-11-01T00:00:00Z" });
        if (!omitMediaArtifact && artifactReport?.selected_destinations?.includes("download")) artifacts.push({ id: "artifact-media", name: `x2telegram-media-${artifactRunId}`, expired: false, size_in_bytes: 4 });
        return Response.json({ artifacts });
      }
      if (path.endsWith("/actions/artifacts/artifact-1/zip")) {
        if (failReportZip) return Response.json({ message: "private details must not leak" }, { status: 503 });
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
beforeEach(() => { githubRuns = []; failDispatch = false; dispatches = []; artifactReport = null; artifactRunId = "123"; omitMediaArtifact = false; omitReportArtifact = false; expireReportArtifact = false; failReportZip = false; runListGate = null; delete ENV.JOB_DISPATCH_RATE_LIMITER; });

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

test("Access accepts an additional exact email and preserves the primary identity", async () => {
  const previousPrimary = ENV.ACCESS_ALLOWED_EMAIL;
  const previousAdditional = ENV.ACCESS_ADDITIONAL_EMAIL;
  ENV.ACCESS_ALLOWED_EMAIL = "owner@example.com";
  ENV.ACCESS_ADDITIONAL_EMAIL = " second@example.com ";
  try {
    for (const email of ["owner@example.com", "SECOND@example.com"]) {
      const response = await worker.fetch(new Request("https://worker.test/auth/check", {
        headers: { "Cf-Access-Jwt-Assertion": accessJwt(email) },
      }), ENV);
      assert.equal(response.status, 200, `${email} should remain explicitly allowed`);
      assert.deepEqual(await response.json(), { status: "ok", authenticated: true });
    }
  } finally {
    ENV.ACCESS_ALLOWED_EMAIL = previousPrimary;
    if (previousAdditional === undefined) delete ENV.ACCESS_ADDITIONAL_EMAIL;
    else ENV.ACCESS_ADDITIONAL_EMAIL = previousAdditional;
  }
});

test("Access still requires the primary allowlist when an additional email is configured", async () => {
  const previousPrimary = ENV.ACCESS_ALLOWED_EMAIL;
  const previousAdditional = ENV.ACCESS_ADDITIONAL_EMAIL;
  delete ENV.ACCESS_ALLOWED_EMAIL;
  ENV.ACCESS_ADDITIONAL_EMAIL = "second@example.com";
  try {
    const response = await worker.fetch(new Request("https://worker.test/auth/check"), ENV);
    assert.equal(response.status, 503);
    assert.equal((await response.json()).error.code, "access_not_configured");
  } finally {
    if (previousPrimary === undefined) delete ENV.ACCESS_ALLOWED_EMAIL;
    else ENV.ACCESS_ALLOWED_EMAIL = previousPrimary;
    if (previousAdditional === undefined) delete ENV.ACCESS_ADDITIONAL_EMAIL;
    else ENV.ACCESS_ADDITIONAL_EMAIL = previousAdditional;
  }
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

test("per-isolate dispatch rate limit blocks the 21st valid request", async () => {
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
        body: JSON.stringify({ url: `https://x.com/rate/status/${index + 1}`, request_id: `rate-${index + 1}` }),
      });
      statuses.push((await worker.fetch(req, ENV)).status);
    }
    assert.deepEqual(statuses.slice(0, 20), Array(20).fill(202));
    assert.equal(statuses[20], 429);
    assert.equal(dispatches.length, 20);
  } finally {
    ENV.ACCESS_ALLOWED_EMAIL = originalEmail;
  }
});

test("configured edge rate limit is keyed by Access identity and blocks dispatch", async () => {
  const originalEmail = ENV.ACCESS_ALLOWED_EMAIL;
  const email = "edge-rate-test@example.com";
  let calls = 0;
  ENV.ACCESS_ALLOWED_EMAIL = email;
  ENV.JOB_DISPATCH_RATE_LIMITER = {
    async limit({ key }) {
      assert.equal(key, `jobs:${email}`);
      calls += 1;
      return { success: calls === 1 };
    },
  };
  try {
    const first = await worker.fetch(new Request("https://worker.test/jobs", {
      method: "POST", headers: { Origin: ENV.DASHBOARD_ORIGIN, "Content-Type": "application/json", "Cf-Access-Jwt-Assertion": accessJwt(email) },
      body: JSON.stringify({ url: "https://x.com/person/status/123", request_id: "edge-rate-1" }),
    }), ENV);
    assert.equal(first.status, 202);
    const second = await worker.fetch(new Request("https://worker.test/jobs", {
      method: "POST", headers: { Origin: ENV.DASHBOARD_ORIGIN, "Content-Type": "application/json", "Cf-Access-Jwt-Assertion": accessJwt(email) },
      body: JSON.stringify({ url: "https://x.com/person/status/124", request_id: "edge-rate-2" }),
    }), ENV);
    assert.equal(second.status, 429);
    assert.equal((await second.json()).error.code, "rate_limited");
    assert.equal(dispatches.length, 1);
  } finally {
    ENV.ACCESS_ALLOWED_EMAIL = originalEmail;
  }
});

test("configured edge rate limiter fails closed when the binding errors", async () => {
  ENV.JOB_DISPATCH_RATE_LIMITER = { async limit() { throw new Error("binding unavailable"); } };
  const response = await worker.fetch(request("/jobs", {
    method: "POST", body: { url: "https://x.com/person/status/125", request_id: "edge-rate-error" },
  }), ENV);
  assert.equal(response.status, 503);
  assert.equal((await response.json()).error.code, "rate_limiter_unavailable");
  assert.equal(dispatches.length, 0);
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
  const body = { url: "https://x.com/person/status/123", destinations: ["mega", "telegram", "dropbox", "download"], request_id: "multi-target-1" };
  const response = await worker.fetch(request("/jobs", { method: "POST", body }), ENV);
  const data = await response.json();
  assert.equal(response.status, 202);
  assert.deepEqual(data.destinations, ["telegram", "mega", "dropbox", "download"]);
  assert.equal(dispatches.length, 1);
  assert.equal(dispatches[0].inputs.destinations, '["telegram","mega","dropbox","download"]');
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

test("request ID conflict is not hidden when both matching and conflicting runs are visible", async () => {
  const body = { url: "https://x.com/u/status/21", request_id: "visible-run-conflict" };
  const first = await worker.fetch(request("/jobs", { method: "POST", body }), ENV);
  const jobId = (await first.json()).job_id;
  githubRuns = [
    run("21", `X2Telegram visible-run-conflict ${jobId}`, "in_progress"),
    run("22", "X2Telegram visible-run-conflict job-ffffffffffffffffffffffffffffffff", "in_progress"),
  ];
  const response = await worker.fetch(request("/jobs", { method: "POST", body }), ENV);
  assert.equal(response.status, 409);
  assert.equal((await response.json()).error.code, "idempotency_conflict");
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

test("recovery-only lookup returns not found without dispatching or consuming the dispatch limiter", async () => {
  let limiterCalls = 0;
  ENV.JOB_DISPATCH_RATE_LIMITER = { async limit() { limiterCalls += 1; return { success: false }; } };
  const response = await worker.fetch(request("/jobs/recover", {
    method: "POST", body: { url: "https://x.com/u/status/88", request_id: "recover-missing" },
  }), ENV);
  const data = await response.json();
  assert.equal(response.status, 404);
  assert.equal(data.error.code, "job_not_found");
  assert.match(data.error.message, /recovery did not dispatch/i);
  assert.equal(dispatches.length, 0);
  assert.equal(limiterCalls, 0);
});

test("recovery-only lookup returns the existing run and changed payload conflicts without dispatch", async () => {
  const body = { url: "https://x.com/u/status/89", request_id: "recover-existing" };
  const first = await worker.fetch(request("/jobs", { method: "POST", body }), ENV);
  const jobId = (await first.json()).job_id;
  githubRuns = [run("89", `X2Telegram recover-existing ${jobId}`, "in_progress")];
  const recovered = await worker.fetch(request("/jobs/recover", { method: "POST", body }), ENV);
  const recoveredData = await recovered.json();
  assert.equal(recovered.status, 200);
  assert.equal(recoveredData.job_id, jobId);
  assert.equal(recoveredData.duplicate, true);
  const conflict = await worker.fetch(request("/jobs/recover", {
    method: "POST", body: { ...body, url: "https://x.com/u/status/90" },
  }), ENV);
  assert.equal(conflict.status, 409);
  assert.equal((await conflict.json()).error.code, "idempotency_conflict");
  assert.equal(dispatches.length, 1);
});

test("idempotent POST returns its existing run before applying a saturated dispatch limiter", async () => {
  const body = { url: "https://x.com/u/status/91", request_id: "retry-before-limit" };
  const first = await worker.fetch(request("/jobs", { method: "POST", body }), ENV);
  const jobId = (await first.json()).job_id;
  githubRuns = [run("91", `X2Telegram retry-before-limit ${jobId}`, "in_progress")];
  let limiterCalls = 0;
  ENV.JOB_DISPATCH_RATE_LIMITER = { async limit() { limiterCalls += 1; return { success: false }; } };
  const response = await worker.fetch(request("/jobs", { method: "POST", body }), ENV);
  assert.equal(response.status, 200);
  assert.equal((await response.json()).job_id, jobId);
  assert.equal(limiterCalls, 0);
  assert.equal(dispatches.length, 1);
});

test("concurrent same-payload POSTs in one isolate share a single dispatch", async () => {
  const originalEmail = ENV.ACCESS_ALLOWED_EMAIL;
  ENV.ACCESS_ALLOWED_EMAIL = "concurrency-test@example.com";
  let arrivals = 0;
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  runListGate = async () => {
    arrivals += 1;
    if (arrivals === 2) release();
    await gate;
    return Response.json({ workflow_runs: [] });
  };
  const body = { url: "https://x.com/u/status/92", request_id: "concurrent-same-payload" };
  const makeRequest = (path = "/jobs") => new Request(`https://worker.test${path}`, {
    method: "POST",
    headers: { Origin: ENV.DASHBOARD_ORIGIN, "Content-Type": "application/json", "Cf-Access-Jwt-Assertion": accessJwt("concurrency-test@example.com") },
    body: JSON.stringify(body),
  });
  try {
    const responses = await Promise.all([worker.fetch(makeRequest(), ENV), worker.fetch(makeRequest(), ENV)]);
    assert.deepEqual(responses.map((response) => response.status).sort(), [200, 202]);
    assert.equal(dispatches.length, 1);
    const recovered = await worker.fetch(makeRequest("/jobs/recover"), ENV);
    assert.equal(recovered.status, 200);
    assert.equal((await recovered.json()).job_id.length > 0, true);
    assert.equal(dispatches.length, 1);
  } finally {
    ENV.ACCESS_ALLOWED_EMAIL = originalEmail;
  }
});

test("concurrent conflicting payloads with one request ID are rejected within one isolate", async () => {
  const originalEmail = ENV.ACCESS_ALLOWED_EMAIL;
  ENV.ACCESS_ALLOWED_EMAIL = "concurrency-conflict@example.com";
  let arrivals = 0;
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  runListGate = async () => {
    arrivals += 1;
    if (arrivals === 2) release();
    await gate;
    return Response.json({ workflow_runs: [] });
  };
  const makeRequest = (url) => new Request("https://worker.test/jobs", {
    method: "POST",
    headers: { Origin: ENV.DASHBOARD_ORIGIN, "Content-Type": "application/json", "Cf-Access-Jwt-Assertion": accessJwt("concurrency-conflict@example.com") },
    body: JSON.stringify({ url, request_id: "concurrent-conflicting-payload" }),
  });
  try {
    const responses = await Promise.all([
      worker.fetch(makeRequest("https://x.com/u/status/93"), ENV),
      worker.fetch(makeRequest("https://x.com/u/status/94"), ENV),
    ]);
    assert.deepEqual(responses.map((response) => response.status).sort(), [202, 409]);
    assert.equal(dispatches.length, 1);
  } finally {
    ENV.ACCESS_ALLOWED_EMAIL = originalEmail;
  }
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

test("completed job identifies a missing report artifact without changing workflow completion", async () => {
  const jobId = "job-1123456789abcdef0123456789abcdef";
  artifactRunId = "124";
  omitReportArtifact = true;
  githubRuns = [run("124", `X2Telegram missing-report ${jobId}`, "completed", "success")];
  const response = await worker.fetch(request(`/jobs/${jobId}`), ENV);
  const data = await response.json();
  assert.equal(response.status, 200);
  assert.equal(data.state, "completed");
  assert.equal(data.result, null);
  assert.deepEqual(data.report_availability, { status: "missing", expires_at: null, error_code: "report_artifact_missing" });
  assert.equal(dispatches.length, 0);
});

test("completed job identifies an expired report artifact and preserves expiry metadata", async () => {
  const jobId = "job-1223456789abcdef0123456789abcdef";
  artifactRunId = "125";
  expireReportArtifact = true;
  githubRuns = [run("125", `X2Telegram expired-report ${jobId}`, "completed", "success")];
  const response = await worker.fetch(request(`/jobs/${jobId}`), ENV);
  const data = await response.json();
  assert.equal(response.status, 200);
  assert.equal(data.result, null);
  assert.deepEqual(data.report_availability, { status: "expired", expires_at: "2026-10-01T00:00:00Z", error_code: "report_expired" });
  assert.equal(dispatches.length, 0);
});

test("report download failure is reported as unavailable, not silently omitted", async () => {
  const jobId = "job-1323456789abcdef0123456789abcdef";
  artifactRunId = "126";
  failReportZip = true;
  githubRuns = [run("126", `X2Telegram report-unavailable ${jobId}`, "completed", "success")];
  const response = await worker.fetch(request(`/jobs/${jobId}`), ENV);
  const data = await response.json();
  assert.equal(response.status, 200);
  assert.equal(data.report_availability.status, "unavailable");
  assert.equal(data.report_availability.error_code, "report_unavailable");
  assert.equal(data.result, null);
  assert.equal(JSON.stringify(data).includes("private details"), false);
});

test("completed job surfaces an outcome-unconfirmed destination state", async () => {
  const jobId = "job-1423456789abcdef0123456789abcdef";
  artifactRunId = "127";
  artifactReport = { status: "outcome_unconfirmed", results: [{
    status: "outcome_unconfirmed", destinations: { telegram: { status: "outcome_unconfirmed", items: [{ status: "outcome_unconfirmed" }] } },
  }] };
  githubRuns = [run("127", `X2Telegram unknown-outcome ${jobId}`, "completed", "failure")];
  const response = await worker.fetch(request(`/jobs/${jobId}`), ENV);
  const data = await response.json();
  assert.equal(response.status, 200);
  assert.equal(data.state, "outcome_unconfirmed");
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
