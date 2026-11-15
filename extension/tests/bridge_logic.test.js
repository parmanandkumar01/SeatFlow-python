// Extension-side tests for the SeatFlow Booking Assistant Chrome extension.
//
// Mocks the Chrome extension API (chrome.runtime, chrome.tabs) and exercises
// the pure message-handling logic in background.js:
// - Envelope validation
// - Sensitive-key rejection (matches desktop host)
// - Ack/error construction
// - ext->app message forwarding to the native host
//
// Run with: node tests/bridge_logic.test.js
// (from the bingo-chrome-extension/ directory)

"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

// ---------------------------------------------------------------------------
// Mock Chrome extension API
// ---------------------------------------------------------------------------

const messages = [];
let nativePort = null;

const mockChrome = {
  runtime: {
    connectNative: (name) => {
      nativePort = {
        postMessage: (msg) => messages.push(msg),
        disconnect: () => { nativePort = null; },
        onMessage: { addListener: () => {} },
        onDisconnect: { addListener: () => {} }
      };
      return nativePort;
    },
    onMessage: { addListener: (cb) => { mockChrome._onMessage = cb; } },
    sendMessage: (request, cb) => { if (cb) cb({ status: "ok" }); }
  },
  tabs: {
    sendMessage: () => {},
    onUpdated: { addListener: () => {} },
    onRemoved: { addListener: () => {} }
  }
};

global.chrome = mockChrome;
global.document = {
  documentElement: {
    querySelector: () => null,
    querySelectorAll: () => []
  },
  addEventListener: () => {}
};

// ---------------------------------------------------------------------------
// Load extension source under test (evaluates background.js)
// ---------------------------------------------------------------------------

const extRoot = path.resolve(__dirname, "..");
const backgroundSrc = fs.readFileSync(path.join(extRoot, "background.js"), "utf8");
eval(backgroundSrc);

// ---------------------------------------------------------------------------
// Pure-function mirrors (same logic as background.js, tested independently)
// ---------------------------------------------------------------------------

function isValidEnvelope(env) {
  if (!env || typeof env !== "object") return false;
  if (typeof env.msg_id !== "string" || !env.msg_id) return false;
  if (typeof env.ts !== "string" || !env.ts) return false;
  if (env.direction !== "app->ext" && env.direction !== "ext->app") return false;
  const validTypes = new Set([
    "open_booking", "form_context", "captcha_detected", "otp_prompt",
    "payment_page", "pnr_received", "ack", "error"
  ]);
  if (!validTypes.has(env.type)) return false;
  if (env.payload === null || typeof env.payload !== "object" || Array.isArray(env.payload)) return false;
  if (env.session_id !== undefined && env.session_id !== null && typeof env.session_id !== "string") {
    return false;
  }
  return true;
}

const SENSITIVE_KEYS = new Set([
  "username", "password", "card_number", "cvv", "pin", "otp",
  "session_id_irctc", "token", "cookie"
]);

function hasSensitiveKeys(obj) {
  if (obj === null || obj === undefined || typeof obj !== "object") return false;
  if (Array.isArray(obj)) return obj.some(hasSensitiveKeys);
  for (const [key, value] of Object.entries(obj)) {
    if (SENSITIVE_KEYS.has(String(key).toLowerCase())) return true;
    if (value !== null && typeof value === "object") {
      if (hasSensitiveKeys(value)) return true;
    }
  }
  return false;
}

function stripSensitive(obj) {
  if (obj === null || obj === undefined || typeof obj !== "object") return obj;
  if (Array.isArray(obj)) return obj.map(stripSensitive);
  const out = {};
  for (const [key, value] of Object.entries(obj)) {
    if (SENSITIVE_KEYS.has(String(key).toLowerCase())) continue;
    out[key] = value !== null && typeof value === "object" ? stripSensitive(value) : value;
  }
  return out;
}

function nowIso() { return new Date().toISOString(); }
function makeAck(inbound, status, message = "") {
  return {
    msg_id: "test-uuid",
    ts: nowIso(),
    direction: "app->ext",
    type: "ack",
    payload: { ack_msg_id: inbound.msg_id || "", status, ...(message ? { message } : {}) },
    session_id: inbound.session_id || null
  };
}
function makeError(code, message, sessionId = null) {
  return {
    msg_id: "test-uuid",
    ts: nowIso(),
    direction: "app->ext",
    type: "error",
    payload: { code, message },
    session_id: sessionId
  };
}

// ---------------------------------------------------------------------------
// Test runner
// ---------------------------------------------------------------------------

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed++;
    console.log(`PASS: ${name}`);
  } catch (e) {
    failed++;
    console.error(`FAIL: ${name} — ${e.message}`);
  }
}
function assertOk(cond, msg) {
  assert.ok(cond, msg);
}

// --- Envelope validation ---

test("valid ext->app envelope passes", () => {
  const env = {
    msg_id: "abc-123",
    ts: nowIso(),
    direction: "ext->app",
    type: "pnr_received",
    payload: { pnr: "ABCD1234" },
    session_id: "sess_1"
  };
  assertOk(isValidEnvelope(env));
});

test("valid app->ext open_booking envelope passes", () => {
  const env = {
    msg_id: "abc-123",
    ts: nowIso(),
    direction: "app->ext",
    type: "open_booking",
    payload: { url: "https://www.irctc.co.in/ntrain/train", train_number: "12345" },
    session_id: null
  };
  assertOk(isValidEnvelope(env));
});

test("null/undefined/string envelope rejected", () => {
  assertOk(!isValidEnvelope(null));
  assertOk(!isValidEnvelope(undefined));
  assertOk(!isValidEnvelope("string"));
});

test("missing msg_id rejected", () => {
  const env = { ts: nowIso(), direction: "ext->app", type: "ack", payload: {} };
  assertOk(!isValidEnvelope(env));
});

test("invalid direction rejected", () => {
  const env = { msg_id: "x", ts: nowIso(), direction: "in->out", type: "ack", payload: {} };
  assertOk(!isValidEnvelope(env));
});

test("unknown type rejected", () => {
  const env = { msg_id: "x", ts: nowIso(), direction: "ext->app", type: "steal_credentials", payload: {} };
  assertOk(!isValidEnvelope(env));
});

test("payload not object rejected", () => {
  const env = { msg_id: "x", ts: nowIso(), direction: "ext->app", type: "ack", payload: [1, 2] };
  assertOk(!isValidEnvelope(env));
});

// --- Sensitive key rejection ---

test("safe payload accepted", () => {
  assertOk(!hasSensitiveKeys({ train_number: "12345", pnr: "ABCD1234", page: "payment" }));
});

test("sensitive top-level key rejected", () => {
  for (const key of ["username", "password", "card_number", "cvv", "pin", "otp", "token", "cookie", "session_id_irctc"]) {
    assertOk(hasSensitiveKeys({ [key]: "secret" }), `key ${key} should be sensitive`);
  }
});

test("nested sensitive key rejected", () => {
  assertOk(hasSensitiveKeys({ inner: { password: "secret" } }));
  assertOk(hasSensitiveKeys({ data: { card_number: "1234" } }));
});

test("stripSensitive removes sensitive keys", () => {
  const stripped = stripSensitive({
    train_number: "12345",
    password: "secret",
    inner: { pnr: "ABCD1234", cvv: "123" },
    otp: "123456"
  });
  assertEqual(stripped.train_number, "12345");
  assertEqual(stripped.password, undefined);
  assertEqual(stripped.otp, undefined);
  assertEqual(stripped.inner.pnr, "ABCD1234");
  assertEqual(stripped.inner.cvv, undefined);
});

function assertEqual(actual, expected, msg) {
  assert.deepStrictEqual(actual, expected, msg);
}

// --- Ack / error construction ---

test("makeAck structure", () => {
  const inbound = { msg_id: "inbound-1", session_id: "sess_1" };
  const ack = makeAck(inbound, "ok", "done");
  assertEqual(ack.direction, "app->ext");
  assertEqual(ack.type, "ack");
  assertEqual(ack.payload.ack_msg_id, "inbound-1");
  assertEqual(ack.payload.status, "ok");
  assertEqual(ack.payload.message, "done");
  assertEqual(ack.session_id, "sess_1");
});

test("makeError structure", () => {
  const err = makeError("bridge_disabled", "host unavailable", "sess_1");
  assertEqual(err.direction, "app->ext");
  assertEqual(err.type, "error");
  assertEqual(err.payload.code, "bridge_disabled");
  assertEqual(err.payload.message, "host unavailable");
  assertEqual(err.session_id, "sess_1");
});

// --- Message routing behavior via real background.js handler ---

test("ext->app valid message forwards to native host", () => {
  messages.length = 0;
  const env = {
    msg_id: "r1", ts: nowIso(), direction: "ext->app",
    type: "pnr_received", payload: { pnr: "ABCD1234" }, session_id: "sess_1"
  };
  let result;
  mockChrome._onMessage({ bridge: true, env }, { sender: {} }, (cb) => { result = cb; });
  assertEqual(messages.length, 1, "should forward to native host");
  assertEqual(messages[0].type, "pnr_received");
  assertOk(result.type === "ack", "should return ack");
});

test("sensitive payload rejected without forwarding", () => {
  messages.length = 0;
  const env = {
    msg_id: "r2", ts: nowIso(), direction: "ext->app",
    type: "pnr_received", payload: { pnr: "ABCD1234", password: "secret" }, session_id: "sess_1"
  };
  let result;
  mockChrome._onMessage({ bridge: true, env }, { sender: {} }, (cb) => { result = cb; });
  assertEqual(messages.length, 0, "should NOT forward sensitive payload");
  assertEqual(result.type, "error");
  assertEqual(result.payload.code, "sensitive_payload");
});

test("invalid envelope from extension rejected", () => {
  messages.length = 0;
  const env = { msg_id: "", ts: "", direction: "bad", type: "bad", payload: null };
  let result;
  mockChrome._onMessage({ bridge: true, env }, { sender: {} }, (cb) => { result = cb; });
  assertEqual(messages.length, 0);
  assertEqual(result.type, "error");
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
