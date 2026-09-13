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
       ├─ check_config()           ← aborts if AUTH0_DOMAIN / AUTH0_AUDIENCE missing
       └─ init_db()                ← applies schema.sql (idempotent)
  └─ routes registered in order; static catch-all declared LAST
```

Route order matters: the catch-all `/{full_path:path}` would shadow every API route if
declared earlier.

## 2. Collector cycle

Startup finds its agent token, connecting through the browser the first time:

```
load_or_enroll_token()
  ├─ AGENT_TOKEN in .env?            → use it
  ├─ ~/.storagewatch/agent_token?    → use it
  └─ enroll_via_browser()
       ├─ listen on 127.0.0.1:<random port>, random state
       ├─ open DASHBOARD_URL/connect?port&state&host
       │    └─ browser: Auth0 sign-in → [Connect] → POST /api/agent-tokens
       │               → redirect to 127.0.0.1:<port>/callback?token&state
       ├─ state matches → save token (0600) → 302 back to the dashboard
       └─ state wrong   → 400, keep waiting
```

Then one iteration every 5 seconds, with a slower nested cycle for hardware inventory:

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
  ├─ for each: send_metrics()       → POST /api/metrics  + agent token
  │                                    reply for "/" carries the host's open alerts
  │                                    → macOS notification for each new one
  ├─ if N % 12 == 0  (~60s)
  │    ├─ send_system_info()        → POST /api/system-info: disks, APFS, FileVault
  │    └─ check_disk_health()       → SMART status via diskutil
  ├─ write_status()                 → ~/.storagewatch/status.json (menu bar app)
  └─ sleep 5
```

The first cycle reports `0` throughput — a rate needs two samples to exist.

## 3. Ingestion

```
POST /api/metrics
  ├─ Depends(require_agent)         → token hash → owner_sub, else 401
  ├─ Metrics (Pydantic)             → 422 on shape mismatch
  ├─ insert_metrics()               → INSERT into filesystem_metrics
  ├─ detect_anomalies()
  │    ├─ check_capacity_alert()    → >=90 critical, >=80 warning
  │    └─ check_io_anomaly()        → per-machine deque(maxlen=20); needs >=5 prior
  │                                    samples; fires if > 4× their mean
  └─ for each anomaly
       ├─ has_recent_alert()        → skip if same type+severity in last 10 min
       └─ insert_alert()            → no LLM call; the AI answers only when asked (section 5)
```

## 4. Dashboard load and poll

```
browser → /
  └─ Auth0Provider
       ├─ not authenticated → redirect to Auth0 → callback → tokens
       └─ authenticated
            ├─ useEffect: fetchPage(), then every 5 s (every 2 s until the
            │             first sample exists); re-run on page or host change
            └─ useEffect: fetchHosts() at sign-in and when Settings opens

fetchPage()
  ├─ document.hidden?                  → skip; background tabs don't poll
  ├─ getAccessTokenSilently()          → Authorization: Bearer <JWT>
  └─ GET /api/dashboard?hostname       → Depends(require_user), then ONE SQL
                                          statement returning JSON: current sample,
                                          last 100 samples (oldest first), every
                                          unresolved alert, volumes seen in the last
                                          hour, disk/APFS snapshot (null until the
                                          collector's first 60 s cycle)
```

Each `require_user` call verifies the JWT against the tenant's JWKS, checking signature,
audience and issuer. An **opaque** token — what Auth0 returns when no registered audience
is requested — fails here, which surfaces as a logged-in dashboard with empty cards and
401s in the network tab.

Pages: `/` the single-page dashboard (PRD §21) with every section, `/settings`, and
`/connect` (the collector's sign-in).

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
  ├─ /install.sh, /collector.py → the collector installer, unauthenticated
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
