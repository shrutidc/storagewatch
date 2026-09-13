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

-- Per-machine preferences, set in the dashboard and applied on the Mac.
--
-- A browser cannot reach the monitored Mac, so a choice made here is stored
-- and the collector on that machine picks it up with its next report.
-- `menu_bar_applied` is what that collector last confirmed is actually true,
-- which is how the dashboard can say "applying" instead of claiming a change
-- it has not seen take effect. A machine with no row takes the defaults.
CREATE TABLE IF NOT EXISTS host_preferences (
    owner_sub TEXT NOT NULL,
    hostname TEXT NOT NULL,
    menu_bar_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    menu_bar_applied BOOLEAN,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (owner_sub, hostname)
);

-- Who is using the disk, over time.
--
-- Sizing a home directory means walking it, so the agent measures on its own
-- slow schedule (half-hourly by default) rather than per sample. That makes
-- this low-volume enough for an ordinary table — a hypertable's chunking buys
-- nothing at a few rows per user per hour — but it is a history, not a
-- snapshot: growth between samples is what identifies a user filling a volume,
-- and a single current figure could not show it.
CREATE TABLE IF NOT EXISTS user_usage (
    time TIMESTAMPTZ NOT NULL,
    owner_sub TEXT NOT NULL,
    hostname TEXT NOT NULL,
    username TEXT NOT NULL,
    uid INTEGER,
    home TEXT,
    used_bytes BIGINT,
    quota_enabled BOOLEAN DEFAULT FALSE,
    quota_soft_bytes BIGINT,
    quota_hard_bytes BIGINT,
    file_count BIGINT,
    -- The largest folders inside the home directory, which comes free from
    -- the same walk and answers "where did the space go?" without a second one.
    largest_folders JSONB
);

CREATE INDEX IF NOT EXISTS idx_user_usage_owner_host_time
    ON user_usage (owner_sub, hostname, username, time DESC);

-- False when the collector couldn't read every folder — another user's home, or
-- privacy-protected folders without Full Disk Access — so the size is a floor.
ALTER TABLE user_usage ADD COLUMN IF NOT EXISTS complete BOOLEAN DEFAULT TRUE;

-- Consent to the privacy page, per account.
--
-- Kept server-side rather than in the browser: this is a record of what a
-- person agreed to and when, and a localStorage flag would be a per-browser
-- guess that vanishes on a new machine. `version` is the policy revision they
-- accepted, so changing the page can require agreement again rather than
-- silently carrying the old consent forward.
CREATE TABLE IF NOT EXISTS policy_acceptance (
    owner_sub TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    accepted_at TIMESTAMPTZ DEFAULT NOW()
);
