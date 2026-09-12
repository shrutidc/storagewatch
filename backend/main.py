from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import os
import requests
import time
from typing import Optional, Tuple
from models import Metrics, MetricsResponse, Alert
from database import init_db, insert_metrics, get_latest_metrics, get_metrics_history, insert_alert, update_alert_explanation, get_recent_alerts, get_all_volumes_latest, save_system_info, get_system_info
from alerts import detect_anomalies

app = FastAPI()

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
    try:
        init_db()
    except Exception as e:
        print(f"Warning: Database initialization failed: {e}")

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/api/metrics")
async def post_metrics(metrics: Metrics, background_tasks: BackgroundTasks):
    """Receive telemetry from monitoring agent."""
    try:
        insert_metrics(metrics)

        # Detect anomalies
        anomalies = detect_anomalies(metrics)

        # Store each alert immediately, then generate its AI explanation in the
        # background — an LLM round-trip takes seconds and would otherwise stall
        # the collector's 5-second ingestion loop.
        for anomaly in anomalies:
            alert_id = insert_alert(
                hostname=metrics.hostname,
                alert_type=anomaly["type"],
                severity=anomaly["severity"],
                message=anomaly["message"],
                metric_value=metrics.used_percent if anomaly["type"] == "HIGH_CAPACITY" else metrics.write_bytes_per_sec,
            )
            background_tasks.add_task(explain_alert_async, alert_id, anomaly, metrics)

        return {"status": "ok", "alerts": len(anomalies)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/metrics/current")
async def get_current_metrics(filesystem: str = "/"):
    """Return the most recent metrics for a given volume (default: boot volume)."""
    try:
        result = get_latest_metrics(filesystem)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="No metrics found")
    return dict(result)

@app.get("/api/metrics/history")
async def get_metrics_history_endpoint(limit: int = 100, filesystem: str = "/"):
    """Return historical metrics (last N records) for a given volume."""
    try:
        results = get_metrics_history(limit, filesystem)
        return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/volumes")
async def get_volumes():
    """Return the latest metrics for every monitored volume."""
    try:
        results = get_all_volumes_latest()
        return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/alerts")
async def get_alerts():
    """Return recent alerts."""
    try:
        results = get_recent_alerts(limit=10)
        return [dict(r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/system-info")
async def post_system_info(data: dict):
    """Receive disk/APFS system info from the collector (runs on the Mac, not here)."""
    try:
        save_system_info(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok"}

@app.get("/api/system-info")
async def get_system_info_endpoint():
    """Return the latest disk/APFS system info."""
    try:
        info = get_system_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not info:
        raise HTTPException(status_code=404, detail="No system info received yet")
    return info

@app.post("/api/alerts/report")
async def report_alert(data: dict, background_tasks: BackgroundTasks):
    """Receive an ad-hoc alert from the collector (e.g. disk health, volume disappeared)
    that isn't tied to a specific metrics sample, and generate its AI explanation."""
    hostname = data.get("hostname", "Unknown")
    alert_type = data.get("alert_type", "UNKNOWN")
    severity = data.get("severity", "warning")
    message = data.get("message", "")

    try:
        alert_id = insert_alert(
            hostname=hostname, alert_type=alert_type, severity=severity,
            message=message, metric_value=None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    prompt = f"""You are an infrastructure observability assistant monitoring a macOS filesystem.

Host: {hostname}
Alert just triggered: {alert_type} ({severity}) - {message}

Proactively explain in 2-3 concise sentences: what's happening, the likely cause, and one recommended action."""

    mock_explanation = (
        f"{message}. (Mock analysis — connect a BACKBOARD_API_KEY with LLM chat credits "
        f"for real AI insights.)"
    )

    def explain():
        explanation, _ = call_backboard(prompt, None, mock_explanation)
        try:
            update_alert_explanation(alert_id, explanation)
        except Exception as e:
            print(f"Failed to attach AI explanation to alert {alert_id}: {e}")

    background_tasks.add_task(explain)
    return {"status": "ok"}

# Backboard defaults to gpt-4o, which bills Backboard's own credits (reserved
# for Memory & RAG on the free tier). Routing to Google uses our BYOK Gemini
# key instead.
#
# Tried in order: an individual Gemini model can be congested (503 "high
# demand") or retired by Google (404 NOT_FOUND) while its siblings answer
# fine, so pinning exactly one model makes the assistant fail for reasons
# that have nothing to do with this app. Refresh the list from
# GET https://app.backboard.io/api/models?provider=google
LLM_PROVIDER = "google"
LLM_MODELS = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash"]


# Gemini regularly returns 503 "high demand" for a single call and then succeeds
# moments later, so a one-shot request fails intermittently for no real reason.
TRANSIENT_MARKERS = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED",
                     "high demand", "overloaded", "try again")


def _is_transient(reason: str) -> bool:
    return any(m.lower() in reason.lower() for m in TRANSIENT_MARKERS)


def call_backboard(content: str, thread_id: Optional[str], mock_reply: str,
                   system_prompt: Optional[str] = None,
                   attempts: int = 2) -> Tuple[str, Optional[str]]:
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

            print(f"[backboard] {model} failed: {reason}")
            # A non-transient failure (e.g. billing) will hit every model
            # identically, so stop rather than hammering the whole list.
            if not _is_transient(reason) and "NOT_FOUND" not in reason:
                return f"AI unavailable: {reason}", thread_id

        if attempt < attempts - 1:
            time.sleep(2)

    return ("Every Gemini model is momentarily unavailable upstream (the provider "
            "reported high demand). Please send that again."), thread_id


def explain_alert_async(alert_id: int, anomaly: dict, metrics: Metrics) -> None:
    """Generate a proactive AI explanation for an alert and attach it to the row."""
    prompt = f"""You are an infrastructure observability assistant monitoring a macOS filesystem.

Host: {metrics.hostname}
Volume: {metrics.filesystem} ({metrics.filesystem_type})
Storage utilization: {metrics.used_percent:.1f}%
Current read throughput: {metrics.read_bytes_per_sec / 1e6:.0f} MB/s
Current write throughput: {metrics.write_bytes_per_sec / 1e6:.0f} MB/s
Alert just triggered: {anomaly['type']} ({anomaly['severity']}) - {anomaly['message']}

Proactively explain in 2-3 concise sentences: what's happening, the likely cause, and one recommended action."""

    mock_explanation = (
        f"{anomaly['message']}. This can be caused by temporary file accumulation, "
        f"a backup or sync job, or cache growth. Check recently modified files and "
        f"~/Library/Caches if this persists. (Mock analysis — connect a BACKBOARD_API_KEY "
        f"with LLM chat credits for real AI insights.)"
    )

    explanation, _ = call_backboard(prompt, None, mock_explanation)
    try:
        update_alert_explanation(alert_id, explanation)
    except Exception as e:
        print(f"Failed to attach AI explanation to alert {alert_id}: {e}")


def build_live_context() -> str:
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
        "rather than guessing. Suggest concrete macOS commands where useful.",
        "",
        "=== LIVE TELEMETRY ===",
    ]

    try:
        volumes = get_all_volumes_latest()
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
        si = get_system_info()
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
                f"APFS container {c['container_reference']} (backed by {c['physical_store']}): "
                f"{used/1e9:.1f} GB used of {c['capacity_ceiling']/1e9:.1f} GB"
            )
            for v in c.get("volumes", []):
                lines.append(
                    f"  - volume {v['name']} [{', '.join(v['roles']) or 'no role'}]: "
                    f"{v['capacity_in_use']/1e9:.1f} GB"
                    f"{', encrypted' if v['encrypted'] else ''}"
                    f"{', FileVault' if v['filevault'] else ''}"
                )
        lines.append(
            f"FileVault: {'on' if si.get('filevault_enabled') else 'off'}; "
            f"local Time Machine snapshots: {si.get('snapshot_count', 0)}"
        )

    try:
        alerts = get_recent_alerts(limit=5)
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
async def ai_chat(data: dict):
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
        message, thread_id, mock_reply, system_prompt=build_live_context()
    )
    return {"message": reply, "thread_id": new_thread_id}

@app.post("/api/tts")
async def text_to_speech(data: dict):
    """Convert text to speech using ElevenLabs."""
    text = data.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY not configured")

    voice_id = "TWutjvRaJqAX89preB4e"  # added to account's own voice library (required for free-tier API access)
    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_flash_v2_5"},
        timeout=30
    )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"ElevenLabs error: {response.status_code}")

    return Response(content=response.content, media_type="audio/mpeg")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
