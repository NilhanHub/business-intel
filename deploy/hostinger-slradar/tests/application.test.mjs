import assert from "node:assert/strict";
import { randomBytes, scryptSync } from "node:crypto";
import { mkdtemp, writeFile } from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  classifySignal,
  createApplication,
  validateLead,
} from "../src/application.mjs";

const TEST_ROOT = path.dirname(fileURLToPath(import.meta.url));
const STATIC_DIRECTORY = path.resolve(TEST_ROOT, "../../../frontend/static");
const PASSWORD = "test-password";

function validLead() {
  return {
    company: "Verified Systems Lanka",
    country: "Sri Lanka",
    sector: "software/IT services",
    trigger_type: "hiring_spike",
    trigger_summary: "Verified Systems Lanka is hiring a software engineer.",
    evidence_url: "https://itpro.lk/jobs",
    evidence_excerpt:
      "Verified Systems Lanka is hiring a senior software engineer for its Colombo delivery team.",
    source_name: "ITPro.lk Jobs",
    source_type: "job_board",
    published_or_seen_date: "2026-07-20",
    fetched_at: "2026-07-20T10:00:00Z",
    verified_live: true,
    "1bt_fit": ["backend/software delivery support"],
    limits: "Public source requires manual contact verification.",
    outreach_angle: "Verify the correct contact before outreach.",
    score: {
      total: 75,
      breakdown: {
        recent_public_trigger: 25,
        "1bt_service_fit": 16,
        local_reachability: 15,
        named_person_found: 8,
        evidence_quality: 8,
        deal_size_likelihood: 3,
      },
      verdict: "Verify contact first",
      scoring_notes: ["Verified public hiring signal."],
    },
  };
}

async function startApplication() {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "slradar-test-"));
  const dataDirectory = path.join(temporary, "data");
  const seedLeadsPath = path.join(temporary, "seed-leads.json");
  const seedStatePath = path.join(temporary, "seed-state.json");
  const sourceRegistryPath = path.join(temporary, "source-registry.json");
  await writeFile(seedLeadsPath, JSON.stringify([validLead()]));
  await writeFile(
    seedStatePath,
    JSON.stringify({
      last_fetch: null,
      total_leads_found: 1,
      sources_enabled: 1,
      sources_ok: 0,
      sources_failed: 0,
      leads_contact_now: 0,
      leads_verify_first: 1,
      leads_watch_list: 0,
      leads_parked: 0,
      notes: "",
    }),
  );
  await writeFile(
    sourceRegistryPath,
    JSON.stringify({
      version: "test",
      sources: [
        {
          source_id: "itpro_jobs",
          source_name: "ITPro.lk Jobs",
          base_url: "https://itpro.lk/jobs",
          type: "job_board",
          country: "Sri Lanka",
          fetch_method: "simple_http",
          enabled: true,
          search_terms: ["Engineer"],
          recovery_candidates: [],
        },
      ],
    }),
  );
  const salt = randomBytes(16);
  const config = {
    app_name: "1BT Opportunity Radar",
    app_version: "1.0.0-test",
    shared_username: "1bt-user",
    password_salt: salt.toString("hex"),
    password_hash: scryptSync(PASSWORD, salt, 64).toString("hex"),
    session_secret: randomBytes(48).toString("base64url"),
    trusted_hosts: ["127.0.0.1"],
    cookie_secure: true,
    session_minutes: 60,
    login_max_attempts: 5,
    login_window_seconds: 300,
    refresh_min_interval_seconds: 0,
    data_dir: dataDirectory,
  };
  const application = await createApplication({
    config,
    staticDirectory: STATIC_DIRECTORY,
    sourceRegistryPath,
    seedLeadsPath,
    seedStatePath,
    fetchImplementation: async () => {
      throw new Error("offline test source");
    },
  });
  const server = http.createServer(application.handle);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  return {
    baseUrl: `http://127.0.0.1:${address.port}`,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

async function login(baseUrl) {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "1bt-user", password: PASSWORD }),
  });
  assert.equal(response.status, 200);
  const setCookie = response.headers.get("set-cookie");
  assert.match(setCookie, /HttpOnly/i);
  assert.match(setCookie, /SameSite=Strict/i);
  assert.match(setCookie, /Secure/i);
  const body = await response.json();
  return {
    cookie: setCookie.split(";")[0],
    csrf: body.csrf_token,
  };
}

test("hosted runtime preserves authentication and API contracts", async (context) => {
  const runtime = await startApplication();
  context.after(runtime.close);

  const health = await fetch(`${runtime.baseUrl}/api/health`);
  assert.equal(health.status, 200);
  assert.equal((await health.json()).runtime, "hostinger-node");

  const invalidLogin = await fetch(`${runtime.baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "1bt-user", password: "wrong" }),
  });
  assert.equal(invalidLogin.status, 401);

  const session = await login(runtime.baseUrl);
  const verify = await fetch(`${runtime.baseUrl}/api/auth/verify`, {
    headers: { Cookie: session.cookie },
  });
  assert.equal(verify.status, 200);
  assert.equal((await verify.json()).user, "1bt-user");

  const csrfFailure = await fetch(`${runtime.baseUrl}/api/state`, {
    method: "PUT",
    headers: {
      Cookie: session.cookie,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ notes: "Blocked without CSRF" }),
  });
  assert.equal(csrfFailure.status, 403);

  const stateUpdate = await fetch(`${runtime.baseUrl}/api/state`, {
    method: "PUT",
    headers: {
      Cookie: session.cookie,
      "Content-Type": "application/json",
      "X-CSRF-Token": session.csrf,
    },
    body: JSON.stringify({ notes: "Hosted workspace note" }),
  });
  assert.equal(stateUpdate.status, 200);
  const state = await fetch(`${runtime.baseUrl}/api/state`, {
    headers: { Cookie: session.cookie },
  });
  assert.equal((await state.json()).notes, "Hosted workspace note");

  const classification = await fetch(`${runtime.baseUrl}/api/agent/classify`, {
    method: "POST",
    headers: {
      Cookie: session.cookie,
      "Content-Type": "application/json",
      "X-CSRF-Token": session.csrf,
    },
    body: JSON.stringify({
      query: "A procurement tender requests bids for a CRM platform.",
    }),
  });
  assert.equal(classification.status, 200);
  assert.equal((await classification.json()).trigger_type, "tender_or_procurement");

  const beforeRefresh = await fetch(`${runtime.baseUrl}/api/leads`, {
    headers: { Cookie: session.cookie },
  });
  assert.equal((await beforeRefresh.json()).count, 1);
  const failedRefresh = await fetch(`${runtime.baseUrl}/api/leads/refresh`, {
    method: "POST",
    headers: {
      Cookie: session.cookie,
      "X-CSRF-Token": session.csrf,
    },
  });
  assert.equal(failedRefresh.status, 503);
  const afterRefresh = await fetch(`${runtime.baseUrl}/api/leads`, {
    headers: { Cookie: session.cookie },
  });
  assert.equal((await afterRefresh.json()).count, 1);

  const logout = await fetch(`${runtime.baseUrl}/api/auth/logout`, {
    method: "POST",
    headers: {
      Cookie: session.cookie,
      "X-CSRF-Token": session.csrf,
    },
  });
  assert.equal(logout.status, 200);
  const copiedCookie = await fetch(`${runtime.baseUrl}/api/auth/verify`, {
    headers: { Cookie: session.cookie },
  });
  assert.equal(copiedCookie.status, 401);
});

test("streamed request bodies are limited to 16 KB", async (context) => {
  const runtime = await startApplication();
  context.after(runtime.close);
  const oversized = await fetch(`${runtime.baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: "1bt-user",
      password: "x".repeat(17_000),
    }),
  });
  assert.equal(oversized.status, 413);
});

test("runtime lead validation rejects unsafe and malformed evidence", () => {
  const unsafe = validLead();
  unsafe.evidence_url = "javascript:alert(1)";
  assert.throws(() => validateLead(unsafe), /unsafe evidence_url/i);

  const invalidScore = validLead();
  invalidScore.score.total = 101;
  assert.throws(() => validateLead(invalidScore), /0-100/);

  const tender = validLead();
  tender.trigger_type = "tender_or_procurement";
  assert.throws(() => validateLead(tender), /tender-only/);
});

test("signal policy behavior remains aligned with the Python application", () => {
  assert.equal(
    classifySignal("We are hiring senior software engineers.").trigger_type,
    "hiring_spike",
  );
  assert.equal(
    classifySignal("Request for proposal for data services.").trigger_type,
    "tender_or_procurement",
  );
});
