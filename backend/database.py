"""Data access.

Every query is scoped to an owner — the Auth0 subject of the administrator
whose agent produced the data. `owner_sub` is the first positional argument on
every read and write rather than an optional filter, so an unscoped query that
would leak one user's machines to another can't be written by accident.
"""

import hashlib
import json
import os
import secrets
import threading
from contextlib import contextmanager

from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

# Opening a connection to Tiger Data costs 300-400 ms (TCP, TLS, auth) against
# ~50 ms for the query itself, and every request used to open a fresh one.
# Connections are now opened once and reused. min == max because psycopg2's
# pool closes any returned connection beyond `minconn` instead of keeping it.
# ponytail: fixed size; raise POOL_SIZE if requests start queueing.
POOL_SIZE = 6
_pool = None
_pool_lock = threading.Lock()
# The pool raises rather than waits when it is empty, so a burst queues here.
_slots = threading.BoundedSemaphore(POOL_SIZE)

def _get_pool():
    # Created lazily: TIGER_DATABASE_URL is only set once load_dotenv() has run.
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadedConnectionPool(
                POOL_SIZE, POOL_SIZE, os.getenv("TIGER_DATABASE_URL"),
                # Stop idle connections being silently dropped in transit.
                keepalives=1, keepalives_idle=30,
            )
    return _pool

@contextmanager
def connection():
    """A pooled connection in autocommit mode. Every call here runs a single
    statement, so a transaction would only add BEGIN and COMMIT round trips —
    measured at ~150 ms per query instead of ~50."""
    with _slots:
        pool = _get_pool()
        conn = pool.getconn()
        conn.autocommit = True
        try:
            yield conn
        finally:
            # A connection the server dropped is discarded, not handed out again.
            pool.putconn(conn, close=bool(conn.closed))

def _all(sql, params=None):
    """Every row, as dicts."""
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()

def _one(sql, params=None):
    """The first row as a dict, or None."""
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchone()

def _execute(sql, params=None):
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)

def init_db():
    """Initialize database schema. Run once on startup."""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r") as f:
        _execute(f.read())

# Every table a request path reads from. The dashboard joins against all of
# them, so one missing table is a broken dashboard rather than a missing panel.
REQUIRED_TABLES = ("filesystem_metrics", "alerts", "agent_tokens", "system_info",
                   "host_preferences", "user_usage")

def missing_tables():
    """Which required tables do not exist. Empty when the schema is complete."""
    rows = _all("""
        SELECT name FROM unnest(%s::text[]) AS name
        WHERE to_regclass('public.' || name) IS NULL
    """, (list(REQUIRED_TABLES),))
    return [r["name"] for r in rows]


# --- agent credentials -----------------------------------------------------

def _hash_token(token):
    """Agent tokens are 256 bits of randomness, so a fast digest is enough —
    there is no low-entropy password here for an attacker to grind against."""
    return hashlib.sha256(token.encode()).hexdigest()

def create_agent_token(owner_sub, label=None):
    """Mint an agent token for a user. Returns the plaintext, which is the only
    time it exists outside the agent's config — only the hash is stored."""
    token = secrets.token_urlsafe(32)
    _execute("""
        INSERT INTO agent_tokens (token_hash, owner_sub, label)
        VALUES (%s, %s, %s)
    """, (_hash_token(token), owner_sub, label))
    return token

def resolve_agent_token(token):
    """Return the owner of an agent token, or None if it isn't a valid one."""
    row = _one("""
        UPDATE agent_tokens SET last_used_at = NOW()
        WHERE token_hash = %s
        RETURNING owner_sub
    """, (_hash_token(token),))
    return row["owner_sub"] if row else None

def list_agent_tokens(owner_sub):
    """Metadata for a user's tokens. Never returns the tokens themselves."""
    return _all("""
        SELECT label, created_at, last_used_at FROM agent_tokens
        WHERE owner_sub = %s ORDER BY created_at DESC
    """, (owner_sub,))


# --- machines --------------------------------------------------------------

def get_hosts(owner_sub):
    """The machines this user has reporting, most recently seen first."""
    return _all("""
        SELECT hostname, MAX(time) AS last_seen
        FROM filesystem_metrics
        WHERE owner_sub = %s
        GROUP BY hostname
        ORDER BY last_seen DESC
    """, (owner_sub,))


# --- metrics ---------------------------------------------------------------

def insert_metrics(owner_sub, metrics):
    """Insert filesystem metrics into database."""
    _execute("""
        INSERT INTO filesystem_metrics (
            owner_sub, time, hostname, filesystem, filesystem_type,
            total_bytes, used_bytes, free_bytes, used_percent,
            read_bytes_per_sec, write_bytes_per_sec
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        owner_sub,
        metrics.timestamp,
        metrics.hostname,
        metrics.filesystem,
        metrics.filesystem_type,
        metrics.total_bytes,
        metrics.used_bytes,
        metrics.free_bytes,
        metrics.used_percent,
        metrics.read_bytes_per_sec,
        metrics.write_bytes_per_sec
    ))

def get_latest_metrics(owner_sub, filesystem="/", hostname=None):
    """Most recent sample for one volume on one of the user's machines."""
    return _one("""
        SELECT * FROM filesystem_metrics
        WHERE owner_sub = %s AND filesystem = %s
          AND (%s::text IS NULL OR hostname = %s)
        ORDER BY time DESC LIMIT 1
    """, (owner_sub, filesystem, hostname, hostname))

def get_metrics_history(owner_sub, limit=100, filesystem="/", hostname=None):
    """Historical samples for one volume on one of the user's machines."""
    return _all("""
        SELECT * FROM filesystem_metrics
        WHERE owner_sub = %s AND filesystem = %s
          AND (%s::text IS NULL OR hostname = %s)
        ORDER BY time DESC LIMIT %s
    """, (owner_sub, filesystem, hostname, hostname, limit))

def get_all_volumes_latest(owner_sub, hostname=None):
    """Latest sample per volume, for one of the user's machines."""
    return _all("""
        SELECT DISTINCT ON (filesystem) *
        FROM filesystem_metrics
        WHERE owner_sub = %s
          AND (%s::text IS NULL OR hostname = %s)
          -- Bounds the scan to recent hypertable chunks instead of the whole
          -- history; a volume silent for an hour is no longer mounted anyway.
          AND time > NOW() - INTERVAL '1 hour'
        ORDER BY filesystem, time DESC
    """, (owner_sub, hostname, hostname))


# --- alerts ----------------------------------------------------------------

def insert_alert(owner_sub, hostname, alert_type, severity, message,
                 metric_value, ai_explanation=None):
    """Insert an alert record. Returns the new alert's id."""
    return _one("""
        INSERT INTO alerts (owner_sub, hostname, alert_type, severity, message,
                            metric_value, ai_explanation)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (owner_sub, hostname, alert_type, severity, message, metric_value,
          ai_explanation))["id"]

def has_recent_alert(owner_sub, hostname, alert_type, severity):
    """Whether this machine raised this alert in the last 10 minutes.

    A condition persists across samples — a disk at 85% is at 85% every five
    seconds — so without this each sample would add a row and an LLM call.
    Severity is part of the key so warning -> critical still fires.
    """
    return _one("""
        SELECT 1 FROM alerts
        WHERE owner_sub = %s AND hostname = %s
          AND alert_type = %s AND severity = %s
          AND created_at > NOW() - INTERVAL '10 minutes'
        LIMIT 1
    """, (owner_sub, hostname, alert_type, severity)) is not None

def get_recent_alerts(owner_sub, limit=10, hostname=None):
    """Unresolved alerts for the user's machines, newest first. limit=None
    returns all of them (LIMIT NULL is no limit in Postgres)."""
    return _all("""
        SELECT * FROM alerts
        WHERE owner_sub = %s AND resolved = FALSE
          AND (%s::text IS NULL OR hostname = %s)
        ORDER BY created_at DESC LIMIT %s
    """, (owner_sub, hostname, hostname, limit))


# --- disk / APFS inventory -------------------------------------------------

def save_system_info(owner_sub, hostname, data):
    """Upsert one machine's disk/APFS snapshot."""
    _execute("""
        INSERT INTO system_info (owner_sub, hostname, updated_at, data)
        VALUES (%s, %s, NOW(), %s)
        ON CONFLICT (owner_sub, hostname)
        DO UPDATE SET updated_at = NOW(), data = EXCLUDED.data
    """, (owner_sub, hostname, json.dumps(data)))

def get_system_info(owner_sub, hostname=None):
    """One machine's disk/APFS snapshot, or None if it hasn't reported."""
    row = _one("""
        SELECT data FROM system_info
        WHERE owner_sub = %s AND (%s::text IS NULL OR hostname = %s)
        ORDER BY updated_at DESC LIMIT 1
    """, (owner_sub, hostname, hostname))
    return row["data"] if row else None


# --- per-machine preferences -----------------------------------------------

def set_menu_bar_enabled(owner_sub, hostname, enabled):
    """Record whether this machine should show the menu bar app.

    Only a wish: the Mac is not reachable from here, so the collector on it
    applies this with its next report. `menu_bar_applied` is deliberately left
    alone so the dashboard keeps showing the change as pending until that
    collector confirms it.
    """
    _execute("""
        INSERT INTO host_preferences (owner_sub, hostname, menu_bar_enabled)
        VALUES (%s, %s, %s)
        ON CONFLICT (owner_sub, hostname)
        DO UPDATE SET menu_bar_enabled = EXCLUDED.menu_bar_enabled, updated_at = NOW()
    """, (owner_sub, hostname, enabled))

def set_menu_bar_applied(owner_sub, hostname, installed):
    """Record what the collector reports is actually on the machine.

    Sent only when it changes, so this runs about once per collector start or
    per toggle rather than on every five-second report.
    """
    _execute("""
        INSERT INTO host_preferences (owner_sub, hostname, menu_bar_applied)
        VALUES (%s, %s, %s)
        ON CONFLICT (owner_sub, hostname)
        DO UPDATE SET menu_bar_applied = EXCLUDED.menu_bar_applied
    """, (owner_sub, hostname, installed))


# --- agent -----------------------------------------------------------------

def get_agent_state(owner_sub, hostname):
    """Everything the collector needs back from a report, as one JSON document.

    The alerts it shows on the Mac and the preferences it has to apply there
    arrive together: a second query here would be a second round trip on every
    five-second report from every machine.
    """
    return _one("""
        SELECT json_build_object(
          'active_alerts', (SELECT coalesce(json_agg(a ORDER BY a.created_at DESC), '[]'::json) FROM (
              SELECT id, alert_type, severity, message, created_at FROM alerts
              WHERE owner_sub = %(owner)s AND resolved = FALSE AND hostname = %(host)s
              ORDER BY created_at DESC LIMIT 5) a),
          -- A machine nobody has configured keeps the menu bar app, which is
          -- what every collector did before the setting existed.
          'menu_bar', coalesce((SELECT menu_bar_enabled FROM host_preferences
              WHERE owner_sub = %(owner)s AND hostname = %(host)s), TRUE)
        )::text AS doc
    """, {"owner": owner_sub, "host": hostname})["doc"]


# --- who is using the disk --------------------------------------------------

def insert_user_usage(owner_sub, hostname, users, measured_at):
    """Record one sizing pass. Users with no measurement yet are skipped, so a
    freshly started collector doesn't write a history of zeroes that later
    reads as a user who deleted everything."""
    rows = []
    for u in users:
        if not u.get("used_bytes"):
            continue
        quota = u.get("quota") or {}
        # A user can hold quotas on several filesystems; the tightest one is
        # what will actually stop them writing.
        limits = quota.get("filesystems") or []
        soft = min((f["soft_limit_bytes"] for f in limits if f["soft_limit_bytes"]), default=0)
        hard = min((f["hard_limit_bytes"] for f in limits if f["hard_limit_bytes"]), default=0)
        rows.append((measured_at, owner_sub, hostname, u["username"], u.get("uid"),
                     u.get("home"), u["used_bytes"], bool(quota.get("enabled")),
                     soft, hard, sum(f.get("file_count", 0) for f in limits),
                     json.dumps(u.get("largest_folders") or [])))
    if not rows:
        return 0
    with connection() as conn, conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO user_usage (time, owner_sub, hostname, username, uid, home,
                                    used_bytes, quota_enabled, quota_soft_bytes,
                                    quota_hard_bytes, file_count, largest_folders)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, rows)
    return len(rows)

def get_user_usage_latest(owner_sub, hostname=None):
    """Each user's most recent measurement, with how much they have added since
    the one before it — the growth that identifies a user filling a volume."""
    return _all("""
        SELECT DISTINCT ON (username)
               username, uid, home, used_bytes, quota_enabled, quota_soft_bytes,
               quota_hard_bytes, file_count, largest_folders, time,
               used_bytes - lag(used_bytes) OVER (PARTITION BY username ORDER BY time)
                   AS growth_bytes,
               lag(time) OVER (PARTITION BY username ORDER BY time) AS previous_time
        FROM user_usage
        WHERE owner_sub = %s AND (%s::text IS NULL OR hostname = %s)
        ORDER BY username, time DESC
    """, (owner_sub, hostname, hostname))

def get_user_usage_history(owner_sub, username, hostname=None, limit=100):
    """One user's measurements over time, oldest first."""
    return _all("""
        SELECT * FROM (
            SELECT time, used_bytes FROM user_usage
            WHERE owner_sub = %s AND username = %s
              AND (%s::text IS NULL OR hostname = %s)
            ORDER BY time DESC LIMIT %s
        ) recent ORDER BY time
    """, (owner_sub, username, hostname, hostname, limit))


# --- dashboard -------------------------------------------------------------

def get_dashboard(owner_sub, hostname=None):
    """Everything the dashboard shows, as one JSON document built by Postgres.

    One statement is one round trip, and Python only forwards the text: on the
    free instance's tenth of a CPU, per-request and serialization overhead —
    not the queries — were what made the dashboard slow.
    """
    return _one("""
        SELECT json_build_object(
          'current', (SELECT row_to_json(c) FROM (
              SELECT * FROM filesystem_metrics
              WHERE owner_sub = %(owner)s AND filesystem = '/'
                AND (%(host)s::text IS NULL OR hostname = %(host)s)
              ORDER BY time DESC LIMIT 1) c),
          'history', (SELECT coalesce(json_agg(h ORDER BY h.time), '[]'::json) FROM (
              SELECT time, read_bytes_per_sec, write_bytes_per_sec FROM filesystem_metrics
              WHERE owner_sub = %(owner)s AND filesystem = '/'
                AND (%(host)s::text IS NULL OR hostname = %(host)s)
              ORDER BY time DESC LIMIT 100) h),
          'alerts', (SELECT coalesce(json_agg(a ORDER BY a.created_at DESC), '[]'::json) FROM (
              SELECT * FROM alerts
              WHERE owner_sub = %(owner)s AND resolved = FALSE
                AND (%(host)s::text IS NULL OR hostname = %(host)s)) a),
          'volumes', (SELECT coalesce(json_agg(v), '[]'::json) FROM (
              SELECT DISTINCT ON (filesystem) * FROM filesystem_metrics
              WHERE owner_sub = %(owner)s
                AND (%(host)s::text IS NULL OR hostname = %(host)s)
                AND time > NOW() - INTERVAL '1 hour'
              ORDER BY filesystem, time DESC) v),
          'system_info', (SELECT data FROM system_info
              WHERE owner_sub = %(owner)s
                AND (%(host)s::text IS NULL OR hostname = %(host)s)
              ORDER BY updated_at DESC LIMIT 1),
          -- Keyed on the machine actually being shown, which is not the
          -- requested host when the dashboard is following whichever machine
          -- reported most recently. Null when none has reported at all.
          -- Ordered by consumption: the question this answers is who is
          -- filling the disk, so the biggest account is the first row.
          'users', (SELECT coalesce(json_agg(u ORDER BY u.used_bytes DESC), '[]'::json) FROM (
              SELECT DISTINCT ON (username)
                     username, uid, home, used_bytes, quota_enabled,
                     quota_soft_bytes, quota_hard_bytes, file_count,
                     largest_folders, time,
                     used_bytes - lag(used_bytes) OVER w AS growth_bytes,
                     lag(time) OVER w AS previous_time
              FROM user_usage
              WHERE owner_sub = %(owner)s
                AND (%(host)s::text IS NULL OR hostname = %(host)s)
              WINDOW w AS (PARTITION BY username ORDER BY time)
              ORDER BY username, time DESC) u),
          'preferences', (SELECT json_build_object(
                'hostname', h.hostname,
                'menu_bar_enabled', coalesce(p.menu_bar_enabled, TRUE),
                'menu_bar_applied', p.menu_bar_applied)
              FROM (SELECT hostname FROM filesystem_metrics
                    WHERE owner_sub = %(owner)s AND filesystem = '/'
                      AND (%(host)s::text IS NULL OR hostname = %(host)s)
                    ORDER BY time DESC LIMIT 1) h
              LEFT JOIN host_preferences p
                ON p.owner_sub = %(owner)s AND p.hostname = h.hostname)
        )::text AS doc
    """, {"owner": owner_sub, "host": hostname})["doc"]
