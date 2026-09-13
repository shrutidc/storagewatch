# StorageWatch

**Storage observability for Macs running private AI.** A lightweight agent on each Mac
reports capacity, throughput, APFS layout, disk health, shared volumes and accounts every
five seconds; a web dashboard and a native menu bar app turn that into alerts and
answers.

**Live:** [storagewatch.tech](https://storagewatch.tech) 

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Monitor a Mac](#monitor-a-mac)
- [Development](#development)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Using the dashboard](#using-the-dashboard)
- [Alerts](#alerts)
- [Menu bar app](#menu-bar-app)
- [Security and privacy](#security-and-privacy)
- [API reference](#api-reference)
- [Data model](#data-model)
- [Troubleshooting](#troubleshooting)
- [Project structure](#project-structure)

## Features

- **One-line install** — works with any Python 3.9+, Apple's own included. The Mac
  connects through a browser sign-in and reports in the background at every login.
- **Storage health** — capacity, live read/write throughput, APFS containers and
  volumes, physical disks with SMART plus the kernel's I/O error, retry and latency
  counts, and inode usage.
- **Shared volumes** — NFS, pNFS, SMB and AFP mounts with capacity and state; a server
  that stops answering is reported, never waited on.
- **Users and quotas** — every account, who is an administrator, who is signed in, and
  quotas, with per-user disk usage on Macs that opt in.
- **Alerts** — capacity, write bursts, disk errors, unresponsive shares and per-user
  rules; summarised on the dashboard, cleared by hand, and sent as macOS notifications.
- **Ask Anything** — an assistant that answers from the Mac's live telemetry.
- **Menu bar app** — native Swift; usage and alerts at a glance without signing in.
- **Private by design** — Auth0 sign-in, each administrator sees only their own Macs,
  and the collector reads system data only — never personal files.
- **Light and dark** — follows the Mac's appearance, or pin either theme.

## Architecture

```mermaid
flowchart LR
  subgraph Mac["Monitored Mac"]
    C["Collector<br/>background agent · every 5 s"]
    M["Menu bar app"]
    C -- "status.json" --> M
  end
  subgraph Server["Backend host · Render or Vultr"]
    A["FastAPI backend"]
    UI["React dashboard"]
    A --> DB[("Tiger Data<br/>TimescaleDB")]
    A --> AI["Backboard → Gemini"]
  end
  C -- "HTTPS · agent token" --> A
  UI -- "Auth0 access token" --> A
  Admin(("Administrator")) --> UI
```

| Component | Runs on | Role |
|---|---|---|
| `collector/` | Each monitored Mac | Samples volumes, disks, APFS, shares and accounts; reports to the backend |
| `backend/` | Render or Vultr (Docker) | Stores telemetry, evaluates alerts, serves the API, the dashboard and the installer |
| `frontend/` | Browser | Single-page React dashboard with Auth0 sign-in |
| `menubar/` | Each monitored Mac | SwiftUI menu bar app fed by the collector's status file |

## Monitor a Mac

On the Mac you want to monitor, run:

```bash
curl -fsSL https://storagewatch.tech/install.sh | sh
```

The installer:

1. picks the newest Python 3.9+ on the Mac — if there is none, it opens Apple's
   installer for the Command Line Tools; run the command again once they are installed;
2. downloads the collector into `~/.storagewatch`;
3. opens the dashboard so you can sign in and click **Connect**;
4. registers the collector and the menu bar app to start at every login.

Data appears on the dashboard within seconds. Until a Mac is connected, the dashboard
shows this command with a **Copy** button. Running your own server? Use the command
under [Deployment](#deployment), which points the installer at your domain.

The collector runs on any macOS with Python 3.9 or later; the menu bar app needs
macOS 13 or later.

**Per-user disk usage** is off by default, because measuring a home directory means
reading every folder in it and makes macOS ask for access to Documents, Desktop, Photos
and more. To turn it on for a Mac:

```bash
curl -fsSL https://storagewatch.tech/install.sh | STORAGEWATCH_SIZE_HOMES=1 sh
```

**Uninstall** (the installer prints this command):

```bash
~/.storagewatch/venv/bin/python ~/.storagewatch/collector.py --uninstall
```

## Development

### Prerequisites

- macOS — the collector reads `diskutil`, `ioreg`, `fdesetup` and `tmutil`
- Python 3.12 for the backend (3.10 or later is required) and Node.js 18+
- Accounts with Tiger Data, Auth0 and Backboard

### Auth0 (one time)

1. **Applications → APIs → Create API** with the identifier `storagewatch-api` and the
   RS256 signing algorithm.
2. In your single-page application's **Settings**, add `http://localhost:3000` and your
   production URL to **Allowed Callback URLs**, **Allowed Logout URLs** and **Allowed Web
   Origins**.
3. **APIs → StorageWatch API → Application Access**: enable **User-delegated Access** for
   the application.
4. *Optional:* enable **Allow Offline Access** on the API and **Refresh Token Rotation**
   on the application, so sign-ins renew silently beyond 24 hours.

### Run locally

Create the two environment files and fill them in (see [Configuration](#configuration)):

```bash
cp .env.example .env                     # backend and collector
cp frontend/.env.example frontend/.env   # dashboard
```

Install the Python dependencies:

```bash
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Then start each service in its own terminal, from the project root:

```bash
cd backend   && python main.py          # API on :8000
cd frontend  && npm ci && npm run dev   # dashboard on :3000
cd collector && python collector.py     # opens the browser to connect this Mac
```

The backend creates its tables on startup. `python collector.py --install` runs the
collector in the background at every login instead, and `--uninstall` removes it.

> [!NOTE]
> Use `python3.12`, not `python3` — on macOS that is Apple's 3.9, which the backend does
> not support. The dev server is pinned to port 3000, which Auth0 and the backend's
> CORS list both name, and exits if the port is busy rather than moving elsewhere.

## Configuration

**Backend and collector** — `.env` in the project root:

| Variable | Required | Description |
|---|---|---|
| `TIGER_DATABASE_URL` | Yes | PostgreSQL/TimescaleDB connection string. URL-encode special characters in the password (`@` → `%40`). |
| `AUTH0_DOMAIN` | Yes | Auth0 tenant, e.g. `your-tenant.us.auth0.com`. |
| `AUTH0_AUDIENCE` | Yes | `storagewatch-api`. Must match `VITE_AUTH0_AUDIENCE`. |
| `BACKBOARD_API_KEY` | No | Enables the assistant; `mock-key` returns canned answers. Add a Gemini key under BYOK in Backboard — its free credits do not cover chat. |
| `BACKEND_URL` | No | Where the collector reports. Default `http://localhost:8000`. |
| `DASHBOARD_URL` | No | Where the collector opens its sign-in. Defaults to `BACKEND_URL`, or the Vite dev server when that is local. |
| `AGENT_TOKEN` | No | Overrides the token the collector saves at sign-in, e.g. on a Mac with no browser. |
| `PORT` | No | Port the backend listens on. Default `8000`. |

**Dashboard** — `frontend/.env` in development and `frontend/.env.production` (committed)
for builds. These values are public by design; the Auth0 client secret never belongs here.

| Variable | Description |
|---|---|
| `VITE_AUTH0_DOMAIN` | Auth0 tenant |
| `VITE_AUTH0_CLIENT_ID` | The single-page application's client ID |
| `VITE_AUTH0_AUDIENCE` | `storagewatch-api` |

**Collector options:**

| Variable | Default | Description |
|---|---|---|
| `STORAGEWATCH_SIZE_HOMES` | Off | `1` enables per-user disk usage. Set it on the install command to keep it for the background agent. |
| `STORAGEWATCH_URL` | `https://storagewatch.tech` | Server the installer downloads from and connects to. |
| `USER_USAGE_INTERVAL_SECONDS` | `1800` | How often per-user usage is measured. |
| `USER_USAGE_TIMEOUT_SECONDS` | `900` | Longest one home directory may take to measure. |

## Deployment

The whole app ships as one Docker image (`Dockerfile`). It builds the dashboard with
Node and serves it — with the API and the installer downloads — from Python on port
`8000`, or `$PORT` if set. The browser talks to a single origin, so there is no CORS or
proxy to configure, and any host that runs a container works. Two are documented here.

Whichever you choose:

- Add the production URL to the Auth0 application's callback, logout and web-origin
  lists.
- The dashboard's Auth0 settings are built into the image from
  `frontend/.env.production`; edit that file before building if you use a different
  Auth0 tenant.
- On any domain other than `storagewatch.tech`, install the collector on each Mac with
  your own domain:

  ```bash
  curl -fsSL https://your-domain/install.sh | STORAGEWATCH_URL=https://your-domain sh
  ```

### Render

`render.yaml` is a ready-made Blueprint.

1. In Render, choose **New → Blueprint** and select this repository. Enter
   `TIGER_DATABASE_URL` and `BACKBOARD_API_KEY` when prompted.
2. Add your domain under **Settings → Custom Domains** and create the DNS record Render
   gives you.

Every push to `main` redeploys. On the free tier the service sleeps after about 15
minutes without traffic and has a tenth of a CPU; a running collector reports every five
seconds and keeps it awake.

### Vultr

A Vultr Cloud Compute instance runs the same image, with Caddy in front for automatic
HTTPS. It never sleeps and gives the backend a full virtual CPU.

1. Deploy a **Cloud Compute** instance running Ubuntu 24.04. 1 vCPU with 2 GB of memory
   builds the image comfortably. Allow inbound TCP 22, 80 and 443 in its firewall group.
2. Point your domain at the instance with an `A` record for its public IPv4 address.
3. On the instance, install Docker, open the web ports if `ufw` is enabled, and build the
   image:

   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo ufw allow 80,443/tcp
   git clone https://github.com/shrutidc/storagewatch.git && cd storagewatch
   docker build -t storagewatch .
   ```

4. Put the backend's settings (see [Configuration](#configuration)) in
   `/etc/storagewatch.env`:

   ```bash
   TIGER_DATABASE_URL=postgres://user:password@host:port/dbname?sslmode=require
   BACKBOARD_API_KEY=your-backboard-key
   AUTH0_DOMAIN=your-tenant.us.auth0.com
   AUTH0_AUDIENCE=storagewatch-api
   ```

5. Start the app, reachable only from the instance itself, and Caddy, which obtains and
   renews a TLS certificate for your domain:

   ```bash
   docker run -d --name storagewatch --restart unless-stopped \
     --env-file /etc/storagewatch.env -p 127.0.0.1:8000:8000 storagewatch
   docker run -d --name caddy --restart unless-stopped --network host \
     -v caddy_data:/data caddy caddy reverse-proxy --from your-domain --to localhost:8000
   ```

6. Check it: `curl https://your-domain/health` should answer `{"status":"ok"}`.

To deploy a new version:

```bash
cd storagewatch && git pull && docker build -t storagewatch .
docker rm -f storagewatch
docker run -d --name storagewatch --restart unless-stopped \
  --env-file /etc/storagewatch.env -p 127.0.0.1:8000:8000 storagewatch
```

### Anywhere else

To run a production build without Docker:

```bash
cd frontend && npm run build      # outputs frontend/dist
cd ../backend && python main.py   # dashboard and API together on :8000
```

## Using the dashboard

Sign in once — the session survives reloads and new tabs. The dashboard is a single page
that refreshes every five seconds (pausing while the tab is in the background) and shows
each fact once:

| Section | Shows |
|---|---|
| **Status** | The machine and its health — Healthy, Warning or Critical — with a picker when you have several Macs |
| **Storage · Read · Write** | Boot-volume capacity and current throughput |
| **Alerts** | One line per alert type with its count; the full list in a drop-down |
| **I/O performance** | Live graph, average and peak, totals since boot |
| **APFS** | Containers and volumes: mount points, roles, encryption, FileVault, seal state, booted snapshot |
| **Other volumes** | Local non-APFS volumes such as an exFAT USB drive, shown only when present |
| **Physical disks** | Model, media, capacity, SMART, and the kernel's error, retry, latency and IOPS counts |
| **Users and quotas** | Accounts, administrators, sign-ins and quotas; per-user usage where enabled; inodes |
| **Shared volumes** | NFS, pNFS, SMB and AFP mounts and NFS client activity |

**Ask Anything** (bottom right) answers questions about the machine from its live
telemetry and suggests starter questions.

**Settings** holds your connected Macs, the install command, the **Menu bar app** switch
for each Mac, and **Appearance** — Light, Dark, or System to follow the Mac. Appearance
is saved in the browser; the menu bar switch is applied by that Mac's collector within
seconds. All animations respect macOS's *Reduce motion* setting.

**Demo:** with a Mac connected, create a burst of writes and watch the graph, an alert
and a notification arrive within about ten seconds:

```bash
mkfile 2g ~/storagewatch-demo && rm ~/storagewatch-demo
```

## Alerts

| Condition | Severity |
|---|---|
| Storage ≥ 90% used | Critical |
| Storage ≥ 80% used | Warning |
| Writes above 4× the average of the previous 20 samples **and** at least 50 MB/s | Warning |
| A disk reports new I/O errors | Critical |
| A disk reports new I/O retries | Warning |
| A shared volume stops responding | Critical |
| A user is over their hard quota | Critical |
| A user is over their soft quota, or within 10% of it | Warning |
| A user's data grows faster than 50 GB/hour | Critical |
| A user's data grows faster than 10 GB/hour | Warning |
| One account holds over 60% of the space in use | Warning |

- A persisting condition raises one alert per machine, type and severity every 10
  minutes, not one per sample.
- The write baseline is kept per machine and needs five samples, so a new collector is
  quiet for its first ~30 seconds.
- Per-user rules need per-user disk usage enabled. They name the account and the
  evidence; they do not guess at intent.
- Alerts never close on their own. **Dismiss** clears one, **Clear** a whole type and
  **Clear all** everything. Cleared alerts are kept on record and disappear from the
  dashboard, the menu bar and the assistant.

## Menu bar app

The menu bar shows boot-volume usage, with ⚠ when an alert is open or the collector has
stopped. Clicking it shows every volume, throughput, disk health, FileVault, local
snapshots, open alerts and **Open Dashboard**. New alerts arrive as macOS notifications.

The app reads the status file the collector writes each cycle
(`~/.storagewatch/status.json`), so it never asks you to sign in. It is installed with
the collector, starts at login, restarts if it crashes, and can be switched off per Mac
in Settings. After changing its source, rebuild the distributed
`menubar/StorageWatch.zip` with `menubar/build.sh`.

## Security and privacy

- **Separate credentials.** The dashboard uses Auth0 access tokens, verified against the
  tenant's signing keys. Each collector uses its own agent token, issued through a
  browser sign-in and stored only as a SHA-256 hash. Neither is accepted in place of
  the other.
- **Your Macs only.** Every record carries the administrator whose collector produced it,
  and every read is filtered to the signed-in user — including what the assistant sees.
- **System data only.** The collector uses `diskutil`, `ioreg`, `df`, `nfsstat`, the
  directory service and similar tools. It opens no personal files unless per-user disk
  usage is enabled, and marks any size it could not fully read as *partial*.
- **Fails closed.** The backend refuses to start without its Auth0 settings.

## API reference

All endpoints except `/health`, `/install.sh`, `/collector.py` and `/StorageWatch.zip`
require authentication: **user** is an Auth0 access token, **agent** a collector token.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | — | Liveness, including whether the database schema is in place |
| GET | `/api/dashboard` | user | Everything the dashboard shows, in one response |
| GET | `/api/metrics/current` | user | Most recent sample |
| GET | `/api/metrics/history?limit=N&filesystem=/` | user | Last N samples for one volume, newest first |
| GET | `/api/volumes` | user | Latest sample per mounted volume |
| GET | `/api/system-info` | user | Disk, APFS, block health and shared-volume inventory |
| GET | `/api/users` | user | Each account's latest usage, quota and growth |
| GET | `/api/users/{username}/history` | user | One account's usage over time |
| GET | `/api/alerts` | user | Unresolved alerts, newest first |
| POST | `/api/alerts/resolve` | user | Mark alerts resolved: `{"ids": [...]}` |
| GET | `/api/hosts` | user | The caller's reporting Macs, most recent first |
| PUT | `/api/preferences` | user | Per-Mac preferences (menu bar app on or off) |
| GET | `/api/agent-tokens` | user | Metadata for the caller's collector tokens |
| POST | `/api/agent-tokens` | user | Issue a collector token (used by the Connect page) |
| POST | `/api/ai/chat` | user | Ask the assistant, grounded in live telemetry |
| POST | `/api/metrics` | agent | Ingest one volume's sample and evaluate alerts |
| POST | `/api/system-info` | agent | Store the disk, APFS, health and share inventory |
| POST | `/api/user-usage` | agent | Store a per-user sizing pass |
| POST | `/api/alerts/report` | agent | Submit an alert raised on the Mac |
| GET | `/install.sh` | — | The collector installer |
| GET | `/collector.py` | — | The collector the installer downloads |
| GET | `/StorageWatch.zip` | — | The menu bar app the installer downloads |

## Data model

Created automatically from `backend/schema.sql` when the backend starts.

| Table | Contents |
|---|---|
| `filesystem_metrics` | TimescaleDB hypertable: one row per volume per sample — capacity, usage and throughput |
| `alerts` | Type, severity, message, value and whether it has been resolved |
| `system_info` | Latest disk, APFS, block-health, shared-volume and account snapshot per Mac (JSONB) |
| `user_usage` | Per-user sizing passes: size, quota, largest folders, and whether the walk was complete |
| `host_preferences` | Per-Mac settings, and what that Mac's collector last confirmed |
| `agent_tokens` | Hashed collector tokens and their owners |

Throughput is measured per physical disk — macOS keeps no per-volume counters — so the
same reading accompanies every volume in a sample.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/authorize` says *"Client is not authorized to access resource server"* | Enable **User-delegated Access** (Auth0 step 3). |
| Signed in, but panels are empty and the API returns 401 | `AUTH0_AUDIENCE` and `VITE_AUTH0_AUDIENCE` must match a registered API. |
| `/health` returns 503 *"database unavailable"* | `TIGER_DATABASE_URL` is missing or wrong. |
| Backend exits with `TypeError: unsupported operand type(s) for \|` | It is running on Python 3.9; use 3.10 or later. |
| A change to `frontend/.env` has no effect | Vite reads only `VITE_` variables, from `frontend/.env` (`.env.local` wins), at startup — restart the dev server. |
| The collector says its token was rejected | It reconnects through the browser automatically; remove any stale `AGENT_TOKEN` from `.env`. |
| The menu bar icon doesn't appear | On a MacBook with a notch, macOS hides icons that don't fit. Hold ⌘ and drag an unneeded icon off the menu bar, and check the switch in Settings is on. |
| macOS asks for access to Documents, Desktop or Photos | Per-user disk usage is on for that Mac; reinstall without `STORAGEWATCH_SIZE_HOMES=1`. |
| Shared volumes is empty | No NFS, SMB or AFP share is mounted; one appears within a minute of mounting. |

## Project structure

```
storagewatch/
├── collector/        Python agent and install.sh — runs on each monitored Mac
├── backend/          FastAPI server: auth, alert rules, schema, installer downloads
├── frontend/         React dashboard (Vite)
├── menubar/          SwiftUI menu bar app; build.sh produces StorageWatch.zip
├── Dockerfile        One image: builds the dashboard, serves it with the API
├── render.yaml       Render deployment
├── requirements.txt  Python dependencies for the backend and collector
├── Memory.md         How the system works, from first principles
├── Decisions.md      Why the code is shaped the way it is
└── Flow.md           Runtime paths, step by step
```

## License

MIT — see [LICENSE](LICENSE).
