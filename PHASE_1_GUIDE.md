# Phase 1: Core Infrastructure — Person A (Backend)

## Overview

Person A implements the FastAPI backend with:
- ✅ Endpoint logic (POST/GET metrics, alerts)
- ✅ Tiger Data integration
- ✅ Anomaly detection (capacity + write spikes)
- ✅ Local testing

**Estimated time:** 3–4 hours

---

## Setup

### 1. Environment Variables

Update `.env` with your Tiger Data connection string:

```bash
# .env
TIGER_DATABASE_URL=postgresql://user:password@host:port/storagewatch
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_CLIENT_ID=your-client-id
AUTH0_CLIENT_SECRET=your-client-secret
BACKBOARD_API_KEY=your-backboard-api-key
BACKEND_URL=http://localhost:8000
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Initialize Database

The backend automatically runs `init_db()` on startup, which:
- Creates `filesystem_metrics` hypertable
- Creates `alerts` table
- Sets up indexes

**Or manually initialize:**

```bash
psql $TIGER_DATABASE_URL < backend/schema.sql
```

---

## Running the Backend

### Start FastAPI server:

```bash
cd backend
python main.py
```

Should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Health check:

```bash
curl http://localhost:8000/health
```

Response:
```json
{"status": "ok"}
```

---

## Testing Phase 1

### Option A: Run Test Suite (No Database Needed)

```bash
python backend/test_phase1.py
```

Tests:
- ✓ Capacity alert detection (50%, 85%, 95%)
- ✓ Write anomaly baseline tracking
- ✓ Pydantic model validation
- ✓ Full anomaly detection pipeline

### Option B: Manual Endpoint Testing

#### 1. POST /api/metrics (Send metrics)

```bash
curl -X POST http://localhost:8000/api/metrics \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-09-12T17:30:15Z",
    "hostname": "MacBook-Pro",
    "filesystem": "/",
    "filesystem_type": "APFS",
    "total_bytes": 1000000000000,
    "used_bytes": 600000000000,
    "free_bytes": 400000000000,
    "used_percent": 60.0,
    "read_bytes_per_sec": 150000000,
    "write_bytes_per_sec": 50000000
  }'
```

Response:
```json
{"status": "ok", "alerts": 0}
```

#### 2. GET /api/metrics/current (Latest metrics)

```bash
curl http://localhost:8000/api/metrics/current
```

Response:
```json
{
  "time": "2026-09-12T17:30:15+00:00",
  "hostname": "MacBook-Pro",
  "filesystem": "/",
  "filesystem_type": "APFS",
  "total_bytes": 1000000000000,
  "used_bytes": 600000000000,
  "free_bytes": 400000000000,
  "used_percent": 60.0,
  "read_bytes_per_sec": 150000000,
  "write_bytes_per_sec": 50000000
}
```

#### 3. GET /api/metrics/history (Last N records)

```bash
curl "http://localhost:8000/api/metrics/history?limit=10"
```

#### 4. GET /api/alerts (Recent alerts)

```bash
curl http://localhost:8000/api/alerts
```

#### 5. Trigger Capacity Alert (85%+)

```bash
curl -X POST http://localhost:8000/api/metrics \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-09-12T17:35:15Z",
    "hostname": "MacBook-Pro",
    "filesystem": "/",
    "filesystem_type": "APFS",
    "total_bytes": 1000000000000,
    "used_bytes": 850000000000,
    "free_bytes": 150000000000,
    "used_percent": 85.0,
    "read_bytes_per_sec": 150000000,
    "write_bytes_per_sec": 50000000
  }'
```

Response:
```json
{"status": "ok", "alerts": 1}
```

#### 6. Trigger Write Anomaly (4x+ baseline)

Send several normal writes, then one spike:

```bash
# Normal baseline (send 5+ times)
curl -X POST http://localhost:8000/api/metrics \
  -H "Content-Type: application/json" \
  -d '{...,"write_bytes_per_sec": 100000000}'

# Then spike (450MB/s when baseline is ~100MB/s)
curl -X POST http://localhost:8000/api/metrics \
  -H "Content-Type: application/json" \
  -d '{...,"write_bytes_per_sec": 450000000}'
```

---

## Success Criteria for Phase 1

✅ Backend starts without errors
✅ Health endpoint returns `{"status": "ok"}`
✅ POST /api/metrics accepts valid requests
✅ POST /api/metrics rejects invalid requests (validation)
✅ GET /api/metrics/current returns latest record
✅ GET /api/metrics/history returns N records sorted by time DESC
✅ Capacity alerts trigger at 80% (warning) and 90% (critical)
✅ Write anomaly detection triggers at 4x+ baseline
✅ GET /api/alerts returns unresolved alerts
✅ Database persists metrics (can query across restarts)

---

## Anomaly Detection Logic

### Capacity Alert
```
0-79%   → no alert
80-89%  → warning: "Storage at X% capacity"
90-100% → critical: "Storage at X% capacity"
```

### Write Anomaly
```
Baseline = average of last 20 write samples
Current write > baseline × 4 → warning: "Write activity X.Xx baseline"
```

---

## Files Modified in Phase 1

| File | Change |
|------|--------|
| `backend/main.py` | Implement POST/GET endpoints, call database + alerts |
| `backend/database.py` | Already complete from Phase 0 |
| `backend/alerts.py` | Already complete from Phase 0 |
| `backend/test_phase1.py` | Created: local test suite |
| `PHASE_1_GUIDE.md` | This file |

---

## Next: Phase 2 (Person A)

After Phase 1 is working:

1. Implement `/api/ai/explain` endpoint → call Backboard
2. Add request/response logging
3. Prepare for dashboard integration

Person B will start dashboard + Auth0 integration while Person A refines the backend.

---

## Troubleshooting

**Error: Cannot connect to Tiger Data**
- Verify TIGER_DATABASE_URL in .env
- Check Tiger instance is running and accessible
- Test connection: `psql $TIGER_DATABASE_URL`

**Error: Table already exists**
- This is safe; schema.sql uses `IF NOT EXISTS`
- Can safely re-run init_db()

**Error: ImportError for models/database**
- Ensure you're in the `/backend` directory when running tests
- Or add parent directory to PYTHONPATH: `export PYTHONPATH=/path/to/storagewatch:$PYTHONPATH`

---

## What Person B (Collector + Frontend) Does in Parallel

While Person A finishes Phase 1:

- Person B builds Python collector using the `Metrics` model
- Person B scaffolds React app with Auth0 login
- Both can integrate at Phase 2 when endpoints are stable

---

## Quick Test Checklist

- [ ] Backend starts without errors
- [ ] `curl http://localhost:8000/health` works
- [ ] `python backend/test_phase1.py` passes
- [ ] Manual curl tests work (POST metrics, GET current/history)
- [ ] Capacity alerts trigger correctly
- [ ] Write anomalies trigger correctly
- [ ] Data persists in Tiger after restart
