# DEPLOY.md

How to ship PocketLedger to production. The repo targets two
deployments:

1. **Local / on-prem** — the user runs `docker compose up` (or the
   `make install && make up` flow) on their own hardware. SQLite lives
   on a bind-mounted volume; `scripts/backup.sh` snapshots it on a
   cron.
2. **Public demo on Render** — `render.yaml` provisions a free Web
   Service with a persistent disk and `DEMO_MODE=true`,
   `SEED_ON_START=true`. Anyone who hits the URL lands on a working
   demo account (`demo` / `demo1234`) seeded with 6 months of fake
   data.

Both deployments refuse to boot with the default `SECRET_KEY` in
production. Set a long random value before exposing the app.

## Local / on-prem

```
git clone <repo> pocketledger && cd pocketledger
SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  docker compose up --build
```

`docker compose` puts the database on a named volume
(`pocketledger-data:/data`). To back it up:

```
docker compose exec -T app sqlite3 /data/pocketledger.db \
  ".backup '/data/backups/pocketledger-$(date -u +%Y%m%dT%H%M%SZ).db'"
```

…or just run `./scripts/backup.sh` with `BACKUP_FILE` set, which
uses the same `.backup` command. Restore with `./scripts/restore.sh`
after stopping the container.

## Public demo on Render

1. Connect the repo to Render.
2. Render reads `render.yaml` and creates the `pocketledger-demo`
   service, a 1 GB persistent disk at `/var/data`, and the env
   variables (`APP_ENV=production`, `DEMO_MODE=true`,
   `SEED_ON_START=true`, `ALLOW_REGISTRATION=false`,
   `DEFAULT_CURRENCY=USD`, `USER_TIMEZONE=UTC`).
3. Render generates a random `SECRET_KEY` on first deploy. Verify
   it's set in the dashboard before exposing the URL publicly.
4. After the deploy, hit `/health`; expect `{"status":"ok"}`.
5. Hit `/auth/login`; the DEMO banner is rendered on every page.
6. Log in as `demo` / `demo1234`. The dashboard shows 6 months of
   fake income + expense, one budget that is over 80% spent
   (warning status).

To redeploy:

```
# Push to the branch Render is watching.
git push origin main
```

Render runs the `buildCommand` from `render.yaml` and rolls the
service. The persistent disk survives redeploys.

## Smoke test

`scripts/smoke_test.sh` boots uvicorn on a free port, hits the
public routes, logs in as the demo user, downloads a CSV, and exits
non-zero on any failure. Run it locally:

```
PORT=18765 ./scripts/smoke_test.sh
```

It is also the script Render's post-deploy hook can call.

## Backups in production

The `scripts/backup.sh` wrapper is the same script used by both
deployments: it issues `sqlite3 .backup` (online, atomic) into the
configured `BACKUP_FILE`. Run it from a cron on the host, or from a
Render Cron Job. The demo database is small (one user's worth of
data) so a daily backup is more than enough.

## Threat model

PocketLedger is single-tenant per data file: every user sees only
their own accounts, categories, transactions, rules, budgets, and
exports. CSRF is enforced on every state-changing POST. Passwords
are stored with Argon2id. Sessions are signed cookies
(itsdangerous). The login endpoint is rate-limited per username+IP.

The demo mode flag (`DEMO_MODE=true`) adds a banner to every page
warning visitors that the data is fake and public. Registration is
disabled in demo mode (`ALLOW_REGISTRATION=false`).

CSV/XLSX exports sanitise formula prefixes (=, +, -, @, tab, CR) to
prevent spreadsheet formula injection (CWE-1236).