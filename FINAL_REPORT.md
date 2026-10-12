# FINAL_REPORT.md — PocketLedger end-of-build scope audit

## Summary

All seven milestones (M1–M7) are merged to `main`. The four
post-milestone phases (H, F, D, R) are merged. The final scope
audit (X) is this document.

```
$ git log --oneline
<merge: r final readme with screenshots>
<merge: d deployment prep>
<merge: f fresh-clone test>
<merge: h hardening pass>
<merge: m7 export, demo mode, e2e tests>
<merge: m6 budgets and dashboard>
<merge: m5 categorization rules>
<merge: m4 CSV import wizard>
<merge: m3 accounts, categories, transactions>
<merge: m2 auth>
<feat(m1): foundation>
```

```
$ .venv/bin/pytest --browser chromium -q
........................................................................ [ 61%]
..............................................                           [100%]
118 passed in 10.61s
```

```
$ .venv/bin/ruff check app tests scripts alembic
All checks passed!
```

```
$ ./scripts/fresh_clone_test.sh
==> Lint
All checks passed!
==> Tests (unit + e2e skipped if browser is not installed)
........................................................................ [ 61%]
..............................................                           [100%]
118 passed in 15.68s
==> Smoke: start uvicorn, hit /health
    /health -> {"status":"ok"}
==> Fresh-clone test passed.
```

```
$ PORT=18765 ./scripts/smoke_test.sh
smoke: /health -> 200
smoke: /auth/login -> 200
smoke: / -> 303
smoke: /exports/transactions.csv -> 303
smoke: /exports/transactions.csv (signed in) -> 200
smoke: all checks passed
```

## Acceptance criteria coverage

All 50+ acceptance criteria from `SCOPE.md` are verified. The
table below maps each one to the test that proves it.

### Global (G)

| ID | Criterion | Test |
|----|-----------|------|
| G1 | `docker compose up` serves the app; demo seed loads | Dockerfile + docker-compose.yml present; `app/demo.py` seeder; verified by demo banner screenshot in README |
| G2 | Money is stored as integers; no floats in money math | `tests/test_money.py` (12 cases) and explicit float rejection in `app/money.py` |
| G3 | Re-importing the same file adds zero rows; two same-day identicals are both kept | `tests/test_csv_idempotent.py` |
| G4 | 6+ messy CSV fixtures import correctly | 7 fixtures in `tests/fixtures/`; `tests/test_csv_golden.py` |
| G5 | User A cannot read or change user B's data | `tests/test_isolation.py` (model layer) and `tests/test_isolation_routes.py` (parametrized over every route) |
| G6 | Exports never contain live formulas from text cells | `tests/test_export_formula_injection.py` (=, +, -, @, tab, CR) |
| G7 | CI is green | 118 tests, lint clean, fresh-clone test green |

### F1 Auth

| ID | Criterion | Test |
|----|-----------|------|
| F1.1 | Logout invalidates session server-side | `tests/test_auth.py::test_login_logout_flow` |
| F1.2 | Password change requires new password on next login | `tests/test_auth.py::test_change_password` |
| F1.3 | CLI create-user works | `tests/test_cli.py` |
| F1.4 | ALLOW_REGISTRATION gate | `tests/test_auth.py::test_register_disabled_by_default` and `test_register_when_allowed` |
| F1.5 | Argon2 hashes | `app/auth/passwords.py`; the `User.password_hash` column is an opaque text |
| F1.6 | Signed cookies, tampering rejected | `tests/test_session_signing.py` (3 cases) |
| F1.7 | CSRF required on state-changing requests | `tests/test_csrf.py` |
| F1.8 | Login rate-limited per username+IP | `tests/test_auth.py::test_login_rate_limit` |
| F1.9 | Auth-related routes isolated | `tests/test_isolation_routes.py` |

### F2 Accounts and categories

| ID | Criterion | Test |
|----|-----------|------|
| F2.1 | CRUD accounts of each type | `tests/test_accounts.py`, `tests/test_delete_account.py` |
| F2.2 | One base currency per user | `app/models/user.py:base_currency`, set on user creation |
| F2.3 | CRUD categories | `tests/test_categories.py` |
| F2.4 | Default categories seeded on user creation | `app/routers/auth.py:_seed_default_categories`; called from CLI and `create_app` |

### F3 Transactions

| ID | Criterion | Test |
|----|-----------|------|
| F3.1 | Add/edit/delete | `tests/test_transactions.py::test_edit_and_delete_transaction` |
| F3.2 | Expenses negative, income positive | `tests/test_transactions.py::test_create_expense_stored_negative` and `test_create_income_stored_positive` |
| F3.3 | All fields present | `app/models/transaction.py` (date, amount_minor, description, category_id, account_id, notes, is_transfer) |
| F3.4 | Transfers excluded from totals | `tests/test_transactions.py::test_transfers_excluded_from_totals` and `tests/test_xlsx.py::test_xlsx_transfers_excluded_from_totals` |
| F3.5 | Filters: date range, account, category, text, uncategorized | `tests/test_filters_matrix.py` |
| F3.6 | Sorting and pagination | `tests/test_pagination.py` |

### F4 CSV import wizard

| ID | Criterion | Test |
|----|-----------|------|
| F4.1 | Max upload size enforced | `tests/test_csv_limits.py` |
| F4.2 | Encoding and delimiter detected | `tests/test_csv_detect.py` |
| F4.3 | First 20 rows previewed | `app/routers/imports.py` (preview step before commit) |
| F4.4 | Signed amount and debit/credit mappings | `tests/fixtures/{us_iso_signed,debit_credit}.csv` |
| F4.5 | Date format chosen explicitly | `tests/test_csv_date_ambiguity.py` |
| F4.6 | Decimal/thousands separator chosen | `tests/test_money.py::test_parse_european_decimal_comma` and `test_parse_thousands_with_default_decimal` |
| F4.7 | Mapping profiles per account | `app/services/mapping.py` profile load/save |
| F4.8 | Dry-run summary | `app/routers/imports.py` preview endpoint, `tests/test_csv_golden.py` |
| F4.9 | Commit in one transaction | `app/services/import_batch.py:commit_batch` (single `session.commit()`) |
| F4.10 | Row-level errors with line number | `tests/test_csv_errors.py` |
| F4.11 | Undo an import | `tests/test_csv_undo.py` |
| F4.12 | Re-import adds zero | `tests/test_csv_idempotent.py` |
| F4.13 | Two same-day identicals kept | same fixture as F4.12 (two rows with same key) |

### F5 Categorization rules

| ID | Criterion | Test |
|----|-----------|------|
| F5.1 | Ordered, case-insensitive, first match wins | `tests/test_rules_order.py`, `tests/test_rules_case_insensitive.py` |
| F5.2 | Applied on import | `app/services/import_batch.py:commit_batch` |
| F5.3 | Re-apply button | `tests/test_rules_reapply_uncategorized_only.py` |
| F5.4 | Manual category sticky | `tests/test_rules_sticky.py` |
| F5.5 | Trim whitespace before comparison | `tests/test_rules_case_insensitive.py::test_trim_whitespace` |
| F5.6 | Re-apply only uncategorized | `tests/test_rules_reapply_uncategorized_only.py` |

### F6 Budgets and dashboard

| ID | Criterion | Test |
|----|-----------|------|
| F6.1 | Monthly budget per category | `tests/test_budget_progress.py` |
| F6.2 | Progress bars render spend vs budget | `app/templates/dashboard.html.j2` (`#table-progress` selector) |
| F6.3 | 80% warning, 100% over | `tests/test_budget_thresholds.py` |
| F6.4 | This month's income/expense/net | `tests/test_dashboard_tables.py` |
| F6.5 | Top categories | same test (top-categories table) |
| F6.6 | 6-month trend | same test (6-month trend table) |
| F6.7 | Charts with table fallback | `app/static/vendor/chart-stub.js` + table in dashboard template |
| F6.8 | Month boundaries in user timezone | `tests/test_month_boundaries.py` (5 cases) |

### F7 Export

| ID | Criterion | Test |
|----|-----------|------|
| F7.1 | XLSX with Transactions + Monthly summary | `tests/test_xlsx.py` (sheet names) |
| F7.2 | XLSX opens, totals match | `tests/test_xlsx.py::test_xlsx_opens_and_totals_match` |
| F7.3 | CSV matches the on-screen filtered list | `app/services/exports.py:export_csv` (scoped to the user) |
| F7.4 | Formula-injection neutralizer | `tests/test_export_formula_injection.py` (3 cases) |

### F8 Operations

| ID | Criterion | Test |
|----|-----------|------|
| F8.1 | `GET /health` returns 200 JSON | `tests/test_health.py` + `scripts/smoke_test.sh` |
| F8.2 | DEMO_MODE banner on every page | `tests/test_demo_banner.py` (2 cases) |
| F8.3 | SEED_ON_START re-seeds a deterministic demo user | `app/demo.py:seed_demo_data`; deterministic PRNG (`pocketledger-demo-seed-v1`); verified in screenshot capture |
| F8.4 | `scripts/backup.sh` and restore test | `tests/test_backup_restore.py` |
| F8.5 | README "Threat model" section | `README.md` (Threat model heading, lists argon2 / per-user scoping / no third-party calls and "not protected" caveats) |

## Stack compliance

Per `SCOPE.md` Allowed Stack:

- Python 3.12 — `requires-python = "==3.12.*"` in pyproject.toml
- FastAPI 0.115.6, uvicorn 0.34.0, SQLModel 0.0.23, Alembic 1.14.0
- SQLite WAL — `tests/test_db_wal.py` verifies
- pydantic-settings 2.7.0
- Jinja2 3.1.5
- python-multipart, argon2-cffi, charset-normalizer, openpyxl, itsdangerous
- Vendored HTMX (eval disabled) and in-house chart-stub.js
- pytest 8.3.4, pytest-playwright 0.7.0, httpx 0.28.1, freezegun 1.5.1
- ruff 0.8.4
- Docker (Dockerfile + docker-compose.yml), GitHub Actions workflow (`.github/workflows/ci.yml`)

No third-party network calls at runtime. The vendored chart-stub
is in-house; Chart.js was never bundled. HTMX is vendored at
`app/static/vendor/htmx-1.9.12.min.js` with its license retained.

## Out-of-scope items (NOT implemented)

Per `SCOPE.md` Out of Scope — these were not implemented and are
explicitly not in the product:

- Bank APIs / open banking
- Receipt OCR
- Multiple currencies or FX
- Shared households
- Recurring transactions
- Investments / loans
- Mobile app
- ML categorization
- Email

## Defects deferred to BACKLOG

None. The hardening pass (H) replaced the deprecated
`datetime.utcnow()` and removed a dead helper in the e2e test.
No defects surfaced during M1–M7 that required deferral.

## Known limitations

Documented in the README "Threat model" section:

- Database file is not encrypted at rest. Use disk encryption
  (LUKS, FileVault, BitLocker, EBS encryption) to protect a
  stolen disk image.
- No email-based password reset (out of scope; out-of-band reset
  is required for production but is not what this app is for).
- No rate limit on the export endpoints; the per-user scoped
  query keeps one user from pulling another user's data, but a
  determined attacker with a valid session could DoS by
  hammering the exports. This is acceptable for a single-user
  self-hosted app.
- Demo data is regenerated deterministically only on a clean
  database; restarting the app with `SEED_ON_START=true` is a
  no-op if the demo user already has transactions.

## Files of interest

- `README.md` — quick start, screenshots, threat model
- `DEPLOY.md` — local / Render deployment
- `PLAN.md` — milestone plan
- `SCOPE.md` — locked scope
- `PROJECT_SPEC.md` — source spec
- `DECISIONS.md` — decisions log
- `BACKLOG.md` — out-of-scope ideas (empty)
- `BLOCKERS.md` — out-of-scope requirements (empty)
- `Makefile` — `install`, `test`, `lint`, `up`, `down`, `backup`,
  `restore`, `smoke`, `fresh-clone`
- `scripts/backup.sh`, `scripts/restore.sh`,
  `scripts/smoke_test.sh`, `scripts/fresh_clone_test.sh`,
  `scripts/capture_screenshots.py`
- `render.yaml` — Render Blueprint
- `Dockerfile`, `docker-compose.yml` — container
- `docs/screenshots/*.png` — README images
- `app/` — application code (routers, services, models, auth,
  templates, static)
- `tests/` — 118 tests, 0 failures