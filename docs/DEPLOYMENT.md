# FitControl — Deployment (Vercel + Render + PostgreSQL)

Production topology:

```
  Telegram ──initData──▶  Vercel (Mini App, React/Vite)  ──HTTPS API──▶  Render Web Service (FastAPI)
                                                                          │
  Telegram ──updates────▶  Render Background Worker (bot, polling)  ──────┤
                           Render Background Worker (scheduler)  ─────────┤
                                                                          ▼
                                                              Render Managed PostgreSQL
                                                              (persistent; backed up separately)
```

- **Frontend** → **Vercel**. Only a public API URL; **no** backend secrets, **no** bot token.
- **Backend** → **Render**: FastAPI **Web Service** + bot **Background Worker** + scheduler **Background Worker**.
- **Database** → **Render Managed PostgreSQL** (persistent; never the service's local disk).
- **Telegram updates** → **primary method: long polling** in the bot Background Worker (independent of any browser). Webhook is supported as an alternative (see below).

> Nothing here is deployed for you — you must run these steps in your own
> Vercel / Render / Telegram accounts.

---

## 0. Prerequisites

- GitHub repo with this code (Render & Vercel deploy from Git).
- A Telegram bot token from [@BotFather](https://t.me/BotFather).
- Accounts on [Vercel](https://vercel.com) and [Render](https://render.com).

---

## 1. PostgreSQL (Render Managed Postgres)

You can let the Blueprint (`render.yaml`) create it, or create it manually:

1. Render dashboard → **New + → PostgreSQL** → name `fitcontrol-db`, pick a region and plan.
2. After it provisions, open the database page and copy the **Internal Connection String** (for services in the same Render region) — it looks like:
   `postgresql://user:pass@host:5432/fitcontrol`.
3. Set `DATABASE_URL` to that connection string. The app is **driver-agnostic
   about the scheme**: it accepts `postgresql://…`, `postgres://…`, or an explicit
   `postgresql+asyncpg://…` and auto-upgrades to the async driver at runtime;
   Alembic auto-converts to a sync driver for migrations. So you can paste
   Render's string as-is.

**Migrations** run automatically on API start (`entrypoint.sh api` → `alembic upgrade head`).
To run them manually: Render shell on `fitcontrol-api` → `alembic upgrade head`.

**Backups are stored separately from the primary DB** — see [§8](#8-disaster-recovery)
and [`BACKUP.md`](BACKUP.md). Do **not** rely on the single managed instance.

---

## 2. Backend on Render

### Option A — Blueprint (recommended)

1. Push this repo to GitHub.
2. Render → **New + → Blueprint** → select the repo. Render reads `render.yaml`
   and proposes: `fitcontrol-db`, `fitcontrol-api` (web), `fitcontrol-bot`
   (worker), `fitcontrol-scheduler` (worker).
3. Fill the secrets marked *"sync: false"* when prompted (see [§5](#5-environment-variables)):
   `TELEGRAM_BOT_TOKEN`, `WEBAPP_URL`, `CORS_ORIGINS` (and, only for webhook mode,
   `TELEGRAM_WEBHOOK_SECRET` + `PUBLIC_API_URL`).
4. Apply. Render builds the Docker image once and runs three services off it.

### Option B — Manual

- **Web Service**: New + → Web Service → repo → Root/Docker context `./backend`,
  Dockerfile `./backend/Dockerfile`, command `./entrypoint.sh api`,
  **Health Check Path** `/health`.
- **Bot worker**: New + → Background Worker → same repo/Docker → command
  `./entrypoint.sh bot`.
- **Scheduler worker**: New + → Background Worker → command `./entrypoint.sh scheduler`.
- Attach `DATABASE_URL` (from the DB) and the env vars from [§5](#5-environment-variables) to each.

The API is then at `https://fitcontrol-api.onrender.com` (your subdomain).
Verify: `curl https://fitcontrol-api.onrender.com/health` → `{"status":"ok",...}`.

> **Free plan note:** Render free web services sleep when idle and cold-start on
> the next request; free workers may also be limited. For real clubs use paid
> plans so the bot/scheduler run continuously.

---

## 3. Frontend on Vercel

1. Vercel → **Add New… → Project** → import the repo.
2. **Root Directory:** `miniapp`. Framework preset auto-detects **Vite**
   (Build `npm run build`, Output `dist`). `miniapp/vercel.json` sets the SPA
   rewrite so client-side routes work.
3. **Environment Variable** (Project Settings → Environment Variables):
   - `VITE_API_BASE = https://fitcontrol-api.onrender.com/api/v1`
     (your Render API URL + `/api/v1`). This is the **only** thing the frontend
     needs. **Never** put `TELEGRAM_BOT_TOKEN` or any backend secret here.
4. Deploy. You get `https://<project>.vercel.app`.
5. Put that URL into the backend as `WEBAPP_URL` and into `CORS_ORIGINS`
   (on Render), then redeploy the API so CORS accepts the Vercel origin.

Cross-origin note: the Mini App sends `X-Init-Data` to the Render API. The API's
CORS allows the configured origin(s) and all headers; it uses **no cookies**, so
`allow_credentials` stays off.

---

## 4. Telegram: BotFather + Mini App + updates

### BotFather

1. `/newbot` → get the **token** → set it as `TELEGRAM_BOT_TOKEN` on Render
   (api + bot + scheduler). Keep it out of the frontend and out of Git.
2. Register the Mini App URL (the Vercel URL):
   - `/newapp` (or `/setmenubutton`) → choose your bot → set the Web App URL to
     `https://<project>.vercel.app`.
3. Set `WEBAPP_URL=https://<project>.vercel.app` on Render so the bot's
   "Открыть FitControl" button opens the Mini App.

### Choosing the update method (pick ONE)

**Primary (documented): long polling via the Background Worker.**
- Keep `TELEGRAM_UPDATE_MODE=polling`. The `fitcontrol-bot` worker calls
  `dp.start_polling`, deletes any stale webhook on start, and runs independently
  of any browser. Nothing else to configure.

**Alternative: webhook into the API.**
- Set on the **api** service: `TELEGRAM_UPDATE_MODE=webhook`,
  `TELEGRAM_WEBHOOK_SECRET=<long-random>`, `PUBLIC_API_URL=https://fitcontrol-api.onrender.com`.
- **Do not also run the polling worker** (polling and webhook are mutually
  exclusive) — scale `fitcontrol-bot` to 0 instances.
- Register the webhook once: Render shell on `fitcontrol-api` →
  `python -m app.manage set-webhook` (uses `PUBLIC_API_URL` + secret).
  Telegram then POSTs to `…/api/v1/telegram/webhook` with the secret header,
  which the backend verifies before processing. Inspect/clear with
  `python -m app.manage webhook-info` / `delete-webhook`.

`initData` from the Mini App is always validated on the backend (HMAC + freshness),
regardless of the update method.

---

## 5. Environment variables

### Backend (Render — api / bot / scheduler)

| Variable | Where | Required | Notes |
|----------|-------|----------|-------|
| `ENVIRONMENT` | all | yes | `production` (disables DEV_AUTH_MODE, tightens behavior) |
| `DATABASE_URL` | all | yes | `postgresql+asyncpg://…` (from Render DB) |
| `TELEGRAM_BOT_TOKEN` | all | yes | BotFather token; secret |
| `WEBAPP_URL` | api, bot | yes | Vercel Mini App URL |
| `CORS_ORIGINS` | api | yes | Vercel origin(s), comma-separated; not `*` in prod |
| `DEV_AUTH_MODE` | api | no | must be `false` in prod (also force-off when prod) |
| `INITDATA_MAX_AGE_SECONDS` | api | no | default 86400 |
| `DEFAULT_TIMEZONE` | api, scheduler | no | default `Asia/Tashkent` |
| `DAILY_SUMMARY_HOUR` | scheduler | no | 0–23, club-local |
| `EXPIRY_REMINDER_DAYS` | scheduler | no | default 3 |
| `TELEGRAM_UPDATE_MODE` | api, bot | no | `polling` (default) or `webhook` |
| `TELEGRAM_WEBHOOK_SECRET` | api | webhook only | long random string |
| `PUBLIC_API_URL` | api | webhook only | this backend's public URL |

### Frontend (Vercel)

| Variable | Required | Notes |
|----------|----------|-------|
| `VITE_API_BASE` | yes | Full API base, e.g. `https://fitcontrol-api.onrender.com/api/v1` |

**Never** set `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`, or any secret on Vercel.

---

## 6. Domains & HTTPS

- **Vercel** serves the Mini App over HTTPS automatically on `*.vercel.app`.
  Custom domain: Project → **Domains** → add your domain, create the DNS record
  Vercel shows; TLS is issued automatically. Update `WEBAPP_URL` + `CORS_ORIGINS`
  + BotFather Web App URL to the custom domain afterwards.
- **Render** serves the API over HTTPS on `*.onrender.com`. Custom domain:
  Service → **Settings → Custom Domains** → add domain + DNS record; TLS
  auto-issued. Update `VITE_API_BASE` (and `PUBLIC_API_URL` if using webhook).
- Telegram **requires HTTPS** for both the Mini App URL and any webhook — both
  platforms provide it out of the box.

---

## 7. Verify: production build & backend tests

Before/after deploying, run locally:

```bash
# Frontend production build (what Vercel runs)
cd miniapp
npm install
npm run typecheck        # tsc, no emit
npm run build            # -> dist/ (Vite production build)

# Backend tests (isolated SQLite; never touches production)
cd ../backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q                # initData, isolation, RBAC, billing, recovery, webhook…
```

Post-deploy smoke checks:

```bash
curl https://fitcontrol-api.onrender.com/health
# open the Mini App URL inside Telegram via the bot's /start button
```

---

## 8. Disaster recovery

### 8a. Recover after a Render service failure

The **database is the source of truth**; web/worker services are stateless and
rebuildable.

1. **Service crashed / bad deploy:** Render → the service → **Manual Deploy →
   Deploy latest commit**, or **Rollback** to a previous successful deploy. The
   image is rebuilt; `entrypoint.sh api` re-runs `alembic upgrade head` (safe /
   idempotent). No data is lost — it lives in the managed DB.
2. **Recreate from scratch (region loss, deleted service):** re-run the
   Blueprint (`render.yaml`) against the repo, set the env vars again, and point
   `DATABASE_URL` at your existing (or restored) database. Because no state is
   kept on a service's local disk, a fresh service is fully functional once it
   has `DATABASE_URL`.
3. **Bot stopped receiving updates:** check the `fitcontrol-bot` worker logs. In
   webhook mode run `python -m app.manage webhook-info`; re-run `set-webhook` if
   the URL is empty. Ensure you are not running polling and webhook at once.

### 8b. Restore the database from a backup

Backups must be kept **separately from the primary DB** (different provider /
bucket / machine). Full procedure in [`BACKUP.md`](BACKUP.md). In short:

```bash
# Take regular dumps (schedule this off-box, e.g. a cron on another host):
pg_dump "$DATABASE_URL_SYNC" -F c > fitcontrol_$(date +%F).dump
#   $DATABASE_URL_SYNC = the postgresql:// (sync) form of your Render DB URL.

# Restore into a fresh/empty database:
pg_restore -d "$TARGET_DATABASE_URL" --clean --if-exists fitcontrol_YYYY-MM-DD.dump

# Then bring schema to head (if the dump predates a migration):
DATABASE_URL="postgresql+asyncpg://…restored…" alembic upgrade head
```

Render paid Postgres plans also offer point-in-time recovery / automatic
backups — enable them, but still keep your own off-site dumps.

---

## 9. Account recovery (lost Telegram account)

Club data is keyed by `club_id`, **never** by a Telegram user — losing a
Telegram account never deletes a club or its data. A Telegram ID is **not** the
only recovery factor: each club can store an out-of-band `recovery_email` /
`recovery_phone` (Settings) that support verifies first.

**Support role.** Recovery is done by a `platform_admin` (support), granted
server-side only:

```bash
# Render shell on fitcontrol-api (or locally with DATABASE_URL set):
python -m app.manage grant-admin <your_support_telegram_id>
python -m app.manage list-admins
```

**Restore access to a new Telegram account** (club_id and all data preserved):

```
POST /api/v1/support/clubs/{club_id}/grant-access
{ "telegram_id": <new_id>, "role": "club_owner", "reason": "verified via recovery_email",
  "deactivate_membership_id": <old_membership_id_optional> }
```

**Change an existing user's Telegram ID** (keeps the same user & every membership):

```
POST /api/v1/support/recovery/change-telegram-id
{ "current_telegram_id": <old>, "new_telegram_id": <new>, "reason": "device lost, verified" }
```

Both require `platform_admin`, require a `reason`, and are written to
`AuditLog` (per affected club). Procedure:

1. Requester contacts support out-of-band.
2. Support verifies identity against the club's `recovery_email`/`recovery_phone`.
3. Support runs the appropriate endpoint above.
4. The audit trail records who did what, when and why.
