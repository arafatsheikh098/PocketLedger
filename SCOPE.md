# SCOPE.md — contract for PocketLedger

> Locked at P0. Do not edit. Changes require an explicit decision recorded in DECISIONS.md and a commit that explains why.

## IN SCOPE

The following features are in scope. The text is copied word-for-word from PROJECT_SPEC.md.

### F1 Auth
login/logout, password change, user creation by CLI (python -m app.cli create-user), optional self-registration controlled by ALLOW_REGISTRATION (default false). argon2 password hashing, signed session cookies, CSRF on all state-changing requests, login rate limit in the database. Every query is scoped to the logged-in user; a test proves user A can never read or modify user B's data.

### F2 Accounts and categories
accounts (name, type: bank/mobile wallet/cash/card); one base currency per user (no conversion); categories CRUD with defaults seeded on user creation.

### F3 Transactions
add/edit/delete; fields: date, amount (integer minor units; expenses negative, income positive), description, category, account, notes, is_transfer flag (transfers are excluded from income, expense and budget totals); list with filters (date range, account, category, text, uncategorized), sorting and pagination.

### F4 CSV import wizard
upload (max size enforced); detect encoding (UTF-8 with or without BOM, common fallbacks) and delimiter; preview the first 20 rows; column mapping UI (date, description, and either a single signed amount column or separate debit/credit columns); explicit choice of date format (never guessed); decimal and thousands separator choice; saved mapping profiles per account; a dry-run summary (new, duplicates, errors) before anything is written; commit inside one database transaction; row-level error report; every import is a batch that can be undone. Duplicate detection key: hash of account + date + amount + normalized description + occurrence index, so two genuinely identical transactions on the same day are both kept while re-importing the same file adds nothing.

### F5 Categorization rules
user-editable ordered rules (description contains text, case-insensitive; first match wins); applied on import and via "re-apply to uncategorized"; a manual category choice is sticky and is never overwritten by rules.

### F6 Budgets and dashboard
monthly budget per category; progress bars; warning at 80% and over-budget banner at 100%; dashboard with this month's income, expense and net, top categories, and a 6-month trend; charts drawn with vendored Chart.js, each with an accessible table fallback; month boundaries in the user's timezone setting.

### F7 Export
XLSX (Transactions sheet and Monthly summary sheet) and CSV. Neutralize spreadsheet formula injection in text cells that begin with = + - @ tab or CR (numeric cells stay numeric).

### F8 Operations
GET /health; DEMO_MODE env var shows a banner "Demo with fake data. Do not enter real data."; SEED_ON_START re-seeds a deterministic demo user with 6 months of fake transactions; scripts/backup.sh (sqlite3 .backup) and a restore test; README "Threat model" section stating what is protected (argon2, per-user scoping, no third-party network calls) and what is not (database file is not encrypted at rest; use disk encryption).

## OUT OF SCOPE

Bank APIs or open banking, receipt OCR, multiple currencies or FX, shared households, recurring transactions, investments, loans, mobile app, machine-learning categorization, email, anything not listed above.

## ALLOWED STACK

Python 3.12; FastAPI; uvicorn; SQLModel; Alembic; SQLite (WAL); pydantic-settings; Jinja2; python-multipart; argon2-cffi; charset-normalizer; openpyxl; vendored HTMX (eval disabled) and vendored Chart.js (license kept); pytest, pytest-playwright, httpx, freezegun; ruff; Docker; GitHub Actions.

## ACCEPTANCE CRITERIA

Numbered, testable checks. Each milestone's gate verifies the criteria tagged for that milestone; the final scope audit verifies all of them.

### Global (G)

- **G1** `docker compose up --build` on a fresh clone serves the app; the demo seed loads.
- **G2** Money is stored as integers; no floats anywhere in money math (test and code search).
- **G3** Importing the same file twice adds zero rows; two identical same-day transactions inside one file are both kept.
- **G4** At least 6 messy CSV fixtures import correctly (different date formats, BOM, semicolon delimiter, decimal commas, thousands separators, debit/credit split columns, quoted commas, empty trailing rows).
- **G5** User A cannot read or change user B's data through any route (parametrized test over all routes with object ids).
- **G6** Exports never contain live formulas from text cells.
- **G7** CI is green.

### Per-feature

#### F1 Auth
- **F1.1** A logged-in user can log out, and the session cookie is invalidated server-side.
- **F1.2** A user can change their own password and the new password is required on next login.
- **F1.3** A user can be created via `python -m app.cli create-user` and can then log in.
- **F1.4** Self-registration is rejected when `ALLOW_REGISTRATION=false` (default) and accepted when `true`.
- **F1.5** Passwords are stored as argon2 hashes (verifiable by inspecting the user record).
- **F1.6** Session cookies are signed; tampering invalidates the session.
- **F1.7** Every state-changing request requires a valid CSRF token; missing or wrong token returns 4xx.
- **F1.8** Login attempts are rate-limited per username+IP in the database; the limit returns 4xx.
- **F1.9** Every query is scoped to the logged-in user (cross-user isolation test passes for auth-related routes).

#### F2 Accounts and categories
- **F2.1** A user can create, rename, and delete accounts of each allowed type.
- **F2.2** Each user has exactly one base currency; it is set on user creation and is editable in account settings.
- **F2.3** A user can create, rename, and delete categories.
- **F2.4** Default categories are seeded on user creation.

#### F3 Transactions
- **F3.1** A user can add, edit, and delete transactions.
- **F3.2** Expenses are stored as negative integers; income as positive integers.
- **F3.3** Each transaction records date, amount, description, category, account, notes, and `is_transfer`.
- **F3.4** Transfers are excluded from income, expense, and budget totals (computed and tested).
- **F3.5** The transactions list supports filters: date range, account, category, text, uncategorized.
- **F3.6** The transactions list supports sorting and pagination.

#### F4 CSV import wizard
- **F4.1** Uploads larger than the configured max size are rejected without being read.
- **F4.2** Encoding is detected (UTF-8 with/without BOM plus common fallbacks) and delimiter is detected.
- **F4.3** The first 20 rows are previewed before any write.
- **F4.4** The mapping UI supports both a single signed amount column and separate debit/credit columns.
- **F4.5** Date format is chosen explicitly by the user; the system never guesses between ambiguous formats.
- **F4.6** Decimal and thousands separator can be chosen; the chosen pair is applied consistently.
- **F4.7** Mapping profiles are saved per account and can be reused.
- **F4.8** A dry-run summary reports new, duplicates, and errors; nothing is written during dry run.
- **F4.9** Commit happens inside a single database transaction (atomic).
- **F4.10** Row-level errors are reported with line number and reason; the user can choose to skip them.
- **F4.11** Every import is a batch that can be undone; undo removes exactly its rows.
- **F4.12** Re-importing the same file adds zero rows.
- **F4.13** Two genuinely identical same-day transactions in one file are both kept.

#### F5 Categorization rules
- **F5.1** Rules are user-editable, ordered, and case-insensitive; the first matching rule wins.
- **F5.2** Rules are applied on import.
- **F5.3** Rules can be re-applied to uncategorized transactions via a button.
- **F5.4** A manually chosen category is sticky; rules never overwrite it.
- **F5.5** Matching trims whitespace before comparison.
- **F5.6** Re-apply only touches uncategorized rows.

#### F6 Budgets and dashboard
- **F6.1** A user can set a monthly budget per category.
- **F6.2** Progress bars render the spend vs. budget for the current month.
- **F6.3** A warning appears at exactly 80% of budget; an over-budget banner appears at exactly 100%.
- **F6.4** The dashboard shows this month's income, expense, and net.
- **F6.5** The dashboard shows the top spending categories for this month.
- **F6.6** The dashboard shows a 6-month trend.
- **F6.7** Charts are drawn with vendored Chart.js; each chart has an accessible table fallback with the same numbers.
- **F6.8** Month boundaries are computed in the user's timezone setting.

#### F7 Export
- **F7.1** XLSX export contains a Transactions sheet and a Monthly summary sheet.
- **F7.2** XLSX opens cleanly with openpyxl; sheet names, headers, and totals match the database.
- **F7.3** CSV export contains the same transactions as the on-screen filtered list.
- **F7.4** Text cells starting with `=`, `+`, `-`, `@`, tab, or CR are written as text with a safe prefix; numeric cells stay numeric.

#### F8 Operations
- **F8.1** `GET /health` returns 200 with a small JSON body.
- **F8.2** When `DEMO_MODE=true`, every page shows the banner "Demo with fake data. Do not enter real data.".
- **F8.3** When `SEED_ON_START=true`, a deterministic demo user is created/re-seeded with 6 months of fake transactions.
- **F8.4** `scripts/backup.sh` creates a SQLite `.backup` file; a restore test brings the data back.
- **F8.5** README contains a "Threat model" section listing what is and is not protected.
