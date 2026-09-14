# Bemas Treyler — Cari Hesap ve Muhasebe Takip Sistemi

Automated invoice/payment reconciliation system for Bemas Treyler: ingests Kolaysoft
e-Fatura Excel exports (incoming/outgoing) and bank transfer PDF receipts, maintains a
per-company current-account ledger, and exports clean Excel statements on demand.

**Desktop-only**: this runs entirely on the local machine — a local FastAPI backend
plus an Electron window — with no public website, domain, or server hosting involved.

## 1. System Architecture & Tech Stack

```
                     ┌─────────────────────────────┐
                     │      SQLite (local file)      │
                     │  (Users, Companies, Invoices,  │
                     │   Transactions, Receipts)      │
                     └───────────────┬────────────────┘
                                     │ SQLAlchemy ORM
                     ┌───────────────▼────────────────┐
                     │   FastAPI Backend (localhost)   │
                     │  backend/app/                   │
                     │   ├─ routers/   (Controller)     │
                     │   ├─ services/  (Service layer)  │
                     │   │   ├─ excel_ingest.py          │
                     │   │   ├─ pdf_receipt_parser.py    │
                     │   │   ├─ ledger_service.py        │
                     │   │   └─ excel_export.py          │
                     │   ├─ models.py (Repository/ORM)  │
                     │   └─ security.py (JWT + bcrypt)   │
                     └───────┬───────────────┬──────────┘
                             │ REST /api/*    │ static /adminpanel/*
                             │                │ (UI, served locally only)
                     ┌───────▼────────────────▼──────────┐
                     │      Electron Desktop App           │
                     │      (desktop/) — native window      │
                     │      pointed at http://localhost:8000 │
                     └───────────────────────────────────────┘
```

- **Backend**: FastAPI + SQLAlchemy, runs locally and serves both the REST API
  (`/api/*`) and the admin-panel UI (`/adminpanel/*`) on `http://localhost:8000` —
  nothing is exposed to the internet.
- **Database**: SQLite, a single file next to the backend — no separate DB server
  to install or maintain.
- **Desktop client**: Electron shell (`desktop/`) that opens
  `http://localhost:8000/adminpanel/` in a native window — this is the only client.
- **UI**: Framework-free HTML/CSS/JS (`frontend/`) — no build step; it's just how
  the desktop app's screens are implemented, not a public website.
- **Layering**: `routers/` (Controller: HTTP I/O, validation) → `services/`
  (business logic: parsing, ledger math, export) → `models.py` +
  SQLAlchemy `Session` (Repository/data access) → `schemas.py` (Pydantic
  request/response contracts), consistent with the required Controller/Service/
  Repository separation.

## 2. Database Schema

Implemented as SQLAlchemy models in [backend/app/models.py](backend/app/models.py).
Equivalent normalized DDL:

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    username      VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,   -- bcrypt hash, never plaintext
    full_name     VARCHAR(128),
    role          VARCHAR(32) NOT NULL DEFAULT 'admin',
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE companies (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    tax_id      VARCHAR(32) UNIQUE NOT NULL,   -- Vergi No / TCKN
    tax_office  VARCHAR(128),
    address     TEXT,
    phone       VARCHAR(32),
    email       VARCHAR(128),
    iban        VARCHAR(34),                    -- used to auto-match bank receipts
    notes       TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE invoices (
    id            INTEGER PRIMARY KEY,
    company_id    INTEGER NOT NULL REFERENCES companies(id),
    direction     VARCHAR(8) NOT NULL CHECK (direction IN ('incoming','outgoing')),
    invoice_number VARCHAR(64) NOT NULL,
    issue_date    DATE NOT NULL,
    due_date      DATE,
    amount        NUMERIC(14,2) NOT NULL,        -- tax-inclusive total
    tax_amount    NUMERIC(14,2),
    currency      VARCHAR(8) NOT NULL DEFAULT 'TRY',
    description   TEXT,
    ettn          VARCHAR(64),                    -- e-Fatura ETTN (Kolaysoft)
    source_file   VARCHAR(255),                   -- originating Excel filename
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (company_id, invoice_number, direction)  -- prevents duplicate re-ingestion
);

CREATE TABLE receipts (
    id                 INTEGER PRIMARY KEY,
    filename           VARCHAR(255) NOT NULL,
    file_path          VARCHAR(500) NOT NULL,
    raw_text           TEXT,
    ocr_used           BOOLEAN NOT NULL DEFAULT FALSE,
    parsed_amount      NUMERIC(14,2),
    parsed_date        DATE,
    parsed_currency    VARCHAR(8),
    sender_name        VARCHAR(255),
    receiver_name      VARCHAR(255),
    sender_iban        VARCHAR(34),
    receiver_iban      VARCHAR(34),
    description        TEXT,
    matched_company_id INTEGER REFERENCES companies(id),
    transaction_id     INTEGER REFERENCES transactions(id),
    uploaded_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE transactions (
    id                  INTEGER PRIMARY KEY,
    company_id          INTEGER NOT NULL REFERENCES companies(id),
    direction           VARCHAR(8) NOT NULL CHECK (direction IN ('inflow','outflow')),
    transaction_date    DATE NOT NULL,
    amount              NUMERIC(14,2) NOT NULL,
    currency            VARCHAR(8) NOT NULL DEFAULT 'TRY',
    counterparty_name   VARCHAR(255),
    counterparty_iban   VARCHAR(34),
    description         TEXT,
    source              VARCHAR(32) NOT NULL DEFAULT 'manual', -- 'manual' | 'receipt_pdf'
    receipt_id          INTEGER REFERENCES receipts(id),
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Balance calculation** (implemented in
[ledger_service.py](backend/app/services/ledger_service.py)), per company:

- `Net Customer Debt`  = Σ(outgoing invoices) − Σ(inflow transactions)  → what they owe us
- `Net Company Debt`   = Σ(incoming invoices) − Σ(outflow transactions) → what we owe them
- `Net Balance`        = `Net Customer Debt` − `Net Company Debt`

## 3. Core Implementation

All working code lives under [backend/app/](backend/app):

| Concern | File |
|---|---|
| Excel ingestion (Kolaysoft headers, Turkish number/date formats, dedup) | [services/excel_ingest.py](backend/app/services/excel_ingest.py) |
| PDF receipt parsing (pdfplumber text + Tesseract OCR fallback, IBAN/amount/date regex) | [services/pdf_receipt_parser.py](backend/app/services/pdf_receipt_parser.py) |
| Ledger / balance calculation | [services/ledger_service.py](backend/app/services/ledger_service.py) |
| Formatted per-company Excel export | [services/excel_export.py](backend/app/services/excel_export.py) |
| JWT auth + bcrypt password hashing | [security.py](backend/app/security.py), [deps.py](backend/app/deps.py) |
| REST endpoints | [routers/](backend/app/routers) (`auth`, `companies`, `invoices`, `uploads`, `receipts`, `ledger`) |
| Admin seed (creates tables + default admin user) | [seed.py](backend/app/seed.py) |

Key endpoints:

- `POST /api/auth/login` — returns a JWT bearer token
- `POST /api/uploads/invoices/excel` (`direction=incoming|outgoing`, `file=<xlsx>`) — parses and upserts invoices
- `POST /api/uploads/receipts/pdf` (`file=<pdf>`) — parses a bank receipt
- `POST /api/receipts/{id}/confirm` — turns a parsed receipt into a ledger `Transaction` once a human confirms the matched company/direction
- `GET /api/ledger/{company_id}` — full receivable/payable ledger + balances
- `GET /api/ledger/{company_id}/export` — downloads the formatted `.xlsx` statement
- `GET /api/companies/balances/all` — dashboard summary across all companies

All of this was smoke-tested end-to-end during development (login → create company →
ingest a synthetic Kolaysoft-style Excel file with Turkish headers/number formats →
parse a synthetic bank receipt PDF with embedded IBANs → compute ledger balances →
export `.xlsx`) — not left as placeholder logic.

**Seeded admin account**: username/password come from `SEED_ADMIN_USERNAME` /
`SEED_ADMIN_PASSWORD` in your own `.env` (see `.env.example`) — set them there
before first run. Stored as a bcrypt hash, never in plaintext.

## 4. Running the Desktop App

Everything runs locally on the machine that uses it — no domain, hosting, or
reverse proxy needed. Two pieces, both local: the backend (data + logic) and the
Electron window (UI).

### 1. Start the backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux/macOS
pip install -r requirements.txt
copy .env.example .env            # edit SECRET_KEY and the admin password
python -m app.seed                # creates tables + seeds the admin user
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Leave this running (it's the local server the desktop app talks to). For OCR of
scanned/photographed receipts, install Tesseract OCR (with the Turkish language
pack) separately and either put it on `PATH` or set `TESSERACT_CMD` in `.env`.
Text-layer (native) PDF receipts work without any OCR install.

### 2. Launch the desktop app

```bash
cd desktop
npm install
npm start                       # opens the native window against http://localhost:8000
npm run dist                    # build a distributable installer (electron-builder)
```

The Electron shell just opens `http://localhost:8000/adminpanel/` in a native
window — the backend from step 1 must already be running.

### Running it on multiple office computers

If more than one person needs this, run the backend on one machine on the local
network (e.g. the office server/PC) and set `BEMAS_SERVER_URL` on the other
machines' desktop app to that machine's local IP, e.g.:

```bash
set BEMAS_SERVER_URL=http://192.168.1.50:8000   # Windows
npm start
```

This still never touches the public internet — it's the same local network only.
