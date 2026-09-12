from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from models import Metrics, MetricsResponse, Alert
from database import init_db

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
    init_db()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/api/metrics")
async def post_metrics(metrics: Metrics):
    """Receive telemetry from monitoring agent."""
    pass

@app.get("/api/metrics/current")
async def get_current_metrics():
    """Return the most recent metrics."""
    pass

@app.get("/api/metrics/history")
async def get_metrics_history(limit: int = 100):
    """Return historical metrics (last N records)."""
    pass

@app.get("/api/alerts")
async def get_alerts():
    """Return recent alerts."""
    pass

@app.post("/api/ai/explain")
async def explain_anomaly(data: dict):
    """Send anomaly to Backboard for AI explanation."""
    pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
