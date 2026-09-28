# FinVault

A private personal finance app for your household that you run yourself. Your accounts, transactions and reports live in a database on your own computer or home server, not with a company.

- Multiple accounts (chequing, savings, credit cards, loans, cash, investments), each in its own currency
- Import statements from **QFX/OFX, QBO, QIF and CSV**, with duplicate detection and one-click undo
- Search, filter and bulk-edit transactions; export to CSV, OFX or JSON
- Rules that categorize repeat purchases automatically, plus "remembered merchants" from your history
- Budgets, recurring transactions (with detection from history), savings goals
- Assets and debts (home, car, RRSP/TFSA, mortgage) with value history
- Net worth and income-vs-expense reports with charts
- Multi-currency, with a visible warning whenever an exchange rate is missing (amounts are never silently guessed)
- Multi-user with per-person data, admin panel, registration controls (open / invite / closed), TOTP two-factor login with recovery codes
- Optional bank sync for **non-Canadian** banks (GoCardless for EU PSD2, Pluggy for Brazil, SimpleFIN for the US)
- Optional AI chat over your own data, **off by default**: use a self-hosted model such as Ollama, or let each member connect their own ChatGPT (OpenAI) account with an API key

### Built for Canadian households

- **TFSA, RRSP and FHSA room tracker:** copy each year's room from CRA My Account (or your Notice of Assessment), link the account, and FinVault counts contributions and withdrawals against it. It warns you before you over-contribute, allows for the RRSP's $2,000 buffer, and reminds you that TFSA withdrawals only come back as room the next January 1. These are reminders, not tax advice.
- **Tax time:** tag categories (Health = medical, and so on) or single transactions as medical, child care, donations, moving or home office, and get a yearly summary plus a CSV to hand to your accountant. Split lines and shared costs are counted correctly.
- **Français:** the whole interface is available in Canadian French (Settings → Language), with French money and date formats. Members who sign up in French get French default categories.
- **Watched import folder:** mount a NAS folder at `/inbox`, turn it on per account, and bank exports saved there are imported every couple of minutes. Imported files move to `imported/`; unreadable ones move to `failed/` with a note explaining why.

### Household money

- **Split and shared costs:** split one transaction across categories, or share it with a person (partner, roommate). Only your part counts as your spending. FinVault tracks who owes whom, and settling up can be linked to the e-transfer that paid you back so it isn't counted as income.
- **Transfer matching:** card payments and moves between your own accounts are paired automatically after each import, so they never count as spending or income. Unclear pairs are offered for review.
- **Bills calendar and reminders:** every recurring bill on a month calendar, with reminders a chosen number of days ahead by ntfy push or email (SMTP). Amounts can be hidden from lock-screen notifications.
- **Receipts:** attach a photo or PDF to any transaction. With OCR turned on, Tesseract reads the text on your own server, the text becomes searchable, and FinVault flags a receipt total that doesn't match the transaction.

## Canadian banks: file import only

FinVault never connects to a Canadian bank and never asks for an online-banking password. Canada doesn't yet have a live consumer open-banking system, and the aggregators that fill the gap usually need your banking password. So for Canadian accounts the only way in is the export file your bank already gives you:

1. Sign in to your bank's own website.
2. Open the account, find **Download** / **Export** / **Download transactions**.
3. Choose **Quicken (QFX)**, **Money (OFX)** or **QuickBooks (QBO)** if offered. This is the standard format and carries stable transaction IDs. Otherwise choose **CSV**.
4. Upload it on the **Import** page and check the preview.

Built-in CSV layouts: RBC, TD, CIBC, BMO (bank and Mastercard), Scotiabank, Tangerine, Simplii, Wealthsimple, Rogers Bank, PC Financial, American Express Canada. EQ Bank, Neo Financial, Triangle (Canadian Tire), Desjardins, National Bank and credit unions are read with the generic matcher, which understands English and French headers, semicolons, decimal commas, separate debit/credit columns and debit/credit type columns. If a bank changes its layout you can remap the columns in the preview. Credit-card files that list purchases as positive numbers are detected and flipped (you can override this).

Canadian accounts are marked "Import only". The sync code refuses to link any account with country CA, CAD currency or a `.ca` institution.

## Run it with Docker

```bash
git clone <this repo> finvault && cd finvault
cp .env.example .env        # optional: edit settings
docker compose up -d --build
```

Open <http://localhost:8000>. The first account you create becomes the admin. Data lives in the `finvault-data` Docker volume (SQLite by default).

Optional extras:

```bash
docker compose --profile postgres up -d   # use Postgres (also set DATABASE_URL in .env)
docker compose --profile ai up -d         # run Ollama next to FinVault for AI chat
docker compose exec ollama ollama pull llama3.1
```

If you expose FinVault beyond your home network, put it behind HTTPS (Caddy, Traefik, Tailscale) and set `COOKIE_SECURE=true`.

### Backups

Everything is in the data volume. For SQLite:

```bash
docker compose exec finvault python -c "import sqlite3; s=sqlite3.connect('/data/finvault.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d)"
docker compose cp finvault:/data/backup.db ./finvault-backup.db
```

Keep `/data/secret.key` (or your `SECRET_KEY`) with the backup: 2FA secrets and provider tokens are encrypted with it.

## Configuration

See [.env.example](.env.example). Everything optional is off by default:

| Setting | Default | What it does |
| --- | --- | --- |
| `REGISTRATION_MODE` | `invite` | Who can sign up after the admin: `open`, `invite` or `closed`. Admins can change it in the app. |
| `DEFAULT_CURRENCY` | `CAD` | Suggested main currency for new members. |
| `BANK_SYNC_ENABLED` | `false` | Master switch for bank sync (admin can toggle). |
| `GOCARDLESS_SECRET_ID/KEY` | empty | Enables EU PSD2 banks via GoCardless Bank Account Data. |
| `PLUGGY_CLIENT_ID/SECRET` | empty | Enables Brazilian banks via Pluggy. |
| `SIMPLEFIN_ENABLED` | `false` | Allows SimpleFIN; each member pastes their own setup token. |
| `AI_ENABLED` | `false` | AI chat. Each member must also opt in under Settings. |
| `AI_BASE_URL` / `AI_MODEL` | Ollama / `llama3.1` | Any OpenAI-compatible endpoint. The admin panel warns if it isn't on your local network. |
| (admin toggle) | off | "Let members connect their own ChatGPT (OpenAI) account". Each member pastes an OpenAI API key in Settings → AI assistant; it's checked with OpenAI, stored encrypted, and billed to their OpenAI account. A ChatGPT Plus/Pro subscription can't be used by other apps, so an API key from platform.openai.com/api-keys is required. |
| `FX_FETCH_ENABLED` | `false` | Adds a button to fetch ECB exchange rates (only currency codes are sent). |

## Security notes

- Passwords are hashed with bcrypt; sessions are HttpOnly, SameSite cookies; write requests need a custom header (CSRF defence).
- Login and 2FA attempts are rate-limited. TOTP secrets and bank provider tokens are encrypted at rest.
- Each member's data is isolated; admins manage members but can't read their finances in the app.
- The app sends strict security headers (CSP, frame denial, no-sniff).

## Development

```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt pytest   # use .venv/bin on macOS/Linux
.venv/Scripts/python -m pytest
.venv/Scripts/python -m scripts.demo_seed      # optional: synthetic demo household (demo@finvault.local / demo-password-123)
.venv/Scripts/python -m uvicorn app.main:app --reload

# frontend (proxies /api to :8000)
cd frontend && npm install && npm run dev
```

API docs are at `/api/docs` while the server runs.

## Credits

The interface follows the look of [Securo](https://github.com/securo-finance/securo), an open-source self-hosted finance manager. No Securo code is included.
