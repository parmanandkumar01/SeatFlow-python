# Bingo Booking Assistant — Chrome Extension

Companion Chrome/Chromium extension for the Bingo Linux Browser Extension Bridge
(RT-04). Runs in the user's **visible** browser and provides user-assistance
context (CAPTCHA, OTP prompt, payment page, PNR) to the Bingo Linux desktop app
over Chrome Native Messaging.

## Project layout

```
bingo-chrome-extension/
├── manifest.json          # Manifest V3
├── background.js          # Service worker: native-messaging port + routing
├── content.js             # DOM observer on IRCTC pages (context only)
├── native-host/
│   └── host_manifest.json # Chrome native host manifest (reference)
└── README.md              # This file
```

## Security policy (non-negotiable)

- The extension carries **UI context only**: train, station, date, class, quota, page stage, PNR.
- It **never** reads, stores, or transmits IRCTC username/password, card number, CVV, PIN, or OTP.
- It **never** programmatically clicks, fills, or submits forms.
- It **never** controls navigation (no headless automation).
- Content script is limited to `https://www.irctc.co.in/*`.
- `externally_connectable.ids` is `["*"]` during development; restrict to the
  assigned extension ID after installation (see below).

## Installation (development / unpacked)

### 1. Register the native-messaging host on Linux

The desktop app (`bingo-linux/src/bingo_linux/integrations/native_host.py`) is the
native-messaging host. Register it with Chrome so the extension can connect:

```bash
# Copy the host manifest to Chrome's native-messaging hosts directory
mkdir -p ~/.config/google-chrome/NativeMessagingHosts/
cp bingo-linux/src/bingo_linux/integrations/host_manifest.json \
   ~/.config/google-chrome/NativeMessagingHosts/com.bingo.linux.bridge.json
```

Edit `~/.config/google-chrome/NativeMessagingHosts/com.bingo.linux.bridge.json` and:

1. Set `"path"` to the absolute path of a Python 3 executable (e.g. `/usr/bin/python3` or the venv python).
2. Replace `__EXTENSION_ID__` in `allowed_origins` with the extension's actual ID
   (assigned by Chrome after the first load; see step 3).
3. Ensure the `path` can launch the native host. The host reads length-prefixed
   JSON from stdin and writes responses to stdout — it performs **no network I/O**.

> Note: For an unpacked extension, Chrome assigns a stable extension ID based on
> the extension directory path. Load the extension once, read its ID from
> `chrome://extensions`, then update `allowed_origins` to
> `chrome-extension://<EXTENSION_ID>/`.

### 2. Load the extension

1. Open Chrome/Chromium and go to `chrome://extensions`.
2. Enable **Developer mode** (toggle in the top-right).
3. Click **Load unpacked** and select the `bingo-chrome-extension/` directory.
4. Note the extension ID shown on the extension's card.

### 3. Update host manifest with the extension ID

Edit `~/.config/google-chrome/NativeMessagingHosts/com.bingo.linux.bridge.json` and set:

```json
"allowed_origins": [
  "chrome-extension://<YOUR_EXTENSION_ID>/"
]
```

### 4. Run the desktop app

Start Bingo Linux (`./run.sh` or `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m src.bingo_linux.main`).

In Settings, enable the **Browser Extension Bridge** (opt-in, default disabled).

### 5. Use

- Open a ticket pair panel and click **Launch Worker**.
- With the bridge enabled, the desktop app sends `open_booking` to the extension,
  which surfaces booking context on the IRCTC page (no form filling).
- The visible browser is always opened; the user performs login, CAPTCHA, and
  payment manually.
- When the extension detects CAPTCHA / OTP / payment page / PNR, it surfaces an
  event to the desktop app, which prompts the user.

## Uninstall / disable

- Disable or remove the extension from `chrome://extensions`.
- The desktop app falls back to clipboard + visible-browser handoff (no error)
  when the extension is absent or the bridge is disabled.
- Remove `~/.config/google-chrome/NativeMessagingHosts/com.bingo.linux.bridge.json`
  to unregister the native host.

## Production (packed CRX)

1. Pack the extension via `chrome://extensions` → "Pack extension" to produce
   `.crx` + `.pem`.
2. Keep the `.pem` private key secure — it determines the extension ID used in
   `allowed_origins`.
3. Distribute the `.crx`; users install it and register the native host as above.
