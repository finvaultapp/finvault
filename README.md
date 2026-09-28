# FinVault

[![CI](https://github.com/henilsarang/finvault/actions/workflows/ci.yml/badge.svg)](https://github.com/henilsarang/finvault/actions/workflows/ci.yml)

Private household finance, sorted on your own hardware.

FinVault is a self-hosted personal finance app for households that want clean budgets, statement imports, shared-cost tracking, and reports without handing bank credentials or transaction history to a cloud company. It is file-first for Canadian banks: download the QFX/OFX/QBO/QIF/CSV export or text-based PDF statement your bank already provides, preview it, import it, and sort the new lines.

![FinVault dashboard](docs/screenshots/dashboard.png)

## Why It Exists

Most finance apps ask for too much trust. FinVault is built around a quieter bargain:

- Your accounts, transactions, receipts, reports, 2FA secrets, and provider tokens live in your own database.
- Canadian accounts never connect directly to a bank and never ask for an online-banking password.
- Optional features such as bank sync, OCR, notifications, exchange-rate fetching, and AI are off until an admin enables them.
- When exchange rates are missing, totals warn you instead of silently guessing.
- Each household member has a separate login and separate finance data.

## Product Tour

### Sort New Transactions

Imported lines without a category land in an amber tray. Rules and remembered merchants suggest where they belong, and the monthly pigeonhole wall shows where spending is going.

![Dashboard sorting room](docs/screenshots/dashboard.png)

### Import Statements

FinVault handles OFX/QFX/QBO, QIF, CSV exports, and text-based PDF statements, including Canadian bank presets and a generic mapper for unusual files. Duplicates are skipped, overlapping date ranges are fine, and imports can be undone.

![Statement import](docs/screenshots/import.png)

### Review Transactions

Search, filter, bulk edit, categorize, split, share, attach receipts, and export as CSV, OFX, or JSON.

![Transactions table](docs/screenshots/transactions.png)

### Understand Trends

Reports show income vs expenses, net worth, category breakdowns, budgets, goals, registered-plan reminders, tax summaries, and multi-currency warnings.

![Reports](docs/screenshots/reports.png)

## Feature Highlights

- Multiple account types: chequing, savings, credit cards, cash, loans, investments, and assets.
- Statement imports for QFX/OFX/QBO, QIF, CSV, TXT, TSV, and text-based PDF.
- Built-in CSV presets for RBC, TD, CIBC, BMO, Scotiabank, Tangerine, Simplii, Wealthsimple, Rogers Bank, PC Financial, American Express Canada, and more.
- Categorization rules, remembered merchants, bulk editing, and one-click sorting.
- Budgets, recurring bills, bill reminders, goals, assets, debts, and net worth.
- TFSA, RRSP, and FHSA contribution-room tracking.
- Tax-time summaries for medical, child care, donations, moving, home office, and other deductible categories.
- Shared expenses, people balances, and settle-up tracking.
- Receipt attachments with optional local OCR through Tesseract.
- Multi-currency conversion with explicit missing-rate warnings.
- Canadian French interface and French default categories.
- Optional non-Canadian bank sync via GoCardless, Pluggy, or SimpleFIN.
- Optional AI chat over your own data, with a preview of exactly what will be sent before using it.

## Canadian Banks

For Canadian accounts, FinVault is import-only by design. Canada does not yet have a live consumer open-banking system, and many aggregators fill that gap by asking for online-banking credentials. FinVault does not do that.

The flow is:

1. Sign in to your bank's website.
2. Download transactions as QFX, OFX, QBO, QIF, CSV, or a text-based PDF statement.
3. Upload the file in FinVault.
4. Review the preview, confirm column mapping if needed, and import.
5. Sort any uncategorized lines.

Canadian accounts are blocked from direct sync when the account country is CA, currency is CAD, or the provider institution looks Canadian.

## Run With Docker

```bash
git clone https://github.com/henilsarang/finvault.git
cd finvault
cp .env.example .env
docker compose up -d --build
```

Open [http://localhost:8000](http://localhost:8000). The first account you create becomes the admin. Data is stored in the `finvault-data` Docker volume.

Optional services:

```bash
docker compose --profile postgres up -d
docker compose --profile ai up -d
docker compose exec ollama ollama pull llama3.1
```

If you expose FinVault beyond a trusted LAN, put it behind HTTPS and set:

```env
COOKIE_SECURE=true
FORWARDED_ALLOW_IPS=<your reverse proxy IP or CIDR>
```

## Configuration

See [.env.example](.env.example) for the full list.

| Setting | Default | Purpose |
| --- | --- | --- |
| `REGISTRATION_MODE` | `invite` | Who can sign up after the admin: `open`, `invite`, or `closed`. |
| `DEFAULT_CURRENCY` | `CAD` | Suggested base currency for new members. |
| `COOKIE_SECURE` | `false` | Set to `true` behind HTTPS. |
| `FORWARDED_ALLOW_IPS` | Uvicorn default | Trust forwarded headers only from your reverse proxy. |
| `ALLOW_PRIVATE_OUTBOUND_URLS` | `false` | Allow user-configured webhook/provider URLs to call LAN hosts. |
| `BANK_SYNC_ENABLED` | `false` | Master switch for optional non-Canadian sync. |
| `SIMPLEFIN_ENABLED` | `false` | Allows SimpleFIN setup tokens. |
| `AI_ENABLED` | `false` | Enables the household AI endpoint. Members must still opt in. |
| `FX_FETCH_ENABLED` | `false` | Enables fetching ECB exchange rates. |
| `FOLDER_IMPORT_ENABLED` | `false` | Enables watched-folder imports. |
| `OCR_ENABLED` | `false` | Enables local receipt OCR. |

## Backups

Everything important is in the data volume. For SQLite:

```bash
docker compose exec finvault python -c "import sqlite3; s=sqlite3.connect('/data/finvault.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d)"
docker compose cp finvault:/data/backup.db ./finvault-backup.db
```

Keep `/data/secret.key` or your `SECRET_KEY` with the backup. TOTP secrets, AI keys, and provider credentials are encrypted with it.

## Security Notes

- Passwords are bcrypt-hashed after SHA-256 prehashing, so long passphrases keep their entropy.
- Sessions are HttpOnly, SameSite cookies; cookie-authenticated writes require the `X-FinVault` header.
- Login throttling applies both per apparent IP/email pair and per email.
- TOTP secrets, provider tokens, and AI keys are encrypted at rest.
- Security headers include no-sniff, frame denial, referrer policy, permissions policy, and CSP for the SPA.
- Uploaded receipts are sniffed by file bytes, stored under random names, and capped at 10 MB.
- Statement imports are capped at 15 MB before parsing.
- PDF statement import is best-effort and works only when the statement contains selectable text. Prefer QFX/OFX or CSV when available.
- User-configured outbound URLs are guarded against localhost/private-network SSRF by default.
- Alembic migrations run at startup, with a compatibility path for older local databases.

## Development

Backend:

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest
.venv/Scripts/python -m scripts.demo_seed
.venv/Scripts/python -m uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
npm run build
npm audit --omit=dev
```

The Vite dev server proxies `/api` to `localhost:8000`. API docs are available at `/api/docs` while the backend is running.

## Screenshots

The screenshots in `docs/screenshots` are generated from the synthetic demo household.

```bash
cd frontend
npm run build
# In another terminal, run the backend with demo data on http://127.0.0.1:8765
npm run screenshots
```

Demo credentials:

```text
demo@finvault.local
demo-password-123
```

All demo transactions and balances are fake.

## CI

GitHub Actions runs:

- backend dependency install and `pytest`
- frontend `npm ci`
- frontend production build
- production dependency audit

## Running the tests

```bash
cd backend && python -m pytest -q          # API and importer tests

cd frontend
npm run build                              # the browser tests use the built app
npx playwright install chromium            # once
npm run test:e2e                           # Playwright, Chromium only
```

`npm run test:e2e` seeds a demo household into a temporary data folder and starts `backend/scripts/serve_local.py` on port 8765 (`E2E_PORT` to change it, `PYTHON` to pick the interpreter with the backend requirements). To test a server that is already running, set `E2E_BASE_URL` instead. CI (`.github/workflows/ci.yml`) runs the backend tests, the frontend build, the browser tests and a Docker build with a health-check smoke test.

## Credits

FinVault's interface takes inspiration from soft household sorting rooms and statement envelopes. Earlier visual exploration referenced [Securo](https://github.com/securo-finance/securo), but no Securo code is included.
