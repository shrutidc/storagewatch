# Phase 0: Schema Alignment

## Pydantic Metrics Model

**Location:** `backend/models.py` → `Metrics` class

**Used by:** Collector (agent) sends this → Backend receives this

```python
class Metrics(BaseModel):
    timestamp: str              # ISO 8601 format: "2026-09-12T17:30:15Z"
    hostname: str               # e.g., "Shrutis-MacBook-Pro"
    filesystem: str             # e.g., "/"
    filesystem_type: str        # e.g., "APFS"

    total_bytes: int            # Total filesystem size
    used_bytes: int             # Used space
    free_bytes: int             # Available space

    used_percent: float         # 0-100

    read_bytes_per_sec: int     # I/O throughput
    write_bytes_per_sec: int    # I/O throughput
```

---

## API Contract

### POST /api/metrics

**Request:** JSON body matching `Metrics` model above

**Example:**
```json
{
    "timestamp": "2026-09-12T17:30:15Z",
    "hostname": "Shrutis-MacBook-Pro",
    "filesystem": "/",
    "filesystem_type": "APFS",
    "total_bytes": 494384795648,
    "used_bytes": 301238293504,
    "free_bytes": 193146502144,
    "used_percent": 61.4,
    "read_bytes_per_sec": 1740800,
    "write_bytes_per_sec": 532480
}
```

**Response:** `{"status": "ok"}`

---

### GET /api/metrics/current

**Response:** Latest metrics record

```json
{
    "timestamp": "2026-09-12T17:30:15Z",
    "hostname": "Shrutis-MacBook-Pro",
    "filesystem": "/",
    "filesystem_type": "APFS",
    "total_bytes": 494384795648,
    "used_bytes": 301238293504,
    "free_bytes": 193146502144,
    "used_percent": 61.4,
    "read_bytes_per_sec": 1740800,
    "write_bytes_per_sec": 532480
}
```

---

### GET /api/metrics/history?limit=100

**Response:** Array of last N metrics records (default 100)

```json
[
    { /* metrics record 1 */ },
    { /* metrics record 2 */ },
    ...
]
```

---

### GET /api/alerts

**Response:** Array of recent alerts

```json
[
    {
        "id": 1,
        "created_at": "2026-09-12T17:35:00Z",
        "hostname": "Shrutis-MacBook-Pro",
        "alert_type": "HIGH_WRITE_ACTIVITY",
        "severity": "warning",
        "message": "Write throughput 7.1x baseline",
        "metric_value": 821000000,
        "resolved": false
    }
]
```

---

### POST /api/ai/explain

**Request:**
```json
{
    "alert_type": "HIGH_WRITE_ACTIVITY",
    "current_write": 820,
    "baseline_write": 105,
    "used_percent": 82,
    "read_throughput": 115
}
```

**Response:** AI explanation from Backboard

```json
{
    "explanation": "The APFS volume is experiencing a significant increase in write activity..."
}
```

---

## Database Schema

### filesystem_metrics (TimescaleDB Hypertable)

```sql
CREATE TABLE filesystem_metrics (
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

SELECT create_hypertable('filesystem_metrics', 'time', if_not_exists => TRUE);
```

**Indexes:**
- `(hostname, time DESC)` — fast queries by host
- `(time DESC)` — recent records fast

---

### alerts

```sql
CREATE TABLE alerts (
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

**Indexes:**
- `(hostname, created_at DESC)`
- `(resolved)`

---

## Environment Variables Required

```
TIGER_DATABASE_URL=postgresql://user:password@host:port/database
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_CLIENT_ID=your-client-id
AUTH0_CLIENT_SECRET=your-client-secret
BACKBOARD_API_KEY=your-backboard-api-key
BACKEND_URL=http://localhost:8000
```

---

## Files for Phase 0

✅ `backend/models.py` — Pydantic models (Metrics, MetricsResponse, Alert)
✅ `backend/schema.sql` — Database schema
✅ `backend/database.py` — Tiger Data connection and CRUD functions
✅ `backend/main.py` — FastAPI app with endpoints stubbed
✅ `.env.example` — Environment variable template (already exists)
✅ `PHASE_0_SCHEMA.md` — This document (for reference)

---

## Phase 1 Readiness

**Person A (Backend):**
- Implement endpoint logic in `main.py`
- Use `database.py` functions
- Implement alert detection in `alerts.py`

**Person B (Collector):**
- Use `Metrics` model from `backend/models.py`
- Collect psutil data
- POST to `http://localhost:8000/api/metrics`

---

## Success Criteria for Phase 0

✅ Pydantic model is defined and importable
✅ Database schema file exists and is ready to run
✅ API contract is documented
✅ Directory structure is clean
✅ .env template is ready for credentials
