PROJECT: PocketLedger
PURPOSE: A privacy-first, self-hosted expense tracker. The user imports bank or mobile-wallet CSV statements, transactions are categorized by their own rules, monthly budgets show progress, and the dashboard shows where the money goes.

IN SCOPE
F1 Auth: login/logout, password change, user creation by CLI (python -m app.cli create-user), optional self-registration controlled by ALLOW_REGISTRATION (default false). argon2 password hashing, signed session cookies, CSRF on all state-changing requests, login rate limit in the database. Every query is scoped to the logged-in user; a test proves user A can never read or modify user B's data.
F2 Accounts and categories: accounts (name, type: bank/mobile wallet/cash/card); one base currency per user (no conversion); categories CRUD with defaults seeded on user creation.
F3 Transactions: add/edit/delete; fields: date, amount (integer minor units; expenses negative, income positive), description, category, account, notes, is_transfer flag (transfers are excluded from income, expense and budget totals); list with filters (date range, account, category, text, uncategorized), sorting and pagination.
F4 CSV import wizard: upload (max size enforced); detect encoding (UTF-8 with or without BOM, common fallbacks) and delimiter; preview the first 20 rows; column mapping UI (date, description, and either a single signed amount column or separate debit/credit columns); explicit choice of date format (never guessed); decimal and thousands separator choice; saved mapping profiles per account; a dry-run summary (new, duplicates, errors) before anything is written; commit inside one database transaction; row-level error report; every import is a batch that can be undone. Duplicate detection key: hash of account + date + amount + normalized description + occurrence index, so two genuinely identical transactions on the same day are both kept while re-importing the same file adds nothing.
F5 Categorization rules: user-editable ordered rules (description contains text, case-insensitive; first match wins); applied on import and via "re-apply to uncategorized"; a manual category choice is sticky and is never overwritten by rules.
F6 Budgets and dashboard: monthly budget per category; progress bars; warning at 80% and over-budget banner at 100%; dashboard with this month's income, expense and net, top categories, and a 6-month trend; charts drawn with vendored Chart.js, each with an accessible table fallback; month boundaries in the user's timezone setting.
F7 Export: XLSX (Transactions sheet and Monthly summary sheet) and CSV. Neutralize spreadsheet formula injection in text cells that begin with = + - @ tab or CR (numeric cells stay numeric).
F8 Operations: GET /health; DEMO_MODE env var shows a banner "Demo with fake data. Do not enter real data."; SEED_ON_START re-seeds a deterministic demo user with 6 months of fake transactions; scripts/backup.sh (sqlite3 .backup) and a restore test; README "Threat model" section stating what is protected (argon2, per-user scoping, no third-party network calls) and what is not (database file is not encrypted at rest; use disk encryption).

OUT OF SCOPE
Bank APIs or open banking, receipt OCR, multiple currencies or FX, shared households, recurring transactions, investments, loans, mobile app, machine-learning categorization, email, anything not listed above.

ALLOWED STACK
Python 3.12; FastAPI; uvicorn; SQLModel; Alembic; SQLite (WAL); pydantic-settings; Jinja2; python-multipart; argon2-cffi; charset-normalizer; openpyxl; vendored HTMX (eval disabled) and vendored Chart.js (license kept); pytest, pytest-playwright, httpx, freezegun; ruff; Docker; GitHub Actions.

GLOBAL ACCEPTANCE CRITERIA
G1 docker compose up --build on a fresh clone serves the app; the demo seed loads.
G2 Money is stored as integers; no floats anywhere in money math (test and code search).
G3 Importing the same file twice adds zero rows; two identical same-day transactions inside one file are both kept.
G4 At least 6 messy CSV fixtures import correctly (different date formats, BOM, semicolon delimiter, decimal commas, thousands separators, debit/credit split columns, quoted commas, empty trailing rows).
G5 User A cannot read or change user B's data through any route (parametrized test over all routes with object ids).
G6 Exports never contain live formulas from text cells.
G7 CI is green.

MILESTONES
M1 Foundation; M2 Auth and per-user isolation; M3 Accounts, categories, transactions; M4 CSV import wizard; M5 Categorization rules; M6 Budgets and dashboard; M7 Export, demo mode, end-to-end tests.
