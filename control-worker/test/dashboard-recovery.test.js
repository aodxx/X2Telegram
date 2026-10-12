import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const html = await readFile(new URL("../../web/index.html", import.meta.url), "utf8");
const inlineScripts = [...html.matchAll(/<script>\s*([\s\S]*?)<\/script>/g)].map((match) => match[1]);
const dashboardScript = inlineScripts.at(-1);
const jobId = "job-abcdef0123456789abcdef0123456789";
const retryJobId = "job-0123456789abcdef0123456789abcdef";

function fakeElement(id = "") {
  const classes = new Set();
  return {
    id, value: "", checked: false, disabled: false, hidden: false, textContent: "", innerHTML: "",
    dataset: {}, style: {}, attributes: {}, listeners: {},
    classList: {
      add(name) { classes.add(name); },
      remove(name) { classes.delete(name); },
      contains(name) { return classes.has(name); },
      toggle(name, force) {
        const next = force === undefined ? !classes.has(name) : Boolean(force);
        if (next) classes.add(name); else classes.delete(name);
        return next;
      },
    },
    addEventListener(name, callback) { this.listeners[name] = callback; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    removeAttribute(name) { delete this.attributes[name]; },
    focus() {},
    closest() { return null; },
  };
}

function makeBrowser({ savedJob, recoveryResponse, statusBody = null }) {
  const elements = new Map();
  const getElement = (id) => {
    if (!elements.has(id)) elements.set(id, fakeElement(id));
    return elements.get(id);
  };
  getElement("urls").value = savedJob.url || (savedJob.urls || []).join("\n");
  getElement("destTelegram").checked = true;
  const store = new Map([["x2telegram.currentJob.v1", JSON.stringify(savedJob)]]);
  const requests = [];
  const listeners = {};
  let timerId = 0;
  const fetch = async (url, options = {}) => {
    const parsed = new URL(url);
    const method = options.method || "GET";
    requests.push({ path: parsed.pathname, method, body: options.body ? JSON.parse(options.body) : null });
    if (parsed.pathname === "/auth/check") return Response.json({ authenticated: true });
    if (parsed.pathname === "/jobs/recover") return Response.json(recoveryResponse.body, { status: recoveryResponse.status });
    if (parsed.pathname === "/jobs" && method === "POST") return Response.json({
      job_id: retryJobId,
      request_id: requests.at(-1).body.request_id,
      state: "accepted",
      destinations: requests.at(-1).body.destinations,
    }, { status: 202 });
    if (parsed.pathname === `/jobs/${retryJobId}`) return Response.json({ job_id: retryJobId, state: "completed", result: { summary: {}, results: [] } });
    if (parsed.pathname === `/jobs/${jobId}`) return Response.json(statusBody || {
      job_id: jobId,
      state: "completed",
      destinations: ["telegram"],
      result: { status: "completed", summary: { sent: 1, failed: 0, outcome_unconfirmed: 0 }, results: [] },
      report_availability: { status: "ready", error_code: null, expires_at: "2026-11-01T00:00:00Z" },
      run_id: "901",
    });
    throw new Error(`Unexpected fetch ${method} ${parsed.pathname}`);
  };
  const context = {
    window: {
      X2TELEGRAM_CONFIG: { apiBase: "https://worker.test" },
      addEventListener(name, callback) { listeners[`window:${name}`] = callback; },
      confirm() { return true; },
    },
    document: {
      hidden: false,
      getElementById: getElement,
      querySelectorAll(selector) {
        if (selector === "#jobStepper li") return [1, 2, 3, 4].map((stage) => {
          const step = fakeElement(`stage-${stage}`);
          step.dataset.stage = String(stage);
          return step;
        });
        return [];
      },
      addEventListener(name, callback) { listeners[`document:${name}`] = callback; },
    },
    localStorage: {
      getItem(key) { return store.has(key) ? store.get(key) : null; },
      setItem(key, value) { store.set(key, String(value)); },
      removeItem(key) { store.delete(key); },
    },
    fetch,
    URL,
    Response,
    setTimeout() { timerId += 1; return timerId; },
    clearTimeout() {},
    console,
    location: { hostname: "worker.test", pathname: "/" },
    crypto: { randomUUID: () => "12345678-1234-1234-1234-123456789abc" },
  };
  vm.runInNewContext(dashboardScript, context, { filename: "dashboard-inline.js" });
  return { elements, requests, store };
}

async function settle() {
  for (let index = 0; index < 8; index += 1) await new Promise((resolve) => setImmediate(resolve));
}

test("reload uses recovery-only lookup and resumes the existing job without POST /jobs", async () => {
  const browser = makeBrowser({
    savedJob: {
      request_id: "dashboard-pending-123",
      url: "https://x.com/person/status/123",
      destinations: ["telegram"],
      large_file_mode: false,
    },
    recoveryResponse: {
      status: 200,
      body: { job_id: jobId, request_id: "dashboard-pending-123", state: "processing", destinations: ["telegram"] },
    },
  });
  await settle();
  assert.ok(browser.requests.some((request) => request.path === "/jobs/recover" && request.method === "POST"));
  assert.ok(browser.requests.some((request) => request.path === `/jobs/${jobId}` && request.method === "GET"));
  assert.equal(browser.requests.some((request) => request.path === "/jobs" && request.method === "POST"), false);
  const saved = JSON.parse(browser.store.get("x2telegram.currentJob.v1"));
  assert.equal(saved.job_id, jobId);
  assert.equal(browser.elements.get("progressText").textContent, "งานเสร็จแล้ว");
});

test("reload with no matching run stays locked for explicit recovery and never dispatches", async () => {
  const browser = makeBrowser({
    savedJob: {
      request_id: "dashboard-pending-456",
      url: "https://x.com/person/status/456",
      destinations: ["telegram"],
      large_file_mode: false,
    },
    recoveryResponse: { status: 404, body: { error: { code: "job_not_found", message: "No matching workflow run is visible" } } },
  });
  await settle();
  assert.ok(browser.requests.some((request) => request.path === "/jobs/recover" && request.method === "POST"));
  assert.equal(browser.requests.some((request) => request.path === "/jobs" && request.method === "POST"), false);
  assert.equal(browser.elements.get("recoveryActions").hidden, false);
  assert.equal(browser.elements.get("runBtn").disabled, true);
  assert.equal(browser.elements.get("runStateBadge").textContent, "ยังไม่ยืนยัน");
  assert.match(browser.elements.get("resultList").innerHTML, /ไม่ส่งงานใหม่เอง/);
});

test("retry UI sends only confirmed failed targets and excludes success or unconfirmed targets", async () => {
  const report = {
    status: "partial_success",
    selected_destinations: ["telegram", "mega", "dropbox", "download"],
    summary: { sent: 1, failed: 2, outcome_unconfirmed: 1 },
    results: [{
      status: "partial_success",
      username: "person",
      post_id: "123",
      destinations: {
        telegram: { status: "success", items: [{ status: "success", media_index: 1 }] },
        mega: { status: "failed", items: [{ status: "failed", media_index: 1 }] },
        dropbox: { status: "outcome_unconfirmed", items: [{ status: "outcome_unconfirmed", media_index: 1 }] },
        download: { status: "failed", items: [{ status: "failed", media_index: 1 }] },
      },
    }],
  };
  const browser = makeBrowser({
    savedJob: { request_id: "old-request", job_id: jobId, url: "https://x.com/person/status/123", destinations: ["telegram"], large_file_mode: false },
    recoveryResponse: { status: 404, body: { error: { code: "job_not_found", message: "unused" } } },
    statusBody: { job_id: jobId, state: "completed", destinations: report.selected_destinations, result: report, report_availability: { status: "ready" } },
  });
  await settle();
  assert.equal(browser.elements.get("retryActions").hidden, false);
  assert.equal(browser.elements.get("retryFailuresBtn").dataset.targets, "mega,download");
  await browser.elements.get("retryFailuresBtn").listeners.click();
  await settle();
  const submit = browser.requests.find((request) => request.path === "/jobs" && request.method === "POST");
  assert.ok(submit);
  assert.deepEqual(submit.body.destinations, ["mega", "download"]);
  assert.equal(submit.body.request_id === "old-request", false);
});
