# Phase 3: Local Integration Testing Setup

## Quick Start (Copy & Paste)

### Prerequisites Check
```bash
# Check Python 3.9+
python3 --version

# Check Node.js 18+
node --version
npm --version
```

### Setup (Run Once)

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### Run All 3 Services (3 separate terminals)

**Terminal 1 — Backend (FastAPI):**
```bash
cd /path/to/storagewatch
cd backend
python main.py
```
Expected output:
```
INFO:     Application startup complete
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Terminal 2 — Frontend (React):**
```bash
cd /path/to/storagewatch
cd frontend
npm run dev
```
Expected output:
```
VITE v5.0.0  ready in XXX ms

➜  Local:   http://localhost:5173/
```

**Terminal 3 — Collector (Python):**
```bash
cd /path/to/storagewatch
python collector/collector.py
```
Expected output:
```
Starting StorageWatch collector...
Backend: http://localhost:8000
Sampling every 5 seconds...

✓ Metrics sent: 62.3% used, R:180MB/s W:45MB/s
✓ Metrics sent: 62.3% used, R:175MB/s W:42MB/s
```

---

## Testing Checklist

### Phase 3A: Verify Backend Health
```bash
# Terminal 4 (or any terminal)
curl http://localhost:8000/health
# Should return: {"status":"ok"}
```

### Phase 3B: Verify Collector is Sending Data
- Watch **Terminal 3** output
- Should see "✓ Metrics sent" messages every 5 seconds
- If you see errors, backend may not be running

### Phase 3C: Verify Backend Received Metrics
```bash
curl http://localhost:8000/api/metrics/current
# Should return: {...with your current disk usage...}
```

### Phase 3D: Open Dashboard & Login
1. Open http://localhost:5173 in browser
2. Click "Login with Auth0"
3. Authenticate (use your Auth0 credentials)
4. Should see dashboard with:
   - Status badge (Healthy/Warning/Critical)
   - 3 metric cards (Storage, Read, Write)
   - Performance graph (will fill up as collector runs)

### Phase 3E: Trigger a Capacity Alert

**Create a large test file:**
```bash
# This creates a 2GB test file
mkfile 2g ~/storagewatch-demo
```

**Watch in real-time:**
- Collector terminal: metrics show increased storage %
- Dashboard: storage % card increases
- Dashboard: graph shows spike
- If storage >= 80%: Alert should appear in Alerts section

### Phase 3F: Test AI Explanation

1. In dashboard, click "Explain with AI" button
2. Should see explanation text appear (mock response)
3. Check it mentions the current situation

### Phase 3G: Cleanup Test File

```bash
rm ~/storagewatch-demo
```

Watch dashboard:
- Storage % decreases
- Graph shows recovery
- Alert may resolve

---

## Success Criteria

✅ All 3 services start without errors
✅ Collector shows "Metrics sent" every 5 seconds
✅ Dashboard loads after Auth0 login
✅ Dashboard shows real metrics (not 0)
✅ Performance graph has 20+ data points
✅ Creating 2GB file triggers alert within 10 seconds
✅ Alert appears in dashboard immediately
✅ "Explain with AI" returns explanation
✅ Deleting file shows immediate storage decrease

---

## Troubleshooting

### Backend won't start
```
Error: Address already in use
```
→ Port 8000 is taken. Kill it:
```bash
lsof -i :8000
kill -9 <PID>
```

### Collector can't connect to backend
```
Error: Connection refused
```
→ Ensure backend is running
→ Check `BACKEND_URL=http://localhost:8000` in collector.py

### Frontend won't start
```
npm: command not found
```
→ Install Node.js from https://nodejs.org/

### Dashboard shows "No metrics"
→ Wait 10+ seconds for collector to send data
→ Check collector terminal for errors
→ Verify `curl http://localhost:8000/api/metrics/current` has data

### Auth0 login fails
→ Verify VITE_AUTH0_* vars in frontend/.env.local
→ Check Auth0 allows localhost:5173 as callback URL

---

## Next: Quick Demo Script

Once everything is working:

1. **Open http://localhost:5173 in browser**
2. **Show dashboard** (current metrics + graph)
3. **Create test file:** `mkfile 2g ~/storagewatch-demo`
4. **Watch:** Storage % increase, graph spike, alert appears
5. **Click:** "Explain with AI" button
6. **See:** AI analysis of the situation
7. **Cleanup:** `rm ~/storagewatch-demo`
8. **Watch:** Storage % decrease, recovery shown

Total demo time: ~2 minutes

