# Phase 1: Collector + Backend + Basic Dashboard

**Timeline:** 2-3 hours | **Commits:** 2-3 per person

---

## Setup (Both People)

1. **Fill in `.env` file** with credentials:
   ```
   TIGER_DATABASE_URL=postgresql://...
   AUTH0_DOMAIN=...
   AUTH0_CLIENT_ID=...
   BACKBOARD_API_KEY=...
   ```

2. **Install dependencies:**
   ```bash
   # Person A (Backend)
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt

   # Person B (Frontend)
   cd frontend
   npm install
   ```

---

## Person A: Backend Infrastructure

### Task 1: Tiger Data Schema (15 min)

**Goal:** Create tables in Tiger Data for metrics and alerts.

**Steps:**
1. Connect to Tiger Data using your `TIGER_DATABASE_URL`
2. Run this SQL to create the hypertable:

```sql
CREATE TABLE IF NOT EXISTS filesystem_metrics (
    time TIMESTAMPTZ NOT NULL,
    hostname TEXT NOT NULL,
    filesystem TEXT NOT NULL,
    filesystem_type TEXT,
    total_bytes BIGINT,
    used_bytes BIGINT,
    free_bytes BIGINT,
    used_percent DOUBLE PRECISION,
    read_bytes_per_sec BIGINT,
    write_bytes_per_sec BIGINT
);

SELECT create_hypertable(
    'filesystem_metrics',
    'time',
    if_not_exists => TRUE
);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    hostname TEXT,
    alert_type TEXT,
    severity TEXT,
    message TEXT,
    metric_value DOUBLE PRECISION,
    resolved BOOLEAN DEFAULT FALSE
);
```

3. Test the connection in `backend/database.py` (see Task 2)

---

### Task 2: Implement `backend/database.py` (30 min)

**Goal:** Write functions to insert/query metrics and alerts.

**Code to add:**

```python
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime

DATABASE_URL = os.getenv("TIGER_DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def insert_metrics(metrics):
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO filesystem_metrics (
            time, hostname, filesystem, filesystem_type,
            total_bytes, used_bytes, free_bytes, used_percent,
            read_bytes_per_sec, write_bytes_per_sec
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        metrics.timestamp,
        metrics.hostname,
        metrics.filesystem,
        metrics.filesystem_type,
        metrics.total_bytes,
        metrics.used_bytes,
        metrics.free_bytes,
        metrics.used_percent,
        metrics.read_bytes_per_sec,
        metrics.write_bytes_per_sec,
    ))
    
    conn.commit()
    cur.close()
    conn.close()

def get_latest_metrics():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT * FROM filesystem_metrics
        ORDER BY time DESC LIMIT 1
    """)
    
    result = cur.fetchone()
    cur.close()
    conn.close()
    
    return result

def get_metrics_history(limit=100):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT * FROM filesystem_metrics
        ORDER BY time DESC LIMIT %s
    """, (limit,))
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return list(reversed(results))

def insert_alert(hostname, alert_type, severity, message, metric_value):
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO alerts (hostname, alert_type, severity, message, metric_value)
        VALUES (%s, %s, %s, %s, %s)
    """, (hostname, alert_type, severity, message, metric_value))
    
    conn.commit()
    cur.close()
    conn.close()

def get_recent_alerts(limit=10):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT * FROM alerts
        WHERE resolved = FALSE
        ORDER BY created_at DESC LIMIT %s
    """, (limit,))
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return results
```

**Commit:** `Backend: Implement database layer for metrics and alerts`

---

### Task 3: Implement FastAPI Endpoints (45 min)

**Goal:** Build 4 endpoints that the dashboard will call.

**Replace `backend/main.py` with:**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
from dotenv import load_dotenv
import requests

from database import (
    insert_metrics, get_latest_metrics, get_metrics_history,
    insert_alert, get_recent_alerts
)
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
    """Receive telemetry from Python collector, store in DB, check for anomalies."""
    
    # Store metrics
    insert_metrics(metrics)
    
    # Check for anomalies
    anomalies = detect_anomalies(metrics)
    
    # Store alerts
    for anomaly in anomalies:
        insert_alert(
            hostname=metrics.hostname,
            alert_type=anomaly["type"],
            severity=anomaly["severity"],
            message=anomaly["message"],
            metric_value=metrics.used_percent if anomaly["type"] == "HIGH_CAPACITY" else metrics.write_bytes_per_sec
        )
    
    return {"status": "ok", "alerts": anomalies}

@app.get("/api/metrics/current")
async def get_current_metrics():
    """Return most recent metric record."""
    
    metrics = get_latest_metrics()
    return metrics if metrics else {}

@app.get("/api/metrics/history")
async def get_metrics_history_endpoint(limit: int = 100):
    """Return historical metrics for graphing."""
    
    history = get_metrics_history(limit)
    return history

@app.post("/api/ai/explain")
async def explain_anomaly(data: dict):
    """Send anomaly data to Backboard for AI analysis."""
    
    backboard_key = os.getenv("BACKBOARD_API_KEY")
    
    prompt = f"""You are an infrastructure monitoring assistant.
Analyze this macOS filesystem event.

Filesystem: {data.get('filesystem_type', 'APFS')}
Storage utilization: {data.get('used_percent', 0)}%
Current read throughput: {data.get('read_bytes_per_sec', 0) / 1e6:.0f} MB/s
Current write throughput: {data.get('write_bytes_per_sec', 0) / 1e6:.0f} MB/s
Detected anomaly: {data.get('anomaly_message', 'Unknown')}

Explain:
1. What happened
2. Possible causes
3. Severity
4. What the administrator should inspect

Keep the response concise and technical."""

    # Call Backboard API
    try:
        response = requests.post(
            "https://api.backboard.sh/v1/chat/completions",  # Adjust endpoint if different
            headers={"Authorization": f"Bearer {backboard_key}"},
            json={"prompt": prompt}
        )
        explanation = response.json().get("message", "Unable to generate explanation")
    except Exception as e:
        explanation = f"Error calling Backboard: {str(e)}"
    
    return {"explanation": explanation}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Commit:** `Backend: Implement FastAPI endpoints for metrics and AI`

---

### Task 4: Implement Python Collector (30 min)

**Goal:** Collect filesystem metrics every 5 seconds and POST to backend.

**Replace `collector/collector.py` with:**

```python
import psutil
import requests
import json
import platform
import subprocess
import time
from datetime import datetime, timezone

BACKEND_URL = "http://localhost:8000"

def get_filesystem_type():
    """Detect filesystem type using diskutil."""
    try:
        result = subprocess.run(
            ["diskutil", "info", "/"],
            capture_output=True,
            text=True
        )
        for line in result.stdout.split("\n"):
            if "File System Personality" in line:
                return line.split(":")[-1].strip()
    except Exception as e:
        print(f"Error detecting filesystem: {e}")
    return "Unknown"

previous_counters = None
previous_time = None

def collect_metrics():
    """Collect filesystem and I/O metrics."""
    global previous_counters, previous_time
    
    # Capacity metrics
    disk = psutil.disk_usage("/")
    
    # I/O counters
    counters = psutil.disk_io_counters()
    current_time = time.time()
    
    # Calculate throughput
    if previous_counters and previous_time:
        time_delta = current_time - previous_time
        
        read_bytes_per_sec = int((counters.read_bytes - previous_counters.read_bytes) / time_delta)
        write_bytes_per_sec = int((counters.write_bytes - previous_counters.write_bytes) / time_delta)
    else:
        read_bytes_per_sec = 0
        write_bytes_per_sec = 0
    
    previous_counters = counters
    previous_time = current_time
    
    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": platform.node(),
        "filesystem": "/",
        "filesystem_type": get_filesystem_type(),
        "total_bytes": disk.total,
        "used_bytes": disk.used,
        "free_bytes": disk.free,
        "used_percent": disk.percent,
        "read_bytes_per_sec": read_bytes_per_sec,
        "write_bytes_per_sec": write_bytes_per_sec,
    }
    
    return metrics

def send_metrics(metrics):
    """POST metrics to backend."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/metrics",
            json=metrics,
            timeout=5
        )
        if response.status_code == 200:
            print(f"✓ Metrics sent: {metrics['used_percent']:.1f}% used")
            return True
    except Exception as e:
        print(f"✗ Error sending metrics: {e}")
    return False

def main():
    """Run collector loop."""
    print("Starting StorageWatch collector...")
    print(f"Backend: {BACKEND_URL}")
    
    while True:
        try:
            metrics = collect_metrics()
            send_metrics(metrics)
            time.sleep(5)  # Collect every 5 seconds
        except KeyboardInterrupt:
            print("\nCollector stopped.")
            break
        except Exception as e:
            print(f"Error in collection loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
```

**Commit:** `Collector: Implement filesystem monitoring with 5-second intervals`

---

### Task 5: Test Backend Locally (15 min)

1. Start the backend:
   ```bash
   cd backend
   python main.py
   ```
   Should see: `Uvicorn running on http://0.0.0.0:8000`

2. In another terminal, test endpoints:
   ```bash
   # Test POST
   curl -X POST http://localhost:8000/api/metrics \
     -H "Content-Type: application/json" \
     -d '{"timestamp":"2026-09-12T18:00:00Z","hostname":"test-mac","filesystem":"/","filesystem_type":"APFS","total_bytes":1000000000,"used_bytes":600000000,"free_bytes":400000000,"used_percent":60.0,"read_bytes_per_sec":1000000,"write_bytes_per_sec":500000}'
   
   # Test GET current
   curl http://localhost:8000/api/metrics/current
   
   # Test GET history
   curl http://localhost:8000/api/metrics/history
   ```

3. If all respond with 200, backend is ready.

---

## Person B: Frontend + Auth0

### Task 1: Setup Auth0 (20 min)

**Goal:** Configure Auth0 application for React dashboard.

**Steps:**
1. Log into Auth0 dashboard (https://manage.auth0.com)
2. Go to **Applications → Your App Name**
3. Under **Settings**, update:
   - **Allowed Callback URLs:** `http://localhost:3000/callback,http://localhost:3000`
   - **Allowed Logout URLs:** `http://localhost:3000`
   - **Allowed Web Origins:** `http://localhost:3000`
4. Go to **APIs → StorageWatch API**
5. Copy: Domain, Client ID, Audience
6. Fill in `.env`:
   ```
   REACT_APP_AUTH0_DOMAIN=your-domain.auth0.com
   REACT_APP_AUTH0_CLIENT_ID=your-client-id
   REACT_APP_AUTH0_AUDIENCE=storagewatch-api
   ```

---

### Task 2: Setup React + Auth0 (15 min)

**Goal:** Configure React app with Auth0 login flow.

**Replace `frontend/src/main.jsx` with:**

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import App from './App.jsx'

const domain = import.meta.env.VITE_AUTH0_DOMAIN || window.location.hostname
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID
const audience = import.meta.env.VITE_AUTH0_AUDIENCE

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      redirectUri={window.location.origin}
      audience={audience}
    >
      <App />
    </Auth0Provider>
  </React.StrictMode>,
)
```

Also update `frontend/vite.config.js`:

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
})
```

**Commit:** `Frontend: Configure Auth0 and Vite proxy`

---

### Task 3: Build Dashboard Components (1 hour)

**Goal:** Create metric cards, charts, and alerts panel.

**Replace `frontend/src/App.jsx` with:**

```jsx
import { useAuth0 } from '@auth0/auth0-react'
import { useState, useEffect } from 'react'
import axios from 'axios'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import './App.css'

function App() {
  const { loginWithRedirect, logout, user, isAuthenticated, isLoading } = useAuth0()
  const [metrics, setMetrics] = useState(null)
  const [history, setHistory] = useState([])
  const [alerts, setAlerts] = useState([])
  const [explaining, setExplaining] = useState(false)
  const [explanation, setExplanation] = useState(null)

  useEffect(() => {
    if (isAuthenticated) {
      fetchMetrics()
      const interval = setInterval(fetchMetrics, 5000)
      return () => clearInterval(interval)
    }
  }, [isAuthenticated])

  const fetchMetrics = async () => {
    try {
      const [current, hist] = await Promise.all([
        axios.get('/api/metrics/current'),
        axios.get('/api/metrics/history?limit=100'),
      ])
      setMetrics(current.data)
      
      // Reverse for chart (oldest to newest)
      if (hist.data && Array.isArray(hist.data)) {
        setHistory(hist.data.map(m => ({
          time: new Date(m.time).toLocaleTimeString(),
          read: (m.read_bytes_per_sec / 1e6).toFixed(0),
          write: (m.write_bytes_per_sec / 1e6).toFixed(0),
        })))
      }
    } catch (err) {
      console.error('Failed to fetch metrics:', err)
    }
  }

  const getSystemStatus = () => {
    if (!metrics) return 'Unknown'
    if (metrics.used_percent >= 90) return 'Critical'
    if (metrics.used_percent >= 80) return 'Warning'
    return 'Healthy'
  }

  const getStatusColor = () => {
    const status = getSystemStatus()
    return status === 'Critical' ? '#d32f2f' : status === 'Warning' ? '#f57c00' : '#388e3c'
  }

  const handleExplainAI = async () => {
    if (!metrics) return
    
    setExplaining(true)
    try {
      const response = await axios.post('/api/ai/explain', {
        filesystem_type: metrics.filesystem_type,
        used_percent: metrics.used_percent,
        read_bytes_per_sec: metrics.read_bytes_per_sec,
        write_bytes_per_sec: metrics.write_bytes_per_sec,
        anomaly_message: `Storage at ${metrics.used_percent.toFixed(1)}%`,
      })
      setExplanation(response.data.explanation)
    } catch (err) {
      setExplanation(`Error: ${err.message}`)
    } finally {
      setExplaining(false)
    }
  }

  if (isLoading) return <div className="loading">Loading...</div>

  if (!isAuthenticated) {
    return (
      <div className="login-container">
        <h1>StorageWatch</h1>
        <p>Monitor your macOS storage with AI-powered insights</p>
        <button className="login-btn" onClick={() => loginWithRedirect()}>Login</button>
      </div>
    )
  }

  return (
    <div className="app">
      <header>
        <div>
          <h1>StorageWatch</h1>
          {metrics && (
            <div className="status-badge" style={{ backgroundColor: getStatusColor() }}>
              {getSystemStatus()}
            </div>
          )}
        </div>
        <div className="user-info">
          <span>{user.name}</span>
          <button onClick={() => logout()}>Logout</button>
        </div>
      </header>

      <main>
        {metrics ? (
          <>
            <div className="metrics-grid">
              <div className="metric-card">
                <h3>Storage Usage</h3>
                <p className="metric-value">{metrics.used_percent.toFixed(1)}%</p>
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${metrics.used_percent}%` }}></div>
                </div>
                <p className="metric-detail">
                  {(metrics.used_bytes / 1e9).toFixed(1)} GB / {(metrics.total_bytes / 1e9).toFixed(1)} GB
                </p>
              </div>

              <div className="metric-card">
                <h3>Read Throughput</h3>
                <p className="metric-value">{(metrics.read_bytes_per_sec / 1e6).toFixed(0)}</p>
                <p className="metric-unit">MB/s</p>
              </div>

              <div className="metric-card">
                <h3>Write Throughput</h3>
                <p className="metric-value">{(metrics.write_bytes_per_sec / 1e6).toFixed(0)}</p>
                <p className="metric-unit">MB/s</p>
              </div>
            </div>

            <div className="chart-container">
              <h2>Performance Graph (Last 100 samples)</h2>
              {history.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={history}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" />
                    <YAxis label={{ value: 'MB/s', angle: -90, position: 'insideLeft' }} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="read" stroke="#8884d8" name="Read" dot={false} />
                    <Line type="monotone" dataKey="write" stroke="#82ca9d" name="Write" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p>Loading chart data...</p>
              )}
            </div>

            <div className="ai-container">
              <h2>AI Analysis</h2>
              <button 
                className="explain-btn" 
                onClick={handleExplainAI}
                disabled={explaining}
              >
                {explaining ? 'Loading...' : 'Explain with AI'}
              </button>
              {explanation && (
                <div className="explanation-box">
                  <pre>{explanation}</pre>
                </div>
              )}
            </div>
          </>
        ) : (
          <p>No metrics available yet. Backend may be starting up...</p>
        )}
      </main>
    </div>
  )
}

export default App
```

**Update `frontend/src/App.css`:**

```css
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #f5f5f5;
  color: #333;
}

.app {
  min-height: 100vh;
}

header {
  background: white;
  padding: 20px;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

header > div:first-child {
  display: flex;
  align-items: center;
  gap: 15px;
}

header h1 {
  font-size: 24px;
  font-weight: 600;
}

.status-badge {
  padding: 6px 12px;
  border-radius: 20px;
  color: white;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
}

.user-info {
  display: flex;
  gap: 15px;
  align-items: center;
}

.user-info button {
  padding: 8px 16px;
  background: #f0f0f0;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.user-info button:hover {
  background: #e0e0e0;
}

main {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.login-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  gap: 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.login-btn {
  padding: 12px 32px;
  background: white;
  color: #667eea;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  font-weight: 600;
}

.login-btn:hover {
  background: #f0f0f0;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  font-size: 18px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.metric-card {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.metric-card h3 {
  font-size: 12px;
  color: #666;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.metric-value {
  font-size: 36px;
  font-weight: bold;
  color: #333;
  margin-bottom: 5px;
}

.metric-unit {
  font-size: 12px;
  color: #999;
}

.metric-detail {
  font-size: 13px;
  color: #666;
  margin-top: 10px;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
  margin: 12px 0;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #667eea, #764ba2);
  transition: width 0.3s ease;
}

.chart-container {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  margin-bottom: 30px;
}

.chart-container h2 {
  margin-bottom: 20px;
  font-size: 18px;
}

.ai-container {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.ai-container h2 {
  margin-bottom: 15px;
  font-size: 18px;
}

.explain-btn {
  padding: 10px 20px;
  background: #667eea;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 15px;
}

.explain-btn:hover {
  background: #764ba2;
}

.explain-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.explanation-box {
  background: #f5f5f5;
  padding: 15px;
  border-radius: 4px;
  border-left: 4px solid #667eea;
}

.explanation-box pre {
  font-family: 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #333;
  white-space: pre-wrap;
  word-wrap: break-word;
}
```

**Commit:** `Frontend: Build dashboard with metrics cards and Recharts`

---

### Task 4: Test Frontend Locally (20 min)

1. Start frontend dev server:
   ```bash
   cd frontend
   npm run dev
   ```

2. Open browser to `http://localhost:3000`

3. Click "Login" → should redirect to Auth0 → authenticate → return to dashboard

4. If backend is running, should see metric cards filling with data

5. Graph should update every 5 seconds

---

## Integration Check (Both)

Once both Person A and Person B complete their tasks:

1. **Backend running:** `python backend/main.py` (port 8000)
2. **Collector running:** `python collector/collector.py` (posts every 5 sec)
3. **Frontend running:** `npm run dev` in frontend folder (port 3000)
4. **Open dashboard:** http://localhost:3000 → login → see live metrics

If all working, **commit and push:**

```bash
git add -A
git commit -m "Phase 1: Full collector + backend + dashboard implementation"
git push origin main
```

---

## What's NOT done yet (Phase 2+):

- ✗ Alerts panel (will add in next phase)
- ✗ Historical graphs beyond current view
- ✗ Vultr deployment
- ✗ .tech domain
- ✗ Advanced Backboard integration
