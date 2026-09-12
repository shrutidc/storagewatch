from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://storagewatch.tech"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Metrics(BaseModel):
    timestamp: str
    hostname: str
    filesystem: str
    filesystem_type: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float
    read_bytes_per_sec: int
    write_bytes_per_sec: int

@app.post("/api/metrics")
async def post_metrics(metrics: Metrics):
    pass

@app.get("/api/metrics/current")
async def get_current_metrics():
    pass

@app.get("/api/metrics/history")
async def get_metrics_history(limit: int = 100):
    pass

@app.post("/api/ai/explain")
async def explain_anomaly(data: dict):
    pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
