// SeatFlow Booking Assistant — Content Script
//
// Runs on https://www.irctc.co.in/* pages. Observes the page DOM for booking
// context and relays user-assistance events to the background service worker,
// which forwards them to the SeatFlow desktop app over native messaging.
//
// USER-ASSISTANCE ONLY — this script MUST:
// - Never read, store, or transmit IRCTC username/password.
// - Never read, store, or transmit card number, CVV, PIN, or OTP.
// - Never programmatically click, fill, or submit forms.
// - Never control navigation (no headless automation).
//
// It only reports page-stage context (CAPTCHA present, OTP prompt, payment
// page reached, PNR shown) so the desktop app can prompt the human user.

const HOST_ORIGIN = "https://www.irctc.co.in";

function nowIso() {
  return new Date().toISOString();
}

function sendExtEvent(type, payload = {}) {
  const env = {
    msg_id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
    ts: nowIso(),
    direction: "ext->app",
    type,
    payload,
    session_id: null
  };
  chrome.runtime.sendMessage({ bridge: true, env });
}

// ---------------------------------------------------------------------------
// Selectors used only to detect page STAGE (not credential values).
// These are heuristic, best-effort selectors for IRCTC's booking flow.
// If a selector does not match, the event is simply not fired.
// ---------------------------------------------------------------------------

const SELECTORS = {
  captchaImage: [
    "img[src*='captcha' i]",
    "img[alt*='captcha' i]",
    ".captcha-img",
    "#captchaImage",
    "[class*='captcha' i] img"
  ],
  captchaInput: [
    "input[name*='captcha' i]",
    "input[id*='captcha' i]",
    ".captcha-input",
    "#captchaInput"
  ],
  otpPrompt: [
    "input[name*='otp' i]",
    "input[id*='otp' i]",
    "[class*='otp' i]",
    "#otp"
  ],
  paymentPage: [
    "[class*='payment' i]",
    "#payment",
    "[id*='payment' i]",
    "a[href*='payment' i], button[href*='payment' i]"
  ],
  pnrDisplay: [
    "[class*='pnr' i]",
    "#pnr",
    "[id*='pnr' i]",
    "td[class*='pnr' i]"
  ]
};

function matchesAny(root, selectors) {
  for (const sel of selectors) {
    try {
      if (root.querySelector(sel)) return true;
    } catch (e) {
      // Invalid selector; skip.
    }
  }
  return false;
}

// ---------------------------------------------------------------------------
// Stage detection. Each stage is reported at most once per page load unless
// the stage changes (tracked by lastStage).
// ---------------------------------------------------------------------------

let lastStage = null;

function detectStage(root) {
  let stage = null;
  const detail = {};

  if (matchesAny(root, SELECTORS.paymentPage)) {
    stage = "payment_page";
    detail.page = "payment";
  } else if (matchesAny(root, SELECTORS.captchaImage) || matchesAny(root, SELECTORS.captchaInput)) {
    stage = "captcha_detected";
    detail.page = "booking";
  } else if (matchesAny(root, SELECTORS.otpPrompt)) {
    stage = "otp_prompt";
    detail.page = "login";
  } else if (matchesAny(root, SELECTORS.pnrDisplay)) {
    stage = "pnr_received";
    detail.page = "post_payment";
  }

  return { stage, detail };
}

// ---------------------------------------------------------------------------
// Observe the DOM for stage changes.
// ---------------------------------------------------------------------------

function startObserving() {
  const root = document.documentElement || document;

  const observer = new MutationObserver((mutations) => {
    const { stage, detail } = detectStage(root);
    if (stage && stage !== lastStage) {
      lastStage = stage;
      sendExtEvent(stage, detail);
    }
  });

  observer.observe(root, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class", "id", "src", "href"]
  });

  // Also run an initial detection.
  const { stage, detail } = detectStage(root);
  if (stage) {
    lastStage = stage;
    sendExtEvent(stage, detail);
  }
}

// ---------------------------------------------------------------------------
// Bridge inbound messages from desktop (app->ext) handled by background.js
// which forwards via chrome.tabs.sendMessage. Listen here to surface UI
// context (e.g. open_booking injects booking context for form assistance).
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((request) => {
  if (!request || request.bridge !== true) return;
  const env = request.env;
  if (!env || env.direction !== "app->ext") return;

  if (env.type === "open_booking") {
    // Surface booking context to the user on the IRCTC page without filling
    // any form. Only read-safe fields (train, stations, date, class, quota)
    // are reflected; nothing is written into form fields.
    const payload = env.payload || {};
    const ctx = {
      url: payload.url,
      train_number: payload.train_number,
      from_station: payload.from_station,
      to_station: payload.to_station,
      journey_date: payload.journey_date,
      class: payload.class,
      quota: payload.quota,
      passengers: Array.isArray(payload.passengers) ? payload.passengers.length : 0
    };
    // Dispatch a custom event that page content (if any) can listen for.
    window.dispatchEvent(new CustomEvent("bingo:open_booking", { detail: ctx }));
  }
});

// Start observing on load.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", startObserving);
} else {
  startObserving();
}
