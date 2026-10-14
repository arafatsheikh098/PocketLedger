# need_fix — pocketledger

Security review 2026-10-14. Scope: security + real correctness bugs.
Full cross-project context: `../SECURITY_REVIEW.md`.

> **No code was changed in this repo.** The shell was unavailable for this
> session, so nothing could be tested; applying unverifiable edits to a second
> repo was not worth the risk. Every item below is open.

The baseline is strong. Sessions are signed with `itsdangerous`
`URLSafeTimedSerializer` (30-day max age, `uid` type-checked on read). CSRF is
double-submit cookie with `hmac.compare_digest` and `SameSite=Lax`, which
blocks the cross-site POST that would otherwise make double-submit weak.
Authorization is the best part: `app/auth/scoped.py` exposes
`scoped_query`/`scoped_get`, both filtering on `user_id`, used consistently by
the routers — so the usual IDOR in a per-user finance app is absent.
CSV/XLSX export implements the OWASP formula-injection mitigation. **Ruled out:**
`mapping_json` is `json.loads`, not `pickle` — not an RCE vector.

This repo is **public** (`github.com/arafatsheikh098/PocketLedger`).

---

## Open, roughly highest value first

### F13 — changing a password does not invalidate sessions — MEDIUM

`app/auth/sessions.py`'s docstring claims:

> changing the password invalidates sessions in the natural way

It does not. The cookie payload is `{"uid": user_id}` signed with `SECRET_KEY`;
`read_session_cookie` only verifies signature and age. Nothing derives from the
password, and `change_password_post` revokes nothing. A stolen session cookie
keeps working for up to **30 days after** the victim changes their password —
the exact action taken to recover from a compromise. The misleading comment is
arguably the worse half: it tells the next reader the protection exists.

**Fix:** put a password-derived value (first bytes of the hash, or a
`session_version` column bumped on change) in the signed payload and compare on
read. Then correct the docstring.

### F8 — import wizard skips the account ownership check — MEDIUM

`app/routers/imports.py`. `upload` validates the target account:

```python
if scoped_get(session, user.id, Account, account_id) is None:
    return _upload_error("invalid account")
```

but `/imports/dry-run` and `/imports/commit` take `account_id: int = Form(...)`
and pass it straight through. `import_batch.commit` then builds
`Transaction(user_id=user_id, account_id=account_id)` from the submitted value
unchecked, so a user can write rows bound to an account they do not own. Reads
are scoped by `user_id`, so the victim's data is not exposed — the impact is
cross-user referential corruption, account-id enumeration, and dedup keys
computed against someone else's account. It breaks the invariant the codebase
documents for itself, and `upload` shows the intent was there.

**Fix:** `scoped_get(...)` at the top of both `dry_run` and `commit`, 404 on
`None`. Two lines, matching the pattern used everywhere else.

### F9 — upload read fully into memory before the size check — MEDIUM

`app/routers/imports.py:upload`:

```python
raw = file.file.read()
if len(raw) > 5 * 1024 * 1024:
```

The whole body is materialised *before* the limit is tested, so a multi-GB
upload exhausts memory regardless of the cap. (The staged-file handling around
it is careful: 0o600 file, 0o700 dir, traversal check via `relative_to`,
per-user filename prefix, hourly cleanup.)

**Fix:** read in bounded chunks, abort once the cap is passed — and source the
cap from settings, which fixes F10 at the same time.

### F5 — production accepts any non-`change-me` `SECRET_KEY` — MEDIUM

`app/__init__.py:26`:

```python
if settings.is_production and settings.secret_key.startswith("change-me"):
```

`SECRET_KEY=abc` boots in production and signs session cookies; a guessable key
means forged sessions for any user id. `config.py`'s docstring and
`.env.example` both promise more than the code enforces.

**Fix:** also require a minimum length (32+) in production. One condition, no
new settings. Same gap exists in `bloodlink`.

### F6 — router registration silently swallows import errors — MEDIUM

`app/__init__.py:_include_feature_routers` catches `ModuleNotFoundError` per
feature router. That fires not only when the router is absent but when
**anything it imports** is missing — so a missing transitive dependency
silently removes an entire feature (transactions, budgets, imports…) from a
production deploy with no error.

**Fix:** only skip when the missing module is the router itself (compare
`exc.name`); let anything else propagate.

### F14 — username enumeration via login timing — LOW/MEDIUM

`app/routers/auth.py:login_post`:

```python
if user is None or not verify_password(user.password_hash, password):
```

Short-circuit means `verify_password` never runs for an unknown username, so
those requests return measurably faster — Argon2 is deliberately slow, making
the gap easy to measure remotely. Sibling project `depthub` solves exactly this
with a precomputed dummy hash; copy that approach.

### F16 — lockout keyed on (username, ip) — LOW/MEDIUM, deployment-dependent

`app/auth/rate_limit.py` pairs username with IP, same structure as depthub's
F1 — but materially less severe here because `login_post` uses
`request.client.host`, not a request header, so it is not directly
attacker-controlled. It becomes spoofable again if uvicorn runs with
`--proxy-headers` behind a proxy that forwards client values, and a multi-IP
attacker still gets 5 attempts per address.

**Check `Dockerfile` / `render.yaml` for `--proxy-headers` before deciding**
whether this needs depthub's email-wide cap.

### F12 — formula-injection mitigation skipped for category names — LOW/MEDIUM

`app/services/exports.py` applies `sanitize()` to `description`, `notes`, and
to category names in the **summary** rows (lines 88, 128) — but `_txn_row`
emits the category raw:

```python
categories_by_id.get(t.category_id or 0, ""),   # not sanitized
```

A category named `=cmd|'/c calc'!A1` lands unsanitized in every transaction row
of both the CSV and the XLSX. Self-inflicted (users name their own categories),
but exported ledgers get mailed to accountants and opened in Excel, and it
defeats a control this module explicitly claims to enforce.

**Fix:** wrap that one expression in `sanitize()`.

### F10 — `MAX_UPLOAD_BYTES` is dead configuration — LOW/MEDIUM

`Settings.max_upload_bytes` exists, is documented in `.env.example`, and is
read nowhere; the limit in F9 is hardcoded. Operators who change it get no
effect — the config silently lies.

### F15 — a successful login does not reset the failure counter — LOW

`app/auth/rate_limit.py`'s docstring claims it does. `record(success=True)`
only inserts a success row; `recent_failures` counts `success == False` rows,
which are left intact. A user who mistypes four times then logs in correctly
stays one failure from a 15-minute lockout.

### F17 — `record()` scans the whole table on every attempt — LOW

`record()` calls `cleanup_old_attempts()` first, which selects every row older
than 7 days and deletes them one at a time, on **every** login attempt. Makes
each login O(table) in writes.

### F18 — registration does not validate the username — LOW

`register_post` takes `username` straight from the form: no strip, no length
bound, no charset restriction, so an empty or arbitrarily long username is
storable when `ALLOW_REGISTRATION` is on. Password length (8+) *is* checked.
Every failure path also redirects with no message, so a user cannot tell why.

### F11 — parser exception text reflected into a redirect URL — LOW

`upload` returns `f"could not parse file: {exc}"` in a query parameter. Jinja2
autoescaping blunts the XSS angle, but parser internals should not reach the
URL bar.

### Minor — `mapping.Mapping.from_json` robustness

`cls(**json.loads(blob))` raises an unhandled `TypeError` (500, not 400) on
unexpected keys or non-dict JSON, and `date_format` is not re-checked against
the `DATE_FORMATS` whitelist when a mapping is rebuilt at commit time.
Arbitrary `strptime` formats are harmless, so this is robustness only.

---

## Unverified: no secret is committed

`git ls-files` could not be run.

```bash
git ls-files | grep -iE '(\.env$|\.db$|\.sqlite3?$|\.pem$|\.key$)'
```

Note there are `pocketledger.db`, `pocketledger_demo.db`, `-shm` and `-wal`
files on disk. `.gitignore` covers `*.db` but **not** the `-shm`/`-wal`
suffixes — check those explicitly:

```bash
git ls-files | grep -E '\.db(-shm|-wal)$'
```

## Not reviewed

`demo.py` / demo mode, `dashboard`, `budgets`, `rules`, `categories` and
`transactions` routers, `money.py`, and the Alembic migrations.

---

# Exact changes

Written without being able to run anything — treat as reviewed-but-untested
patches. Apply one at a time and run `pytest -q` between each. Ordered by
value. Items 1–6 are small and self-contained; item 7 is the one that needs
real care.

## 1. F8 — ownership check on the import routes

`app/routers/imports.py`. `scoped_get`, `Account` and `HTTPException` are
already imported, so this adds no imports. Add to **both** `dry_run` and
`commit`, as the first line of each body:

```python
    if scoped_get(session, user.id, Account, account_id) is None:
        raise HTTPException(status_code=404)
    staged_file = _resolve_staged_file(user.id, tmp_path)   # existing line
```

## 2. F12 — sanitize the category name in export rows

`app/services/exports.py`, in `_txn_row`:

```python
-        categories_by_id.get(t.category_id or 0, ""),
+        sanitize(categories_by_id.get(t.category_id or 0, "")),
```

## 3. F5 — require a real `SECRET_KEY` length in production

`app/__init__.py`:

```python
-    if settings.is_production and settings.secret_key.startswith("change-me"):
-        raise RuntimeError(
-            "SECRET_KEY is the default value. Set a real SECRET_KEY in production."
-        )
+    if settings.is_production and (
+        settings.secret_key.startswith("change-me") or len(settings.secret_key) < 32
+    ):
+        raise RuntimeError(
+            "SECRET_KEY is the default or too short (need 32+ chars). "
+            "Set a real SECRET_KEY in production."
+        )
```

## 4. F6 — stop swallowing real import errors

`app/__init__.py`, in `_include_feature_routers`:

```python
         try:
             mod = import_module(name)
-        except ModuleNotFoundError:
-            continue
+        except ModuleNotFoundError as exc:
+            # Skip only when the feature router itself is absent (milestones
+            # add them incrementally). A missing transitive import is a real
+            # error and must not silently delete the feature.
+            if exc.name == name:
+                continue
+            raise
```

`exc.name` is the module that could not be found, so a typo'd import *inside*
`accounts.py` now raises instead of removing the accounts feature.

## 5. F9 + F10 — bound the upload while reading, from settings

`app/routers/imports.py`. Add `from ..config import get_settings` to the
imports, then replace the read in `upload`:

```python
-    raw = file.file.read()
-    if len(raw) > 5 * 1024 * 1024:
-        return _upload_error("file too large")
+    max_bytes = get_settings().max_upload_bytes
+    chunks: list[bytes] = []
+    total = 0
+    while True:
+        chunk = file.file.read(64 * 1024)
+        if not chunk:
+            break
+        total += len(chunk)
+        if total > max_bytes:
+            return _upload_error("file too large")
+        chunks.append(chunk)
+    raw = b"".join(chunks)
```

This caps memory at the configured limit instead of the full body, and makes
`MAX_UPLOAD_BYTES` live (F10). Note the limit is now 5 MiB *by default* rather
than always — if a test asserts the old hardcoded behaviour, it will need the
setting overridden.

## 6. F14 + F15 — timing padding, and make a success actually reset

`app/routers/auth.py` — add a module-level dummy hash and use it when the
username is unknown, so both paths pay the same Argon2 cost:

```python
+_DUMMY_HASH = hash_password("pocketledger_timing_protection_dummy")
+
...
     user = get_user_by_username(session, username)
-    if user is None or not verify_password(user.password_hash, password):
+    if user is None:
+        # Same verification cost as a real user, so response time does not
+        # reveal whether the account exists.
+        verify_password(_DUMMY_HASH, password)
+        record(session, username, ip, success=False)
+        return _render_login(request, None, error="invalid username or password")
+    if not verify_password(user.password_hash, password):
         record(session, username, ip, success=False)
         return _render_login(request, None, error="invalid username or password")
```

(`hash_password` is already imported. This adds one Argon2 hash to process
startup — depthub does the same thing.)

`app/auth/rate_limit.py` — make `record` match its own docstring:

```python
 def record(session: Session, username: str, ip: str, success: bool) -> None:
     cleanup_old_attempts(session)
+    if success:
+        # Documented behaviour: a successful login clears the failure streak
+        # for this (username, ip) pair.
+        stale = session.exec(
+            select(LoginAttempt)
+            .where(LoginAttempt.username == username)
+            .where(LoginAttempt.ip == ip)
+            .where(LoginAttempt.success == False)  # noqa: E712
+        ).all()
+        for row in stale:
+            session.delete(row)
     session.add(LoginAttempt(username=username, ip=ip, success=success))
     session.commit()
```

## 7. F13 — invalidate sessions on password change (do this one carefully)

This is the only change here that touches several call sites, and it logs
every user out once on deploy. Do it on its own branch.

The idea: put a password-derived fingerprint in the signed cookie and compare
it on read, so changing the password changes the fingerprint and old cookies
stop validating.

`app/auth/sessions.py`:

```python
import hashlib

def password_fingerprint(password_hash: str) -> str:
    """Non-reversible marker that changes whenever the password changes."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def make_session_cookie(user_id: int, password_hash: str) -> str:
    return _serializer().dumps(
        {"uid": user_id, "pv": password_fingerprint(password_hash)}
    )


def read_session_payload(value: str) -> dict | None:
    """Return the signed payload, or None if the signature/age is bad."""
    try:
        data = _serializer().loads(value, max_age=_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return data if isinstance(data, dict) else None
```

Then `current_user_optional` in `app/routers/deps.py` does the comparison,
since it is the only place that reads the cookie *and* has the DB session:

```python
    payload = read_session_payload(pocketledger_session)
    if payload is None:
        return None
    uid = payload.get("uid")
    if not isinstance(uid, int):
        return None
    user = get_user_by_id(session, uid)
    if user is None:
        return None
    if payload.get("pv") != password_fingerprint(user.password_hash):
        return None   # password changed since this cookie was issued
    return user
```

Call sites to update, because `make_session_cookie` now needs the hash:

- `set_session_cookies(response, user_id)` in `deps.py` → pass the user (or the
  hash) instead of just the id
- `login_post` and `register_post` in `routers/auth.py`
- `change_password_post` — after rehashing, re-issue the cookie so the user
  changing their own password is not logged out

And **fix the docstring** in `sessions.py`, which currently claims this already
works.

Cheaper alternative if you'd rather not touch the payload: add a
`session_version: int` column to `User`, bump it in `change_password_post`,
and carry it in the cookie. Same shape, one migration, more explicit.

## 8. Lower value

- **F16** — first check `Dockerfile` / `render.yaml` for `--proxy-headers`. If
  present, the IP is client-controlled and this needs depthub's account-wide
  cap; if absent, leave it.
- **F17** — rather than tuning it, move `cleanup_old_attempts()` out of
  `record()` and into the CLI or a scheduled job. Per-request table cleanup is
  the wrong place for it.
- **F18** — in `register_post`: `username = username.strip()` and reject
  outside `3 <= len(username) <= 32`, and give the failure redirects an
  `?error=` message so a user can tell what went wrong.
- **F11** — drop `{exc}` from the `_upload_error` string; log it server-side
  instead.
