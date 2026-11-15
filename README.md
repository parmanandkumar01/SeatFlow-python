# Bingo Linux Replacement

A native Linux desktop application for managing train booking profiles, IRCTC accounts, and related local data.

This is an independent reimplementation of the original Bingo Windows application, built with Python and PySide6.

## Features (MVP)

- Ticket profile management
- IRCTC account management
- Booking history
- PNR viewer
- Application settings
- Master vault (planned)

## Technology Stack

- Python 3.14+
- PySide6 6.12.0
- SQLite (planned)

## Getting Started

### Prerequisites

- Python 3.10 or later

### Installation

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m src.bingo_linux.main
```

## Project Structure

```
bingo-linux/
├── .venv/
├── src/
│   └── bingo_linux/
│       ├── main.py
│       ├── app/
│       ├── ui/
│       ├── services/
│       ├── database/
│       ├── security/
│       ├── integrations/
│       └── utils/
├── tests/
├── assets/
├── requirements.txt
├── .gitignore
└── README.md
```

## License

MIT License
