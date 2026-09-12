-- StorageWatch Database Schema
-- For Tiger Data (PostgreSQL/TimescaleDB)

-- Create filesystem_metrics hypertable
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

-- Convert to hypertable for TimescaleDB (idempotent)
SELECT create_hypertable('filesystem_metrics', 'time', if_not_exists => TRUE);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_filesystem_metrics_hostname_time
    ON filesystem_metrics (hostname, time DESC);

CREATE INDEX IF NOT EXISTS idx_filesystem_metrics_time
    ON filesystem_metrics (time DESC);

-- Alerts table
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

ALTER TABLE alerts ADD COLUMN IF NOT EXISTS ai_explanation TEXT;

-- Latest disk/APFS status snapshot from the collector. A point-in-time status
-- rather than a metric history, so it's a single upserted row instead of a
-- hypertable — but it lives in the DB so it survives a backend restart.
CREATE TABLE IF NOT EXISTS system_info (
    id INTEGER PRIMARY KEY,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    data JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alerts_hostname_created
    ON alerts (hostname, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_resolved
    ON alerts (resolved);
