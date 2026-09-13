# StorageWatch

A macOS filesystem observability platform for monitoring AI infrastructure storage.

A Python agent samples the machine's volumes every 5 seconds and POSTs telemetry to a
FastAPI backend, which stores it in Tiger Data (TimescaleDB), detects anomalies, and
serves it to an Auth0-protected React dashboard with AI-assisted analysis.

**Further reading:** [Memory.md](Memory.md) explains the system from scratch, including
the APFS model that drives most of its behaviour. [Decisions.md](Decisions.md) records
why the code is shaped the way it is. [Flow.md](Flow.md) traces the runtime paths.

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
   Fill in `TIGER_DATABASE_URL`, `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` and
   `BACKBOARD_API_KEY`. Leave `AGENT_TOKEN` empty — the collector connects itself in
   step 4. `AUTH0_AUDIENCE` and `VITE_AUTH0_AUDIENCE` must match.

2. **Python dependencies:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Start the backend and dashboard**, each in its own terminal:
   ```bash
   cd backend   && python main.py               # :8000
   cd frontend  && npm install && npm run dev   # :3000
   ```
   The backend creates its tables on startup, so no manual migration step is needed.

4. **Start the collector** in a third terminal:
   ```bash
   cd collector && python collector.py
   ```
   On first run it opens the dashboard in your browser. Sign in, click **Connect**, and
   you land on the Dashboard as data starts arriving. The token is saved to
   `~/.storagewatch/agent_token`, so later runs connect without asking.

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

### Deploying to Render

`render.yaml` deploys the API and dashboard as one Docker service. The image is
built in two stages because the app needs both toolchains — Node for the
dashboard, Python to serve it — and Render's native Python runtime has no Node.

1. Render dashboard → **New → Blueprint** → pick this repo. It reads
   `render.yaml` and prompts for the secrets marked `sync: false`:
   `TIGER_DATABASE_URL`, `BACKBOARD_API_KEY`.
2. After the first deploy, add the custom domain under **Settings → Custom
   Domains** and create the DNS record it gives you at your registrar.
3. In Auth0, add `https://storagewatch.tech` to Allowed Callback URLs, Logout
   URLs and Web Origins.
4. On the monitored Mac, set `BACKEND_URL=https://storagewatch.tech` in `.env`
   and restart the collector.

The frontend's Auth0 settings come from the committed
`frontend/.env.production`, since Vite inlines `VITE_*` at build time and those
three values are public to the browser regardless. The Auth0 **client secret is
not among them** and must never be — the browser never sees it.

Note: Render's free tier sleeps after ~15 minutes idle, but the collector posts
every 5 seconds, which keeps the service awake as long as the Mac is running.

### Authentication

| Caller | Credential |
|---|---|
| Dashboard (browser) | Auth0 access token, verified against the tenant's JWKS |
| Collector agent | A per-user agent token, obtained once by signing in through the browser |

The backend refuses to start without `AUTH0_DOMAIN` and `AUTH0_AUDIENCE`, rather than
serving telemetry unprotected.

### Data ownership

Telemetry is private to the administrator whose agent produced it. Each agent token
belongs to an Auth0 user; every ingested row records that owner, and every read is
filtered to the signed-in user. One person's machines are never visible to another,
including to the AI assistant, whose context is built from the caller's own data.

Agent tokens are stored only as a SHA-256 hash — a leaked database yields no working
credentials — and the plaintext only ever lives in `~/.storagewatch/agent_token` on the Mac. Rows predating ownership
have a NULL owner and are visible to nobody, which is the safe direction.

A user with several machines picks between them with the host selector in the header;
without one, the backend answers for whichever reported most recently.

## Architecture

```
Mac Agent (collector) → FastAPI Backend → Tiger Data
                                      ↓
                              React Dashboard ← Auth0
                                      ↑
                                 Backboard (AI)
```

## API

Every API endpoint except `/health` is authenticated. `agent` means an agent token
obtained by the collector's browser sign-in; `user` means an Auth0 access token. (In a production build the backend
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
| GET | `/api/hosts` | user | The caller's reporting machines, most recent first |
| GET | `/api/agent-tokens` | user | Metadata for the caller's agent tokens |
| POST | `/api/agent-tokens` | user | Mint an agent token; called by the Connect page (plaintext returned once) |
| POST | `/api/ai/chat` | user | Conversational analysis, grounded in live telemetry |
| POST | `/api/ai/explain` | user | Explain one alert (`{"alert_id": N}`) with Backboard; stored on the alert |

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
| Write throughput > 4× the average of the previous 20 samples | warning |

The write baseline is kept per machine and needs 5 prior samples before it will fire,
so a freshly started collector stays quiet for the first ~30 seconds. A condition that
persists raises one alert per machine, type and severity every 10 minutes, not one per
sample — otherwise a disk sitting at 85% would add a row and an LLM call every 5 seconds.

## Dashboard

Everything the PRD's single-page dashboard (§21) calls for is on **Dashboard**: system
status and host, storage / read / write cards, the I/O graph, and alerts beside an AI
Analysis panel with **Explain with AI**. **Volumes**, **Disks**, **APFS**,
**Performance**, **Alerts** and **Settings** are optional drill-downs. Each page fetches
only its own data, and polling pauses while the tab is in the background.

## Demo

With all three services running and logged in:

```bash
mkfile 2g ~/storagewatch-demo   # write burst → spike on the Performance chart
rm ~/storagewatch-demo          # capacity recovers
```

Expect the write-activity alert within ~10 seconds. Select it and click **Explain with
AI** to see Backboard analyze it against the live numbers.

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

**Collector says the backend rejected its token** — the token belongs to a different
backend or database (e.g. minted locally, now pointed at Render). The collector drops it
and reconnects through the browser on its own. If `.env` sets `AGENT_TOKEN`, remove it,
or that stale value is used again on the next start.

## Project Structure

```
storagewatch/
├── collector/          # Python agent (runs on the Mac being monitored)
├── backend/            # FastAPI server, auth, anomaly detection, schema
├── frontend/           # React dashboard (Vite)
├── requirements.txt    # Python dependencies
├── README.md
└── LICENSE
```

## License

MIT — see [LICENSE](LICENSE).
