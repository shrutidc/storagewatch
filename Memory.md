# Memory

Everything needed to understand StorageWatch from scratch. Setup and operational
instructions live in [README.md](README.md); the reasoning behind the design is in
[Decisions.md](Decisions.md); runtime paths are in [Flow.md](Flow.md).

## What this is

StorageWatch monitors macOS filesystem health for machines running AI workloads, where
a runaway training job or dataset ingest can fill a disk quickly and quietly. An agent
on the Mac samples capacity and disk I/O every five seconds, ships it to a backend that
stores it as a time series and flags anomalies, and a web dashboard renders it with an
AI assistant that can answer questions about the machine's actual numbers.

The unit of concern is the **volume**, and the thing that makes this harder than it
sounds is APFS — see below.

## The APFS model (read this first)

Most of the subtle behaviour in this codebase comes from one fact: **on modern macOS,
no single volume's usage figures describe the disk.**

- A physical disk holds an APFS **container**. The container holds several **volumes**,
  which all draw from **one shared free-space pool**. A volume has no fixed size.
- `/` is a **sealed, read-only system snapshot** — roughly 12 GB. Your files are not
  there; they live on a sibling `Data` volume.
- So `psutil.disk_usage("/")` describes the sealed snapshot, not the disk. It reported
  2.6% used on a disk that was 52.1% full, and the numbers openly contradicted each
  other: 12.6 GB used + 237.0 GB free ≠ 494.4 GB total.

StorageWatch therefore reads capacity from the **container** (`APFSContainerSize` /
`APFSContainerFree` via `diskutil`), which is the real constraint and what macOS itself
reports. Non-APFS volumes keep psutil's numbers, which are correct for filesystems
without a shared pool.

Two consequences worth internalising:

- **Capacity must be reported per storage pool, not summed across volumes.** Adding up
  every volume counts one container's capacity several times.
- **Throughput is measured at the physical disk.** macOS exposes no per-volume I/O
  counters, so the same read/write figure is attached to every volume in a sample. It
  is a property of the disk, not of the volume it is filed under.

## Components

| Component | Runs | Responsibility |
|---|---|---|
| `collector/` | On the monitored Mac | Samples volumes, disks, APFS state; POSTs to the backend; installs itself as a LaunchAgent via `/install.sh` |
| `backend/` | Anywhere reachable | Ingests, stores, detects anomalies, serves the API and AI, serves the built dashboard in production |
| `frontend/` | Browser | Single-page React dashboard, Settings, Auth0 login, Recharts, AI chat |

The collector must stay on the machine being monitored — it shells out to `diskutil`,
`fdesetup` and `tmutil`. The backend can live elsewhere; `BACKEND_URL` points the agent
at it.

**Backend modules:** `main.py` (routes, AI), `auth.py` (both credential paths),
`database.py` (all SQL), `alerts.py` (anomaly rules), `models.py` (Pydantic),
`schema.sql` (tables, applied on startup).

## Two kinds of caller

This shapes the whole auth design. The dashboard has a human who can sign in; the
collector does not.

| Caller | Credential | Enforced by |
|---|---|---|
| Dashboard | Auth0 access token, verified against tenant JWKS (audience + issuer checked) | `require_user` |
| Collector | Per-user agent token, obtained once via browser sign-in, stored hashed | `require_agent` |

The roles are **disjoint, not hierarchical**: the agent token is rejected on dashboard
reads, and a user token is rejected on ingest. The backend aborts startup if
`AUTH0_DOMAIN` or `AUTH0_AUDIENCE` is missing, rather than quietly
serving telemetry unprotected.

## External services

- **Tiger Data** (managed TimescaleDB) — time-series storage. `filesystem_metrics` is a
  hypertable partitioned on `time`.
- **Auth0** — dashboard login and API token issuance. A registered API
  (`storagewatch-api`) is mandatory: without it Auth0 issues an *opaque* token the
  backend cannot verify.
- **Backboard** — LLM gateway. Routed to **Gemini via BYOK**, because Backboard's own
  free-tier credits do not cover LLM chat.
- **Render** — deployment, as a single Docker service serving both API and dashboard.

## Data model

Three tables, created automatically from `backend/schema.sql`:

- **`filesystem_metrics`** — hypertable on `time`. One row per volume per sample.
- **`alerts`** — `alert_type`, `severity`, `message`, `metric_value`, `resolved`, plus
  an `ai_explanation` column that is no longer written (the AI is chat-only).
- **`system_info`** — single upserted JSONB row: physical disks, APFS containers,
  FileVault state, snapshot count. In the database rather than in memory so a backend
  restart doesn't blank the Disks and APFS pages.

## Anomaly rules

| Condition | Severity |
|---|---|
| `used_percent >= 90` | critical |
| `used_percent >= 80` | warning |
| Write throughput > 4× mean of the previous 20 samples | warning |

The write baseline is an in-process `deque(maxlen=20)` per machine and needs 5 prior
samples before it fires — a freshly started backend stays quiet for ~30 seconds. Being
in-process, it also **resets on restart**. A persisting condition raises at most one
alert per machine, type and severity every 10 minutes.

## Known limits

- The write baseline lives in the backend process and does not survive a restart.
- Only the boot volume and `/Volumes/*` are monitored. macOS-internal container slices
  (VM, Preboot, Update) and containers under 10 GB are deliberately excluded as
  meaningless to an operator.
- SMART status comes from `diskutil`; no `smartctl`, so no detailed attributes.
- Alerts are never auto-resolved — `resolved` exists but nothing sets it.
- The dashboard polls every 5 seconds, only for the open page's data, and pauses in a
  background tab. There is no push/websocket path.
- The AI runs on a Gemini free-tier key: 20 requests per model per day. Enable billing on
  the key's Google project before relying on it.
- Render's free tier sleeps after ~15 minutes idle; a running collector keeps it awake.

## Provenance

Built as a two-person project: **Shruti** on the backend, database, anomaly detection
and AI wiring; **Om** on the collector and the React frontend. It was organised in
phases 0–3, whose task documents have been folded into these files now that the work is
done. Git history is the authoritative record — commit messages carry the reasoning and
are worth reading directly.
