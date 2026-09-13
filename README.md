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

4. **APIs → StorageWatch API → Settings**: enable **Allow Offline Access**, and in
   **Applications → your SPA → Settings** enable **Refresh Token Rotation**. Optional —
   without them a login lasts until the access token expires (24 h by default); with
   them it renews silently.

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
   `~/.storagewatch/agent_token`, so later runs connect without asking. To keep it
   running in the background at every login instead, run `python collector.py --install`
   once (`--uninstall` removes it).

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
4. On each Mac to monitor, run `curl -fsSL https://storagewatch.tech/install.sh | sh`.
   It connects the Mac to your account and keeps the collector running in the
   background at every login. The dashboard shows this command until a Mac reports.

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

Every API endpoint except `/health`, `/install.sh`, `/collector.py` and `/StorageWatch.zip`
is authenticated. `agent` means an agent token
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
| POST | `/api/system-info` | agent | Store physical disk / APFS container inventory, block health and shared volumes |
| POST | `/api/user-usage` | agent | Store one sizing pass; runs the per-user alert rules |
| GET | `/api/users` | user | Each account's latest usage, quota and growth |
| GET | `/api/users/{username}/history` | user | One account's usage over time |
| GET | `/api/system-info` | user | Read that inventory |
| GET | `/api/dashboard` | user | Everything the dashboard shows, in one response built by one SQL query |
| GET | `/api/hosts` | user | The caller's reporting machines, most recent first |
| PUT | `/api/preferences` | user | Set a per-machine preference (menu bar app on/off); the collector applies it |
| GET | `/api/agent-tokens` | user | Metadata for the caller's agent tokens |
| POST | `/api/agent-tokens` | user | Mint an agent token; called by the Connect page (plaintext returned once) |
| POST | `/api/ai/chat` | user | Conversational analysis, grounded in live telemetry |
| GET | `/install.sh` | — | One-line collector installer for macOS |
| GET | `/collector.py` | — | The collector script the installer downloads |
| GET | `/StorageWatch.zip` | — | The menu bar app the installer downloads |

## Data model

Created automatically from `backend/schema.sql`:

- **`filesystem_metrics`** — a TimescaleDB hypertable on `time`. One row per volume per
  sample: `hostname`, `filesystem`, `filesystem_type`, `total_bytes`, `used_bytes`,
  `free_bytes`, `used_percent`, `read_bytes_per_sec`, `write_bytes_per_sec`.
- **`alerts`** — `alert_type`, `severity`, `message`, `metric_value`, `resolved`.
- **`system_info`** — JSONB snapshot of disks, APFS containers (with each volume's
  mount point, seal state and booted snapshot) and FileVault state.
- **`host_preferences`** — one row per machine: what the administrator chose in the
  dashboard (`menu_bar_enabled`) and what the collector on that machine last confirmed
  is true (`menu_bar_applied`). A machine with no row takes the defaults.
- **`user_usage`** — home directory size, quota limits and the largest folders inside,
  per user per sizing pass. A history rather than a snapshot: growth between passes is
  what identifies an account filling a volume.

Throughput is measured at the physical disk, since macOS exposes no per-volume I/O
counters. The same reading is therefore attached to every volume in a sample.

## Alerting

| Condition | Severity |
|---|---|
| `used_percent >= 90` | critical |
| `used_percent >= 80` | warning |
| Write throughput > 4× the average of the previous 20 samples | warning |
| A disk reported new I/O **errors** since the last check | critical |
| A disk reported new I/O **retries** since the last check | warning |
| A shared volume stopped answering | critical |
| A user is over their hard quota | critical |
| A user is over their soft quota, or within 10% of it | warning |
| A user's data grew faster than 50 GB/hour | critical |
| A user's data grew faster than 10 GB/hour | warning |
| One account holds over 60% of everything in use | warning |

The write baseline is kept per machine and needs 5 prior samples before it will fire,
so a freshly started collector stays quiet for the first ~30 seconds. A condition that
persists raises one alert per machine, type and severity every 10 minutes, not one per
sample — otherwise a disk sitting at 85% would add a row and an LLM call every 5 seconds.

## Dashboard

One page, per the PRD's single-page dashboard (§21): system status and host, storage /
read / write cards, then I/O performance with the graph, every alert, volumes, physical
disks and APFS containers. Questions about any of it go to the **Ask AI** chat.
**Settings** lists connected Macs and the install command. Polling pauses while the tab
is in the background.

**Block storage health** reports, per disk, the I/O the hardware failed to complete
(errors) or had to repeat (retries), its average service time in microseconds, and
sustained IOPS and throughput. These come from the kernel's own block storage driver via
`ioreg`, and move long before SMART stops saying "Verified" — which is all `diskutil`
will tell you, and only once a disk is already failing.

**Shared volumes** lists NFS, pNFS, SMB and AFP mounts with their server, export,
protocol version and capacity, plus NFS client RPC counts by operation. Every call
against a share has a five-second limit, so a server that has gone away is reported as
not responding rather than stalling the collector — an unguarded `statvfs` on a dead NFS
mount blocks in the kernel forever and would take the local disks down with it.

**Users and quotas** shows each account's home directory size, its share of everything in
use, quota limits from `quota(1)`, growth since the previous measurement, and the largest
folders inside each home. Sizing means walking the directory — 77 seconds for a 68 GB
home on the machine this was written on — so the collector measures on a background
thread every 30 minutes (`USER_USAGE_INTERVAL_SECONDS`) and the page says when the
reading was taken. macOS ships with quotas disabled, which the page states rather than
leaving blank.

On "nefarious users": an administrator cannot read intent from telemetry and this tool
does not try to. What it reports is which account is consuming the space, how fast, and
whether that is unlike the account's own recent history — each alert names the account
and the evidence, and a person decides what it means.

The APFS section carries what `diskutil apfs list` prints, so nobody has to open a
terminal to read it: per volume the device identifier, **mount point**, roles, capacity,
encryption, FileVault and whether it is sealed, locked or read-only; per container the
UUID, the physical store with its own UUID and size, and the capacity split. A sealed
system volume reports no mount point of its own — the Mac runs from a read-only snapshot
of it — so the snapshot's device, UUID and mount point are shown too. The assistant is
told the dashboard already shows all of this, and to answer from it rather than
suggesting a command to look it up. (The one thing `diskutil` prints that isn't here is
volume case-sensitivity, which it exposes in no plist.)

## Menu bar app

**StorageWatch** can also sit in the macOS menu bar and open at login. It is on by
default; the **Menu bar app** switch at the bottom of the Dashboard turns it off or back
on per machine. A browser cannot reach the monitored Mac, so the choice is stored against
that machine and the collector there applies it with its next report — a few seconds —
installing or removing the app itself. Until that collector confirms what it did, the
Dashboard says the change is still being applied rather than claiming it took effect.
Switching it off leaves monitoring untouched: only the icon goes.

The bar shows boot-volume usage (⚠ when an alert is open or the collector stops); a
click shows every volume, read/write throughput, disk SMART status, FileVault, local
snapshots and open alerts, plus **Open Dashboard**. New alerts also arrive as macOS
notifications. It reads `~/.storagewatch/status.json`, which the collector rewrites every
cycle, so it never asks for a login. Source in `menubar/`; rebuild the served
`menubar/StorageWatch.zip` with `menubar/build.sh` after changing it.

## Demo

With all three services running and logged in:

```bash
mkfile 2g ~/storagewatch-demo   # write burst → spike on the Performance chart
rm ~/storagewatch-demo          # capacity recovers
```

Expect the write-activity alert within ~10 seconds. Ask the AI (bottom right) about the
spike to see it analyze the live numbers.

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
