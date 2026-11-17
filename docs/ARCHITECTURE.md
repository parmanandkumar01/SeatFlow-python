# SeatFlow Architecture & Project Structure Guide

## 1. Project Directory Structure

```
SeatFlow/
├── assets/                         # Application branding & static assets
│   ├── branding/                   # Marketing & promotional graphics
│   │   └── SeatFlow Neon Train Logo.png
│   └── logo.png                    # Primary desktop application window logo
│
├── docs/                           # Architecture, guides, and engineering specifications
│   └── ARCHITECTURE.md             # This document
│
├── src/seatflow/                   # Main SeatFlow Python Package
│   ├── app/                        # Application bootstrap, routing & window coordinators
│   │   ├── application.py          # Central coordinator connecting UI, services & engines
│   │   └── __init__.py
│   │
│   ├── data/                       # Static station and train reference JSON data
│   │   ├── stations.json
│   │   └── trains.json
│   │
│   ├── database/                   # SQLite persistence, connection lifecycle & migrations
│   │   ├── database.py
│   │   └── __init__.py
│   │
│   ├── engines/                    # Pluggable Multi-Engine Subsystem
│   │   ├── base.py                 # Abstract Base Booking Engine, States, Capabilities & Models
│   │   ├── config.py               # Engine configuration & execution options
│   │   ├── events.py               # Strongly-typed lifecycle event models
│   │   ├── registry.py             # Dynamic Engine Registry & Factory (@register_engine)
│   │   ├── runner.py               # Threaded EngineWorker bridging engines to Qt Signals
│   │   ├── drivers/                # Shared browser/network drivers (Playwright, CDP, HTTP)
│   │   │   ├── browser_driver.py   # BaseBrowserDriver contract
│   │   │   └── http_driver.py      # BaseHttpDriver contract
│   │   └── implementations/        # Concrete engine implementations
│   │       ├── mock/               # Offline test & simulation engine
│   │       │   └── engine.py
│   │       └── README.md           # Guide on implementing new engines
│   │
│   ├── integrations/               # External browser & system bridges
│   │   ├── host_manifest.json      # Chrome native messaging manifest
│   │   └── native_host.py          # Native messaging host script
│   │
│   ├── repositories/               # Repository layer for domain persistence
│   │   ├── base_repository.py
│   │   ├── booking_history_repository.py
│   │   ├── irctc_account_repository.py
│   │   ├── pnr_repository.py
│   │   ├── proxy_repository.py
│   │   ├── settings_repository.py
│   │   ├── ticket_repository.py
│   │   └── vault_repository.py
│   │
│   ├── security/                   # Encryption, hashing & credential vault
│   │   ├── encryption.py
│   │   ├── password_hash.py
│   │   └── vault.py
│   │
│   ├── services/                   # Business domain orchestration services
│   │   ├── booking_service.py      # State machine & booking workflow orchestrator
│   │   ├── chrome_worker.py        # External browser worker runner
│   │   ├── irctc_account_service.py# Account credential management
│   │   ├── pnr_sync_service.py     # Background PNR status synchronization
│   │   ├── ticket_service.py       # Passenger & ticket profile service
│   │   └── train_service.py        # Train list search & live availability service
│   │
│   ├── ui/                         # PySide6 Desktop User Interface
│   │   ├── dialogs/                # Modal dialogs (Accounts, Captcha, 2FA, Payment, etc.)
│   │   ├── pages/                  # Views embedded in Main Window (Tickets, PNR, Settings)
│   │   ├── widgets/                # Reusable UI controls (Date picker, Toggle switch)
│   │   ├── app_icon.py             # Logo loader & icon cache
│   │   ├── main_window.py          # Primary application window
│   │   ├── ticket_panel_window.py  # Standalone worker & tatkal countdown panel
│   │   ├── theme.py                # Visual styling & color palettes
│   │   └── book_window.py          # Train booking form window
│   │
│   ├── utils/                      # Common utilities (Dates, Mappings, Watermark, Logger)
│   │   ├── dates.py
│   │   └── text.py
│   │
│   └── main.py                     # CLI entrypoint
│
├── tests/                          # Automated Pytest suite
│   ├── test_accounts.py
│   ├── test_engines_architecture.py# Tests for multi-engine contracts, registry & runner
│   ├── test_database.py
│   └── ...
│
├── pyproject.toml                  # Python package configuration & pytest settings
├── requirements.txt                # Python dependencies
└── run.sh                          # Desktop application launcher shell script
```

---

## 2. Pluggable Multi-Engine Architecture

SeatFlow is designed to support **multiple booking automation engines** side-by-side.

```
                    ┌────────────────────────────┐
                    │      SeatFlow Qt UI        │
                    │  (TicketPanelWindow, etc.) │
                    └──────────────┬─────────────┘
                                   │ Qt Signals
                                   ▼
                    ┌────────────────────────────┐
                    │       EngineWorker         │
                    │  (Async Thread Runner)     │
                    └──────────────┬─────────────┘
                                   │ EngineEvent Callbacks
                                   ▼
                    ┌────────────────────────────┐
                    │     BaseBookingEngine      │
                    └──────────────┬─────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│   Mock Engine    │      │  Ocean Hybrid    │      │ Playwright Direct│
│ (Simulation/Dev) │      │  (Stealth CDP)   │      │ (Browser Auto)   │
└──────────────────┘      └──────────────────┘      └──────────────────┘
```

### Key Components:
1. **`BaseBookingEngine` (`engines/base.py`)**: Abstract contract standardizing `prepare()`, `start()`, `pause()`, `resume()`, `stop()`, `cleanup()`.
2. **`EngineRegistry` (`engines/registry.py`)**: Registry & factory allowing runtime engine discovery and selection.
3. **`EngineWorker` (`engines/runner.py`)**: Executes an engine in a separate worker thread and emits thread-safe PySide6 Qt Signals to update UI elements without freezing the interface.
4. **`EngineEvent` (`engines/events.py`)**: Event models for status changes, step-by-step progress, CAPTCHA requests, 2FA requests, payment handoffs, and booking completion.

---

## 3. How to Implement a New Engine

1. Create a module under `src/seatflow/engines/implementations/<engine_name>/`.
2. Subclass `BaseBookingEngine` and decorate with `@register_engine`.
3. Implement the lifecycle methods:
   - `prepare(journey, passengers, account, config)`
   - `start()`
   - `pause()`, `resume()`, `stop()`, `cleanup()`
4. Emit events as steps progress:
   ```python
   self.emit_event(StepProgressEvent(self.engine_id, "LOGIN", 1, 5, "Logging in..."))
   ```
5. When completed, emit `BookingCompletedEvent(...)`.

---

## 4. Guidelines for Adding Future Features

| Future Feature | Recommended Location | Implementation Pattern |
|---|---|---|
| **New Engine** | `src/seatflow/engines/implementations/<engine>/` | Subclass `BaseBookingEngine`, decorate with `@register_engine` |
| **New Service** | `src/seatflow/services/<feature>_service.py` | Create service class, register in `services/__init__.py` |
| **New Database Table** | `src/seatflow/database/database.py` & `src/seatflow/repositories/` | Add table schema, create dedicated repository |
| **New UI Page / View** | `src/seatflow/ui/pages/<feature>_page.py` | Create `QWidget` inheriting class, add to sidebar in `MainWindow` |
| **New Modal Dialog** | `src/seatflow/ui/dialogs/<feature>_dialog.py` | Create `QDialog` inheriting class, wire to `Application` |
| **New External Integration** | `src/seatflow/integrations/<feature>/` | Provide self-contained client / bridge logic |

---

## 5. Development & Testing Commands

* **Run all tests:**
  ```bash
  .venv/bin/pytest
  ```
* **Run specific test:**
  ```bash
  .venv/bin/pytest tests/test_engines_architecture.py
  ```
* **Launch Application:**
  ```bash
  ./run.sh
  ```

---

## 6. Standalone Compilation & Packaging Guide

SeatFlow is engineered for turnkey compilation into standalone executable binaries (Linux ELF / Windows EXE) with **all dependencies, Qt shared libraries, master datasets, and pluggable engines bundled**.

### Compilation Tools
* **Specification File:** `packaging/SeatFlow.spec` (Custom PyInstaller spec configured with dynamic engine discovery, Qt plugins, and assets)
* **Build Script:** `packaging/build_binary.py` & `packaging/build.sh`

### How to Compile

1. **Install Build Requirements:**
   ```bash
   pip install pyinstaller>=6.0.0
   # Or install via optional build extras:
   pip install -e ".[build]"
   ```

2. **Compile as Directory Bundle (Recommended for fast launch):**
   ```bash
   ./packaging/build.sh
   # Binary output: dist/SeatFlow/SeatFlow
   ```

3. **Compile as Single Executable Binary (`--onefile`):**
   ```bash
   ./packaging/build.sh --onefile
   # Single binary output: dist/SeatFlow
   ```

### How Asset & Engine Bundling Works Under the Hood
1. **Dynamic Engine Discovery:** `packaging/SeatFlow.spec` automatically scans `seatflow.engines.implementations` and registers all engine classes as `hiddenimports`. Any new engine you write in `engines/implementations/` is automatically packaged into the compiled binary without manual config edits.
2. **Master Railway Data:** `src/seatflow/data/*.json` and `assets/*` are bundled inside the binary (`datas` section).
3. **Runtime Resource Resolution:** `seatflow.utils.resources` detects whether the app is running in standard Python mode, PyInstaller `sys._MEIPASS` (onefile), or `sys.frozen` (onedir), ensuring that logos and JSON master datasets never throw `FileNotFoundError`.

