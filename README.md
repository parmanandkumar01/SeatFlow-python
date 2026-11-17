# SeatFlow

A modern, native Linux desktop application built with Python and PySide6 for train booking management, IRCTC account credentials, PNR tracking, and automated multi-engine booking execution.

---

## Key Features

- **Profile & Ticket Management:** Seamless creation, editing, and duplication of passenger lists and journey profiles.
- **Pluggable Multi-Engine Architecture:** Modular engine subsystem supporting multiple independent booking automation engines (Mock, Hybrid, Browser CDP, Direct API) with unified Qt event integration.
- **IRCTC Account Vault:** Secure local credential management, 2FA/CAPTCHA workflows, and multi-account rotation.
- **PNR & Booking History:** Local tracking of booked tickets, automatic status sync, and printable Electronic Reservation Slip (ERS) HTML rendering.
- **High-Performance Tatkal Clock:** Millisecond-accurate countdown timer for Tatkal AC (10:00 AM) and Non-AC (11:00 AM) booking windows.
- **Native Security & Privacy:** Default-deny network privacy model, encrypted local SQLite database, and offline-first design.

---

## Directory Structure

```
SeatFlow/
├── assets/                     # Application logos and brand imagery
│   ├── branding/
│   │   └── SeatFlow Neon Train Logo.png
│   └── logo.png
├── docs/                       # Architecture and developer documentation
│   └── ARCHITECTURE.md         # Detailed architectural blueprint & guide
├── src/seatflow/               # Core application package
│   ├── app/                    # Application bootstrap & lifecycle management
│   ├── data/                   # Static train & station reference data
│   ├── database/               # SQLite database schemas and migrations
│   ├── engines/                # Pluggable multi-engine subsystem
│   │   ├── base.py             # BaseBookingEngine contract & domain models
│   │   ├── events.py           # Engine event models (Status, Steps, CAPTCHA, Payment)
│   │   ├── registry.py         # Dynamic engine registry & factory
│   │   ├── runner.py           # Thread-safe EngineWorker Qt signal bridge
│   │   ├── drivers/            # Shared browser and HTTP automation drivers
│   │   └── implementations/    # Engine implementations (Mock, Ocean Hybrid, etc.)
│   ├── integrations/           # Browser extensions and native messaging hosts
│   ├── repositories/           # Database repositories
│   ├── security/               # Encryption, hashing, and password vault
│   ├── services/               # Domain business logic services
│   ├── ui/                     # PySide6 desktop user interface
│   │   ├── dialogs/            # Modal popup dialogs
│   │   ├── pages/              # Embedded views
│   │   ├── widgets/            # Reusable UI widgets
│   │   └── ... windows         # Main, Ticket Panel, Book, Vault windows
│   ├── utils/                  # Date, text, and helper utilities
│   └── main.py                 # Application startup entrypoint
├── tests/                      # Automated test suite (520+ tests)
├── pyproject.toml              # Build config and pytest settings
├── requirements.txt            # Dependency list
└── run.sh                      # Launch script
```

---

## Getting Started

### Prerequisites
* Python 3.10 or later
* Linux (Ubuntu/Debian/Fedora/Arch)

### Installation
```bash
# 1. Create virtual environment
python3 -m venv .venv

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
./run.sh
# Or directly via Python:
python3 -m seatflow.main
```

### Running Tests
```bash
.venv/bin/pytest
```

For detailed architectural documentation and instructions on developing new engines, please see [ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## License
MIT License
