from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
import json
import os
import requests
import time
from pathlib import Path
from models import Metrics, MetricsResponse, Alert
from database import (init_db, insert_metrics, get_latest_metrics, get_metrics_history,
                      insert_alert, has_recent_alert, get_recent_alerts, resolve_alerts,
                      get_all_volumes_latest, save_system_info, get_system_info,
                      get_hosts, create_agent_token, list_agent_tokens, get_dashboard,
                      get_agent_state, set_menu_bar_enabled, set_menu_bar_applied,
                      insert_user_usage, get_user_usage_latest, get_user_usage_history,
                      missing_tables)
from alerts import detect_anomalies, detect_user_anomalies
from auth import require_user, require_agent, check_config

# Handlers are plain `def`, not `async def`: they make blocking database and
# LLM calls, and FastAPI runs a sync handler in a worker thread. Inside
# `async def` those calls ran on the event loop, so every request queued
# behind whichever one was waiting on the database.
app = FastAPI()

# Vite fingerprints its bundles, so /assets/index-<hash>.js never changes
# meaning and can be cached forever. index.html is the opposite: it names which
# bundles are current, so a cached copy keeps loading an old app after every
# deploy. Neither carried a Cache-Control header, which left browsers guessing
# a freshness window from Last-Modified — and guessing wrong, holding a stale
# shell that pointed at bundles the server had already replaced.
@app.middleware("http")
async def cache_control(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif response.headers.get("content-type", "").startswith("text/html"):
        # Not "no-store": the browser may keep it, but must revalidate first,
        # so an unchanged shell still costs only a 304.
        response.headers["Cache-Control"] = "no-cache"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://storagewatch.tech"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    """Initialize database on startup."""
    check_config()
    try:
        init_db()
    except Exception as e:
        print(f"Warning: Database initialization failed: {e}")

# Checked once and then remembered: the host polls /health constantly, and a
# query per poll is load the free instance cannot spare. Tables do not vanish
# once created, so one confirmation per process is enough.
_schema_verified = False

@app.get("/health")
def health_check():
    """Liveness, and whether this build's schema actually applied.

    The host routes traffic by this check, so reporting unhealthy when a
    migration has not landed means a deployment that cannot serve requests is
    not promoted over the one currently serving them. Reporting "ok" while
    /api/dashboard returns 500 to every user would be the worse failure.
    """
    global _schema_verified
    if _schema_verified:
        return {"status": "ok"}

    try:
        missing = missing_tables()
        if missing:
            # A migration can fail on a transient error during startup, so try
            # once more here rather than staying broken until a redeploy.
            init_db()
            missing = missing_tables()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"database unavailable: {e}")

    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"schema incomplete, missing: {', '.join(missing)}")

    _schema_verified = True
    return {"status": "ok"}

@app.post("/api/metrics")
def post_metrics(metrics: Metrics, owner_sub: str = Depends(require_agent)):
    """Receive telemetry from monitoring agent."""
    try:
        insert_metrics(owner_sub, metrics)

        # Detect anomalies. The AI answers only when asked in the chat, so
        # ingestion never waits on, or pays for, an LLM call.
        anomalies = detect_anomalies(metrics, owner_sub)

        for anomaly in anomalies:
            if has_recent_alert(owner_sub, metrics.hostname, anomaly["type"], anomaly["severity"]):
                continue
            insert_alert(
                owner_sub=owner_sub,
                hostname=metrics.hostname,
                alert_type=anomaly["type"],
                severity=anomaly["severity"],
                message=anomaly["message"],
                metric_value=metrics.used_percent if anomaly["type"] == "HIGH_CAPACITY" else metrics.write_bytes_per_sec,
            )

        # The collector reports this only when it changes, so the write happens
        # about once per collector start rather than every five seconds.
        if metrics.menu_bar_installed is not None:
            set_menu_bar_applied(owner_sub, metrics.hostname, metrics.menu_bar_installed)

        reply = {"status": "ok", "alerts": len(anomalies)}
        if metrics.filesystem == "/":
            # The reply is the only channel back to the Mac: a browser cannot
            # reach it. It carries the alerts the menu bar app and macOS
            # notifications show without anyone signing in, plus the settings
            # the administrator changed in the dashboard for that machine.
            reply.update(json.loads(get_agent_state(owner_sub, metrics.hostname)))
        return reply
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/metrics/current")
def get_current_metrics(filesystem: str = "/", hostname: str | None = None,
                              user: dict = Depends(require_user)):
    """Most recent sample for a volume on one of the caller's machines."""
    try:
        result = get_latest_metrics(user["sub"], filesystem, hostname)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="No metrics found")
    return dict(result)

@app.get("/api/metrics/history")
def get_metrics_history_endpoint(limit: int = 100, filesystem: str = "/",
                                       hostname: str | None = None,
                                       user: dict = Depends(require_user)):
    """Historical samples for a volume on one of the caller's machines."""
    try:
        results = get_metrics_history(user["sub"], limit, filesystem, hostname)
        return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/volumes")
def get_volumes(hostname: str | None = None,
                      user: dict = Depends(require_user)):
    """Latest sample per volume on one of the caller's machines."""
    try:
        results = get_all_volumes_latest(user["sub"], hostname)
        return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/alerts")
def get_alerts(hostname: str | None = None,
                     user: dict = Depends(require_user)):
    """Every unresolved alert for the caller's machines, newest first. Unbounded:
    alerts are deduplicated at ingest, so the list stays short."""
    try:
        results = get_recent_alerts(user["sub"], limit=None, hostname=hostname)
        return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/system-info")
def post_system_info(data: dict, owner_sub: str = Depends(require_agent)):
    """Receive disk/APFS system info from the collector (runs on the Mac, not here)."""
    try:
        save_system_info(owner_sub, data.get("hostname", "unknown"), data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok"}

@app.get("/api/system-info")
def get_system_info_endpoint(hostname: str | None = None,
                                   user: dict = Depends(require_user)):
    """Disk/APFS inventory for one of the caller's machines."""
    try:
        info = get_system_info(user["sub"], hostname)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not info:
        raise HTTPException(status_code=404, detail="No system info received yet")
    return info

@app.post("/api/user-usage")
def post_user_usage(data: dict, owner_sub: str = Depends(require_agent)):
    """Receive one sizing pass: who holds how much, and under what quota.

    Home directories take minutes to walk, so this arrives on the collector's
    own slow schedule rather than with the five-second telemetry.
    """
    hostname = data.get("hostname", "unknown")
    users = data.get("users") or []
    # Null while the first background pass is still running, which is not the
    # same as a pass that measured nothing.
    measured_at = data.get("measured_at")
    if not measured_at:
        return {"status": "ok", "stored": 0, "detail": "no completed measurement yet"}

    try:
        stored = insert_user_usage(owner_sub, hostname, users, measured_at)
        # Re-read rather than trusting the payload: growth is the difference
        # from the previous stored pass, which only the database knows.
        latest = [dict(r) for r in get_user_usage_latest(owner_sub, hostname)]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    for u in latest:
        u["elapsed_hours"] = ((u["time"] - u["previous_time"]).total_seconds() / 3600
                              if u.get("previous_time") else 0)

    volume_used = sum(u["used_bytes"] or 0 for u in latest)
    raised = 0
    for user, anomaly in detect_user_anomalies(latest, volume_used):
        if has_recent_alert(owner_sub, hostname, anomaly["type"], anomaly["severity"]):
            continue
        insert_alert(owner_sub=owner_sub, hostname=hostname,
                     alert_type=anomaly["type"], severity=anomaly["severity"],
                     message=anomaly["message"], metric_value=user.get("used_bytes"))
        raised += 1
    return {"status": "ok", "stored": stored, "alerts": raised}

@app.get("/api/users")
def get_users_endpoint(hostname: str | None = None, user: dict = Depends(require_user)):
    """Each account's latest measured usage, quota and growth."""
    try:
        rows = [dict(r) for r in get_user_usage_latest(user["sub"], hostname)]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    for r in rows:
        r["time"] = r["time"].isoformat() if r.get("time") else None
        r["previous_time"] = r["previous_time"].isoformat() if r.get("previous_time") else None
    return rows

@app.get("/api/users/{username}/history")
def get_user_history_endpoint(username: str, hostname: str | None = None,
                              limit: int = 100, user: dict = Depends(require_user)):
    """One account's usage over time, oldest first."""
    try:
        rows = get_user_usage_history(user["sub"], username, hostname, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return [{"time": r["time"].isoformat(), "used_bytes": r["used_bytes"]} for r in rows]

@app.get("/api/dashboard")
def get_dashboard_endpoint(hostname: str | None = None,
                           user: dict = Depends(require_user)):
    """Everything the dashboard shows, in one response from one query.

    On the free instance's tenth of a CPU, five requests per poll queued behind
    each other (~950 ms each when ten arrived together). One request, with the
    JSON built by Postgres rather than Python, avoids that.
    """
    try:
        doc = get_dashboard(user["sub"], hostname)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return Response(content=doc, media_type="application/json")

@app.get("/api/hosts")
def get_hosts_endpoint(user: dict = Depends(require_user)):
    """Machines reporting for the signed-in user, most recently seen first."""
    try:
        return [
            {"hostname": h["hostname"], "last_seen": h["last_seen"].isoformat()}
            for h in get_hosts(user["sub"])
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/preferences")
def set_preferences(data: dict, user: dict = Depends(require_user)):
    """Change a setting the collector on one of the caller's machines applies.

    Saving is not doing: this only records the choice. The collector on that
    Mac picks it up with its next report, which is why the dashboard shows the
    change as pending until that machine confirms it.
    """
    hostname = (data or {}).get("hostname")
    enabled = (data or {}).get("menu_bar_enabled")
    if not hostname or not isinstance(enabled, bool):
        raise HTTPException(status_code=400,
                            detail="hostname and a boolean menu_bar_enabled are required")
    try:
        set_menu_bar_enabled(user["sub"], hostname, enabled)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok", "hostname": hostname, "menu_bar_enabled": enabled}

@app.get("/api/agent-tokens")
def list_agent_tokens_endpoint(user: dict = Depends(require_user)):
    """Metadata for the caller's agent tokens. Never returns the tokens."""
    try:
        return [
            {
                "label": t["label"],
                "created_at": t["created_at"].isoformat(),
                "last_used_at": t["last_used_at"].isoformat() if t["last_used_at"] else None,
            }
            for t in list_agent_tokens(user["sub"])
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/agent-tokens")
def create_agent_token_endpoint(data: dict = None,
                                      user: dict = Depends(require_user)):
    """Mint an agent token for the caller's collector.

    The plaintext is returned exactly once — only its hash is stored, so a
    lost token is replaced rather than recovered.
    """
    label = (data or {}).get("label") or "collector"
    try:
        token = create_agent_token(user["sub"], label)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"token": token, "label": label}

@app.post("/api/alerts/resolve")
def resolve_alerts_endpoint(data: dict, user: dict = Depends(require_user)):
    """Mark alerts resolved when an administrator clears them on the dashboard.
    Nothing resolves an alert on its own, so this is the only way one closes."""
    ids = data.get("ids")
    if (not isinstance(ids, list) or not ids or len(ids) > 1000
            or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids)):
        raise HTTPException(status_code=400, detail="ids must be a list of 1 to 1000 alert ids")
    try:
        resolved = resolve_alerts(user["sub"], ids)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"resolved": resolved}

@app.post("/api/alerts/report")
def report_alert(data: dict, owner_sub: str = Depends(require_agent)):
    """Receive an ad-hoc alert from the collector (e.g. disk health, volume disappeared)
    that isn't tied to a specific metrics sample."""
    hostname = data.get("hostname", "Unknown")
    alert_type = data.get("alert_type", "UNKNOWN")
    severity = data.get("severity", "warning")
    message = data.get("message", "")

    try:
        insert_alert(
            owner_sub=owner_sub, hostname=hostname, alert_type=alert_type,
            severity=severity, message=message, metric_value=None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "ok"}

# Backboard defaults to gpt-4o, which bills Backboard's own credits (reserved
# for Memory & RAG on the free tier). Routing to Google uses our BYOK Gemini
# key instead.
#
# Tried in order: an individual Gemini model can be congested (503 "high
# demand") or retired by Google (404 NOT_FOUND) while its siblings answer
# fine, so pinning exactly one model makes the assistant fail for reasons
# that have nothing to do with this app. The free tier's quota is also per
# model, so a longer list is more requests per day. Flash-lite models come
# first: they answered in ~2 s where the larger "thinking" models take several,
# and a dashboard chat needs the quick answer. Refresh the list from
# GET https://app.backboard.io/api/models?provider=google — it still lists
# gemini-2.5-* models that now return NOT_FOUND.
LLM_PROVIDER = "google"
LLM_MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite",
              "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.8-flash"]


# Gemini regularly returns 503 "high demand" for a single call and then succeeds
# moments later, so a one-shot request fails intermittently for no real reason.
TRANSIENT_MARKERS = ("503", "UNAVAILABLE", "high demand", "overloaded", "try again")

# A 429 is a quota, not congestion: the free tier allows 20 requests per model
# per day. Retrying that model is pointless, but its siblings have their own
# quotas, so it is skipped and they answer instead — without every request
# first walking through the exhausted models. A daily quota or a retired model
# is skipped for hours, a per-minute quota for a minute.
QUOTA_MARKERS = ("429", "RESOURCE_EXHAUSTED", "quota")
_quota_blocked_until: dict[str, float] = {}


def _is_transient(reason: str) -> bool:
    return any(m.lower() in reason.lower() for m in TRANSIENT_MARKERS)


def _is_quota(reason: str) -> bool:
    return any(m.lower() in reason.lower() for m in QUOTA_MARKERS)


def call_backboard(content: str, thread_id: str | None, mock_reply: str,
                   system_prompt: str | None = None,
                   attempts: int = 2) -> tuple[str, str | None]:
    """Send a message to Backboard, reusing thread_id for conversation continuity.

    Retries transient upstream failures. Returns (reply_text, thread_id); on
    permanent failure the reply states the actual reason rather than pretending
    a canned response is the answer.
    """
    backboard_key = os.getenv("BACKBOARD_API_KEY", "mock-key")
    if backboard_key == "mock-key":
        return mock_reply, thread_id or "mock-thread"

    payload = {
        "content": content,
        "stream": False,
        "llm_provider": LLM_PROVIDER,
    }
    if system_prompt:
        payload["system_prompt"] = system_prompt
    if thread_id and thread_id != "mock-thread":
        payload["thread_id"] = thread_id

    reason = "unknown error"
    for attempt in range(attempts):
        for model in LLM_MODELS:
            if _quota_blocked_until.get(model, 0) > time.time():
                continue
            try:
                response = requests.post(
                    "https://app.backboard.io/api/threads/messages",
                    headers={"X-API-Key": backboard_key},
                    json={**payload, "model_name": model},
                    timeout=45
                )
            except Exception as e:
                reason = f"request failed: {e}"
            else:
                if response.status_code == 200:
                    result = response.json()
                    if result.get("status") == "COMPLETED":
                        return (result.get("content") or mock_reply,
                                result.get("thread_id", thread_id))
                    # A 200 with a non-COMPLETED status carries the real reason
                    # (billing, retired model, provider error) in `content`.
                    reason = result.get("content") or f"status={result.get('status')}"
                else:
                    reason = f"HTTP {response.status_code}: {response.text[:200]}"

            print(f"[backboard] {model} failed: {reason[:300]}")
            if _is_quota(reason) or "NOT_FOUND" in reason:
                lasting = "PerDay" in reason or "NOT_FOUND" in reason
                _quota_blocked_until[model] = time.time() + (6 * 3600 if lasting else 60)
                continue
            # A non-transient failure (e.g. billing) will hit every model
            # identically, so stop rather than hammering the whole list.
            if not _is_transient(reason) and "NOT_FOUND" not in reason:
                return f"AI unavailable: {reason}", thread_id

        if all(_quota_blocked_until.get(m, 0) > time.time() for m in LLM_MODELS):
            return ("AI unavailable: the Gemini key has used its free-tier quota on every "
                    "model (20 requests per model per day). It resets daily; enabling "
                    "billing on the key's Google project lifts the limit."), thread_id
        if attempt < attempts - 1:
            time.sleep(2)

    return ("Every Gemini model is momentarily unavailable upstream (the provider "
            "reported high demand). Please send that again."), thread_id


def build_live_context(owner_sub: str, hostname: str | None = None) -> str:
    """Snapshot the machine's current telemetry as grounding for the assistant.

    Without this the model has no idea which machine it's attached to, and a
    question like "storage?" gets answered as a general encyclopedia query
    instead of being about the administrator's actual disk.
    """
    lines = [
        "You are StorageWatch AI, a macOS storage-monitoring assistant embedded in an "
        "observability dashboard. Answer the administrator's questions about THIS machine "
        "using the live telemetry below. Cite the actual numbers. Be concise — a few "
        "sentences unless asked for more. If the telemetry doesn't cover something, say so "
        "rather than guessing.",
        "",
        "The administrator is reading this dashboard, which already shows everything "
        "below — device identifiers, mount points, roles, seal state, encryption, "
        "FileVault, snapshots, SMART status and capacity. Answer from it directly. Do NOT "
        "tell them to run a command to look up something that appears below; that is the "
        "question they just asked you, and the dashboard exists so they don't have to. "
        "Name the section of the page where it is shown instead. Suggest a command only "
        "for something the telemetry genuinely does not carry, or to carry out a change.",
        "",
        "=== LIVE TELEMETRY ===",
    ]

    try:
        volumes = get_all_volumes_latest(owner_sub, hostname)
        if volumes:
            lines.append(f"Host: {volumes[0]['hostname']}")
            lines.append(f"Monitored volumes ({len(volumes)}):")
            for v in volumes:
                lines.append(
                    f"  - {v['filesystem']} ({v['filesystem_type']}): "
                    f"{v['used_bytes']/1e9:.1f} GB used of {v['total_bytes']/1e9:.1f} GB "
                    f"({v['used_percent']:.1f}%), {v['free_bytes']/1e9:.1f} GB free"
                )
            latest = volumes[0]
            lines.append(
                f"Current disk throughput: {latest['read_bytes_per_sec']/1e6:.1f} MB/s read, "
                f"{latest['write_bytes_per_sec']/1e6:.1f} MB/s write "
                f"(measured at the physical disk; macOS exposes no per-volume I/O)"
            )
    except Exception as e:
        lines.append(f"(volume telemetry unavailable: {e})")

    try:
        si = get_system_info(owner_sub, hostname)
    except Exception:
        si = None
    if si:
        for d in si.get("physical_disks", []):
            lines.append(
                f"Physical disk {d['device_identifier']}: {d['model']}, "
                f"{d['size_bytes']/1e9:.0f} GB, {'SSD' if d['solid_state'] else 'HDD'}, "
                f"{d['protocol']}, {'internal' if d['internal'] else 'external'}, "
                f"SMART status: {d['smart_status']}"
            )
        for c in si.get("apfs_containers", []):
            used = c["capacity_ceiling"] - c["capacity_free"]
            lines.append(
                f"APFS container {c['container_reference']} (backed by {c['physical_store']}, "
                f"UUID {c.get('uuid') or 'unknown'}): "
                f"{used/1e9:.1f} GB used of {c['capacity_ceiling']/1e9:.1f} GB, "
                f"{c['capacity_free']/1e9:.1f} GB not allocated"
            )
            for v in c.get("volumes", []):
                # Mount point and seal state are the questions that used to send
                # people to `diskutil apfs list`, so they belong in the context.
                if v.get("mount_point"):
                    where = f"mounted at {v['mount_point']}"
                elif v.get("snapshot"):
                    where = (f"mounted at {v['snapshot']['mount_point']} via snapshot "
                             f"{v['snapshot']['device_identifier']}")
                else:
                    where = "not mounted"
                lines.append(
                    f"  - volume {v['name']} on device "
                    f"{v.get('device_identifier') or 'unknown'} "
                    f"[{', '.join(v['roles']) or 'no role'}], {where}: "
                    f"{v['capacity_in_use']/1e9:.1f} GB"
                    f"{', sealed' if v.get('sealed') else ''}"
                    f"{', read-only' if v.get('mount_point') and not v.get('writable', True) else ''}"
                    f"{', encrypted' if v['encrypted'] else ''}"
                    f"{', FileVault' if v['filevault'] else ''}"
                )
        lines.append(
            f"FileVault: {'on' if si.get('filevault_enabled') else 'off'}; "
            f"local Time Machine snapshots: {si.get('snapshot_count', 0)}"
        )

    try:
        alerts = get_recent_alerts(owner_sub, limit=5, hostname=hostname)
        if alerts:
            lines.append(f"Active alerts ({len(alerts)}):")
            for a in alerts:
                lines.append(f"  - [{a['severity']}] {a['alert_type']}: {a['message']}")
        else:
            lines.append("Active alerts: none")
    except Exception:
        pass

    return "\n".join(lines)


@app.post("/api/ai/chat")
def ai_chat(data: dict, user: dict = Depends(require_user)):
    """Conversational follow-up chat with the AI, using Backboard thread continuity."""
    message = data.get("message", "")
    thread_id = data.get("thread_id")
    if not message:
        raise HTTPException(status_code=400, detail="No message provided")

    mock_reply = (
        "This is a mock response — connect a BACKBOARD_API_KEY with LLM chat credits "
        "for real conversational answers."
    )

    # Rebuilt per turn so the assistant always sees current numbers, not the
    # state from whenever the conversation started.
    reply, new_thread_id = call_backboard(
        message, thread_id, mock_reply,
        system_prompt=build_live_context(user["sub"])
    )
    return {"message": reply, "thread_id": new_thread_id}

# The collector has to run on the Mac it measures, so the backend hands out a
# one-line installer: curl -fsSL https://storagewatch.tech/install.sh | sh
COLLECTOR_DIR = Path(__file__).resolve().parent.parent / "collector"

@app.get("/install.sh")
def install_script():
    return FileResponse(COLLECTOR_DIR / "install.sh", media_type="text/plain")

@app.get("/collector.py")
def collector_script():
    return FileResponse(COLLECTOR_DIR / "collector.py", media_type="text/plain")

@app.get("/StorageWatch.zip")
def menu_bar_app():
    """The menu bar app the installer puts in ~/Applications (built by menubar/build.sh)."""
    return FileResponse(COLLECTOR_DIR.parent / "menubar" / "StorageWatch.zip",
                        media_type="application/zip")

# Serve the built dashboard from this same app, so the browser talks to one
# origin and /api calls need no CORS or proxy. Vite's dev proxy only exists
# under `npm run dev`, so a production build has to be served this way.
# Declared last: FastAPI matches routes in order, and the catch-all below
# would otherwise shadow every API route.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_dashboard(full_path: str):
        """Hand every non-API path to the SPA so client-side routes work on reload."""
        # Without this an unknown /api/... path would render the dashboard HTML
        # instead of returning a 404, which is confusing to debug against.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        requested = FRONTEND_DIST / full_path
        if full_path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    print(f"No frontend build at {FRONTEND_DIST} — run `npm run build` in frontend/ "
          f"to serve the dashboard from this app.")

if __name__ == "__main__":
    import uvicorn
    # No access log: every dashboard poll and collector report would write a
    # line, which is CPU the free instance doesn't have to spare.
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), access_log=False)
