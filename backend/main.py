from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
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
    pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
