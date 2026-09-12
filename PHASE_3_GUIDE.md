# Phase 3: End-to-End Integration Testing

## Overview

All backend, collector, and frontend components are complete. Phase 3 is integration testing:

- ✅ Collector sends metrics to backend
- ✅ Backend stores metrics in Tiger Data
- ✅ Backend detects anomalies and stores alerts
- ✅ Dashboard fetches metrics and displays them
- ✅ Dashboard fetches alerts
- ✅ Dashboard calls AI explanation endpoint
- ✅ AI explanations render on dashboard

**Time estimate:** 1–2 hours (mostly testing and debugging)

---

## Architecture Overview

```
┌─────────────────────────────────────┐
│         Mac (Your Machine)          │
│                                     │
│   Python Collector (collector.py)   │
│   Samples every 5 seconds           │
│   Sends to backend via HTTP         │
└────────────┬────────────────────────┘
             │
             │ POST /api/metrics
             │ (JSON telemetry)
             ▼
┌─────────────────────────────────────┐
│     FastAPI Backend (main.py)       │
│                                     │
│  • Store metrics in Tiger Data      │
│  • Detect anomalies (capacity + I/O)│
│  • Save alerts to DB                │
│  • Provide API endpoints            │
└────────────┬────────────────────────┘
             │
             ├─────────────────────────────┐
             │                             │
             ▼                             ▼
     ┌──────────────┐           ┌──────────────────┐
     │  Tiger Data  │           │  React Dashboard │
     │ (Metrics DB) │           │  (localhost:3000)│
     │ (Alerts DB)  │           │                  │
     └──────────────┘           │ Auth0 Protected  │
                                └──────────────────┘
                                       ▲
                                       │
                                GET /api/metrics/*
                                GET /api/alerts
                                POST /api/ai/explain
```

---

## Setup & Configuration

### 1. Environment Variables

Make sure all services have the required env vars:

**Mac (Collector):**
```bash
# collector/collector.py uses this
BACKEND_URL=http://localhost:8000
```

**Backend:**
```bash
# backend/.env
TIGER_DATABASE_URL=postgresql://user:password@host:port/storagewatch
BACKBOARD_API_KEY=mock-key  # or your real key
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_CLIENT_ID=your-client-id
AUTH0_CLIENT_SECRET=your-client-secret
REACT_APP_AUTH0_DOMAIN=your-domain.auth0.com
REACT_APP_AUTH0_CLIENT_ID=your-client-id
REACT_APP_AUTH0_AUDIENCE=storagewatch-api
BACKEND_URL=http://localhost:8000
```

**Frontend:**
```bash
# frontend/.env (if needed, usually via REACT_APP_* vars)
VITE_API_URL=http://localhost:8000
```

### 2. Start Services (3 terminals)

**Terminal 1 — Backend:**
```bash
cd backend
python main.py
# Should see: Uvicorn running on http://0.0.0.0:8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm install  # if needed
npm run dev
# Should see: Local: http://localhost:5173
```

**Terminal 3 — Collector:**
```bash
cd collector
python collector.py
# Should see: Starting StorageWatch collector...
```

---

## End-to-End Test Scenario

### Step 1: Verify Backend Health

```bash
curl http://localhost:8000/health
# Response: {"status": "ok"}
```

### Step 2: Verify Collector is Sending Data

Watch collector output (Terminal 3):
```
✓ Metrics sent: 62.3% used, R:180MB/s W:45MB/s
✓ Metrics sent: 62.3% used, R:175MB/s W:42MB/s
✓ Metrics sent: 62.3% used, R:160MB/s W:48MB/s
```

### Step 3: Check Backend Received Metrics

```bash
curl http://localhost:8000/api/metrics/current
# Response: {...metrics from collector...}
```

### Step 4: Login to Dashboard

- Open `http://localhost:5173` (or whatever frontend shows)
- Click "Login"
- Authenticate with Auth0
- Should see dashboard with:
  - System status indicator
  - Current storage percentage
  - Read/Write throughput cards
  - Performance graph (should have data points)

### Step 5: Trigger a Capacity Alert

**On your Mac, create a large test file:**

```bash
# This creates a 2GB file (modify size as needed)
mkfile 2g ~/storagewatch-demo
```

**Watch:**
- Collector detects increased storage usage
- Backend stores metrics
- Dashboard graph updates with spike
- Storage percentage card shows increased value
- If >= 80%, alert should appear

### Step 6: Verify Alerts Panel

```bash
curl http://localhost:8000/api/alerts
# Response: Array of alerts including HIGH_CAPACITY or HIGH_WRITE_ACTIVITY
```

Dashboard should display:
- Alert type and severity
- Alert message
- Time created

### Step 7: Click "Explain with AI" (on Dashboard)

- Click "Explain with AI" button on alert
- Backend calls `/api/ai/explain` endpoint
- AI explanation should appear:
  ```
  Analysis for your-hostname:
  
  The system is experiencing high_capacity_alert.
  Storage is at XX% capacity.
  
  Potential causes:
  - Temporary file accumulation
  - System backup in progress
  ...
  
  Recommended actions:
  ...
  ```

### Step 8: Cleanup Test File

```bash
rm ~/storagewatch-demo
```

Watch dashboard:
- Storage percentage decreases
- Write throughput spike disappears
- Graph shows recovery
- New alert may appear when back to normal

---

## Success Criteria for Phase 3

✅ Collector runs without errors and sends metrics every 5 seconds
✅ Backend receives and stores metrics in Tiger Data
✅ `GET /api/metrics/current` returns latest metrics
✅ `GET /api/metrics/history?limit=100` returns 100+ records
✅ Dashboard loads and authenticates with Auth0
✅ Dashboard displays current metrics
✅ Dashboard displays performance graph with 100+ data points
✅ Creating disk activity triggers capacity alert
✅ Alerts appear in dashboard immediately
✅ `GET /api/alerts` returns recent alerts
✅ "Explain with AI" button fetches explanation
✅ Explanations render correctly on dashboard
✅ All endpoints are responsive (<1 second latency)
✅ No console errors in browser or terminals

---

## Troubleshooting

### Collector can't connect to backend
```
Error: Connection refused
```
- Ensure backend is running: `curl http://localhost:8000/health`
- Check BACKEND_URL in collector/collector.py
- Check firewall if backend is on different machine

### Dashboard shows "No metrics found"
- Ensure collector has been running for at least 5 seconds
- Check backend is receiving metrics: `curl http://localhost:8000/api/metrics/current`
- Check browser console for API errors

### Auth0 login fails
- Verify AUTH0_DOMAIN and CLIENT_ID in `.env`
- Check that Auth0 app is configured to allow `localhost:5173`
- Check browser console for CORS errors

### AI explanation returns error
- If using mock-key, should return mock explanation (safe)
- If using real key, check it's valid
- Verify CORS is enabled (it is in main.py)

### Performance graph is empty
- Collector needs to run for >5 seconds to have data
- Check `/api/metrics/history` returns data
- Verify frontend is receiving data: check Network tab in browser DevTools

---

## Performance & Monitoring

### Metrics to Monitor

**Collector (every 5 seconds):**
- ✓ Metrics successfully sent?
- ✓ Error rate?

**Backend:**
- ✓ Metrics endpoint latency
- ✓ Alert detection accuracy
- ✓ Database write throughput

**Dashboard:**
- ✓ Graph updates in real-time
- ✓ No lag when fetching history
- ✓ Alert notifications appear immediately

### Check Backend Logs

```bash
# In backend terminal, should see:
INFO:     Application startup complete [started server process]
INFO:     GET /health [client-ip]
INFO:     POST /api/metrics [client-ip]
INFO:     GET /api/metrics/current [client-ip]
```

---

## Demo Script (for presentation)

1. **Start all services** (3 terminals)
   ```bash
   # Terminal 1: Backend
   cd backend && python main.py
   
   # Terminal 2: Frontend
   cd frontend && npm run dev
   
   # Terminal 3: Collector
   cd collector && python collector.py
   ```

2. **Open dashboard** at `http://localhost:5173`

3. **Show current metrics:**
   - Storage percentage
   - Read/Write throughput
   - Performance graph

4. **Create activity:**
   ```bash
   mkfile 2g ~/storagewatch-demo
   ```

5. **Watch spike:**
   - Dashboard graph updates
   - Storage percentage increases
   - Alert appears

6. **Click "Explain with AI"**
   - AI explanation appears
   - Shows analysis of increased activity

7. **Cleanup:**
   ```bash
   rm ~/storagewatch-demo
   ```

---

## What Each Component Does (Architecture Summary)

### Collector (Om - Complete ✅)
- Runs on Mac, samples every 5 seconds
- Collects: disk usage, I/O throughput, hostname, filesystem type
- Sends JSON to backend via HTTP POST

### Backend (Shruti - Complete ✅)
- Receives telemetry from collector
- Stores in Tiger Data (time-series DB)
- Detects anomalies:
  - Capacity: warning at 80%, critical at 90%
  - I/O: write > 4x baseline
- Stores alerts
- Serves REST API for dashboard

### Frontend (Om - Complete ✅)
- React app with Recharts
- Auth0 authentication
- Displays:
  - Current metrics (storage %, throughput)
  - Performance graph (time-series)
  - Alerts panel
  - AI explanation panel

### Full Flow
```
Metrics → Collector → Backend → Database
                    ↓
              Anomaly Detection
                    ↓
                  Alerts
                    ↓
           Dashboard ← API Endpoints
                    ↓
            AI Explanation
```

---

## Next Steps After Phase 3

If all tests pass:

1. **Deploy to Vultr** (production deployment)
2. **Set up .tech domain** (DNS configuration)
3. **Production Auth0 config** (real app settings)
4. **Real Backboard API** (production API key)
5. **Create demo presentation** (show the flow)
6. **Document setup** (deployment instructions)

---

## Quick Checklist

- [ ] Backend starts without errors
- [ ] Frontend starts without errors
- [ ] Collector starts without errors
- [ ] Collector shows "Metrics sent" messages
- [ ] Dashboard loads and shows current metrics
- [ ] Dashboard graph has 20+ data points
- [ ] Dashboard metric cards update every 5 seconds
- [ ] Creating large file triggers alert in <10 seconds
- [ ] Alert appears in dashboard immediately
- [ ] "Explain with AI" button works
- [ ] AI explanation text appears on dashboard
- [ ] Deleting file shows storage decrease
- [ ] No errors in browser console
- [ ] No errors in terminal logs
