# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

- Backend: Python (FastAPI, SQLAlchemy). SQLite by default, Postgres optional.
- Frontend: React + Vite single-page app, built inside Docker and served by the Python backend.
- Deploy: Docker / docker compose on the user's own computer or home server. One container plus a data volume.

## Users

A household (a couple or family) sharing one self-hosted instance on a home server or NAS. Each person has their own login and their own data. One member is the admin who runs the server, controls registration, and manages users. Users are privacy-conscious and do not want their banking data held by a third-party company.

## Product Purpose

A private personal finance app. It tracks accounts, transactions, budgets, recurring bills, savings goals, assets, and net worth, and all data stays on hardware the household controls. Success means a household can see where its money goes and what it is worth without handing bank credentials or transaction history to a cloud service.

## Positioning

Self-hosted and file-first. For Canadian banks the app deliberately never connects to the bank directly. Data comes in through the bank's own standard export files (OFX/QFX/QBO, QIF, CSV). The user never gives their banking password to anyone, including this app. Direct sync exists only as an optional, off-by-default feature for non-Canadian providers (EU PSD2 via GoCardless, Brazil via Pluggy, SimpleFIN), and only when the admin supplies credentials.

## Operating Context

- Main workflow: log in to online banking, download a statement export, and import it here. Preview, map columns, dedupe, and auto-categorize with rules.
- Canadian institutions the household uses: RBC, TD, BMO, Scotiabank, CIBC, Tangerine, Simplii, EQ Bank, Wealthsimple, Neo Financial, Triangle (Canadian Tire Bank), Rogers Bank, PC Financial (PC Optimum Mastercard), Desjardins, National Bank, and credit unions.
- Mixed currencies are common (for example CAD and USD accounts), so conversion to a base currency needs configured exchange rates.

## Capabilities and Constraints

- Multi-user with per-user data isolation, admin settings, registration controls (open, invite-only, closed), and TOTP two-factor login.
- Accounts, transactions (search, filter, export), import (OFX/QFX/QBO, QIF, CSV with bank presets and a generic mapper), categorization rules, budgets, recurring transactions, savings goals, assets and liabilities, net worth and income-vs-expense reports with charts.
- Multi-currency with visible warnings when an exchange rate is missing.
- Canadian accounts: direct bank connection is disabled by policy. Import is the only path.
- Optional AI chat over the user's own data is off by default and aimed at self-hosted models (OpenAI-compatible endpoints such as Ollama).

## Brand Commitments

- Name: FinVault.
- Must not be a copy of Securo (github.com/securo-finance/securo). A first build copied its look (white sidebar, slate ground, indigo accent, icon tiles) and the user rejected it as "extremely similar". Its softness is welcome; its exact layout, indigo and icon-tile grammar are not.
- 2026-09-28: the user asked for a mix: Securo's softness and beauty (white rounded cards, soft shadows, friendly type, generous space) combined with the Sorting Case ideas (unsorted tray, category pigeonholes, postmarked imports). A strict Sorting Case build read as too technical: no all-caps condensed type, square corners or heavy rules. Teal and amber accents, not Securo's indigo.
- Must not feel like a bank or fintech marketing site, gamified, a dense spreadsheet, or clinical.

## Evidence on Hand

None. No testimonials, users, or benchmarks exist, and none may be invented.

## Product Principles

1. The data never leaves the household's hardware unless a member explicitly turns on a feature that sends it out.
2. Never ask for bank passwords. Standard export files are the trusted path.
3. Numbers must be honest. Show a warning instead of silently guessing a missing exchange rate or dropping amounts.
4. Importing a statement should be a two-minute routine, not a chore.
5. Everything optional (sync, AI) is off until someone turns it on.
