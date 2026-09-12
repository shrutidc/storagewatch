from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import requests
from models import Metrics, MetricsResponse, Alert
from database import init_db, insert_metrics, get_latest_metrics, get_metrics_history, insert_alert, get_recent_alerts
from alerts import detect_anomalies

load_dotenv()

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
async def post_metrics(metrics: Metrics):
    """Receive telemetry from monitoring agent."""
    try:
        insert_metrics(metrics)

        # Detect anomalies
        anomalies = detect_anomalies(metrics)

        # Save alerts to database
        for anomaly in anomalies:
            insert_alert(
                hostname=metrics.hostname,
                alert_type=anomaly["type"],
                severity=anomaly["severity"],
                message=anomaly["message"],
                metric_value=metrics.used_percent if anomaly["type"] == "HIGH_CAPACITY" else metrics.write_bytes_per_sec
            )

        return {"status": "ok", "alerts": len(anomalies)}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.get("/api/metrics/current")
async def get_current_metrics():
    """Return the most recent metrics."""
    try:
        result = get_latest_metrics()
        if not result:
            return {"error": "No metrics found"}, 404
        return dict(result)
    except Exception as e:
        return {"error": str(e)}, 500

@app.get("/api/metrics/history")
async def get_metrics_history_endpoint(limit: int = 100):
    """Return historical metrics (last N records)."""
    try:
        results = get_metrics_history(limit)
        return [dict(r) for r in results]
    except Exception as e:
        return {"error": str(e)}, 500

@app.get("/api/alerts")
async def get_alerts():
    """Return recent alerts."""
    try:
        results = get_recent_alerts(limit=10)
        return [dict(r) for r in results]
    except Exception as e:
        return {"error": str(e)}, 500

@app.post("/api/ai/explain")
async def explain_anomaly(data: dict):
    """Send anomaly to Backboard for AI explanation."""
    try:
        backboard_key = os.getenv("BACKBOARD_API_KEY", "mock-key")
        hostname = data.get("hostname", "Unknown")
        alert_type = data.get("alert_type", "ANOMALY_DETECTED")
        used_percent = data.get("used_percent", 0)
        write_throughput = data.get("write_throughput", 0)
        read_throughput = data.get("read_throughput", 0)
        filesystem_type = data.get("filesystem_type", "APFS")

        prompt = f"""You are an infrastructure observability assistant.
Analyze this macOS filesystem event.

Host: {hostname}
Filesystem: {filesystem_type}
Storage utilization: {used_percent:.1f}%
Current read throughput: {read_throughput / 1e6:.0f} MB/s
Current write throughput: {write_throughput / 1e6:.0f} MB/s
Detected anomaly: {alert_type}

Provide a concise technical analysis:
1. What's happening
2. Possible causes
3. Recommended action
Keep response under 200 words."""

        if backboard_key == "mock-key":
            explanation = f"""Analysis for {hostname}:

The system is experiencing {alert_type.lower()}.
Storage is at {used_percent:.1f}% capacity.

Potential causes:
- Temporary file accumulation
- System backup in progress
- Application cache growth
- Media file ingestion

Recommended actions:
- Check ~/Library/Caches for large files
- Review recent file additions
- Monitor for pattern recurrence
- Consider archiving older files if capacity > 80%

This is a mock analysis. Connect BACKBOARD_API_KEY for AI-powered insights."""
            return {"explanation": explanation}

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": backboard_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-3-sonnet-20240229",
                "max_tokens": 500,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            explanation = result.get("content", [{}])[0].get("text", "Analysis unavailable")
        else:
            explanation = f"API error: {response.status_code}"

        return {"explanation": explanation}

    except Exception as e:
        return {"explanation": f"Error: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
