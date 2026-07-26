import {
  createHash,
  createHmac,
  randomBytes,
  scryptSync,
  timingSafeEqual,
} from "node:crypto";
import {
  mkdir,
  open,
  readFile,
  rename,
  stat,
} from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const MODULE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BODY_LIMIT_BYTES = 16 * 1024;
const MAX_FETCH_BYTES = 1_500_000;
const FETCH_TIMEOUT_MS = 12_000;
const SESSION_COOKIE_NAME = "bt_session";
const SUPPORTED_VERDICTS = new Set([
  "Contact now",
  "Verify contact first",
  "Watch list",
  "Park",
]);
const SCORE_LIMITS = {
  recent_public_trigger: 25,
  "1bt_service_fit": 25,
  local_reachability: 20,
  named_person_found: 15,
  evidence_quality: 10,
  deal_size_likelihood: 5,
};
const SIMULATION_MARKERS = [
  "example.test",
  "sample data",
  "synthetic",
  "simulated",
  "fake source",
  "sample-",
];
const DEFAULT_STATE = {
  last_fetch: null,
  total_leads_found: 0,
  sources_enabled: 4,
  sources_ok: 0,
  sources_failed: 0,
  leads_contact_now: 0,
  leads_verify_first: 0,
  leads_watch_list: 0,
  leads_parked: 0,
  notes: "",
};
const TRIGGER_KEYWORDS = {
  tender_or_procurement: [
    "tender",
    "rfp",
    "request for proposal",
    "procurement",
    "bid invitation",
    "quotation",
  ],
  hiring_spike: [
    "hiring",
    "vacancy",
    "vacancies",
    "career",
    "careers",
    "job",
    "jobs",
    "recruiting",
    "engineer",
    "developer",
  ],
  leadership_change: [
    "appoint",
    "appointed",
    "joins as",
    "new ceo",
    "new cio",
    "new cto",
    "chief digital",
    "head of it",
  ],
  expansion: [
    "expansion",
    "expanded",
    "opens",
    "opened",
    "new branch",
    "new facility",
    "regional office",
    "capacity",
  ],
  acquisition_or_merger: [
    "acquisition",
    "merger",
    "merged",
    "acquired",
    "strategic investment",
  ],
  product_launch: ["launch", "launched", "new product", "new app", "platform"],
  ai_or_digital_initiative: [
    "ai",
    "artificial intelligence",
    "automation",
    "digital transformation",
    "data platform",
    "analytics",
  ],
  compliance_or_regulatory_pressure: [
    "regulatory",
    "compliance",
    "audit",
    "risk",
    "data protection",
  ],
  system_integration_pressure: [
    "integration",
    "api",
    "erp",
    "core banking",
    "migration",
    "middleware",
    "omnichannel",
  ],
  generic_pr_fluff: [
    "award",
    "celebrates",
    "anniversary",
    "csr",
    "sponsorship",
    "recognised",
  ],
};
const SERVICE_KEYWORDS = {
  "AI apps / workflow automation": [
    " ai ",
    "artificial intelligence",
    "automation",
    "workflow",
    "machine learning",
    "mlops",
  ],
  "Dynamics 365 / CRM / Power Platform": [
    "crm",
    "customer relationship",
    "dynamics 365",
    "power platform",
    "customer service",
  ],
  "managed IT/application support": [
    "application support",
    "managed it",
    "technical support",
    "it support",
    "support engineer",
  ],
  "data workflows": [
    "data",
    "analytics",
    "reporting",
    "dashboard",
    "business intelligence",
    "bi ",
    "data engineer",
  ],
  integrations: [
    "integration",
    " api ",
    " erp ",
    "middleware",
    "core banking",
    "migration",
  ],
  "backend/software delivery support": [
    "software",
    "developer",
    "engineer",
    "backend",
    ".net",
    "java",
    "python",
  ],
};

class HttpError extends Error {
  constructor(status, detail, headers = {}) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.headers = headers;
  }
}

class SlidingWindowLimiter {
  constructor() {
    this.events = new Map();
  }

  ensureAllowed(key, maxEvents, windowSeconds) {
    const now = Date.now();
    const cutoff = now - windowSeconds * 1000;
    const entries = (this.events.get(key) || []).filter((value) => value >= cutoff);
    if (entries.length >= maxEvents) {
      throw new HttpError(429, "Too many attempts. Try again later.", {
        "Retry-After": String(windowSeconds),
      });
    }
    entries.push(now);
    this.events.set(key, entries);
  }

  reset(key) {
    this.events.delete(key);
  }
}

class KeyedMutex {
  constructor() {
    this.queues = new Map();
  }

  async run(key, operation) {
    const previous = this.queues.get(key) || Promise.resolve();
    let release;
    const current = new Promise((resolve) => {
      release = resolve;
    });
    this.queues.set(key, current);
    await previous;
    try {
      return await operation();
    } finally {
      release();
      if (this.queues.get(key) === current) {
        this.queues.delete(key);
      }
    }
  }
}

export async function loadRuntimeConfig(
  configPath = process.env.BT_CONFIG_FILE || path.join(MODULE_ROOT, "runtime-config.json"),
) {
  const config = JSON.parse(await readFile(configPath, "utf8"));
  validateRuntimeConfig(config);
  return config;
}

export async function createApplication(options = {}) {
  const config = options.config;
  validateRuntimeConfig(config);
  const staticDirectory = path.resolve(
    options.staticDirectory || config.static_dir || path.join(MODULE_ROOT, "public"),
  );
  const dataDirectory = path.resolve(config.data_dir);
  const sourceRegistryPath = path.resolve(
    options.sourceRegistryPath || path.join(MODULE_ROOT, "source-registry.json"),
  );
  const seedLeadsPath = path.resolve(
    options.seedLeadsPath || path.join(MODULE_ROOT, "seed-leads.json"),
  );
  const seedStatePath = path.resolve(
    options.seedStatePath || path.join(MODULE_ROOT, "seed-state.json"),
  );
  const fetchImplementation = options.fetchImplementation || globalThis.fetch;
  const registry = JSON.parse(await readFile(sourceRegistryPath, "utf8"));
  const enabledSources = (registry.sources || []).filter((source) => source.enabled === true);
  validateSourceRegistry(enabledSources);

  const sessions = new Map();
  const loginLimiter = new SlidingWindowLimiter();
  const mutex = new KeyedMutex();
  const refreshRuns = new Map();
  await mkdir(dataDirectory, { recursive: true });
  await bootstrapJson(
    path.join(dataDirectory, "leads.json"),
    seedLeadsPath,
    [],
    (value) => validateRuntimeLeads(value),
  );
  await bootstrapJson(
    path.join(dataDirectory, "state.json"),
    seedStatePath,
    { ...DEFAULT_STATE, sources_enabled: enabledSources.length },
    validateState,
  );

  const secureHeaders = {
    "Content-Security-Policy": [
      "default-src 'self'",
      "base-uri 'none'",
      "connect-src 'self'",
      "font-src 'self'",
      "form-action 'self'",
      "frame-ancestors 'none'",
      "img-src 'self' data:",
      "object-src 'none'",
      "script-src 'self'",
      "style-src 'self'",
      "upgrade-insecure-requests",
    ].join("; "),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
  };

  function pruneSessions() {
    const now = Date.now();
    for (const [jti, session] of sessions.entries()) {
      if (session.expiresAt <= now) {
        sessions.delete(jti);
      }
    }
  }

  function createSession() {
    pruneSessions();
    const jti = randomBytes(24).toString("base64url");
    const csrf = randomBytes(24).toString("base64url");
    const expiresAt = Date.now() + config.session_minutes * 60_000;
    const payload = Buffer.from(
      JSON.stringify({
        sub: config.shared_username,
        role: "viewer",
        jti,
        csrf,
        exp: expiresAt,
      }),
    ).toString("base64url");
    const signature = createHmac("sha256", config.session_secret)
      .update(payload)
      .digest("base64url");
    sessions.set(jti, { csrf, expiresAt });
    return { token: `${payload}.${signature}`, csrf, expiresAt };
  }

  function verifySession(request) {
    pruneSessions();
    const token = parseCookies(request.headers.cookie || "")[SESSION_COOKIE_NAME];
    if (!token) {
      return null;
    }
    const [payload, signature, extra] = token.split(".");
    if (!payload || !signature || extra !== undefined) {
      return null;
    }
    const expected = createHmac("sha256", config.session_secret)
      .update(payload)
      .digest("base64url");
    if (!safeEqual(signature, expected)) {
      return null;
    }
    try {
      const decoded = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
      const registered = sessions.get(decoded.jti);
      if (
        decoded.sub !== config.shared_username ||
        decoded.role !== "viewer" ||
        !registered ||
        registered.expiresAt !== decoded.exp ||
        registered.csrf !== decoded.csrf ||
        decoded.exp <= Date.now()
      ) {
        return null;
      }
      return decoded;
    } catch {
      return null;
    }
  }

  function requireAuth(request) {
    const session = verifySession(request);
    if (!session) {
      throw new HttpError(401, "Session expired or invalid");
    }
    return session;
  }

  function requireCsrf(request) {
    const session = requireAuth(request);
    const supplied = String(request.headers["x-csrf-token"] || "");
    if (!supplied || !safeEqual(supplied, session.csrf)) {
      throw new HttpError(403, "CSRF validation failed");
    }
    const fetchSite = String(request.headers["sec-fetch-site"] || "");
    if (fetchSite && !["same-origin", "same-site", "none"].includes(fetchSite)) {
      throw new HttpError(403, "Cross-site request blocked");
    }
    return session;
  }

  async function readLeads() {
    const leads = await readJson(path.join(dataDirectory, "leads.json"));
    return validateRuntimeLeads(leads);
  }

  async function writeLeads(leads) {
    const validated = validateRuntimeLeads(leads);
    await mutex.run("leads", () =>
      atomicWriteJson(path.join(dataDirectory, "leads.json"), validated),
    );
  }

  async function readState() {
    return validateState(await readJson(path.join(dataDirectory, "state.json")));
  }

  async function updateState(operation) {
    return mutex.run("state", async () => {
      const current = await readState();
      const updated = operation({ ...current });
      const validated = validateState(updated);
      await atomicWriteJson(path.join(dataDirectory, "state.json"), validated);
      return validated;
    });
  }

  async function readSourceStatus() {
    try {
      const value = await readJson(path.join(dataDirectory, "source-status.json"));
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new Error("Source status must be an object.");
      }
      return value;
    } catch (error) {
      if (error && error.code === "ENOENT") {
        return {};
      }
      throw error;
    }
  }

  async function handle(request, response) {
    applyHeaders(response, secureHeaders);
    try {
      enforceTrustedHost(request, config.trusted_hosts);
      const url = new URL(request.url || "/", "https://slradar.globalapps.world");
      const route = url.pathname;
      const method = String(request.method || "GET").toUpperCase();

      if (method === "GET" && route === "/api/health") {
        return sendJson(response, 200, {
          status: "ok",
          app: config.app_name,
          version: config.app_version,
          runtime: "hostinger-node",
        });
      }

      if (method === "POST" && route === "/api/auth/login") {
        const clientKey = clientAddress(request);
        loginLimiter.ensureAllowed(
          clientKey,
          config.login_max_attempts,
          config.login_window_seconds,
        );
        const body = strictObject(await readJsonBody(request), ["username", "password"]);
        requireString(body.username, "username", 1, 100);
        requireString(body.password, "password", 1, 200);
        const usernameMatches = safeEqual(body.username, config.shared_username);
        const suppliedHash = scryptSync(
          body.password,
          Buffer.from(config.password_salt, "hex"),
          64,
        );
        const passwordMatches = safeBufferEqual(
          suppliedHash,
          Buffer.from(config.password_hash, "hex"),
        );
        if (!usernameMatches || !passwordMatches) {
          throw new HttpError(401, "Invalid credentials");
        }
        loginLimiter.reset(clientKey);
        const session = createSession();
        response.setHeader(
          "Set-Cookie",
          serializeCookie(SESSION_COOKIE_NAME, session.token, {
            maxAge: config.session_minutes * 60,
            secure: config.cookie_secure,
          }),
        );
        return sendJson(response, 200, {
          ok: true,
          user: config.shared_username,
          role: "viewer",
          expires_in_minutes: config.session_minutes,
          csrf_token: session.csrf,
        });
      }

      if (method === "POST" && route === "/api/auth/logout") {
        const session = requireCsrf(request);
        sessions.delete(session.jti);
        response.setHeader(
          "Set-Cookie",
          serializeCookie(SESSION_COOKIE_NAME, "", {
            maxAge: 0,
            secure: config.cookie_secure,
          }),
        );
        return sendJson(response, 200, {
          ok: true,
          message: "Session cleared",
        });
      }

      if (method === "GET" && route === "/api/auth/verify") {
        const session = requireAuth(request);
        return sendJson(response, 200, {
          ok: true,
          user: config.shared_username,
          role: "viewer",
          csrf_token: session.csrf,
        });
      }

      if (method === "GET" && route === "/api/leads") {
        requireAuth(request);
        const leads = await readLeads();
        return sendJson(response, 200, {
          ok: true,
          count: leads.length,
          leads,
        });
      }

      if (method === "GET" && route === "/api/leads/stats") {
        requireAuth(request);
        return sendJson(response, 200, {
          ok: true,
          ...buildStats(await readLeads()),
        });
      }

      if (method === "POST" && route === "/api/leads/refresh") {
        const session = requireCsrf(request);
        const previousRun = refreshRuns.get(session.sub) || 0;
        const elapsed = Date.now() - previousRun;
        if (elapsed < config.refresh_min_interval_seconds * 1000) {
          const retryAfter = Math.ceil(
            (config.refresh_min_interval_seconds * 1000 - elapsed) / 1000,
          );
          throw new HttpError(429, "Refresh is cooling down. Try again shortly.", {
            "Retry-After": String(retryAfter),
          });
        }
        refreshRuns.set(session.sub, Date.now());
        try {
          const result = await runLiveRefresh({
            sources: enabledSources,
            fetchImplementation,
          });
          if (!result.leads.length) {
            throw new Error("Live refresh returned no verified leads.");
          }
          await writeLeads(result.leads);
          await mutex.run("source-status", () =>
            atomicWriteJson(
              path.join(dataDirectory, "source-status.json"),
              Object.fromEntries(
                result.coverage.map((item) => [item.source_id, item]),
              ),
            ),
          );
          await updateState((state) => ({
            ...state,
            last_fetch: result.fetched_at,
            total_leads_found: result.leads.length,
            sources_enabled: enabledSources.length,
            sources_ok:
              result.coverage.filter((item) =>
                ["success", "recovered"].includes(item.fetch_status),
              ).length,
            sources_failed: result.coverage.filter(
              (item) => item.fetch_status === "failed",
            ).length,
            ...verdictState(result.leads),
          }));
          return sendJson(response, 200, {
            ok: true,
            count: result.leads.length,
            source: "live_fetch",
            coverage: result.summary,
          });
        } catch (error) {
          process.stderr.write(
            `Live refresh failed; existing verified leads preserved: ${error.message}\n`,
          );
          throw new HttpError(
            503,
            "Live refresh failed; existing verified leads were preserved.",
          );
        }
      }

      if (method === "GET" && route === "/api/sources") {
        requireAuth(request);
        const status = await readSourceStatus();
        const sources = (registry.sources || []).map((source) => ({
          source_id: String(source.source_id || ""),
          source_name: String(source.source_name || ""),
          source_type: String(source.type || ""),
          country: String(source.country || ""),
          fetch_method: String(source.fetch_method || ""),
          enabled: source.enabled === true,
          notes: String(source.notes || ""),
          limitations:
            "Public page fetch only; extraction may be low-yield or require manual verification.",
          search_terms: Array.isArray(source.search_terms)
            ? source.search_terms.map(String)
            : [],
          last_fetch_status: status[source.source_id] || null,
          base_url: String(source.base_url || ""),
          fetch_url: String(source.base_url || ""),
          recovery_candidates: Array.isArray(source.recovery_candidates)
            ? source.recovery_candidates.map(String)
            : [],
          previous_urls: Array.isArray(source.previous_urls)
            ? source.previous_urls.map(String)
            : [],
        }));
        return sendJson(response, 200, {
          ok: true,
          registry_version: registry.version,
          public_url_policy:
            "Configured public source names and URLs are not confidential.",
          include_urls: true,
          source_count: sources.length,
          sources,
        });
      }

      if (method === "GET" && route === "/api/state") {
        requireAuth(request);
        return sendJson(response, 200, { ok: true, ...(await readState()) });
      }

      if (method === "PUT" && route === "/api/state") {
        requireCsrf(request);
        const body = strictObject(await readJsonBody(request), ["notes"]);
        const notes = requireString(body.notes, "notes", 0, 5000);
        await updateState((state) => ({ ...state, notes }));
        return sendJson(response, 200, { ok: true });
      }

      if (method === "POST" && route === "/api/agent/classify") {
        requireCsrf(request);
        const body = strictObject(await readJsonBody(request), ["query"]);
        const query = requireString(body.query, "query", 1, 5000);
        return sendJson(response, 200, {
          ok: true,
          ...classifySignal(query),
        });
      }

      if (method === "POST" && route === "/api/agent/fit-preview") {
        requireCsrf(request);
        const body = strictObject(await readJsonBody(request), ["query"]);
        const query = requireString(body.query, "query", 1, 5000);
        return sendJson(response, 200, {
          ok: true,
          classification: classifySignal(query),
          service_fit: detectServiceFit(query),
          verified_lead: false,
          explanation:
            "This is a text-only fit preview. It is not a verified lead, does not carry a lead score, and must not be used as evidence without a genuine live public source.",
        });
      }

      if (method === "GET" && route === "/") {
        if (verifySession(request)) {
          return redirect(response, "/app");
        }
        return sendStatic(response, path.join(staticDirectory, "login.html"));
      }

      if (method === "GET" && route === "/app") {
        if (!verifySession(request)) {
          return redirect(response, "/");
        }
        return sendStatic(response, path.join(staticDirectory, "index.html"));
      }

      const staticFiles = {
        "/static/css/app.css": ["css", "app.css"],
        "/static/js/app.js": ["js", "app.js"],
        "/static/js/login.js": ["js", "login.js"],
      };
      if (method === "GET" && Object.hasOwn(staticFiles, route)) {
        return sendStatic(response, path.join(staticDirectory, ...staticFiles[route]));
      }

      throw new HttpError(404, "Not found");
    } catch (error) {
      const status = error instanceof HttpError ? error.status : 500;
      if (!(error instanceof HttpError)) {
        process.stderr.write(`Request failed: ${error.stack || error.message}\n`);
      }
      if (error instanceof HttpError) {
        for (const [key, value] of Object.entries(error.headers)) {
          response.setHeader(key, value);
        }
      }
      return sendJson(response, status, {
        detail:
          error instanceof HttpError
            ? error.detail
            : "The workspace data is currently unavailable.",
      });
    }
  }

  return {
    handle,
    config,
    paths: { dataDirectory, staticDirectory },
  };
}

function validateRuntimeConfig(config) {
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    throw new Error("Runtime configuration is missing.");
  }
  requireString(config.app_name, "app_name", 1, 100);
  requireString(config.app_version, "app_version", 1, 30);
  requireString(config.shared_username, "shared_username", 1, 100);
  requireHex(config.password_salt, "password_salt", 16);
  requireHex(config.password_hash, "password_hash", 64);
  requireString(config.session_secret, "session_secret", 32, 512);
  requireString(config.data_dir, "data_dir", 1, 1000);
  if (
    !Array.isArray(config.trusted_hosts) ||
    !config.trusted_hosts.length ||
    config.trusted_hosts.some((host) => typeof host !== "string" || !host.trim())
  ) {
    throw new Error("trusted_hosts must be a non-empty string array.");
  }
  config.cookie_secure = config.cookie_secure !== false;
  config.session_minutes = boundedInteger(config.session_minutes, 480, 15, 1440);
  config.login_max_attempts = boundedInteger(
    config.login_max_attempts,
    5,
    1,
    20,
  );
  config.login_window_seconds = boundedInteger(
    config.login_window_seconds,
    300,
    30,
    3600,
  );
  config.refresh_min_interval_seconds = boundedInteger(
    config.refresh_min_interval_seconds,
    30,
    0,
    3600,
  );
}

function boundedInteger(value, fallback, minimum, maximum) {
  const candidate = Number.isInteger(value) ? value : fallback;
  if (candidate < minimum || candidate > maximum) {
    throw new Error(`Configuration integer must be between ${minimum} and ${maximum}.`);
  }
  return candidate;
}

function requireHex(value, name, minimumBytes) {
  const text = requireString(value, name, minimumBytes * 2, 2048);
  if (!/^[0-9a-f]+$/i.test(text) || text.length % 2 !== 0) {
    throw new Error(`${name} must be hexadecimal.`);
  }
  return text;
}

function requireString(value, name, minimum, maximum) {
  if (typeof value !== "string" || value.length < minimum || value.length > maximum) {
    throw new HttpError(422, `${name} must contain ${minimum}-${maximum} characters.`);
  }
  return value;
}

function strictObject(value, allowedKeys) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new HttpError(422, "A JSON object is required.");
  }
  const unexpected = Object.keys(value).filter((key) => !allowedKeys.includes(key));
  const missing = allowedKeys.filter((key) => !Object.hasOwn(value, key));
  if (unexpected.length || missing.length) {
    throw new HttpError(422, "Request fields do not match the API contract.");
  }
  return value;
}

function enforceTrustedHost(request, trustedHosts) {
  const rawHost = String(request.headers.host || "").trim().toLowerCase();
  const hostname = rawHost.startsWith("[")
    ? rawHost.slice(1, rawHost.indexOf("]"))
    : rawHost.split(":")[0];
  if (!hostname || !trustedHosts.map((item) => item.toLowerCase()).includes(hostname)) {
    throw new HttpError(400, "Invalid host header");
  }
}

function clientAddress(request) {
  const forwarded = String(request.headers["x-forwarded-for"] || "")
    .split(",")[0]
    .trim()
    .slice(0, 128);
  return forwarded || String(request.socket.remoteAddress || "unknown").slice(0, 128);
}

function parseCookies(header) {
  const cookies = {};
  for (const pair of header.split(";")) {
    const separator = pair.indexOf("=");
    if (separator <= 0) {
      continue;
    }
    const key = pair.slice(0, separator).trim();
    const value = pair.slice(separator + 1).trim();
    try {
      cookies[key] = decodeURIComponent(value);
    } catch {
      cookies[key] = "";
    }
  }
  return cookies;
}

function serializeCookie(name, value, options) {
  const parts = [
    `${name}=${encodeURIComponent(value)}`,
    "Path=/",
    `Max-Age=${options.maxAge}`,
    "HttpOnly",
    "SameSite=Strict",
  ];
  if (options.secure) {
    parts.push("Secure");
  }
  return parts.join("; ");
}

function safeEqual(left, right) {
  const leftBuffer = Buffer.from(String(left), "utf8");
  const rightBuffer = Buffer.from(String(right), "utf8");
  return safeBufferEqual(leftBuffer, rightBuffer);
}

function safeBufferEqual(left, right) {
  return left.length === right.length && timingSafeEqual(left, right);
}

async function readJsonBody(request) {
  const declaredLength = Number.parseInt(
    String(request.headers["content-length"] || "0"),
    10,
  );
  if (Number.isFinite(declaredLength) && declaredLength > BODY_LIMIT_BYTES) {
    throw new HttpError(413, "Request body is too large.");
  }
  const chunks = [];
  let total = 0;
  for await (const chunk of request) {
    total += chunk.length;
    if (total > BODY_LIMIT_BYTES) {
      throw new HttpError(413, "Request body is too large.");
    }
    chunks.push(chunk);
  }
  if (!chunks.length) {
    return {};
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new HttpError(400, "Request body must be valid JSON.");
  }
}

function applyHeaders(response, headers) {
  for (const [key, value] of Object.entries(headers)) {
    response.setHeader(key, value);
  }
}

function sendJson(response, status, payload) {
  const body = Buffer.from(JSON.stringify(payload));
  response.statusCode = status;
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.setHeader("Content-Length", String(body.length));
  response.end(body);
}

async function sendStatic(response, filePath) {
  const extension = path.extname(filePath).toLowerCase();
  const contentTypes = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
  };
  const body = await readFile(filePath);
  response.statusCode = 200;
  response.setHeader(
    "Cache-Control",
    extension === ".html" ? "no-store" : "public, max-age=3600",
  );
  response.setHeader(
    "Content-Type",
    contentTypes[extension] || "application/octet-stream",
  );
  response.setHeader("Content-Length", String(body.length));
  response.end(body);
}

function redirect(response, location) {
  response.statusCode = 303;
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Location", location);
  response.setHeader("Content-Length", "0");
  response.end();
}

async function bootstrapJson(destination, seedPath, fallback, validator) {
  try {
    await stat(destination);
    validator(await readJson(destination));
    return;
  } catch (error) {
    if (error && error.code !== "ENOENT") {
      throw error;
    }
  }
  let value = fallback;
  try {
    value = JSON.parse(await readFile(seedPath, "utf8"));
  } catch (error) {
    if (!error || error.code !== "ENOENT") {
      throw error;
    }
  }
  validator(value);
  await atomicWriteJson(destination, value);
}

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

async function atomicWriteJson(filePath, value) {
  await mkdir(path.dirname(filePath), { recursive: true });
  const temporary = path.join(
    path.dirname(filePath),
    `.${path.basename(filePath)}-${process.pid}-${randomBytes(8).toString("hex")}.tmp`,
  );
  let handle;
  try {
    handle = await open(temporary, "wx", 0o600);
    await handle.writeFile(`${JSON.stringify(value, null, 2)}\n`, "utf8");
    await handle.sync();
    await handle.close();
    handle = null;
    await rename(temporary, filePath);
  } finally {
    if (handle) {
      await handle.close();
    }
  }
}

function validateState(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("State must be a JSON object.");
  }
  const state = { ...DEFAULT_STATE, ...value };
  if (state.last_fetch !== null && typeof state.last_fetch !== "string") {
    throw new Error("State last_fetch must be null or a string.");
  }
  requireString(state.notes, "notes", 0, 5000);
  for (const field of [
    "total_leads_found",
    "sources_enabled",
    "sources_ok",
    "sources_failed",
    "leads_contact_now",
    "leads_verify_first",
    "leads_watch_list",
    "leads_parked",
  ]) {
    if (!Number.isInteger(state[field]) || state[field] < 0) {
      throw new Error(`State ${field} must be a non-negative integer.`);
    }
  }
  return state;
}

export function validateRuntimeLeads(value) {
  if (!Array.isArray(value)) {
    throw new Error("Runtime leads must be an array.");
  }
  return value.map((lead, index) => validateLead(lead, index));
}

export function validateLead(lead, index = 0) {
  if (!lead || typeof lead !== "object" || Array.isArray(lead)) {
    throw new Error(`Runtime lead ${index} must be an object.`);
  }
  for (const field of [
    "company",
    "evidence_url",
    "evidence_excerpt",
    "source_name",
    "fetched_at",
  ]) {
    if (typeof lead[field] !== "string" || !lead[field].trim()) {
      throw new Error(`Runtime lead ${index} is missing ${field}.`);
    }
  }
  if (lead.verified_live !== true) {
    throw new Error(`Runtime lead ${index} verified_live must be true.`);
  }
  let parsedUrl;
  try {
    parsedUrl = new URL(lead.evidence_url);
  } catch {
    throw new Error(`Runtime lead ${index} has an invalid evidence_url.`);
  }
  if (
    !["http:", "https:"].includes(parsedUrl.protocol) ||
    !parsedUrl.hostname ||
    parsedUrl.username ||
    parsedUrl.password
  ) {
    throw new Error(`Runtime lead ${index} has an unsafe evidence_url.`);
  }
  const searchable = Object.values(lead)
    .filter((item) => ["string", "number", "boolean"].includes(typeof item))
    .join(" ")
    .toLowerCase();
  if (SIMULATION_MARKERS.some((marker) => searchable.includes(marker))) {
    throw new Error(`Runtime lead ${index} contains simulation data.`);
  }
  if (lead.trigger_type === "tender_or_procurement") {
    throw new Error(`Runtime lead ${index} is tender-only.`);
  }
  if (!lead.score || typeof lead.score !== "object") {
    throw new Error(`Runtime lead ${index} is missing score.`);
  }
  if (
    !Number.isInteger(lead.score.total) ||
    lead.score.total < 0 ||
    lead.score.total > 100
  ) {
    throw new Error(`Runtime lead ${index} score total must be 0-100.`);
  }
  if (!SUPPORTED_VERDICTS.has(lead.score.verdict)) {
    throw new Error(`Runtime lead ${index} has an unsupported verdict.`);
  }
  if (
    !lead.score.breakdown ||
    typeof lead.score.breakdown !== "object" ||
    Array.isArray(lead.score.breakdown)
  ) {
    throw new Error(`Runtime lead ${index} is missing score breakdown.`);
  }
  for (const [field, maximum] of Object.entries(SCORE_LIMITS)) {
    const component = lead.score.breakdown[field];
    if (!Number.isInteger(component) || component < 0 || component > maximum) {
      throw new Error(
        `Runtime lead ${index} score component ${field} is invalid.`,
      );
    }
  }
  if (
    lead.score.scoring_notes !== undefined &&
    (!Array.isArray(lead.score.scoring_notes) ||
      lead.score.scoring_notes.some((note) => typeof note !== "string"))
  ) {
    throw new Error(`Runtime lead ${index} scoring notes are invalid.`);
  }
  return lead;
}

function buildStats(leads) {
  const verdicts = {};
  const sectors = {};
  const triggerTypes = {};
  let totalScore = 0;
  for (const lead of leads) {
    verdicts[lead.score.verdict] = (verdicts[lead.score.verdict] || 0) + 1;
    const sector = String(lead.sector || "Unknown");
    sectors[sector] = (sectors[sector] || 0) + 1;
    const trigger = String(lead.trigger_type || "Unknown");
    triggerTypes[trigger] = (triggerTypes[trigger] || 0) + 1;
    totalScore += lead.score.total;
  }
  return {
    total: leads.length,
    avg_score: leads.length ? Math.round((totalScore / leads.length) * 10) / 10 : 0,
    verdicts,
    sectors,
    trigger_types: triggerTypes,
  };
}

function verdictState(leads) {
  const stats = buildStats(leads).verdicts;
  return {
    leads_contact_now: stats["Contact now"] || 0,
    leads_verify_first: stats["Verify contact first"] || 0,
    leads_watch_list: stats["Watch list"] || 0,
    leads_parked: stats.Park || 0,
  };
}

export function classifySignal(value) {
  const signalText = cleanText(value);
  const lowered = ` ${signalText.toLowerCase()} `;
  if (!signalText) {
    return {
      trigger_type: "irrelevant",
      confidence: 0,
      reason: "No text supplied.",
    };
  }
  const hitCounts = Object.fromEntries(
    Object.entries(TRIGGER_KEYWORDS).map(([trigger, keywords]) => [
      trigger,
      keywords.filter((keyword) => lowered.includes(keyword.toLowerCase())).length,
    ]),
  );
  if (hitCounts.tender_or_procurement) {
    return {
      trigger_type: "tender_or_procurement",
      confidence: 0.9,
      reason:
        "Tender/procurement language was detected; outside this app's non-tender scope.",
    };
  }
  const ranked = Object.entries(hitCounts)
    .filter(([trigger]) => trigger !== "tender_or_procurement")
    .sort((left, right) => right[1] - left[1]);
  const [triggerType, count] = ranked[0] || ["irrelevant", 0];
  if (!count) {
    return {
      trigger_type: "irrelevant",
      confidence: 0.25,
      reason: "No supported live buying signal found.",
    };
  }
  const fit = detectServiceFit(signalText);
  if (triggerType === "generic_pr_fluff" && !fit.length) {
    return {
      trigger_type: "generic_pr_fluff",
      confidence: 0.8,
      reason:
        "PR-style wording found without concrete IT/AI/CRM/data/support relevance.",
    };
  }
  return {
    trigger_type: triggerType,
    confidence: Math.round(
      Math.min(0.95, 0.5 + 0.1 * count + 0.08 * fit.length) * 100,
    ) / 100,
    reason: `Detected ${triggerType} language with ${fit.length} 1BT-fit service areas.`,
  };
}

export function detectServiceFit(value) {
  const lowered = ` ${cleanText(value).toLowerCase()} `;
  return Object.entries(SERVICE_KEYWORDS)
    .filter(([, keywords]) =>
      keywords.some((keyword) => lowered.includes(keyword.toLowerCase())),
    )
    .map(([label]) => label);
}

function cleanText(value) {
  return value === null || value === undefined
    ? ""
    : String(value).replace(/\s+/g, " ").trim();
}

function validateSourceRegistry(sources) {
  if (!Array.isArray(sources) || !sources.length) {
    throw new Error("At least one enabled public source is required.");
  }
  for (const source of sources) {
    for (const field of ["source_id", "source_name", "base_url", "type"]) {
      if (typeof source[field] !== "string" || !source[field].trim()) {
        throw new Error(`Source registry entry is missing ${field}.`);
      }
    }
    const parsed = new URL(source.base_url);
    if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname) {
      throw new Error(`Source ${source.source_id} has an unsafe URL.`);
    }
  }
}

async function runLiveRefresh({ sources, fetchImplementation }) {
  const allowedHosts = allowedSourceHosts(sources);
  const sourceResults = await Promise.all(
    sources.slice(0, 4).map((source) =>
      fetchSource(source, fetchImplementation, allowedHosts),
    ),
  );
  const coverage = sourceResults.map((result) => result.coverage);
  const jobs = [];
  const sourceTextCandidates = [];
  for (const result of sourceResults) {
    if (!result.ok) {
      continue;
    }
    const terms = (result.source.search_terms || []).map((term) =>
      String(term).toLowerCase(),
    );
    const links = extractLinks(result.html, result.url)
      .filter((link) => {
        const lowered = link.text.toLowerCase();
        return (
          link.text.length >= 18 &&
          (!terms.length || terms.some((term) => lowered.includes(term)))
        );
      })
      .slice(0, 8);
    for (const link of links) {
      jobs.push({ result, link });
    }
    const sentences = stripHtml(result.html)
      .split(/(?<=[.!?])\s+|\n+/)
      .map(cleanText)
      .filter(
        (sentence) =>
          sentence.length >= 50 &&
          sentence.length <= 500 &&
          (!terms.length ||
            terms.some((term) => sentence.toLowerCase().includes(term))),
      )
      .slice(0, 6);
    for (const sentence of sentences) {
      sourceTextCandidates.push(
        candidateFromEvidence({
          excerpt: sentence,
          evidenceUrl: result.url,
          relatedUrl: result.url,
          source: result.source,
          fetchedAt: result.fetchedAt,
          fetchStatus: result.coverage.fetch_status,
        }),
      );
    }
  }

  const linkedCandidates = await mapWithConcurrency(
    jobs.slice(0, 25),
    5,
    async ({ result, link }) => {
      try {
        const detail = await fetchPublic(
          link.url,
          fetchImplementation,
          allowedHosts,
        );
        const title = extractTitle(detail.html);
        const detailText = stripHtml(detail.html);
        const excerpt = cleanText(
          `${title || link.text} ${relevantExcerpt(
            detailText,
            result.source.search_terms || [],
          )}`,
        ).slice(0, 500);
        return candidateFromEvidence({
          excerpt: excerpt || link.text,
          evidenceUrl: detail.url,
          relatedUrl: detail.url,
          source: result.source,
          fetchedAt: detail.fetchedAt,
          fetchStatus: result.coverage.fetch_status,
        });
      } catch {
        return candidateFromEvidence({
          excerpt: link.text,
          evidenceUrl: result.url,
          relatedUrl: link.url,
          source: result.source,
          fetchedAt: result.fetchedAt,
          fetchStatus: result.coverage.fetch_status,
        });
      }
    },
  );

  const leads = [];
  const seen = new Set();
  for (const candidate of [...linkedCandidates, ...sourceTextCandidates]) {
    if (!candidate) {
      continue;
    }
    const key = [
      candidate.company.toLowerCase(),
      candidate.evidence_url.toLowerCase(),
      candidate.trigger_summary.toLowerCase(),
    ].join("|");
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    leads.push(candidate);
  }
  leads.sort((left, right) => right.score.total - left.score.total);
  const verified = validateRuntimeLeads(leads.slice(0, 10));
  const fetchedAt = new Date().toISOString();
  return {
    fetched_at: fetchedAt,
    leads: verified,
    coverage,
    summary: {
      sources_checked: coverage.length,
      sources_succeeded: coverage.filter(
        (item) => item.fetch_status === "success",
      ).length,
      sources_recovered: coverage.filter(
        (item) => item.fetch_status === "recovered",
      ).length,
      sources_failed: coverage.filter((item) => item.fetch_status === "failed")
        .length,
    },
  };
}

async function fetchSource(source, fetchImplementation, allowedHosts) {
  const candidates = [
    source.base_url,
    ...(Array.isArray(source.recovery_candidates)
      ? source.recovery_candidates
      : []),
  ].filter((value, index, values) => value && values.indexOf(value) === index);
  let firstError = "";
  for (let index = 0; index < candidates.length; index += 1) {
    try {
      const fetched = await fetchPublic(
        candidates[index],
        fetchImplementation,
        allowedHosts,
      );
      const recovered = index > 0;
      return {
        ok: true,
        ...fetched,
        source,
        coverage: {
          source_id: source.source_id,
          source_name: source.source_name,
          source_type: source.type,
          configured_url: source.base_url,
          fetch_status: recovered ? "recovered" : "success",
          failure_reason: recovered ? firstError : "",
          failure_type: recovered ? "configured_source_failed" : "",
          recovery_attempted: recovered,
          recovered_url: recovered ? fetched.url : null,
          recovery_note: recovered
            ? `Configured source failed and recovery used ${fetched.url}.`
            : "",
          status_code: fetched.status,
          fetched_at: fetched.fetchedAt,
        },
      };
    } catch (error) {
      firstError ||= error.message;
    }
  }
  return {
    ok: false,
    source,
    coverage: {
      source_id: source.source_id,
      source_name: source.source_name,
      source_type: source.type,
      configured_url: source.base_url,
      fetch_status: "failed",
      failure_reason: firstError || "Source fetch failed.",
      failure_type: "fetch_failed",
      recovery_attempted: candidates.length > 1,
      recovered_url: null,
      recovery_note: "No configured recovery URL returned usable public evidence.",
      status_code: null,
      fetched_at: new Date().toISOString(),
    },
  };
}

async function fetchPublic(
  initialUrl,
  fetchImplementation,
  allowedHosts,
  redirectCount = 0,
) {
  const parsed = new URL(initialUrl);
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    !allowedHosts.has(parsed.hostname.toLowerCase())
  ) {
    throw new Error("Public fetch target is not in the fixed source registry.");
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetchImplementation(parsed, {
      redirect: "manual",
      signal: controller.signal,
      headers: {
        Accept: "text/html,application/rss+xml;q=0.9,*/*;q=0.8",
        "User-Agent":
          "Business_Intel/1.0 (+Hostinger public-source opportunity radar)",
      },
    });
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      if (redirectCount >= 3) {
        throw new Error("Public source exceeded the redirect limit.");
      }
      const location = response.headers.get("location");
      if (!location) {
        throw new Error("Public source redirect was missing a location.");
      }
      return fetchPublic(
        new URL(location, parsed).href,
        fetchImplementation,
        allowedHosts,
        redirectCount + 1,
      );
    }
    if (!response.ok) {
      throw new Error(`Public source returned HTTP ${response.status}.`);
    }
    const declared = Number.parseInt(
      response.headers.get("content-length") || "0",
      10,
    );
    if (Number.isFinite(declared) && declared > MAX_FETCH_BYTES) {
      throw new Error("Public source body exceeded the size limit.");
    }
    const body = await readBoundedResponse(response, MAX_FETCH_BYTES);
    return {
      url: parsed.href,
      status: response.status,
      html: body.toString("utf8"),
      fetchedAt: new Date().toISOString(),
    };
  } finally {
    clearTimeout(timeout);
  }
}

async function readBoundedResponse(response, maximum) {
  if (!response.body || typeof response.body.getReader !== "function") {
    const body = Buffer.from(await response.arrayBuffer());
    if (body.length > maximum) {
      throw new Error("Public source body exceeded the size limit.");
    }
    return body;
  }
  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      total += value.byteLength;
      if (total > maximum) {
        await reader.cancel();
        throw new Error("Public source body exceeded the size limit.");
      }
      chunks.push(Buffer.from(value));
    }
  } finally {
    reader.releaseLock();
  }
  return Buffer.concat(chunks);
}

function allowedSourceHosts(sources) {
  const hosts = new Set();
  for (const source of sources) {
    const values = [
      source.base_url,
      ...(source.recovery_candidates || []),
      ...(source.previous_urls || []),
    ];
    for (const value of values) {
      if (!value) {
        continue;
      }
      const hostname = new URL(value).hostname.toLowerCase();
      hosts.add(hostname);
      hosts.add(hostname.startsWith("www.") ? hostname.slice(4) : `www.${hostname}`);
    }
  }
  return hosts;
}

function extractLinks(html, baseUrl) {
  const links = [];
  const pattern = /<a\s+[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi;
  for (const match of html.matchAll(pattern)) {
    const label = cleanText(stripHtml(match[2]));
    if (!label || !match[1] || match[1].startsWith("#")) {
      continue;
    }
    try {
      const url = new URL(decodeEntities(match[1]), baseUrl);
      if (["http:", "https:"].includes(url.protocol)) {
        links.push({ url: url.href, text: label });
      }
    } catch {
      // Ignore malformed public-page links.
    }
  }
  return links;
}

function stripHtml(value) {
  return decodeEntities(
    String(value)
      .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, " ")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/(?:p|div|li|h1|h2|h3|a)>/gi, "\n")
      .replace(/<[^>]+>/g, " "),
  )
    .replace(/[ \t\r\f\v]+/g, " ")
    .replace(/\n\s+/g, "\n");
}

function decodeEntities(value) {
  return String(value)
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&#(\d+);/g, (_match, decimal) =>
      String.fromCodePoint(Number.parseInt(decimal, 10)),
    )
    .replace(/&#x([0-9a-f]+);/gi, (_match, hexadecimal) =>
      String.fromCodePoint(Number.parseInt(hexadecimal, 16)),
    );
}

function extractTitle(html) {
  const match = String(html).match(/<title\b[^>]*>([\s\S]*?)<\/title>/i);
  return match ? cleanText(stripHtml(match[1])) : "";
}

function relevantExcerpt(text, searchTerms) {
  const cleaned = cleanText(text);
  if (!cleaned) {
    return "";
  }
  const lowered = cleaned.toLowerCase();
  const indexes = searchTerms
    .map((term) => lowered.indexOf(String(term).toLowerCase()))
    .filter((index) => index >= 0);
  const start = indexes.length ? Math.max(0, Math.min(...indexes) - 120) : 0;
  return cleaned.slice(start, start + 380);
}

function candidateFromEvidence({
  excerpt,
  evidenceUrl,
  relatedUrl,
  source,
  fetchedAt,
  fetchStatus,
}) {
  const cleaned = cleanText(excerpt);
  if (
    cleaned.length < 18 ||
    /\b(intern|internship|trainee)\b/i.test(cleaned) ||
    SIMULATION_MARKERS.some((marker) =>
      `${cleaned} ${evidenceUrl}`.toLowerCase().includes(marker),
    )
  ) {
    return null;
  }
  const classification = classifySignal(cleaned);
  const fit = detectServiceFit(cleaned);
  if (
    ["irrelevant", "generic_pr_fluff", "tender_or_procurement"].includes(
      classification.trigger_type,
    ) &&
    !fit.length
  ) {
    return null;
  }
  if (classification.trigger_type === "tender_or_procurement") {
    return null;
  }
  const company = inferCompany(cleaned, relatedUrl || evidenceUrl);
  if (!company) {
    return null;
  }
  const lead = {
    company,
    country: "Sri Lanka",
    sector: inferSector(cleaned, source.type),
    trigger_type: classification.trigger_type,
    trigger_summary: cleaned.slice(0, 280),
    evidence_url: evidenceUrl,
    evidence_excerpt: cleaned.slice(0, 500),
    source_name: source.source_name,
    source_type: source.type,
    published_or_seen_date: extractDate(cleaned) || fetchedAt.slice(0, 10),
    fetched_at: fetchedAt,
    verified_live: true,
    source_fetch_status: fetchStatus,
    source_fetch_url: evidenceUrl,
    "1bt_fit": fit,
    limits:
      "Source page was fetched live, but company/contact details may require manual verification before outreach.",
  };
  lead.score = scoreLead(lead);
  lead.outreach_angle = fit.length
    ? `Use the public signal from ${lead.source_name} to ask whether ${lead.company} needs help with ${fit.slice(0, 3).join(", ")}. Cite ${lead.evidence_url} and verify the right contact before emailing.`
    : "Do not outreach yet; verify stronger IT/AI/CRM/data/support relevance first.";
  try {
    return validateLead(lead);
  } catch {
    return null;
  }
}

function inferCompany(text, url) {
  let decodedUrl = "";
  try {
    decodedUrl = decodeURIComponent(url || "");
  } catch {
    decodedUrl = String(url || "");
  }
  const slug = decodedUrl.match(/-at-([^/?#]+)/i);
  if (slug) {
    const words = slug[1]
      .replace(/[-_]+/g, " ")
      .replace(/\b(pvt|ltd)\b/gi, (value) => value.toUpperCase())
      .trim()
      .split(/\s+/)
      .map((word) =>
        ["PVT", "LTD", "PLC", "AI", "IT"].includes(word.toUpperCase())
          ? word.toUpperCase()
          : `${word.charAt(0).toUpperCase()}${word.slice(1).toLowerCase()}`,
      );
    const candidate = words.join(" ").replace(" PVT LTD", " (Pvt) Ltd");
    if (candidate) {
      return candidate.slice(0, 120);
    }
  }
  const patterns = [
    /\b([A-Z0-9][A-Za-z0-9&.'-]*(?:\s+[A-Z0-9][A-Za-z0-9&.'-]*){0,5}\s+\(Pvt\)\s+Ltd)\b/,
    /\b([A-Z][A-Za-z&.'-]*(?:\s+[A-Z][A-Za-z&.'-]*){0,5}\s+(?:PLC|Private Limited|Limited|Ltd\.?|Group|Holdings|Bank|Finance|Insurance|Hotels?|Technologies|Solutions|Systems|Digital|Global|Lanka))\b/,
    /\b([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){1,3})\s+(?:appoints|appointed|launches|launched|opens|opened|partners|wins|is hiring|seeks)/,
    /(?:at|with|for)\s+([A-Z][A-Za-z&.'-]+(?:\s+[A-Z][A-Za-z&.'-]+){0,4})\b/,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match && !["sri lanka", "daily ft", "all jobs"].includes(match[1].toLowerCase())) {
      return cleanText(match[1]).slice(0, 120);
    }
  }
  return "";
}

function inferSector(text, sourceType) {
  const lowered = text.toLowerCase();
  if (sourceType === "job_board") {
    return "software/IT services";
  }
  if (/(bank|finance|insurance|financial)/.test(lowered)) {
    return "finance/insurance";
  }
  if (/(apparel|garment|export|manufacturing)/.test(lowered)) {
    return "apparel/manufacturing/export";
  }
  if (/(hotel|tourism|travel|leisure)/.test(lowered)) {
    return "hospitality/tourism";
  }
  if (/(logistics|shipping|warehouse|freight)/.test(lowered)) {
    return "logistics";
  }
  if (/(health|hospital|clinic)/.test(lowered)) {
    return "healthcare";
  }
  if (/(retail|fmcg|consumer)/.test(lowered)) {
    return "retail/FMCG";
  }
  if (/(software|tech|digital|\bit\b|\bai\b)/.test(lowered)) {
    return "software/IT services";
  }
  return "unknown";
}

function extractDate(text) {
  return (
    text.match(
      /\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+\d{1,2}\s+[A-Z][a-z]+\s+20\d{2}\b/,
    )?.[0] ||
    text.match(/\b\d{1,2}\s+[A-Z][a-z]+\s+20\d{2}\b/)?.[0] ||
    text.match(/\b20\d{2}-\d{1,2}-\d{1,2}\b/)?.[0] ||
    ""
  );
}

function scoreLead(lead) {
  const text = [
    lead.company,
    lead.sector,
    lead.trigger_summary,
    lead.evidence_excerpt,
    lead.source_name,
  ]
    .map(cleanText)
    .join(" ");
  const classification = classifySignal(text);
  const fit = detectServiceFit(text);
  const [recency, recencyNote] = recencyScore(lead.published_or_seen_date);
  let serviceFit = Math.min(25, fit.length * 8);
  if (["tender_or_procurement", "irrelevant"].includes(classification.trigger_type)) {
    serviceFit = 0;
  }
  let reachable = 0;
  if (/sri lanka/i.test(text) || /\.lk\b/i.test(lead.evidence_url)) {
    reachable += 10;
  }
  if (/\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b/.test(lead.evidence_excerpt)) {
    reachable += 5;
  }
  if (lead.evidence_url) {
    reachable += 5;
  }
  reachable = Math.min(20, reachable);
  let namedPerson = 0;
  if (/\b(appointed|chief|ceo|cio|cto|director|head of|manager)\b/i.test(text)) {
    namedPerson = 8;
  }
  if (/\b[A-Z][a-z]+\s+[A-Z][a-z]+\b/.test(lead.evidence_excerpt)) {
    namedPerson = Math.max(namedPerson, 10);
  }
  if (/appointed/i.test(text) && namedPerson) {
    namedPerson = 15;
  }
  let evidenceQuality = 0;
  if (lead.evidence_url) evidenceQuality += 3;
  if (lead.evidence_excerpt.length >= 80) evidenceQuality += 3;
  if (lead.source_name) evidenceQuality += 2;
  if (classification.confidence >= 0.65) evidenceQuality += 2;
  evidenceQuality = Math.min(10, evidenceQuality);
  let dealSize = serviceFit ? 3 : 0;
  if (/(bank|plc|group|enterprise|dialog|slt|hospital|apparel)/i.test(text)) {
    dealSize = 5;
  }
  const breakdown = {
    recent_public_trigger: recency,
    "1bt_service_fit": serviceFit,
    local_reachability: reachable,
    named_person_found: namedPerson,
    evidence_quality: evidenceQuality,
    deal_size_likelihood: dealSize,
  };
  const total = Math.min(
    100,
    Object.values(breakdown).reduce((sum, value) => sum + value, 0),
  );
  let verdict =
    total >= 80
      ? "Contact now"
      : total >= 60
        ? "Verify contact first"
        : total >= 40
          ? "Watch list"
          : "Park";
  if (
    ["tender_or_procurement", "irrelevant", "generic_pr_fluff"].includes(
      classification.trigger_type,
    ) &&
    serviceFit === 0
  ) {
    verdict = "Park";
  }
  return {
    total,
    breakdown,
    verdict,
    scoring_notes: [classification.reason, recencyNote],
  };
}

function recencyScore(value) {
  const parsed = Date.parse(String(value || ""));
  if (!Number.isFinite(parsed)) {
    return [8, "No published date parsed; using low recency credit for seen-live evidence."];
  }
  const age = Math.floor((Date.now() - parsed) / 86_400_000);
  if (age < 0) {
    return [12, `Published date appears future-dated by ${Math.abs(age)} days; verify manually.`];
  }
  if (age <= 30) return [25, `Recent public signal, ${age} days old.`];
  if (age <= 60) return [18, `Moderately recent public signal, ${age} days old.`];
  if (age <= 90) return [12, `Aging public signal, ${age} days old.`];
  return [0, `Stale public signal, ${age} days old.`];
}

async function mapWithConcurrency(items, concurrency, operation) {
  const results = new Array(items.length);
  let nextIndex = 0;
  async function worker() {
    while (true) {
      const index = nextIndex;
      nextIndex += 1;
      if (index >= items.length) {
        return;
      }
      results[index] = await operation(items[index], index);
    }
  }
  await Promise.all(
    Array.from({ length: Math.min(concurrency, items.length) }, () => worker()),
  );
  return results;
}
