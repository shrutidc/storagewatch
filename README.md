# StorageWatch

A macOS filesystem observability platform for monitoring AI infrastructure storage.

A Python agent samples the machine's volumes every 5 seconds and POSTs telemetry to a
FastAPI backend, which stores it in Tiger Data (TimescaleDB), detects anomalies, and
serves it to an Auth0-protected React dashboard with AI-assisted analysis.

## Quick Start

### Prerequisites
- **Python 3.10+** (the backend uses `X | Y` type annotations, which raise
  `TypeError` on 3.9)
- Node.js 18+
- macOS (the collector reads `diskutil` / `fdesetup` / `tmutil`)
- Access to: Tiger Data, Auth0, Backboard

### One-time Auth0 setup

The backend verifies access tokens, which Auth0 only issues as verifiable JWTs when the
request names a registered API. In the Auth0 dashboard:

1. **Applications → APIs → Create API**, identifier exactly `storagewatch-api`,
   signing algorithm RS256.
2. **Applications → your SPA → Settings → Application URIs**: add
   `http://localhost:3000` to Allowed Callback URLs, Logout URLs and Web Origins.
3. **APIs → StorageWatch API → Application Access**: enable **User-delegated Access**
   for your SPA. Tenants set to *per-app authorization* grant nothing by default, so
   creating the API in step 1 is not sufficient on its own.

Skipping step 1 makes Auth0 return an opaque token and every API call 401s. Skipping
step 3 fails earlier and louder — `/authorize` refuses with *"Client is not authorized
to access resource server"* and login never completes.

### Setup

1. **Environment files** — there are two, and both are required:
   ```bash
   cp .env.example .env                     # backend + collector
   cp frontend/.env.example frontend/.env   # frontend (Vite reads VITE_* here only)
   ```
   Fill in `TIGER_DATABASE_URL`, `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`,
   `BACKBOARD_API_KEY`, and generate the collector's shared secret:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # -> AGENT_TOKEN
   ```
   `AUTH0_AUDIENCE` and `VITE_AUTH0_AUDIENCE` must match.

2. **Python dependencies:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Run all three, each in its own terminal** (they are long-running):
   ```bash
   cd backend   && python main.py               # :8000
   cd frontend  && npm install && npm run dev   # :3000
   cd collector && python collector.py
   ```

Dashboard at `http://localhost:3000`. The backend creates its tables on startup, so no
manual migration step is needed.

### Production build

For deployment the backend serves the built dashboard itself, so the browser
talks to a single origin and `/api` needs no CORS or proxy (Vite's dev proxy
only exists under `npm run dev`):

```bash
cd frontend && npm run build     # -> frontend/dist
cd ../backend && python main.py  # serves the dashboard and the API on one port
```

The whole app is then on `:8000`. The host's `PORT` variable is honoured if set.
The collector still runs on the monitored Mac, with `BACKEND_URL` pointing at
the public URL.

### Authentication

| Caller | Credential |
|---|---|
| Dashboard (browser) | Auth0 access token, verified against the tenant's JWKS |
| Collector agent | `AGENT_TOKEN` shared secret — it runs unattended with no user to sign in as |

The backend refuses to start if `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` or `AGENT_TOKEN` is
missing, rather than serving telemetry unprotected.

## Architecture

```
Mac Agent (collector) → FastAPI Backend → Tiger Data
                                      ↓
                              React Dashboard ← Auth0
                                      ↑
                                 Backboard (AI)
```

## API

Every API endpoint except `/health` is authenticated. `agent` means the `AGENT_TOKEN`
shared secret; `user` means an Auth0 access token. (In a production build the backend
also serves the dashboard's static files on unmatched paths — see above.)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | — | Liveness check |
| POST | `/api/metrics` | agent | Ingest one volume's telemetry; runs anomaly detection |
| GET | `/api/metrics/current` | user | Most recent sample |
| GET | `/api/metrics/history?limit=N&filesystem=/` | user | Last N samples for one volume, newest first (defaults: 100, `/`) |
| GET | `/api/volumes` | user | Latest sample per mounted volume |
| GET | `/api/alerts` | user | Unresolved alerts, newest first |
| POST | `/api/alerts/report` | agent | Agent-side alert submission |
| POST | `/api/system-info` | agent | Store physical disk / APFS container inventory |
| GET | `/api/system-info` | user | Read that inventory |
| POST | `/api/ai/chat` | user | Conversational analysis, grounded in live telemetry |

## Data model

Three tables, created automatically from `backend/schema.sql`:

- **`filesystem_metrics`** — a TimescaleDB hypertable on `time`. One row per volume per
  sample: `hostname`, `filesystem`, `filesystem_type`, `total_bytes`, `used_bytes`,
  `free_bytes`, `used_percent`, `read_bytes_per_sec`, `write_bytes_per_sec`.
- **`alerts`** — `alert_type`, `severity`, `message`, `metric_value`, `resolved`.
- **`system_info`** — JSONB snapshot of disks, APFS containers and FileVault state.

Throughput is measured at the physical disk, since macOS exposes no per-volume I/O
counters. The same reading is therefore attached to every volume in a sample.

## Alerting

| Condition | Severity |
|---|---|
| `used_percent >= 90` | critical |
| `used_percent >= 80` | warning |
| Write throughput > 4× the trailing 20-sample average | warning |

The write baseline needs at least 5 samples before it will fire, so a freshly started
collector stays quiet for the first ~25 seconds.

## Dashboard

Six pages, all behind Auth0 login: **Dashboard** (overview), **Volumes**, **Disks**,
**APFS**, **Performance**, **Alerts**.

## Demo

With all three services running and logged in:

```bash
mkfile 2g ~/storagewatch-demo   # write burst → spike on the Performance chart
rm ~/storagewatch-demo          # capacity recovers
```

Expect the write-activity alert within ~10 seconds. Ask the AI panel about the spike to
see it cite the live numbers.

## Troubleshooting

**`/authorize` returns "Client is not authorized to access resource server"** — the
per-app grant from Auth0 setup step 3 is missing. Creating the API is not enough.

**Login succeeds but every card is empty, network tab shows 401** — Auth0 issued an
opaque token instead of a JWT. `AUTH0_AUDIENCE` and `VITE_AUTH0_AUDIENCE` must match
each other and name a registered API.

**Backend exits with `TypeError: unsupported operand type(s) for |`** — you are on
Python 3.9. Use 3.10+.

**Frontend ignores an env change** — Vite reads `frontend/.env`, not the project root,
only exposes `VITE_`-prefixed names, and prefers `.env.local` over `.env` if both
exist. Restart the dev server after editing; values are inlined at startup.

**Collector logs 401** — `AGENT_TOKEN` differs between `.env` and the running backend,
or the backend was started before the value was set.

## Project Structure

```
storagewatch/
├── collector/          # Python agent (runs on the Mac being monitored)
├── backend/            # FastAPI server, auth, anomaly detection, schema
├── frontend/           # React dashboard (Vite)
├── requirements.txt    # Python dependencies
└── README.md
```
