from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import os
import requests
from models import Metrics, MetricsResponse, Alert
from database import init_db, insert_metrics, get_latest_metrics, get_metrics_history, insert_alert, update_alert_explanation, get_recent_alerts, get_all_volumes_latest
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

# Slow-changing disk/APFS info (model, protocol, SMART, FileVault, snapshots).
# Kept in memory rather than the time-series DB — it's a point-in-time status
# snapshot, not a metric history, and the collector refreshes it every ~60s.
LATEST_SYSTEM_INFO = {}

@app.post("/api/system-info")
async def post_system_info(data: dict):
    """Receive disk/APFS system info from the collector (runs on the Mac, not here)."""
    global LATEST_SYSTEM_INFO
    LATEST_SYSTEM_INFO = data
    return {"status": "ok"}

@app.get("/api/system-info")
async def get_system_info():
    """Return the latest disk/APFS system info."""
    if not LATEST_SYSTEM_INFO:
        raise HTTPException(status_code=404, detail="No system info received yet")
    return LATEST_SYSTEM_INFO

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
# key instead. Google deprecates model names fairly aggressively — if calls
# start failing with NOT_FOUND, bump this to a current one from
# GET https://app.backboard.io/api/models?provider=google
LLM_PROVIDER = "google"
LLM_MODEL = "gemini-3.8-flash"


def call_backboard(content: str, thread_id: str | None, mock_reply: str) -> tuple[str, str | None]:
    """Send a message to Backboard, reusing thread_id for conversation continuity.

    Returns (reply_text, thread_id). Falls back to mock_reply on any failure
    (missing key, non-200 response, or the account lacking LLM chat credits).
    """
    backboard_key = os.getenv("BACKBOARD_API_KEY", "mock-key")
    if backboard_key == "mock-key":
        return mock_reply, thread_id or "mock-thread"

    payload = {
        "content": content,
        "stream": False,
        "llm_provider": LLM_PROVIDER,
        "model_name": LLM_MODEL,
    }
    if thread_id and thread_id != "mock-thread":
        payload["thread_id"] = thread_id

    try:
        response = requests.post(
            "https://app.backboard.io/api/threads/messages",
            headers={"X-API-Key": backboard_key},
            json=payload,
            timeout=45
        )
    except Exception as e:
        print(f"[backboard] request failed: {e}")
        return mock_reply, thread_id or "mock-thread"

    if response.status_code == 200:
        result = response.json()
        if result.get("status") == "COMPLETED":
            return result.get("content") or mock_reply, result.get("thread_id", thread_id)
        # A 200 with a non-COMPLETED status carries the real reason (billing,
        # deprecated model, provider error) in `content` — surface it rather
        # than silently pretending the mock response is the answer.
        print(f"[backboard] status={result.get('status')}: {result.get('content')}")
    else:
        print(f"[backboard] HTTP {response.status_code}: {response.text[:300]}")

    return mock_reply, thread_id or "mock-thread"


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

    reply, new_thread_id = call_backboard(message, thread_id, mock_reply)
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
