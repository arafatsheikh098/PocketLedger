# PLAN.md — milestones, files, and tests

Each milestone lists the files it creates/modifies and the tests it must include. Milestones run in order; the previous milestone's gate must pass before the next one starts. A milestone is complete only when every acceptance criterion tagged for it is verified by a real command output.

## M1 — Foundation

**Scope tags:** G1, G2, G7 (partial: CI skeleton)

**Files to create**

- `pyproject.toml` — pinned dependencies, ruff config, pytest config
- `app/__init__.py` — FastAPI app factory
- `app/config.py` — pydantic-settings `Settings` (env, defaults, .env.example)
- `app/db.py` — SQLModel engine, `get_session`, WAL pragma, foreign keys pragma
- `app/models/__init__.py` — re-exports all SQLModel models
- `app/models/user.py` — `User` (id, username, password_hash, base_currency, timezone, created_at)
- `app/models/account.py` — `Account` (id, user_id, name, type)
- `app/models/category.py` — `Category` (id, user_id, name, is_default)
- `app/models/transaction.py` — `Transaction` (id, user_id, account_id, category_id, date, amount_minor, currency, description, notes, is_transfer, import_batch_id, dedup_key, manual_category)
- `app/models/import_batch.py` — `ImportBatch` (id, user_id, account_id, filename, mapping, created_at, status)
- `app/models/rule.py` — `Rule` (id, user_id, pattern, category_id, position, created_at)
- `app/models/budget.py` — `Budget` (id, user_id, category_id, month, amount_minor)
- `app/models/login_attempt.py` — `LoginAttempt` (id, username, ip, success, created_at)
- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/0001_initial.py` — initial schema
- `app/money.py` — integer minor-units helpers: `parse`, `format`, `to_minor`, `from_minor` (configurable decimal/thousands separators, sign conventions, parentheses, empty handling)
- `app/main.py` — FastAPI app entrypoint, mounts `GET /health`
- `app/templates/base.html.j2` — Jinja base layout
- `app/static/vendor/htmx.min.js` — vendored HTMX (eval disabled by CSP)
- `.env.example` — documented env vars
- `Dockerfile` — non-root, HEALTHCHECK, data volume
- `docker-compose.yml` — app + named volume
- `Makefile` — `make test`, `make lint`, `make up`, `make down`
- `.github/workflows/ci.yml` — ruff + pytest on push
- `tests/conftest.py` — temp DB, client fixture
- `tests/test_money.py` — covers `"1,234.56"`, `"1.234,56"`, `"(500.00)"`, `"-500"`, `"500-"`, empty values, with explicit expected results/errors
- `tests/test_health.py` — `GET /health` returns 200
- `tests/test_db_wal.py` — SQLite journal mode is WAL
- `tests/test_alembic.py` — `alembic upgrade head` and `alembic downgrade base` succeed

**Tests it must include**
- Money parsing table (A3)
- `/health` 200
- WAL mode enabled
- Alembic upgrade + downgrade round-trip

**Acceptance evidence (gate)**
- `docker compose up --build` serves `/health` and writes DB to the volume
- `alembic upgrade head` and `alembic downgrade base` clean
- `pytest` green
- `ruff check` clean
- `git diff --stat main` shows only M1 files

## M2 — Auth and per-user isolation

**Scope tags:** F1.1–F1.9, G5 (fixture established here, applied per-route in later milestones)

**Files to create**

- `app/auth/passwords.py` — argon2-cffi hash + verify
- `app/auth/sessions.py` — signed cookie session, secret-loaded
- `app/auth/csrf.py` — token issue + verify
- `app/auth/rate_limit.py` — DB-backed per username+IP
- `app/auth/scoped.py` — `scoped_query(Session, User, Model)` helper used by every later route
- `app/middleware.py` — session + CSRF middleware
- `app/routers/auth.py` — login, logout, password change, optional register
- `app/templates/login.html.j2`, `change_password.html.j2`
- `app/cli.py` — `python -m app.cli create-user`
- `tests/test_auth.py` — login, logout, password change, register flag, rate limit
- `tests/test_csrf.py` — state-changing request without CSRF fails
- `tests/test_session_signing.py` — tampered cookie rejected
- `tests/test_isolation.py` — two-user fixture; every M2 route tested cross-user
- `tests/test_secret_key_required.py` — production startup refuses default `SECRET_KEY`

**Acceptance evidence (gate)**
- Parametrized test discovers M2 routes and enforces session+CSRF
- Two-user isolation test green for M2
- Registration default-off, on with env
- Rate limit + cookie flags asserted
- Production refuses default `SECRET_KEY`

## M3 — Accounts, categories, transactions

**Scope tags:** F2.1–F2.4, F3.1–F3.6, G5 (isolation applied to all new routes)

**Files to create**

- `app/routers/accounts.py` — CRUD; uses `scoped_query`
- `app/routers/categories.py` — CRUD; seeds defaults on user creation
- `app/routers/transactions.py` — add/edit/delete/list with filters, sort, pagination
- `app/templates/accounts/*`, `categories/*`, `transactions/*` — list + form templates
- `app/services/totals.py` — income/expense/net, excluding `is_transfer`
- `tests/test_accounts.py`, `test_categories.py`, `test_transactions.py`
- `tests/test_totals.py` — transfers excluded
- `tests/test_filters_matrix.py` — date × account × category × text × uncategorized combinations
- `tests/test_pagination.py` — boundaries
- `tests/test_delete_account.py` — block-with-transactions or cascade (decision logged)
- `tests/test_isolation_routes.py` — extended to every M3 route

**Acceptance evidence (gate)**
- Sign convention test
- Transfers excluded test
- Filter matrix test
- Pagination boundary test
- Isolation test for every M3 route

## M4 — CSV import wizard

**Scope tags:** F4.1–F4.13, G3, G4

**Files to create**

- `app/services/csv_detect.py` — encoding via `charset-normalizer`, delimiter via `csv.Sniffer` + fallback
- `app/services/csv_parse.py` — preview 20 rows
- `app/services/mapping.py` — single signed amount OR debit/credit; date format choice; decimal/thousands choice
- `app/services/dedup.py` — `dedup_key = sha256(account|iso_date|amount_minor|normalized_description|occurrence_index)`
- `app/services/import_batch.py` — dry-run, commit-in-one-transaction, error report, undo
- `app/routers/imports.py` — wizard endpoints
- `app/templates/imports/*` — upload, preview, mapping, dry-run, result, undo
- `tests/fixtures/*.csv` — 6 messy fixtures (varied date formats, BOM, semicolon, decimal comma, thousands separator, debit/credit split, quoted commas, empty trailing rows)
- `tests/fixtures/expected/*.json` — golden files per fixture
- `tests/test_csv_detect.py`
- `tests/test_csv_dryrun.py` — dry run writes nothing
- `tests/test_csv_idempotent.py` — re-import adds 0; same-day duplicate kept
- `tests/test_csv_errors.py` — row errors reported with line numbers
- `tests/test_csv_undo.py` — undo removes exactly the batch's rows
- `tests/test_csv_limits.py` — oversize + non-CSV rejected
- `tests/test_csv_date_ambiguity.py` — ambiguous date requires explicit format choice
- `tests/test_isolation_routes.py` — extended to M4 routes

**Acceptance evidence (gate)**
- 6 fixtures match golden files
- Dry run writes nothing
- Re-import adds zero
- Same-day identical kept
- Row error reporting
- Undo exact
- Oversize/non-CSV rejected
- Date format never guessed

## M5 — Categorization rules

**Scope tags:** F5.1–F5.6, G5

**Files to create**

- `app/services/rules.py` — `apply_rules(description, rules) -> category_id | None`, case-insensitive, trimmed, first match wins, sticky
- `app/routers/rules.py` — CRUD with order
- `app/templates/rules/*`
- Modify `app/services/import_batch.py` — apply rules on import
- `app/routers/transactions.py` — `POST /transactions/reapply-rules` (uncategorized only)
- `tests/test_rules_order.py` — first match wins, order editable
- `tests/test_rules_sticky.py` — manual category never overwritten
- `tests/test_rules_case_insensitive.py` — case + trim
- `tests/test_rules_reapply_uncategorized_only.py`
- `tests/test_isolation_routes.py` — extended to M5 routes

**Acceptance evidence (gate)**
- Order + first-match test
- Sticky manual category test
- Case + trim test
- Re-apply scoped to uncategorized
- Isolation test green

## M6 — Budgets and dashboard

**Scope tags:** F6.1–F6.8, G2, G5

**Files to create**

- `app/services/budgets.py` — integer-sum progress, 80% / 100% thresholds, monthly aggregation
- `app/routers/budgets.py` — set/delete per category per month
- `app/routers/dashboard.py` — current month income/expense/net, top categories, 6-month trend
- `app/static/vendor/chart.umd.js` + `LICENSE` — vendored Chart.js
- `app/templates/dashboard.html.j2` — charts + accessible table fallbacks
- `app/templates/budgets/*`
- `tests/test_budget_progress.py` — integer sums, hand-worked example
- `tests/test_budget_thresholds.py` — 80% warning, 100% banner at exact boundaries
- `tests/test_month_boundaries.py` — freezegun, user's timezone
- `tests/test_dashboard_tables.py` — table fallback numbers equal chart numbers
- `tests/test_playwright_dashboard.py` — chart renders, screenshot non-empty
- `tests/test_isolation_routes.py` — extended to M6 routes

**Acceptance evidence (gate)**
- Integer-sum progress matches hand example
- 80% / 100% boundary tests
- Timezone month boundaries
- Playwright screenshot non-empty
- Table fallback numbers equal chart numbers
- Transfers excluded everywhere
- Isolation test green

## M7 — Export, demo mode, end-to-end tests

**Scope tags:** F7.1–F7.4, F8.1–F8.5, G6

**Files to create**

- `app/services/exports.py` — XLSX (openpyxl) + CSV; formula-injection neutralizer
- `app/routers/exports.py` — download endpoints
- `app/demo.py` — `DEMO_MODE` banner middleware, `SEED_ON_START` deterministic seeder (6 months fake)
- `scripts/backup.sh` — `sqlite3 .backup`
- `scripts/restore.sh` — restore from backup
- `tests/test_backup_restore.py` — back up, wipe, restore, counts/totals match
- `tests/test_xlsx.py` — openpyxl opens; sheets and totals match DB
- `tests/test_export_formula_injection.py` — text-cell neutralization
- `tests/test_demo_banner.py` — banner on every page
- `tests/test_e2e.py` — Playwright: import fixture → categorized → over-budget banner → download XLSX
- `README.md` — Threat model section

**Acceptance evidence (gate)**
- XLSX opens; totals match
- Formula-injection neutralizer test
- E2E Playwright test green
- Backup/restore round-trip
- DEMO_MODE banner test

## Post-M7 phases (do not implement during milestones)

- **H** — Hardening pass (defects only, no features)
- **F** — Fresh-clone test in a temp dir, only README commands
- **D** — Deployment prep (Render demo + scripts/smoke_test.sh)
- **R** — Final README with screenshots
- **X** — Final scope audit + FINAL_REPORT.md
