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

CREATE INDEX IF NOT EXISTS idx_alerts_hostname_created
    ON alerts (hostname, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_resolved
    ON alerts (resolved);

-- Telemetry ownership.
--
-- An administrator must only ever see their own machines. Every ingested row
-- carries the Auth0 subject of the person whose agent sent it, and every read
-- is filtered to the signed-in user. Rows predating this column have a NULL
-- owner and are therefore visible to nobody, which is the safe direction.
ALTER TABLE filesystem_metrics ADD COLUMN IF NOT EXISTS owner_sub TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS owner_sub TEXT;

CREATE INDEX IF NOT EXISTS idx_filesystem_metrics_owner_time
    ON filesystem_metrics (owner_sub, hostname, time DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_owner_created
    ON alerts (owner_sub, created_at DESC);

-- Agent credentials, one or more per user. Only the hash is stored: a leaked
-- database should not yield working agent tokens, and the plaintext is shown
-- to the user exactly once when minted.
CREATE TABLE IF NOT EXISTS agent_tokens (
    token_hash TEXT PRIMARY KEY,
    owner_sub TEXT NOT NULL,
    label TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_agent_tokens_owner ON agent_tokens (owner_sub);

-- The first version of this table was a single global row keyed on id=1, so
-- whichever collector reported last overwrote everyone else's hardware. Its
-- contents are a cache the agents rebuild within a minute, so replacing it
-- outright is safe; the guard means this only fires on the old shape.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'system_info' AND column_name = 'id'
    ) THEN
        DROP TABLE system_info;
    END IF;
END $$;

-- Latest disk/APFS snapshot per machine. A point-in-time status rather than a
-- metric history, so it's upserted rather than appended — but keyed by owner
-- and host.
CREATE TABLE IF NOT EXISTS system_info (
    owner_sub TEXT NOT NULL,
    hostname TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    data JSONB NOT NULL,
    PRIMARY KEY (owner_sub, hostname)
);
