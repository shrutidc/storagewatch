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
              ORDER BY updated_at DESC LIMIT 1)
        )::text AS doc
    """, {"owner": owner_sub, "host": hostname})["doc"]
