# Flow

How StorageWatch executes at runtime — the paths a request or a sample actually takes.
Concepts are in [Memory.md](Memory.md), rationale in [Decisions.md](Decisions.md).

## System overview

```
  monitored Mac                    backend host                    browser
┌────────────────┐          ┌────────────────────────┐         ┌──────────────┐
│  collector.py  │  POST    │       FastAPI          │  GET    │    React     │
│   every 5s ────┼─────────▶│  require_agent         │◀────────┼─ every 5s    │
│                │  +token  │  require_user          │  +JWT   │              │
└────────────────┘          └───────────┬────────────┘         └──────┬───────┘
       │ diskutil                       │                             │ login
       │ fdesetup                       ▼                             ▼
       │ tmutil                 ┌───────────────┐              ┌────────────┐
       │ psutil                 │  Tiger Data   │              │   Auth0    │
       ▼                        │ (TimescaleDB) │              └────────────┘
  local volumes                 └───────────────┘
                                        ▲
                                        │ grounding
                                ┌───────┴────────┐
                                │ Backboard →    │
                                │ Gemini (BYOK)  │
                                └────────────────┘
```

## 1. Backend startup

```
main.py
  └─ load_dotenv()                 ← before any import that reads env at import time
  └─ FastAPI app, CORS
  └─ @on_event("startup")
       ├─ check_config()           ← aborts if AUTH0_DOMAIN / AUTH0_AUDIENCE /
       │                             AGENT_TOKEN missing
       └─ init_db()                ← applies schema.sql (idempotent)
  └─ routes registered in order; static catch-all declared LAST
```

Route order matters: the catch-all `/{full_path:path}` would shadow every API route if
declared earlier.

## 2. Collector cycle

One iteration every 5 seconds, with a slower nested cycle for hardware inventory:

```
main() loop, cycle N
  ├─ get_monitored_volumes()        → "/" plus /Volumes/* (internal slices excluded)
  ├─ check_volume_changes()         → mount/unmount detection
  ├─ collect_metrics()              → list, one entry per volume
  │    ├─ psutil.disk_io_counters() → delta vs previous sample ÷ elapsed = B/s
  │    │                              (physical-disk level; same value per volume)
  │    └─ per volume: diskutil info -plist
  │         ├─ APFS?  → container size/free  (the real capacity constraint)
  │         └─ other? → psutil.disk_usage(mountpoint)
  │       used_percent = used / total * 100
  ├─ for each: send_metrics()       → POST /api/metrics  + AGENT_TOKEN
  ├─ if N % 12 == 0  (~60s)
  │    ├─ send_system_info()        → POST /api/system-info: disks, APFS, FileVault
  │    └─ check_disk_health()       → SMART status via diskutil
  └─ sleep 5
```

The first cycle reports `0` throughput — a rate needs two samples to exist.

## 3. Ingestion

```
POST /api/metrics
  ├─ Depends(require_agent)         → 401 unless AGENT_TOKEN matches
  ├─ Metrics (Pydantic)             → 422 on shape mismatch
  ├─ insert_metrics()               → INSERT into filesystem_metrics
  ├─ detect_anomalies()
  │    ├─ check_capacity_alert()    → >=90 critical, >=80 warning
  │    └─ check_io_anomaly()        → append to deque(maxlen=20);
  │                                    needs >=5 samples; fires if > 4× mean
  └─ for each anomaly
       ├─ insert_alert()            → row written immediately, returns alert_id
       └─ background_tasks.add_task(explain_alert_async, ...)
                                    → responds NOW; LLM runs after
```

The background task is what keeps ingestion at 5-second cadence: an LLM round-trip takes
seconds and would otherwise stall the collector's loop.

```
explain_alert_async (background)
  └─ call_backboard(prompt)  →  update_alert_explanation(alert_id, text)
```

## 4. Dashboard load and poll

```
browser → /
  └─ Auth0Provider
       ├─ not authenticated → redirect to Auth0 → callback → tokens
       └─ authenticated
            └─ useEffect: fetchAll(), then setInterval(fetchAll, 5000)

fetchAll()
  ├─ getAccessTokenSilently()          → Authorization: Bearer <JWT>
  ├─ Promise.all, all Depends(require_user):
  │    ├─ /api/metrics/current
  │    ├─ /api/metrics/history?limit=100   → reversed for display (API is newest-first)
  │    ├─ /api/alerts
  │    └─ /api/volumes                     → grouped per storage pool
  └─ then /api/system-info separately, in its own try/catch
                                           → Disks + APFS pages; 404s until the
                                             collector's first 60s cycle lands, so a
                                             failure here must not break the main poll
```

Each `require_user` call verifies the JWT against the tenant's JWKS, checking signature,
audience and issuer. An **opaque** token — what Auth0 returns when no registered audience
is requested — fails here, which surfaces as a logged-in dashboard with empty cards and
401s in the network tab.

Pages: `/` overview, `/volumes`, `/disks`, `/apfs`, `/performance`, `/alerts`.

## 5. AI chat turn

```
POST /api/ai/chat  { message, thread_id? }
  ├─ Depends(require_user)
  ├─ build_live_context()            ← REBUILT EVERY TURN, from the database
  │    ├─ get_all_volumes_latest()   → volumes, capacity, throughput
  │    ├─ get_system_info()          → disks, APFS roles, encryption, FileVault
  │    └─ get_recent_alerts(5)       → active alerts
  └─ call_backboard(message, thread_id, system_prompt=context)
       │
       └─ for attempt in 1..2:
            for model in [gemini-3.7-flash, 3.6-flash, 3.5-flash]:
              POST app.backboard.io/api/threads/messages   (X-API-Key, llm_provider=google)
                ├─ 200 + COMPLETED        → return (reply, thread_id)   ✓
                ├─ transient (503/429/…)  → try next model
                └─ permanent (billing/…)  → return the reason immediately
            sleep 2 between attempts
```

`thread_id` carries conversation continuity across turns; the grounding context is
regenerated each time so answers cannot drift onto stale figures.

## 6. Request routing in production

With `frontend/dist` built, one origin serves everything:

```
request
  ├─ /health                → JSON, unauthenticated
  ├─ /api/*  matched        → API route, authenticated
  ├─ /api/*  unmatched      → JSON 404       (never the dashboard)
  └─ anything else          → index.html     (client-side routes survive reload)
```

## Failure behaviour

| Failure | Result |
|---|---|
| Backend down | Collector logs the error, sleeps 5s, retries — no crash, no backfill |
| A volume unreadable | That volume is skipped; others still report |
| Missing required secret | Backend exits at startup |
| Bad/absent token | 401 before any handler runs |
| Every Gemini model 503 | Chat returns a message naming the upstream reason |
| Backend restart | Write baseline resets (in-process); `system_info` survives (in DB) |
