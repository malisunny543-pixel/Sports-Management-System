# SportsPro — Phase 11A: Deployment Readiness Audit Report

**Project Root:** `D:\Projects\Sports-Management-System\`
**Target Platform:** Render (free Python web service) + Aiven (free MySQL 8.0 database)
**Date:** October 2, 2026
**Status:** Preparation complete — NOT yet deployed.

---

## 1. Files Inspected

| File | Purpose |
| :--- | :--- |
| `app.py` | Flask entry point, WSGI object, session config, all routes |
| `auth.py` | `@login_required`, `@admin_required`, `@player_required`, `get_current_user()` |
| `config.py` | `DB_CONFIG` and `APP_CONFIG` from environment variables |
| `database.py` | `get_db_connection()` using `mysql.connector` |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variable template |
| `.gitignore` | Confirmed `.env` is excluded from Git |
| `database/schema.sql` | Local development schema |
| `templates/` | All Jinja2 templates (no hardcoded localhost/credentials found) |
| `static/css/`, `static/js/` | Static assets (filesystem-only, no external storage) |

---

## 2. Files Changed

| File | Change | Reason |
| :--- | :--- | :--- |
| `config.py` | Added `DB_SSL_CA` env var, `FLASK_ENV`, `session_cookie_secure` flag | Aiven requires TLS; `SESSION_COOKIE_SECURE` must be `True` in production |
| `app.py` | Added `ProxyFix` middleware; `SESSION_COOKIE_SECURE` now reads from config; dev `debug=True` replaced with env-conditional | Render sits behind a TLS-terminating proxy; debug must be off in production |
| `requirements.txt` | Added `gunicorn==26.2.0` | Render's Python web service expects a WSGI production server |

## 3. Files Created

| File | Purpose |
| :--- | :--- |
| `Procfile` | Render start command |
| `database/schema_deploy.sql` | Deployment-safe schema (IF NOT EXISTS, no USE statement, no data) |
| `database/demo_data.sql` | Optional fictional demo data (placeholder passwords — see note) |

---

## 4. Startup Command

### Production (Render)
```
gunicorn app:app --workers 2 --bind 0.0.0.0:$PORT --timeout 120 --log-file=-
```
- `app:app` — module `app.py`, Flask object `app`
- `$PORT` — Render injects this automatically
- `--log-file=-` — routes logs to stdout (visible in Render dashboard)
- 2 workers suit Render's free tier (512 MB RAM)

### Local development (unchanged)
```
python app.py
```
or
```
flask run
```

---

## 5. Required Environment Variables

Set these in Render → your web service → **Environment** tab. Never commit values to Git.

| Variable | Required | Example / Notes |
| :--- | :---: | :--- |
| `FLASK_SECRET_KEY` | ✅ | `python -c "import secrets; print(secrets.token_hex(32))"` — generate a new 64-char hex string |
| `FLASK_ENV` | ✅ | `production` — disables debug, enables secure cookies |
| `DB_HOST` | ✅ | Aiven hostname e.g. `mysql-abc123.aivencloud.com` |
| `DB_PORT` | ✅ | Aiven port e.g. `12345` |
| `DB_USER` | ✅ | Aiven username |
| `DB_PASSWORD` | ✅ | Aiven password |
| `DB_NAME` | ✅ | Aiven database name |
| `DB_SSL_CA` | ✅ | **Absolute path** to the Aiven CA certificate file (`ca.pem`) on the Render filesystem — see Section 8 for how to handle this |
| `SESSION_COOKIE_SECURE` | optional | Defaults to `true` when `FLASK_ENV=production`; omit unless you need to override |

> **`DB_SSL_CA` note:** Aiven mandates TLS. The CA certificate (`ca.pem`) must be available on the Render container filesystem at a known path. The recommended approach for the free tier is to base64-encode the file contents and decode it at startup via a build script (see Section 8).

---

## 6. Database Setup and Import Instructions

### 6A. Create an Aiven MySQL database
1. Register at [aiven.io](https://aiven.io) and create a **free MySQL 8.0** service.
2. Wait for the service to start (2–5 minutes).
3. In the Aiven Console → your service → **Overview**, copy:
   - Service URI (or the individual Host / Port / User / Password / Database fields)
   - Click **Download CA certificate** → save as `ca.pem`.

### 6B. Import the deployment schema
Run from your local machine (one-time only, never in the application):

```bash
mysql -h <AIVEN_HOST> -P <AIVEN_PORT> -u <AIVEN_USER> -p \
      --ssl-ca=ca.pem \
      <AIVEN_DATABASE> < database/schema_deploy.sql
```

Verify:
```sql
SHOW TABLES;   -- should list 8 tables
```

### 6C. Import optional demo data (fictional only)
> ⚠️ The demo data file contains **placeholder** password hashes that will **not** work for login. Create real accounts using the helper scripts after import (see Section 9).

```bash
mysql -h <AIVEN_HOST> -P <AIVEN_PORT> -u <AIVEN_USER> -p \
      --ssl-ca=ca.pem \
      <AIVEN_DATABASE> < database/demo_data.sql
```

### 6D. Create the first admin account
After deployment, use the project's helper script locally (pointed at the Aiven database via env vars):

```bash
# Set env vars temporarily
set DB_HOST=<AIVEN_HOST>
set DB_PORT=<AIVEN_PORT>
set DB_USER=<AIVEN_USER>
set DB_PASSWORD=<AIVEN_PASSWORD>
set DB_NAME=<AIVEN_DATABASE>
set DB_SSL_CA=ca.pem

python create_admin.py
```

---

## 7. Handling the Aiven TLS Certificate on Render

Render's free tier does not support persistent file storage (no volumes). Options for making `ca.pem` available:

### Option A — Commit the CA certificate to Git (recommended for free tier)
Aiven CA certificates are **not secret** — they identify Aiven's CA, not your database. It is acceptable to commit `ca.pem` to your repository.

```bash
cp ~/Downloads/ca.pem database/ca.pem
# Add to Git:
git add database/ca.pem
```

Then in Render set:
```
DB_SSL_CA=/opt/render/project/src/database/ca.pem
```

### Option B — Build script (advanced)
Store the base64-encoded cert in an env var and decode it during the build phase.

---

## 8. Security Checks Performed

| Check | Finding | Status |
| :--- | :--- | :--- |
| Hardcoded credentials in code | None found in `app.py`, `config.py`, `database.py`, or templates | ✅ Pass |
| SQL injection defense | All queries use `%s` parameterized placeholders | ✅ Pass |
| Debug mode in production | Changed to env-conditional (`FLASK_ENV != production`) | ✅ Fixed |
| `SESSION_COOKIE_SECURE` | Now `True` when `FLASK_ENV=production` | ✅ Fixed |
| Reverse proxy / HTTPS headers | `ProxyFix` added (`x_for=1, x_proto=1, x_host=1`) | ✅ Fixed |
| CSRF protection | Global `CSRFProtect(app)` preserved on all POST routes | ✅ Pass |
| Admin role creation via `/register` | Server hardcodes `role='player'` regardless of form input | ✅ Pass |
| Password hashing | Werkzeug `scrypt` — not MD5/SHA1 | ✅ Pass |
| Security response headers | `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy` via `@after_request` | ✅ Pass |
| Error handler information leakage | `/db-test` returns generic error message, not raw exception | ✅ Pass |
| Secrets in `.gitignore` | `.env` excluded; `.env.example` has no real values | ✅ Pass |
| File uploads / local filesystem deps | None — no file uploads, no filesystem writes by the app | ✅ Pass |
| TLS for Aiven connection | `DB_SSL_CA` env var supported; activates `ssl_ca`, `ssl_verify_cert`, `ssl_verify_identity` | ✅ Added |

---

## 9. Test Results

```
# Full regression suite run after all changes
.\venv\Scripts\python.exe -m unittest discover -p "test_*.py"
Ran 271 tests in ~19s
OK  (0 failures, 0 errors)

# App import verification (confirms ProxyFix and config changes are valid)
.\venv\Scripts\python.exe -c "import app; print(type(app.app.wsgi_app).__name__)"
ProxyFix

# Config verification (local dev — no side effects on existing .env)
.\venv\Scripts\python.exe -c "from config import APP_CONFIG, DB_CONFIG; print(...)"
env: development
secure_cookie: False        ← correct for local HTTP
db_host: localhost
ssl_ca_present: False       ← correct — DB_SSL_CA not set locally
```

---

## 10. Known Blockers and Assumptions

| # | Blocker / Assumption | Action Required |
| :--- | :--- | :--- |
| B1 | `DB_SSL_CA` must point to a valid `ca.pem` on the Render container | Commit `database/ca.pem` and set `DB_SSL_CA=/opt/render/project/src/database/ca.pem` |
| B2 | Aiven free tier databases pause after 1 hour of inactivity | First request after cold start may time out; application handles `None` from `get_db_connection()` gracefully |
| B3 | Render free web services spin down after 15 minutes of inactivity (cold start ~30 seconds) | Expected; no fix needed unless upgrading to paid tier |
| B4 | `demo_data.sql` password hashes are non-functional placeholder strings | Create real accounts using `create_admin.py` and `/register` after first deploy |
| B5 | No email verification on `/register` | Players self-register with immediate active status; admin can deactivate via `/admin/users` |
| B6 | Render free plan has no persistent disk | Static files are served from the repository; no file upload features exist in this app |
| B7 | `mysql-connector-python==26.7.0` is a very new version | Verified working in local environment; no known incompatibilities with Aiven MySQL 8.0 |

---

## 11. Exact Next Steps (Manual — You Must Do These)

### Step 1: Generate a strong secret key
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Copy the output — you will paste it as `FLASK_SECRET_KEY` in Render.

### Step 2: Create Aiven MySQL service
1. Go to [console.aiven.io](https://console.aiven.io) → Create Service → MySQL → Free plan.
2. Download `ca.pem` from the service overview.
3. Copy: Host, Port, User, Password, Database Name.

### Step 3: Copy ca.pem into the project
```bash
copy <path-to-downloaded-ca.pem> database\ca.pem
```

### Step 4: Import the schema into Aiven
```bash
mysql -h <HOST> -P <PORT> -u <USER> -p --ssl-ca=database\ca.pem <DATABASE> < database\schema_deploy.sql
```

### Step 5: Create a GitHub repository
```bash
git init
git add .
git commit -m "Initial SportsPro deployment"
git remote add origin https://github.com/<YOUR_USERNAME>/<REPO_NAME>.git
git push -u origin main
```
> Verify `.env` is **not** in the commit: `git status` should not list `.env`.

### Step 6: Connect to Render
1. Go to [render.com](https://render.com) → New → Web Service → Connect GitHub repo.
2. **Runtime:** Python 3
3. **Build command:** `pip install -r requirements.txt`
4. **Start command:** `gunicorn app:app --workers 2 --bind 0.0.0.0:$PORT --timeout 120 --log-file=-`

### Step 7: Set environment variables in Render
In Render → your service → **Environment** → add:

| Key | Value |
| :--- | :--- |
| `FLASK_SECRET_KEY` | *(64-char hex from Step 1)* |
| `FLASK_ENV` | `production` |
| `DB_HOST` | *(Aiven host)* |
| `DB_PORT` | *(Aiven port)* |
| `DB_USER` | *(Aiven user)* |
| `DB_PASSWORD` | *(Aiven password)* |
| `DB_NAME` | *(Aiven database name)* |
| `DB_SSL_CA` | `/opt/render/project/src/database/ca.pem` |

### Step 8: Deploy and verify
1. Click **Deploy** in Render.
2. Watch the build log — look for `Successfully installed` and `Gunicorn running`.
3. Open your `https://<app>.onrender.com` URL.
4. Visit `https://<app>.onrender.com/db-test` — should return `{"status": "SUCCESS"}`.

### Step 9: Create the admin account
```bash
# Set Aiven vars in your local terminal, then:
python create_admin.py
```
Or use the Render **Shell** tab (if available on your plan).

### Step 10: Verify all features
- [ ] Homepage loads (`/`)
- [ ] Register a player (`/register`)
- [ ] Login as player → redirected to `/player/dashboard`
- [ ] Login as admin → redirected to `/admin/dashboard`
- [ ] Admin CRUD: Sports, Teams, Players, Tournaments, Matches
- [ ] Record match result and view standings
- [ ] Admin Reports and CSV exports
- [ ] Player profile self-service
- [ ] Confirm player cannot access admin routes (403)
- [ ] Confirm admin cannot access player routes (403)

---

## 12. Free-Tier Limitations

| Platform | Limitation | Impact |
| :--- | :--- | :--- |
| Render free | Web service sleeps after ~15 min inactivity | First request has ~30 s cold start delay |
| Render free | 512 MB RAM, shared CPU | Adequate for demo; 2 gunicorn workers fit comfortably |
| Render free | No persistent disk | No file uploads; static assets served from repo ✅ |
| Aiven free | MySQL pauses after 1 hour idle | Application handles `None` connection gracefully; first request reconnects |
| Aiven free | Limited storage (~5 GB) | Sufficient for demo and small production usage |
| Aiven free | 1 database per free account | Create one Aiven account per project if needed |

---

## 13. Files Summary

```
D:\Projects\Sports-Management-System\
├── app.py                          ← CHANGED (ProxyFix, env-conditional cookies & debug)
├── config.py                       ← CHANGED (DB_SSL_CA, FLASK_ENV, session_cookie_secure)
├── requirements.txt                ← CHANGED (added gunicorn==26.2.0)
├── Procfile                        ← NEW    (Render start command)
├── database/
│   ├── schema.sql                  ← unchanged (local dev reference)
│   ├── schema_deploy.sql           ← NEW    (deployment-safe, IF NOT EXISTS, no USE)
│   └── demo_data.sql               ← NEW    (fictional only, placeholder passwords)
└── PHASE_11A_DEPLOYMENT_READINESS.md ← this report
```
