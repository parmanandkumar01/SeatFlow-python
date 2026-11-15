// SeatFlow Booking Assistant — Chrome Extension Background Service Worker
//
// Native-messaging bridge between the SeatFlow desktop app (native host)
// and this extension's content script on IRCTC pages.
//
// The extension is USER-ASSISTANCE ONLY:
// - It observes page context (CAPTCHA, OTP prompt, payment page, PNR) and
//   surfaces it to the desktop app.
// - It NEVER automates navigation, form filling, form submission, CAPTCHA
//   solving, or credential handling.
// - It NEVER reads, stores, or transmits IRCTC credentials, card numbers,
//   CVVs, PINs, or OTPs.
//
// Message envelope (see architecture/ipc_message_protocol.md):
// {
//   "msg_id": "<uuid>",
//   "ts": "<ISO-8601 UTC>",
//   "direction": "app->ext | ext->app",
//   "type": "<message type>",
//   "payload": { ... },
//   "session_id": "<optional booking session uuid>"
// }

const HOST_NAME = "com.seatflow.bridge";

// Sensitive keys that must never be forwarded across the bridge in either
// direction. Matches the desktop host's rejection list.
const SENSITIVE_KEYS = new Set([
  "username", "password", "card_number", "cvv", "pin", "otp",
  "session_id_irctc", "token", "cookie"
]);

let port = null;
let contentTabId = null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function nowIso() {
  return new Date().toISOString();
}

function hasSensitiveKeys(obj, path = "payload") {
  if (obj === null || obj === undefined || typeof obj !== "object") {
    return false;
  }
  if (Array.isArray(obj)) {
    return obj.some((v, i) => hasSensitiveKeys(v, `${path}[${i}]`));
  }
  for (const [key, value] of Object.entries(obj)) {
    if (SENSITIVE_KEYS.has(String(key).toLowerCase())) {
      return true;
    }
    if (value !== null && typeof value === "object") {
      if (hasSensitiveKeys(value, `${path}.${key}`)) {
        return true;
      }
    }
  }
  return false;
}

function stripSensitive(obj) {
  // Return a shallow clone with sensitive keys removed (defense in depth).
  if (obj === null || obj === undefined || typeof obj !== "object") {
    return obj;
  }
  if (Array.isArray(obj)) {
    return obj.map(stripSensitive);
  }
  const out = {};
  for (const [key, value] of Object.entries(obj)) {
    if (SENSITIVE_KEYS.has(String(key).toLowerCase())) {
      continue;
    }
    out[key] = value !== null && typeof value === "object" ? stripSensitive(value) : value;
  }
  return out;
}

function makeAck(inbound, status, message = "") {
  return {
    msg_id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
    ts: nowIso(),
    direction: "app->ext",
    type: "ack",
    payload: {
      ack_msg_id: inbound.msg_id || "",
      status,
      ...(message ? { message } : {})
    },
    session_id: inbound.session_id || null
  };
}

function makeError(code, message, sessionId = null) {
  return {
    msg_id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
    ts: nowIso(),
    direction: "app->ext",
    type: "error",
    payload: { code, message },
    session_id: sessionId
  };
}

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

// ---------------------------------------------------------------------------
// Native host connection
// ---------------------------------------------------------------------------

function connectToHost() {
  if (port) {
    try { port.disconnect(); } catch (e) { /* ignore */ }
    port = null;
  }
  try {
    port = chrome.runtime.connectNative(HOST_NAME);
  } catch (e) {
    // Host not available (desktop app not running or bridge disabled).
    port = null;
    return;
  }

  port.onMessage.addListener((env) => {
    try {
      if (!isValidEnvelope(env)) {
        // Ignore malformed inbound messages from the host.
        return;
      }
      if (env.direction !== "app->ext") {
        // Host should only send app->ext.
        return;
      }
      // Defense in depth: strip any sensitive keys before delivering to content.
      const safeEnv = {
        ...env,
        payload: stripSensitive(env.payload || {})
      };

      // Route app->ext messages to the content script on the active IRCTC tab.
      if (contentTabId) {
        chrome.tabs.sendMessage(contentTabId, { bridge: safeEnv }).catch(() => {
          // Tab may have navigated away; content script will re-announce.
        });
      }
    } catch (e) {
      // Ignore delivery errors; host remains connected.
    }
  });

  port.onDisconnect.addListener(() => {
    port = null;
  });
}

connectToHost();

// Reconnect when the host becomes available again (poll lightly).
setInterval(() => {
  if (!port) {
    connectToHost();
  }
}, 3000);

// ---------------------------------------------------------------------------
// Messages from content script (ext->app) -> native host
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (!request || request.bridge !== true) {
    return false; // not a bridge message
  }

  const env = request.env;
  if (!isValidEnvelope(env)) {
    sendResponse(makeError("invalid_envelope", "Malformed envelope from extension", env && env.session_id));
    return true;
  }
  if (env.direction !== "ext->app") {
    sendResponse(makeError("invalid_direction", "Extension must send ext->app", env.session_id));
    return true;
  }

  // Reject any sensitive keys in the payload (defense in depth).
  if (hasSensitiveKeys(env.payload || {})) {
    sendResponse(makeError("sensitive_payload", "Sensitive keys are not allowed in bridge messages", env.session_id));
    return true;
  }

  const safeEnv = { ...env, payload: stripSensitive(env.payload || {}) };

  if (!port) {
    sendResponse(makeError("bridge_disabled", "Desktop bridge host is unavailable", safeEnv.session_id));
    return true;
  }

  try {
    port.postMessage(safeEnv);
    sendResponse(makeAck(safeEnv, "ok", "Message forwarded to desktop host."));
  } catch (e) {
    sendResponse(makeError("host_error", String(e.message || e), safeEnv.session_id));
  }
  return true;
});

// ---------------------------------------------------------------------------
// Track the active IRCTC tab for the content script
// ---------------------------------------------------------------------------

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.url && tab.url.startsWith("https://www.irctc.co.in/")) {
    contentTabId = tabId;
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  if (contentTabId === tabId) {
    contentTabId = null;
  }
});
