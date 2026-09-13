# Decisions

Why the code is the way it is. Each entry records what was chosen, what it was chosen
over, and what went wrong with the alternative — most of these were arrived at by
getting it wrong first.

Background concepts are in [Memory.md](Memory.md). Git history is the primary source;
these are the decisions worth not rediscovering.

---

## Measurement

### Capacity comes from the APFS container, not from `psutil.disk_usage("/")`

`/` is a sealed read-only system snapshot of ~12 GB, so psutil described the snapshot
rather than the disk: 2.6% used on a disk that was 52.1% full, with three headline
numbers that contradicted each other (12.6 GB used + 237.0 GB free ≠ 494.4 GB total).

Every volume in an APFS container shares one free-space pool and user data lives on a
sibling `Data` volume, so **no single volume's figures describe the disk**. Capacity now
reads `APFSContainerSize` / `APFSContainerFree` from `diskutil` — the actual constraint,
and what macOS itself reports. Non-APFS volumes keep psutil's numbers, correct for
filesystems without a shared pool.

### `used_percent` is `used/total`, not psutil's `percent`

psutil computes `used/(used+free)`, which on APFS diverges from `used/total` because
total includes space shared with sibling volumes. The displayed percentage no longer
matches the displayed GB figures. Computing it directly keeps the card internally
consistent — a number that visibly disagrees with the two numbers beside it destroys
trust in the whole dashboard.

### Capacity is reported per storage pool, not summed across volumes

Summing every volume counts a shared container's capacity once per volume. The Volumes
page groups by pool and shows the container reference alongside each volume's own
consumption, so shared-capacity figures explain themselves.

### Throughput is disk-level and duplicated across volumes

macOS exposes no per-volume I/O counters. Rather than invent per-volume numbers, the
same physical-disk reading is attached to every volume in a sample. Documented rather
than disguised.

### macOS-internal volumes and containers are excluded

Container slices (VM, Preboot, Update) and containers under 10 GB are filtered out.
They are implementation detail, not something an operator can act on, and they bury the
volumes that matter. The 10 GB threshold cleanly separates internal containers (<6 GB)
from any real user-facing one.

---

## Authentication

### Two credential types, disjoint rather than hierarchical

Before this, Auth0 protected only the frontend route — hitting `:8000` directly returned
every metric, alert and disk detail with no sign-in. Tolerable on localhost, not on a
public domain.

The two callers cannot authenticate the same way: the dashboard has a signed-in human,
the collector runs unattended. So the dashboard sends an Auth0 access token verified
against the tenant's JWKS, and the collector presents a per-user agent token obtained
through a one-time browser sign-in and stored only as a hash. Critically the
roles are **disjoint** — the agent token is refused on dashboard reads and a user token
is refused on ingest. A compromised agent secret cannot read history.

### The collector connects itself through the browser

Copying a token from a Settings page into `.env` was the step people disliked most. A
web page cannot start a program on the Mac, so the collector is still started by hand —
but on first run it opens the dashboard's `/connect` page, the administrator signs in and
clicks Connect, and the page redirects the minted token to a one-shot listener on
`127.0.0.1`. The same pattern CLIs such as `gh` and `vercel` use. The redirect only ever
targets the loopback address on a numeric port, and a random `state` stops any other page
from planting a token. No backend change was needed: the page calls the existing
`POST /api/agent-tokens`.

### Missing secrets abort startup

Absent `AUTH0_DOMAIN` or `AUTH0_AUDIENCE`, the process exits. Failing
open here means silently serving unprotected telemetry, and nobody notices until it
matters.

### The Auth0 audience is always requested

The audience was briefly dropped to get login working, then restored. Requesting an
audience is precisely what makes Auth0 issue a **verifiable JWT** instead of an opaque
token — verification cannot work without it. The real prerequisite was registering the
API in the tenant, which the README now covers. *Removing the audience treated the
symptom and disabled the feature it was blocking.*

### Auth0 per-app authorization must be granted explicitly

Registering `storagewatch-api` is not sufficient on tenants set to per-app
authorization. The SPA needs **User-delegated Access** enabled under the API's
Application Access tab, or `/authorize` refuses outright with *"Client is not authorized
to access resource server"*. This cost about an hour; it is now README step 3.

Only the dashboard app is granted, and only User-delegated. Client Access is for
`client_credentials`, which this app never uses.

### No `cacheLocation="localstorage"`

Reverted to the SDK's in-memory default so access tokens are not readable by any
injected script.

### `React.StrictMode` removed

StrictMode double-invokes effects in development, which made Auth0 exchange its
authorization code twice — the second exchange failed with "invalid state" and login
landed on a blank screen.

---

## AI

### Backboard, routed to Gemini via BYOK

Backboard defaults to `gpt-4o`, billed against Backboard's own credits, which on the
free tier are reserved for Memory & RAG — so every call failed regardless of the key.
Requests now pass `llm_provider`/`model_name` to route through the user's Gemini key.

### The endpoint is Backboard's, not Anthropic's

An earlier implementation sent the Backboard API key to `api.anthropic.com`, which
rejected it — wrong host, wrong auth scheme, wrong provider. It surfaced as a bare
"API error: 401". Corrected to `app.backboard.io/api/threads/messages` with an
`X-API-Key` header.

*This shipped because it was written and committed without ever being run.* The cost of
one `curl` would have been seconds.

### A fallback list of models, never a pinned one

A pinned model is a single point of failure: `gemini-3.8-flash` returned 503 for every
request while 3.7, 3.6 and 3.5 answered normally, and `gemini-2.5-flash` had been
retired outright (404). Requests now walk a list.

### Transient failures are retried; permanent ones stop immediately

Gemini intermittently returns 503 "high demand" and answers fine moments later, which
made the assistant look randomly broken. Those are retried. A non-transient failure —
billing, say — will hit every model identically, so the loop stops rather than hammering
the list.

### Failures state the upstream reason

Errors used to be reported as "connect a BACKBOARD_API_KEY with LLM chat credits", which
is actively misleading when a key *is* present, and sends you off debugging keys and
billing while the real fault is elsewhere. A wrong error message is worse than none.

### The system prompt is rebuilt from live telemetry every turn

Without grounding, asking the assistant about "storage" produced a generic encyclopedia
answer about SSDs and Google Drive rather than anything about the administrator's Mac.
Each turn now assembles volumes, capacity, throughput, disks, APFS roles, encryption,
FileVault, snapshots and active alerts from the database. Rebuilt **per turn** rather
than per conversation, so a long chat cannot drift onto stale figures.

### Alerts are explained on demand, not automatically

Every alert used to trigger a background LLM call, so a burst of alerts meant a burst of
spend nobody necessarily read. The dashboard's **Explain with AI** button now calls
`POST /api/ai/explain` for the selected alert, as the PRD specifies, and the answer is
stored on the alert. The AI handlers are plain `def` so FastAPI runs them in a worker
thread: the LLM call blocks for seconds and would otherwise stall ingestion on the event
loop.

### Pages fetch only what they display

The dashboard used to poll six endpoints every five seconds on every page, including two
that scan the whole metrics history. Each page now requests only its own data, the
machine list loads at sign-in and on Settings, `/api/volumes` scans only the last hour,
and polling pauses while the tab is in the background.

---

## Storage and state

### `system_info` lives in the database, not a module-level dict

Held in memory, a backend restart blanked the Disks and APFS pages — and the AI's
hardware context — until the collector's next 60-second cycle. Now upserted into a
table.

### Disk and APFS inventory refreshes every 60s, metrics every 5s

Hardware topology changes rarely and each refresh costs several `diskutil` subprocess
calls. Sampling it at the metrics rate would be twelve times the subprocess overhead for
identical data.

---

## Platform and packaging

### Python 3.10+ is required, rather than staying 3.9-compatible

The backend uses `X | Y` annotations, which are a runtime `TypeError` before 3.10 —
stock macOS ships 3.9.6, so the backend refused to start. Briefly rewritten to
`typing.Optional`, then reverted: the README now states 3.10+ instead. Stating the
requirement is cheaper than contorting the code around the oldest interpreter that
happens to be preinstalled.

### The backend serves the built dashboard

Vite's `/api` proxy exists only under `npm run dev`, so a production build had nothing
to talk to — it would call `/api` on whatever static host served it and 404. The backend
now serves `frontend/dist`: one service, one domain, one certificate, no CORS.

Two details this depends on:
- The catch-all is declared **after** every API route, since FastAPI matches in order
  and it would otherwise shadow them all.
- It returns `index.html` for unmatched paths so client-side routes survive a reload,
  but refuses anything under `/api/` so an unknown endpoint returns a JSON 404 instead
  of silently rendering the dashboard.

### Requirements split by component

`backend/requirements.txt` deliberately excludes `psutil` — that belongs to the
collector, and the deployed container runs only the backend. Including it also breaks
the image build: psutil has no prebuilt wheel for every platform and the slim Python
image has no compiler. The root file `-r`-includes both, so local install is unchanged.

### `frontend/.env.production` is committed

It holds only the Auth0 domain, client ID and audience. Vite inlines `VITE_*` at build
time and an SPA ships these to the browser regardless — they appear in any network
trace. The **client secret is not among them and must never be.**

### The collector's `BACKEND_URL` is configurable

It was hardcoded to localhost while `.env` advertised a `BACKEND_URL` that nothing read,
so pointing the agent at a remote backend silently did nothing. It now loads from the
project-root `.env`, addressed explicitly since the collector runs from its own
directory.

---

## Corrections worth remembering

### `load_dotenv()` must run before importing modules that read env at import time

`database.py` read `TIGER_DATABASE_URL` at module level, and `load_dotenv()` ran *after*
the import — so it read `None`. Fixed on both sides: `load_dotenv()` moved to the top of
`main.py`, and `database.py` now reads the variable lazily inside `get_connection()`.

### FastAPI errors must `raise HTTPException`, not return a tuple

Flask-style `(body, status_code)` returns serialize as a **JSON array with HTTP 200**.
Error responses therefore looked like valid data to axios, and the frontend crashed
calling `.toFixed()` on an array.

### Dead configuration is removed, not left as documentation

`REACT_APP_AUTH0_*` (Create-React-App naming from the scaffold, inert under Vite) and an
unused `ELEVENLABS_API_KEY` were deleted along with the `/api/tts` endpoint nothing
called. Env vars that nothing reads are worse than absent — they imply a wiring that
does not exist and send people debugging the wrong thing.

### Charts must reverse the API's history

`/api/metrics/history` returns newest-first. Plotted unreversed, the x-axis ran backwards
in time. The frontend reverses for display, and Performance takes its "current" value
from the end of the series accordingly.

### The write baseline excludes the sample being judged

Averaging the current sample into its own baseline dampens the spike being measured: on
a five-sample window a 7× burst read as 3.2× and never fired. The baseline is now the
previous samples only, kept per machine so one agent's writes can't set another's.

### A persisting condition alerts once, not every sample

A disk at 85% is at 85% on every 5-second sample, and each alert costs a row and an LLM
call. An alert is skipped when the same machine raised the same type and severity in the
last 10 minutes; a severity change (warning → critical) still fires.
